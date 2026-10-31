import hashlib
from functools import lru_cache
from pathlib import Path
from app.core.config import settings
from app.services.embeddings import embedding_key

@lru_cache(maxsize=4)
def _collection(path, key):
    import chromadb
    from chromadb.config import Settings
    client=chromadb.PersistentClient(path=path,settings=Settings(anonymized_telemetry=False))
    return client.get_or_create_collection('passages-'+hashlib.sha256(key.encode()).hexdigest()[:16],
        metadata={'hnsw:space':'cosine','embedding_key':key},embedding_function=None)

def collection():
    return _collection(str(Path(settings.data_dir).resolve()/'chroma'),embedding_key())

def upsert(chunks, vectors):
    store=collection()
    for start in range(0,len(chunks),128):
        batch=chunks[start:start+128]
        store.upsert(ids=[c.chunk_id for c in batch],embeddings=vectors[start:start+128],documents=[c.text for c in batch],
            metadatas=[{k:v for k,v in c.model_dump(exclude={'text','score'}).items() if v is not None} for c in batch])

def remove(document_id):
    collection().delete(where={'document_id':document_id})

def remove_document(document_id, company_id, key):
    # Use the document's stored embedding collection, even after a model change.
    store=_collection(str(Path(settings.data_dir).resolve()/'chroma'),key or embedding_key())
    store.delete(where={'$and':[{'document_id':document_id},{'company_id':company_id}]})

def search(vector, document_ids, count, company_id=None):
    if not document_ids or not collection().count():
        return []
    where={'document_id':{'$in':document_ids}}
    if company_id is not None:
        where={'$and':[where,{'company_id':company_id}]}
    result=collection().query(query_embeddings=[vector],where=where,n_results=min(count,collection().count()),include=['distances'])
    return [(cid,1-distance) for cid,distance in zip(result['ids'][0],result['distances'][0])]
