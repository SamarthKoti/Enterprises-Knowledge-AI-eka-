from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    demo_email: str = 'demo@example.com'
    deloitte_admin_email: str = 'admin@deloitte.local'
    deloitte_admin_password_hash: str = ''
    infosys_admin_email: str = 'admin@infosys.local'
    infosys_admin_password_hash: str = ''
    tcs_admin_email: str = 'admin@tcs.local'
    tcs_admin_password_hash: str = ''
    company_code_secret: str = ''
    demo_password_hash: str = ''
    # Optional compatibility hash for a rotated local demo password.
    demo_legacy_password_hash: str = ''
    database_path: str = 'knowledge.sqlite3'
    data_dir: str = 'data'
    model_cache_dir: str = 'data/models'
    embedding_model: str = 'sentence-transformers/all-MiniLM-L6-v2'
    embedding_revision: str = 'c9745ed1d9f207416be6d2e6f8de32d1f16199bf'
    embedding_batch_size: int = 32
    max_file_bytes: int = 10 * 1024 * 1024
    max_request_bytes: int = 30 * 1024 * 1024
    max_upload_files: int = 10
    max_pdf_pages: int = 1000
    max_extracted_chars: int = 2_000_000
    chunk_tokens: int = 500
    chunk_overlap: int = 75
    retrieval_top_k: int = 6
    semantic_min_score: float = 0.25
    context_max_chars: int = 16000
    llm_provider: str = 'gemini'
    gemini_api_key: str = ''
    gemini_model: str = 'gemini-3.8-flash'
    llm_timeout_ms: int = 120000
    llm_max_output_tokens: int = 3000
    session_ttl_seconds: int = 28800
    cookie_secure: bool = False
    allowed_origins: str = 'http://localhost:5173,http://127.0.0.1:5173'
    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parents[3] / '.env', extra='ignore')

settings = Settings()
