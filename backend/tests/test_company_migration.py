from app.core.database import connection, initialize
from app.core.config import settings


def test_company_migration_preserves_unscoped_records(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'database_path', str(tmp_path / 'migration.sqlite3'))
    with connection() as db:
        db.execute('CREATE TABLE users(email TEXT PRIMARY KEY,password_hash TEXT NOT NULL,created_at INTEGER NOT NULL)')
        db.execute("INSERT INTO users VALUES ('old@example.com','existing-hash',1)")
        db.execute('CREATE TABLE documents(id TEXT PRIMARY KEY,filename TEXT NOT NULL,format TEXT NOT NULL,policy_family TEXT,version TEXT,effective_date TEXT,status TEXT NOT NULL)')
        db.execute("INSERT INTO documents VALUES ('old','policy.txt','txt',NULL,NULL,NULL,'current')")
    initialize()
    initialize()
    with connection() as db:
        assert [r['name'] for r in db.execute('SELECT name FROM companies ORDER BY name')] == ['Infosys', 'TCS']
        assert db.execute("SELECT company_id FROM documents WHERE id='old'").fetchone()[0] is None
        user = db.execute("SELECT * FROM users WHERE email='old@example.com'").fetchone()
        assert user['password_hash'] == 'existing-hash'
        assert user['company_id'] is None and user['role'] is None
