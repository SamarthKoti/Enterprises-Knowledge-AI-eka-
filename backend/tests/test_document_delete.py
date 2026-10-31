from pathlib import Path
import pytest
from fastapi import HTTPException
from app.core.config import settings
from app.core.database import connection
from app.models.contracts import UploadMetadata,Question
from app.services import ingestion,vector_store,retrieval
from test_rag import store
from test_auth import clients,admin,code,register,upload


def add(company,text):
    return ingestion.ingest('policy.txt',text.encode(),UploadMetadata(policy_family='leave',version='2026',status='current'),company)[0]


def test_delete_removes_original_passages_and_original_embedding_collection(store,monkeypatch):
    target=add('infosys','Medical leave is 12 days.')
    other=add('tcs','Medical leave is 10 days.')
    index=vector_store.collection()
    with connection() as db:
        db.execute("INSERT INTO documents(id,filename,format,company_id,status,superseded_by) VALUES ('older','old.txt','txt','infosys','current',?)",(target.id,))
    monkeypatch.setattr(settings,'embedding_revision','new-revision')
    ingestion.delete_document(target.id,'infosys')
    assert not (Path(settings.data_dir)/'uploads'/f'{target.id}.txt').exists()
    assert (Path(settings.data_dir)/'uploads'/f'{other.id}.txt').exists()
    assert not index.get(where={'document_id':target.id})['ids']
    assert index.get(where={'document_id':other.id})['ids']
    with connection() as db:
        assert not db.execute('SELECT 1 FROM documents WHERE id=?',(target.id,)).fetchone()
        assert not db.execute('SELECT 1 FROM passages WHERE document_id=?',(target.id,)).fetchone()
        old=db.execute("SELECT * FROM documents WHERE id='older'").fetchone()
        assert old['status']=='superseded' and old['superseded_by'] is None


def test_delete_failure_is_retryable_and_excluded_from_retrieval(store,monkeypatch):
    doc=add('infosys','Medical leave is 12 days.')
    original=vector_store.remove_document
    def fail(*args):raise RuntimeError('storage offline')
    monkeypatch.setattr(vector_store,'remove_document',fail)
    with pytest.raises(HTTPException) as caught:ingestion.delete_document(doc.id,'infosys')
    assert caught.value.status_code==503
    assert ingestion.get_document(doc.id,'infosys').processing_status=='deleting'
    assert retrieval.retrieve(Question(question='medical leave'),'infosys')[0]==[]
    monkeypatch.setattr(vector_store,'remove_document',original)
    ingestion.delete_document(doc.id,'infosys')
    with pytest.raises(HTTPException) as caught:ingestion.get_document(doc.id,'infosys')
    assert caught.value.status_code==404


def test_delete_wrong_tenant_does_not_touch_storage(store,monkeypatch):
    doc=add('infosys','Medical leave is 12 days.')
    monkeypatch.setattr(vector_store,'remove_document',lambda *a:pytest.fail('Unauthorized vector deletion'))
    with pytest.raises(HTTPException) as caught:ingestion.delete_document(doc.id,'tcs')
    assert caught.value.status_code==404
    assert ingestion.get_document(doc.id,'infosys').processing_status=='ready'


def test_delete_endpoint_admin_only_and_tenant_scoped(clients,monkeypatch):
    a,b=clients
    company_code=code(a)
    document_id=upload(a,'Medical leave is 12 days.')
    admin(b,'tcs')
    calls=[]
    monkeypatch.setattr(vector_store,'remove_document',lambda *args:calls.append(args))
    assert b.delete('/api/documents/'+document_id).status_code==404
    register(a,'Infosys',company_code)
    assert a.delete('/api/documents/'+document_id).status_code==403
    a.post('/api/auth/logout')
    assert a.delete('/api/documents/'+document_id).status_code==401
    assert not calls
    admin(a)
    response=a.delete('/api/documents/'+document_id)
    assert response.status_code==204 and not response.content
    assert calls[0][0:2]==(document_id,'infosys')
    assert a.get('/api/documents/'+document_id).status_code==404
    assert a.get('/api/documents/'+document_id+'/download').status_code==404
    assert a.get('/api/documents').json()==[]
    assert a.delete('/api/documents/'+document_id).status_code==404
