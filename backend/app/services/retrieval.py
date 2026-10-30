import json
import logging
import re
from collections import defaultdict
from fastapi import HTTPException
from app.core.config import settings
from app.core.database import connection
from app.models.contracts import Chunk
from app.services import embeddings, vector_store, versioning

log=logging.getLogger(__name__)
STOP={'the','is','a','an','what','how','when','where','which','and','or','of','to','for','in','on','are','does','do','current','policy','please'}
STOP.update({'many','much','was','were','allowed','allowance','company','companies','employee','employees','our','can','i','my','s','compare','between','provide','provided','per','year','latest','today','policies'})
def tokens(text):
    words=[w for w in re.findall(r'\w+',text.lower()) if w not in STOP and not re.fullmatch(r'20\d{2}',w)]
    return [w[:-1] if len(w)>3 and w.endswith('s') and not w.endswith(('ss','us','is')) else w for w in words]

def is_control_block(text):
    # Document-control fields describe a source, not an employee entitlement.
    return len(re.findall(r'(?im)^\s*(?:policy id|policy family|version|effective date|(?:document )?status)\s*:',text))>=3

def keyword_rank(question, chunks, count):
    from rank_bm25 import BM25Plus
    corpus=[tokens((c.section or '')+' '+c.text) or [''] for c in chunks]
    query=tokens(question)
    scores=BM25Plus(corpus).get_scores(query)
    ranked=sorted(zip(chunks,scores),key=lambda item:item[1],reverse=True)
    return [(c.chunk_id,float(score)) for c,score in ranked if set(query)&set(tokens((c.section or '')+' '+c.text))][:count]

def retrieve(query, company_id=None):
    with connection() as db:
        documents=[dict(r) for r in db.execute("SELECT * FROM documents WHERE processing_status='ready' AND company_id IS ?",(company_id,))]
        ids,warnings=versioning.resolve(documents,query)
        incompatible={d['id'] for d in documents if d['id'] in ids and d['embedding_key']!=embeddings.embedding_key()}
        if incompatible:
            raise HTTPException(503,'Embedding configuration changed; re-ingest documents to rebuild vectors')
        if not ids:
            return [],warnings
        marks=','.join('?' for _ in ids)
        rows=db.execute(f'SELECT p.*,d.filename,d.policy_family,d.version,d.status FROM passages p JOIN documents d ON d.id=p.document_id WHERE p.document_id IN ({marks})',ids).fetchall()
    chunks=[Chunk(chunk_id=r['id'],document_id=r['document_id'],document_name=r['filename'],policy_family=r['policy_family'],version=r['version'],version_status=r['status'],section=r['section'],page=r['page'],text=r['text'],is_table=json.loads(r['metadata']).get('is_table',False)) for r in rows if not is_control_block(r['text'])]
    if not chunks:
        return [],warnings
    for chunk in chunks: chunk.company_id=company_id
    count=max(query.top_k*4,24)
    try:
        # Search the full question and its topic terms: dates belong to version
        # resolution, and question boilerplate should not crowd out the topic.
        variants=list(dict.fromkeys([query.question,' '.join(tokens(query.question))]))
        variants=[v for v in variants if v]
        matches={}
        for vector in embeddings.encode(variants):
            results=vector_store.search(vector,ids,count,company_id) if company_id is not None else vector_store.search(vector,ids,count)
            for cid,score in results: matches[cid]=max(score,matches.get(cid,-1))
        semantic=sorted(matches.items(),key=lambda item:(-item[1],item[0]))
    except Exception as exc:
        raise HTTPException(503,'Semantic retrieval unavailable; check embedding model and Chroma storage') from exc
    semantic=[(cid,score) for cid,score in semantic if score>=settings.semantic_min_score]
    rankings=[semantic]
    if query.mode=='hybrid':
        try:
            rankings.append(keyword_rank(query.question,chunks,count))
        except Exception:
            log.warning('BM25 unavailable; using semantic retrieval',exc_info=True)
            warnings.append('Keyword retrieval unavailable; semantic fallback used')
    scores=defaultdict(float)
    for ranking in rankings:
        for rank,(cid,_) in enumerate(ranking,1):
            scores[cid]+=1/(60+rank)
    by_id={c.chunk_id:c for c in chunks}
    topic=set(tokens(query.question))
    overlap={c.chunk_id:len(topic & set(tokens((c.section or '')+' '+c.text))) for c in chunks}
    best_overlap=max(overlap.values(),default=0)
    semantic_scores=dict(semantic)
    best_semantic=max((score for cid,score in semantic if cid in by_id),default=0)
    # Ignore single generic keyword hits when a passage matches the actual topic.
    # Strong semantic-only matches remain available for genuine paraphrases.
    required=min(2,len(topic))
    if best_overlap>=required and required:
        scores={cid:score for cid,score in scores.items() if overlap.get(cid,0)>=required or semantic_scores.get(cid,0)>=max(.45,best_semantic*.85)}
    selected=[];seen=set();used=0
    ordered=sorted(scores,key=lambda k:(-scores[k],k))
    if len(set(re.findall(r'\b20\d{2}\b',query.question)))>1:
        # Reserve a relevant passage for each resolved version before filling.
        first={}
        for cid in ordered:
            if cid in by_id: first.setdefault(by_id[cid].version,cid)
        ordered=list(first.values())+[cid for cid in ordered if cid not in first.values()]
    for cid in ordered:
        c=by_id.get(cid)
        if not c or (c.document_id,c.text) in seen:
            continue
        if used+len(c.text)>settings.context_max_chars:
            continue
        c.score=scores[cid];selected.append(c);seen.add((c.document_id,c.text));used+=len(c.text)
        if len(selected)>=query.top_k:
            break
    log.info('Retrieval company=%s passages=%s diagnostics=%s',company_id,[c.chunk_id for c in selected],warnings)
    return selected,warnings
