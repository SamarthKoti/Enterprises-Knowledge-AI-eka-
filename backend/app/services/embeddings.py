from functools import lru_cache
from threading import Lock
from pathlib import Path
from app.core.config import settings

MODEL_LOCK = Lock()

@lru_cache(maxsize=1)
def model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(settings.embedding_model, revision=settings.embedding_revision or None,
        cache_folder=settings.model_cache_dir, device='cpu', trust_remote_code=False)

def encode(texts):
    import numpy as np
    with MODEL_LOCK:
        encoder = model()
        # MiniLM truncates at 256 tokens: embed all subwindows and pool them.
        pieces, owners = [], []
        capacity = encoder.max_seq_length-2
        for index,text in enumerate(texts):
            ids = encoder.tokenizer.encode(text,add_special_tokens=False)
            for start in range(0,len(ids),capacity):
                pieces.append(encoder.tokenizer.decode(ids[start:start+capacity],skip_special_tokens=True))
                owners.append(index)
        if not pieces:
            return []
        vectors = encoder.encode(pieces,batch_size=settings.embedding_batch_size,normalize_embeddings=True,show_progress_bar=False)
        result=[]
        for index in range(len(texts)):
            vector=np.mean(vectors[np.array(owners)==index],axis=0)
            result.append((vector/max(float(np.linalg.norm(vector)),1e-12)).tolist())
        return result

def embedding_key():
    return settings.embedding_model+'@'+settings.embedding_revision+':pooled-v1'
