import json
import math
import os
from datetime import date
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.main import app
from app.api.auth import current_user
from app.core.config import settings
from app.core.database import connection, initialize
from app.models.contracts import UploadMetadata, Question, Draft, Claim, Verification
from app.services import ingestion, parsing, chunking, embeddings, vector_store, retrieval, answering, llm

# Deterministic unit-test vectors only. The integration test uses real MiniLM.
def fake_encode(texts):
    vocabulary=['medical','leave','12','10','travel','meal','remote','equipment']
    values=[]
    for text in texts:
        vec=[float(word in text.lower()) for word in vocabulary]+[0.01]
        norm=math.sqrt(sum(x*x for x in vec))
        values.append([x/norm for x in vec])
    return values

@pytest.fixture
def store(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'database_path',str(tmp_path/'metadata.sqlite3'))
    monkeypatch.setattr(settings,'data_dir',str(tmp_path/'data'))
    monkeypatch.setattr(embeddings,'encode',fake_encode)
    initialize()
    return tmp_path

@pytest.fixture
def api(store):
    app.dependency_overrides[current_user]=lambda:{'email':'test@example.com','role':'admin','company_id':'infosys'}
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()

def add(text='Employees receive 12 days of medical leave per year.',version='2026',status='current',family='leave',ext='md'):
    return ingestion.ingest('leave.'+ext,text.encode(),UploadMetadata(policy_family=family,version=version,status=status,effective_date=date(int(version),1,1)))[0]

@pytest.fixture
def policies(store):
    old=add('Employees receive 10 days of medical leave per year.','2024','superseded')
    new=add()
    return old,new

def test_pdf_pages_and_tables():
    import pymupdf
    doc=pymupdf.open()
    page=doc.new_page()
    page.insert_text((50,40),'MEDICAL LEAVE',fontsize=18)
    for y in [70,100,130]:
        page.draw_line((50,y),(350,y))
    for x in [50,220,350]:
        page.draw_line((x,70),(x,130))
    page.insert_text((60,90),'Allowance')
    page.insert_text((230,90),'Days')
    page.insert_text((60,120),'Medical leave')
    page.insert_text((230,120),'12')
    page=doc.new_page();page.insert_text((50,80),'Requests require manager approval.')
    blocks,warnings=parsing.parse(doc.tobytes(),'pdf');doc.close()
    assert {b.page for b in blocks}=={1,2}
    table=next(b for b in blocks if b.is_table)
    assert 'Allowance' in table.text and 'Medical leave' in table.text and '12' in table.text
    assert table.section=='MEDICAL LEAVE'

@pytest.mark.parametrize('ext,text,section',[('txt','MEDICAL LEAVE\nEmployees receive 12 days.', 'MEDICAL LEAVE'),('md','# Medical leave\nEmployees receive 12 days.', 'Medical leave')])
def test_text_ingestion(store,ext,text,section):
    doc=add(text,ext=ext)
    assert doc.processing_status=='ready'
    with connection() as db:
        row=db.execute('SELECT * FROM passages WHERE document_id=?',(doc.id,)).fetchone()
    assert row['page'] is None and row['section']==section
    assert vector_store.collection().count()>0

def test_table_chunk_headers(monkeypatch):
    monkeypatch.setattr(settings,'chunk_tokens',40)
    monkeypatch.setattr(settings,'chunk_overlap',5)
    text='| Benefit | Days |\n| --- | --- |\n'+'\n'.join(f'| Leave type {i} | {i} |' for i in range(15))
    blocks,_=parsing.parse(text.encode(),'md')
    chunks=chunking.chunk(blocks,{'id':'d','filename':'table.md','policy_family':None,'version':None,'status':'current'})
    assert len(chunks)>1
    assert all(c.text.startswith('| Benefit | Days |') and c.is_table for c in chunks)
    assert all(len(chunking.TOKEN.findall(c.text))<=40 for c in chunks)

def test_duplicate_and_conflicting_metadata(store,monkeypatch):
    doc=add()
    monkeypatch.setattr(embeddings,'encode',lambda _:pytest.fail('Duplicate recomputed embeddings'))
    duplicate,flag=ingestion.ingest('renamed.md',b'Employees receive 12 days of medical leave per year.',UploadMetadata(policy_family='leave',version='2026',status='current',effective_date=date(2026,1,1)))
    assert flag and duplicate.id==doc.id
    with pytest.raises(HTTPException) as error:
        add(version='2024')
    assert error.value.status_code==409

def test_current_and_historical(policies):
    old,new=policies
    current,_=retrieval.retrieve(Question(question='What is the current medical leave allowance?'))
    historical,_=retrieval.retrieve(Question(question='What was medical leave in 2024?'))
    assert current and {c.document_id for c in current}=={new.id}
    assert historical and {c.document_id for c in historical}=={old.id}
    explicit,_=retrieval.retrieve(Question(question='Medical leave?',version='2024'))
    assert {c.document_id for c in explicit}=={old.id}

def test_ambiguity_and_future_date(policies):
    add('Medical leave allowance is 14 days.','2025','current')
    chunks,warnings=retrieval.retrieve(Question(question='Current medical leave?'))
    assert not chunks and any('Ambiguous' in w for w in warnings)
    with connection() as db:
        db.execute("UPDATE documents SET effective_date='2099-01-01' WHERE version='2025'")
    chunks,_=retrieval.retrieve(Question(question='Current medical leave?'))
    assert chunks and all(c.version=='2026' for c in chunks)

def test_hybrid_and_semantic_fallback(policies,monkeypatch):
    hybrid,_=retrieval.retrieve(Question(question='medical leave',mode='hybrid'))
    semantic,_=retrieval.retrieve(Question(question='medical leave',mode='semantic'))
    assert hybrid and semantic
    def unavailable(*args):raise ImportError('BM25 unavailable')
    monkeypatch.setattr(retrieval,'keyword_rank',unavailable)
    fallback,warnings=retrieval.retrieve(Question(question='medical leave'))
    assert [c.chunk_id for c in fallback]==[c.chunk_id for c in semantic]
    assert warnings

def mock_answer(monkeypatch,partial=False,invalid=False,unsupported=False):
    def generate(schema,instruction,payload):
        c=payload['evidence'][0]
        if schema is Draft:
            return Draft(claims=[Claim(text='Employees receive 12 days of medical leave per year.',chunk_id='invented' if invalid else c['chunk_id'],quote='Employees receive 12 days of medical leave per year.')])
        return Verification(supported_claims=[] if unsupported else [0],supported_parts=['Medical leave allowance'] if not unsupported else [],unsupported_parts=['Travel allowance'] if partial else [],all_parts_covered=not partial)
    monkeypatch.setattr(llm,'generate',generate)

@pytest.mark.parametrize('partial,status',[(False,'answered'),(True,'partially_answered')])
def test_answer_classification(policies,monkeypatch,partial,status):
    mock_answer(monkeypatch,partial)
    result=answering.ask(Question(question='What is the medical leave allowance and travel allowance?' if partial else 'What is the current medical leave allowance?'))
    assert result.status==status
    assert result.citations[0].version=='2026'
    assert result.citations[0].page is None
    assert result.citations[0].document=='leave.md'
    assert bool(result.unsupported_parts)==partial

def test_invalid_citation(policies,monkeypatch):
    mock_answer(monkeypatch,invalid=True)
    result=answering.ask(Question(question='medical leave'))
    assert result.status=='not_covered' and result.citations==[]

def test_unsupported_claim(policies,monkeypatch):
    mock_answer(monkeypatch,unsupported=True)
    assert answering.ask(Question(question='medical leave')).status=='not_covered'

def test_empty_no_llm(store,monkeypatch):
    monkeypatch.setattr(llm,'generate',lambda *args:pytest.fail('LLM called without evidence'))
    assert answering.ask(Question(question='What is the lunar travel allowance?')).status=='not_covered'

def test_llm_unavailable(policies,monkeypatch):
    monkeypatch.setattr(settings,'gemini_api_key','')
    with pytest.raises(HTTPException) as error:
        answering.ask(Question(question='medical leave'))
    assert error.value.status_code==503

def test_upload_api_and_limits(api,monkeypatch):
    meta={'policy_family':'leave','version':'2026','status':'current','effective_date':'2026-01-01'}
    response=api.post('/api/documents/upload',files=[('files',('../policy.md',b'# Leave\nMedical leave is 12 days.','text/markdown')),('files',('notes.txt',b'Approval is required.','text/plain'))],data={'metadata':json.dumps([meta,{**meta,'policy_family':'approvals'}])})
    assert response.status_code==201
    docs=response.json()['results']
    assert docs[0]['document']['filename']=='policy.md'
    assert len(api.get('/api/documents').json())==2
    assert api.get('/api/documents/'+docs[0]['document']['id']).status_code==200
    assert api.get('/api/documents/missing').status_code==404
    assert api.post('/api/documents/upload',files={'files':('bad.exe',b'bad')}).status_code==415
    monkeypatch.setattr(settings,'max_file_bytes',10)
    assert api.post('/api/documents/upload',files={'files':('large.txt',b'x'*11)}).status_code==413
    monkeypatch.setattr(settings,'max_request_bytes',20)
    assert api.post('/api/documents/upload',files={'files':('large.txt',b'x'*100)}).status_code==413

def test_parse_failure_and_retry(store,monkeypatch):
    with pytest.raises(HTTPException):
        ingestion.ingest('broken.pdf',b'not pdf',UploadMetadata())
    with connection() as db:
        assert db.execute('SELECT processing_status FROM documents').fetchone()[0]=='failed'
    original=embeddings.encode
    monkeypatch.setattr(embeddings,'encode',lambda _:(_ for _ in ()).throw(RuntimeError('model offline')))
    with pytest.raises(HTTPException) as err:add()
    assert err.value.status_code==503
    monkeypatch.setattr(embeddings,'encode',original)
    assert add().processing_status=='ready'

@pytest.mark.integration
@pytest.mark.skipif(os.environ.get('RUN_MODEL_TESTS')!='1',reason='Set RUN_MODEL_TESTS=1 for real MiniLM integration')
def test_real_semantic_persistence(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'database_path',str(tmp_path/'real.sqlite3'))
    monkeypatch.setattr(settings,'data_dir',str(tmp_path/'real-data'))
    initialize()
    medical=add()
    add('Business travel meals are reimbursed up to 500 rupees per day.',family='travel')
    result,_=retrieval.retrieve(Question(question='How much time off can staff take when they are ill?',mode='semantic'))
    assert result and result[0].document_id==medical.id
    count=vector_store.collection().count()
    vector_store._collection.cache_clear()
    assert vector_store.collection().count()==count
    import subprocess, sys
    process=subprocess.run([sys.executable,'-c',
        "import chromadb,sys; print(chromadb.PersistentClient(path=sys.argv[1]).get_collection(sys.argv[2]).count())",
        str((tmp_path/'real-data'/'chroma').resolve()),vector_store.collection().name],capture_output=True,text=True,check=True,timeout=60)
    assert int(process.stdout.strip())==count
    mock_answer(monkeypatch)
    response=answering.ask(Question(question='What is the current medical leave allowance?',policy_family='leave'))
    assert response.status=='answered' and response.citations[0].version=='2026'
    if os.environ.get('RAG_EXAMPLE_PATH'):
        from pathlib import Path
        Path(os.environ['RAG_EXAMPLE_PATH']).write_text(json.dumps({'note':'Real MiniLM and Chroma; Gemini generation and verification mocked for this fictional test.', 'response':response.model_dump()},indent=2),encoding='utf-8')
    result,_=retrieval.retrieve(Question(question='current medical leave allowance',mode='hybrid'))
    assert result and result[0].document_id==medical.id


def test_unrelated_question_abstains(policies,monkeypatch):
    monkeypatch.setattr(llm,'generate',lambda *args:pytest.fail('Unrelated evidence reached LLM'))
    result=answering.ask(Question(question='What is the interplanetary relocation allowance?',mode='semantic'))
    assert result.status=='not_covered'

def test_quote_and_numeric_rejection(policies):
    from app.services.citations import validate_claims
    evidence,_=retrieval.retrieve(Question(question='medical leave'))
    cid=evidence[0].chunk_id
    invalid=[Claim(text='Employees receive 120 days.',chunk_id=cid,quote='Employees receive 12 days of medical leave per year.'),Claim(text='Paid leave.',chunk_id=cid,quote='A quote absent from the source.')]
    assert validate_claims(invalid,evidence)==([],[])

def test_gemini_structured_adapter(monkeypatch):
    from types import SimpleNamespace
    calls=[]
    class Models:
        def generate_content(self,**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(text='{"claims":[]}')
    monkeypatch.setattr(settings,'gemini_api_key','test-only-key')
    monkeypatch.setattr(llm,'client',lambda *args:SimpleNamespace(models=Models()))
    result=llm.generate(Draft,'Evidence only.',{'question':'test','evidence':[]})
    assert result.claims==[]
    assert calls[0]['config'].response_mime_type=='application/json'
    assert calls[0]['config'].temperature==0
    assert calls[0]['config'].max_output_tokens==settings.llm_max_output_tokens


def test_later_upload_does_not_override_authority(store):
    current=add()
    add('Medical leave was 10 days.','2024','superseded')
    chunks,_=retrieval.retrieve(Question(question='Current medical leave?'))
    assert chunks and all(c.document_id==current.id for c in chunks)

def test_missing_family_and_draft_abstain(store):
    add(family=None)
    chunks,warnings=retrieval.retrieve(Question(question='Current medical leave?'))
    assert not chunks and warnings
    add('Draft proposes 20 medical leave days.',family='leave',status='draft')
    chunks,_=retrieval.retrieve(Question(question='Current medical leave?'))
    assert not chunks


def test_real_chroma_company_filter(store):
    metadata=UploadMetadata(policy_family='leave',version='2026',status='current',effective_date=date(2026,1,1))
    first=ingestion.ingest('leave.txt',b'Employees receive 12 days medical leave.',metadata,company_id='infosys')[0]
    second=ingestion.ingest('leave.txt',b'Employees receive 10 days medical leave.',metadata,company_id='tcs')[0]
    vector=embeddings.encode(['medical leave'])[0]
    for company,document in [('infosys',first),('tcs',second)]:
        # Even an overbroad document allowlist cannot bypass the vector tenant predicate.
        matches=vector_store.search(vector,[first.id,second.id],8,company_id=company)
        assert matches and all(cid.startswith(document.id+':') for cid,_ in matches)
        for mode in ('semantic','hybrid'):
            chunks,_=retrieval.retrieve(Question(question='medical leave',mode=mode),company_id=company)
            assert chunks and all(c.company_id==company and c.document_id==document.id for c in chunks)
