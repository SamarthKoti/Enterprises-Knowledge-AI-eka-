# Enterprise Knowledge AI

React/Vite and FastAPI with company-isolated SQLite, MiniLM/Chroma retrieval, Gemini answers, citations, and version management.

## Start locally (Windows PowerShell)
Open the project folder in VS Code, choose Terminal > New Terminal, and use two terminals. Dependencies are already installed in this workspace.

Terminal 1, from the project folder:
```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
Terminal 2, from the project folder:
```powershell
cd frontend
npm run dev
```
Open http://127.0.0.1:5173. Keep both terminals open. Use one backend worker. For a fresh checkout, create the backend virtual environment, install requirements.lock.txt, and run npm ci in frontend.

If ports 8000 or 5173 are already reserved, run the backend on 8001 and start the frontend with `VITE_API_TARGET=http://127.0.0.1:8001 npm run dev -- --port 5174` (PowerShell syntax is shown below in the final run instructions).

## Company setup
Copy .env.example to the root .env for a fresh installation. Configure INFOSYS_ADMIN_EMAIL, INFOSYS_ADMIN_PASSWORD_HASH, TCS_ADMIN_EMAIL, TCS_ADMIN_PASSWORD_HASH, DELOITTE_ADMIN_EMAIL, DELOITTE_ADMIN_PASSWORD_HASH, and COMPANY_CODE_SECRET. Generate each administrator password hash from backend:
```powershell
.\.venv\Scripts\python.exe -m app.core.password
```
The interactive helper accepts an 8–12-character administrator password and prints only its Argon2 hash. Generate the shared secret once:
```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
```
Save it as COMPANY_CODE_SECRET. Keep it unchanged and back it up with the database; changing it invalidates company-code verification. Restart the backend after configuration changes. The first administrator for each company can register through the app; a company is locked to one administrator after that.

1. Use Register > Admin to create the first administrator for Infosys, TCS, or Deloitte. Later, use the common Login screen; the backend determines the account's role and company from the stored account.
2. Generate the company verification code once. Copy/save the displayed four-digit code immediately; only its keyed hash is stored, so it cannot be displayed again. Refresh/restart does not regenerate it.
3. Upload company policies with explicit policy family, version, date and authority status. The UI accepts up to 60 files, uploading sequentially; each file is limited to 10 MiB.
4. Employees choose Sign Up: name/email/five-digit ID/company, then company code, then password confirmation. Employee passwords are exactly eight characters under the Phase 3 specification. Leading zeros in employee IDs and codes are preserved.
5. Employee Login uses email and password. The company was securely bound to the employee during registration after its four-digit company-code check. Employees receive Assistant, Batch and personal Reports; admins receive Documents, Employees and company Analytics.

Existing unscoped accounts/documents remain preserved but cannot enter either company's workspace. No automatic ownership assignment is performed. Re-upload authorized originals under the correct administrator. Legacy DEMO_* settings no longer provide login access.

## Gemini and data
Set GEMINI_API_KEY and GEMINI_MODEL in the root .env using a model available to your Google account. The default is gemini-3.8-flash. No credentials belong in frontend code. Missing provider access produces a service error when evidence exists; missing evidence produces not_covered. MiniLM may download its pinned model on first use. SQLite and Chroma persist under backend configuration paths.

All document, vector, keyword, citation, batch and analytics requests derive company identity from the server session. Employee CSV batches require a question column, at most 100 rows and 1 MiB. CSV/JSON exports include answer statuses and citations. Keep the batch page open until completion.

Analytics use real stored events, rolling 7/30/365-day UTC windows, and conservative keyword question categories with Other for ambiguity. Failed requests are labeled as errors. No synthetic metrics are displayed. Set COOKIE_SECURE=true behind HTTPS in deployment and use a same-origin API proxy.

## Verification
From backend:
```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
$env:RUN_MODEL_TESTS='1'
.\.venv\Scripts\python.exe -m pytest tests -q -m integration
```
From frontend:
```powershell
npm run build
```
Tests use temporary fictional documents and mocked Gemini. The opt-in integration test uses real MiniLM and persistent Chroma; it does not verify live Gemini. API contracts are available at http://127.0.0.1:8000/docs.
