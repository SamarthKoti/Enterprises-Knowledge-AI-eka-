import re
import logging
import unicodedata
from app.core.database import connection
from app.models.contracts import Citation


log=logging.getLogger(__name__)

def normalize(text):
    return ' '.join(unicodedata.normalize('NFC',text).split())

def validate_claims(claims, evidence, company_id=None):
    allowed={c.chunk_id:c for c in evidence}
    valid=[];citations=[]
    with connection() as db:
        for claim in claims:
            if claim.chunk_id not in allowed:
                log.warning('Citation rejected reason=unknown_passage company=%s',company_id)
                continue
            row=db.execute('SELECT p.*,d.filename,d.version FROM passages p JOIN documents d ON d.id=p.document_id WHERE p.id=? AND d.company_id IS ?',(claim.chunk_id,company_id)).fetchone()
            if not row or row['document_id']!=allowed[claim.chunk_id].document_id or not normalize(claim.quote) or normalize(claim.quote) not in normalize(row['text']):
                log.warning('Citation rejected reason=source_or_quote_mismatch company=%s passage=%s',company_id,claim.chunk_id)
                continue
            if normalize(claim.quote) not in normalize(allowed[claim.chunk_id].text):
                continue
            # Cheap deterministic guard before semantic entailment verification.
            numbers=set(re.findall(r'\d+(?:[.,]\d+)?',claim.quote))
            # A year label can be supported by authoritative metadata, while
            # quantities still require exact support in the quoted passage.
            numeric_text=claim.text
            if row['version'] and re.fullmatch(r'20\d{2}',row['version']) and row['version']==allowed[claim.chunk_id].version:
                year=re.escape(row['version'])
                numeric_text=re.sub(r'\b(?:in|for|during)\s+(?:the\s+year\s+)?'+year+r'\b|\b'+year+r'\s+(?:policy|version)\b','',numeric_text,flags=re.I)
            if not set(re.findall(r'\d+(?:[.,]\d+)?',numeric_text)) <= numbers:
                log.warning('Citation rejected reason=unsupported_number company=%s passage=%s',company_id,claim.chunk_id)
                continue
            if not claim.text.strip():
                continue
            valid.append(claim)
            citations.append(Citation(document_id=row['document_id'],passage_id=row['id'],chunk_id=row['id'],filename=row['filename'],document=row['filename'],version=row['version'],section=row['section'],page=row['page'],quote=claim.quote))
    return valid,citations
