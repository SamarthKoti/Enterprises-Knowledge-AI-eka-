import hashlib
import json
import re
import sqlite3
import threading
import uuid
from pathlib import Path
from fastapi import HTTPException
from app.core.config import settings
from app.core.database import connection
from app.models.contracts import Document
from app.services import parsing, chunking, embeddings, vector_store

INGEST_LOCK=threading.Lock()

def document_model(row):
    value=dict(row)
    value['warnings']=json.loads(value['warnings'])
    return Document.model_validate(value)

def get_document(document_id, company_id=None):
    with connection() as db:
        row=db.execute('SELECT * FROM documents WHERE id=? AND company_id IS ?',(document_id,company_id)).fetchone()
    if not row:
        raise HTTPException(404,'Document not found')
    return document_model(row)

def ingest(filename, data, metadata, company_id=None):
    filename=re.sub(r'[^\w. ()-]','_',filename.replace('\\','/').split('/')[-1])[:180]
    extension=Path(filename).suffix.lower().lstrip('.')
    if extension not in {'pdf','txt','md'}:
        raise HTTPException(415,'Allowed file extensions: PDF, TXT, MD')
    if not data or len(data)>settings.max_file_bytes:
        raise HTTPException(413,'File is empty or exceeds configured size limit')
    digest=hashlib.sha256(data).hexdigest()
    with INGEST_LOCK:
        with connection() as db:
            old=db.execute('SELECT * FROM documents WHERE content_hash=? AND company_id IS ?',(digest,company_id)).fetchone()
            meta=metadata.model_dump(mode='json')
            if old:
                if any(old[k]!=v for k,v in meta.items()):
                    raise HTTPException(409,'Identical content already exists with different policy metadata')
                if old['processing_status']=='ready' and old['embedding_key']==embeddings.embedding_key():
                    return get_document(old['id'],company_id), True
                if old['processing_status']=='processing':
                    raise HTTPException(409,'Document processing is in progress; recover interrupted jobs before retry')
                document_id=old['id']
                db.execute("UPDATE documents SET processing_status='processing',error=NULL WHERE id=?",(document_id,))
            else:
                document_id=str(uuid.uuid4())
                if meta['superseded_by'] and not db.execute('SELECT 1 FROM documents WHERE id=? AND company_id IS ?',(meta['superseded_by'],company_id)).fetchone():
                    raise HTTPException(422,'superseded_by must reference an existing document')
                try:
                    db.execute("INSERT INTO documents(id,filename,format,policy_family,version,effective_date,status,superseded_by,content_hash,company_id,processing_status) VALUES (?,?,?,?,?,?,?,?,?,?,'processing')",(document_id,filename,extension,meta['policy_family'],meta['version'],meta['effective_date'],meta['status'],meta['superseded_by'],digest,company_id))
                except sqlite3.IntegrityError as exc:
                    raise HTTPException(409,'Concurrent duplicate upload; retry') from exc
        try:
            folder=Path(settings.data_dir)/'uploads';folder.mkdir(parents=True,exist_ok=True)
            (folder/(document_id+'.'+extension)).write_bytes(data)
            blocks,warnings=parsing.parse(data,extension)
            record={'id':document_id,'filename':filename,**meta}
            chunks=chunking.chunk(blocks,record)
            for chunk in chunks: chunk.company_id=company_id
            try:
                vectors=embeddings.encode([((c.section+'\n') if c.section else '')+c.text for c in chunks])
                vector_store.remove(document_id)
                vector_store.upsert(chunks,vectors)
            except Exception as exc:
                raise HTTPException(503,'Embedding/vector service unavailable; retry upload after checking model storage and connectivity') from exc
            with connection() as db:
                db.execute('DELETE FROM passages WHERE document_id=?',(document_id,))
                db.executemany('INSERT INTO passages(id,document_id,text,section,page,metadata) VALUES (?,?,?,?,?,?)',[(c.chunk_id,document_id,c.text,c.section,c.page,json.dumps({'is_table':c.is_table})) for c in chunks])
                db.execute("UPDATE documents SET processing_status='ready',chunk_count=?,warnings=?,embedding_key=? WHERE id=?",(len(chunks),json.dumps(warnings),embeddings.embedding_key(),document_id))
            return get_document(document_id,company_id), False
        except Exception as exc:
            message=exc.detail if isinstance(exc,HTTPException) else str(exc) if isinstance(exc,ValueError) else 'Document processing failed'
            with connection() as db:
                db.execute("UPDATE documents SET processing_status='failed',error=? WHERE id=?",(message,document_id))
            if isinstance(exc,HTTPException):
                raise
            raise HTTPException(422 if isinstance(exc,ValueError) else 500,message) from exc
