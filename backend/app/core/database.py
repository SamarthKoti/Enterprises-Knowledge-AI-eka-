import sqlite3
from contextlib import contextmanager
from app.core.config import settings

@contextmanager
def connection():
    db = sqlite3.connect(settings.database_path)
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA busy_timeout=10000')
    db.row_factory = sqlite3.Row
    try:
        yield db
        db.commit()
    finally:
        db.close()

def initialize():
    with connection() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS users (email TEXT PRIMARY KEY, password_hash TEXT NOT NULL, created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, email TEXT NOT NULL, expires INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS login_attempts (client TEXT PRIMARY KEY, count INTEGER NOT NULL, until INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, filename TEXT NOT NULL, format TEXT NOT NULL, policy_family TEXT, version TEXT, effective_date TEXT, status TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS passages (id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id), text TEXT NOT NULL, section TEXT, page INTEGER, metadata TEXT NOT NULL DEFAULT '{}');
        ''')

        # Additive migration preserves Phase 1 sessions and metadata.
        columns = {row['name'] for row in db.execute('PRAGMA table_info(documents)')}
        for name, kind in {
            'content_hash': 'TEXT', 'superseded_by': 'TEXT',
            'processing_status': "TEXT NOT NULL DEFAULT 'pending'",
            'error': 'TEXT', 'warnings': "TEXT NOT NULL DEFAULT '[]'",
            'chunk_count': 'INTEGER NOT NULL DEFAULT 0',
            'embedding_key': 'TEXT',
        }.items():
            if name not in columns:
                db.execute(f'ALTER TABLE documents ADD COLUMN {name} {kind}')
        db.execute('CREATE INDEX IF NOT EXISTS passage_document ON passages(document_id)')
        initialize_company_schema(db)


def initialize_company_schema(db):
    """Add company metadata without assigning legacy records to a tenant."""
    db.executescript('''
    CREATE TABLE IF NOT EXISTS companies (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL UNIQUE CHECK(name IN ('Infosys','TCS')),
        verification_code_record TEXT UNIQUE,
        verification_code_generated_at INTEGER
    );
    INSERT OR IGNORE INTO companies(id,name) VALUES ('infosys','Infosys'),('tcs','TCS');
    ''')
    additions = {
        'users': {
            'id': 'TEXT', 'name': 'TEXT', 'employee_id': 'TEXT',
            'role': "TEXT CHECK(role IN ('admin','employee'))",
            'company_id': 'TEXT REFERENCES companies(id)', 'last_login_at': 'INTEGER',
        },
        'documents': {'company_id': 'TEXT REFERENCES companies(id)'},
        'sessions': {
            'user_id': 'TEXT', 'role': 'TEXT',
            'company_id': 'TEXT REFERENCES companies(id)',
        },
    }
    for table, fields in additions.items():
        present = {row['name'] for row in db.execute(f'PRAGMA table_info({table})')}
        for name, kind in fields.items():
            if name not in present:
                db.execute(f'ALTER TABLE {table} ADD COLUMN {name} {kind}')
    db.executescript('''
    CREATE UNIQUE INDEX IF NOT EXISTS user_identity ON users(id);
    DROP INDEX IF EXISTS document_hash;
    CREATE UNIQUE INDEX IF NOT EXISTS company_document_hash ON documents(company_id,content_hash);
    CREATE UNIQUE INDEX IF NOT EXISTS company_employee ON users(company_id,employee_id);
    CREATE UNIQUE INDEX IF NOT EXISTS company_admin ON users(company_id) WHERE role='admin';
    CREATE INDEX IF NOT EXISTS company_documents ON documents(company_id);
    CREATE TABLE IF NOT EXISTS question_events (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
        company_id TEXT NOT NULL REFERENCES companies(id), category TEXT NOT NULL,
        answer_status TEXT NOT NULL, created_at INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS access_events (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
        company_id TEXT NOT NULL REFERENCES companies(id), event_type TEXT NOT NULL,
        created_at INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS company_question_time ON question_events(company_id,created_at);
    CREATE INDEX IF NOT EXISTS company_access_time ON access_events(company_id,created_at);
    CREATE TABLE IF NOT EXISTS signup_tickets (
        token_hash TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL,
        employee_id TEXT NOT NULL, company_id TEXT NOT NULL REFERENCES companies(id),
        expires INTEGER NOT NULL
    );
    ''')
