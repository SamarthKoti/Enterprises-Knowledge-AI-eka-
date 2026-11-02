import hashlib
import hmac
import re
import secrets
import sqlite3
import time
import uuid
from typing import Literal
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import APIRouter, HTTPException, Request, Response, Depends
from pydantic import BaseModel, Field, ConfigDict, field_validator
from app.core.config import settings
from app.core.database import connection
from app.core.password import hasher

router=APIRouter(prefix='/auth',tags=['Authentication'])
COOKIE='ekai_session'
DUMMY_HASH=hasher.hash(secrets.token_urlsafe(32))

def digest(token): return hashlib.sha256(token.encode()).hexdigest()

def identity(row):
    return {k:row[k] for k in ('id','name','email','employee_id','role','company_id','company_name')}

def current_user(request: Request):
    with connection() as db:
        row=db.execute('''SELECT u.*,c.name AS company_name FROM sessions s JOIN users u ON u.id=s.user_id
            JOIN companies c ON c.id=u.company_id WHERE s.token_hash=? AND s.expires>?
            AND s.company_id=u.company_id AND s.role=u.role AND u.role IN ('admin','employee')''',
            (digest(request.cookies.get(COOKIE,'')),int(time.time()))).fetchone()
    if not row: raise HTTPException(401,'Sign in to your company workspace')
    return identity(row)

def admin_user(user=Depends(current_user)):
    if user['role']!='admin': raise HTTPException(403,'Administrator access required')
    return user

def employee_user(user=Depends(current_user)):
    if user['role']!='employee': raise HTTPException(403,'Employee access required')
    return user

class StrictModel(BaseModel):
    model_config=ConfigDict(extra='forbid')

class Credentials(StrictModel):
    email: str=Field(min_length=3,max_length=254)
    password: str=Field(min_length=1,max_length=1024)

    @field_validator('email')
    @classmethod
    def valid_email(cls,value):
        value=value.strip().casefold()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',value): raise ValueError('Enter a valid email address')
        return value

class EmployeeLogin(Credentials):
    company: Literal['Infosys','TCS','Deloitte']
    code: str=Field(pattern=r'^[0-9]{4}$')

class VerifySignup(StrictModel):
    name: str=Field(min_length=1,max_length=120)
    email: str=Field(min_length=3,max_length=254)
    employee_id: str=Field(pattern=r'^[0-9]{5}$')
    company: Literal['Infosys','TCS','Deloitte']
    code: str=Field(pattern=r'^[0-9]{4}$')

    @field_validator('name')
    @classmethod
    def valid_name(cls,value):
        if not value.strip(): raise ValueError('Full name is required')
        return value.strip()

    @field_validator('email')
    @classmethod
    def valid_email(cls,value): return Credentials.valid_email(value)

class Signup(StrictModel):
    verification_token: str=Field(min_length=20,max_length=200)
    password: str=Field(min_length=8,max_length=8)
    confirm_password: str=Field(min_length=8,max_length=8)

class AdminSignup(StrictModel):
    name: str=Field(min_length=1,max_length=120)
    email: str=Field(min_length=3,max_length=254)
    employee_id: str=Field(pattern=r'^[0-9]{5}$')
    company: Literal['Infosys','TCS','Deloitte']
    password: str=Field(min_length=8,max_length=8)
    confirm_password: str=Field(min_length=8,max_length=8)

    @field_validator('name')
    @classmethod
    def valid_name(cls,value): return VerifySignup.valid_name(value)

    @field_validator('email')
    @classmethod
    def valid_email(cls,value): return Credentials.valid_email(value)

def throttle(request,scope='login'):
    now=int(time.time()); client=f'{scope}:{request.client.host if request.client else "unknown"}'
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('DELETE FROM login_attempts WHERE until<=?',(now,))
        row=db.execute('SELECT count FROM login_attempts WHERE client=?',(client,)).fetchone()
        if row and row['count']>=10: raise HTTPException(429,'Too many attempts. Try again in 15 minutes.')
        db.execute('INSERT INTO login_attempts VALUES (?,1,?) ON CONFLICT(client) DO UPDATE SET count=count+1',(client,now+900))
    return client

def code_record(code):
    if len(settings.company_code_secret)<32: raise HTTPException(503,'Company code secret is not configured')
    return hmac.new(settings.company_code_secret.encode(),code.encode(),hashlib.sha256).hexdigest()

def verify_code(db,company,code):
    row=db.execute('SELECT * FROM companies WHERE name=?',(company,)).fetchone()
    if not row or not row['verification_code_record'] or not hmac.compare_digest(row['verification_code_record'],code_record(code)):
        raise HTTPException(401,'Invalid company or verification code')
    return row

def password_valid(encoded,password):
    try: return hasher.verify(encoded or DUMMY_HASH,password)
    except (VerificationError,InvalidHashError): return False

def start_session(row,request,response,client):
    now=int(time.time()); token=secrets.token_urlsafe(32)
    with connection() as db:
        db.execute('DELETE FROM login_attempts WHERE client=?',(client,))
        db.execute('DELETE FROM sessions WHERE expires<=? OR token_hash=?',(now,digest(request.cookies.get(COOKIE,''))))
        db.execute('INSERT INTO sessions(token_hash,email,expires,user_id,role,company_id) VALUES (?,?,?,?,?,?)',
            (digest(token),row['email'],now+settings.session_ttl_seconds,row['id'],row['role'],row['company_id']))
        db.execute('UPDATE users SET last_login_at=? WHERE id=?',(now,row['id']))
        if row['role']=='employee': db.execute('INSERT INTO access_events VALUES (?,?,?,?,?)',(str(uuid.uuid4()),row['id'],row['company_id'],'login',now))
    response.set_cookie(COOKIE,token,httponly=True,secure=settings.cookie_secure,samesite='lax',max_age=settings.session_ttl_seconds,path='/')
    return identity(row)

def provision_admins():
    with connection() as db:
        for company in ('infosys','tcs','deloitte'):
            email=getattr(settings,f'{company}_admin_email').strip().casefold()
            encoded=getattr(settings,f'{company}_admin_password_hash')
            if not encoded: continue
            existing=db.execute("SELECT * FROM users WHERE company_id=? AND role='admin'",(company,)).fetchone()
            if existing:
                db.execute('UPDATE users SET password_hash=? WHERE id=?',(encoded,existing['id']))
                continue
            if db.execute('SELECT 1 FROM users WHERE email=?',(email,)).fetchone(): raise RuntimeError('Configured admin email already exists; choose a different admin email')
            db.execute('INSERT INTO users(email,password_hash,created_at,id,name,role,company_id) VALUES (?,?,?,?,?,?,?)',
                (email,encoded,int(time.time()),str(uuid.uuid4()),f'{company.title()} Administrator','admin',company))

@router.post('/admin/login')
def admin_login(data: Credentials,request: Request,response: Response):
    client=throttle(request)
    with connection() as db:
        row=db.execute("SELECT u.*,c.name AS company_name FROM users u JOIN companies c ON c.id=u.company_id WHERE email=? AND role='admin'",(data.email,)).fetchone()
    valid=password_valid(row['password_hash'] if row else DUMMY_HASH,data.password)
    if not row or not valid: raise HTTPException(401,'Invalid administrator credentials')
    return start_session(row,request,response,client)

@router.post('/sign-in')
def sign_in(data: Credentials,request: Request,response: Response):
    """Common login. The stored account, never the browser, determines role and company."""
    client=throttle(request,'common-login')
    with connection() as db:
        row=db.execute("SELECT u.*,c.name AS company_name FROM users u JOIN companies c ON c.id=u.company_id WHERE u.email=? AND u.role IN ('admin','employee')",(data.email,)).fetchone()
    valid=password_valid(row['password_hash'] if row else DUMMY_HASH,data.password)
    if not row or not valid: raise HTTPException(401,'Invalid email or password')
    return start_session(row,request,response,client)

@router.post('/admin/register',status_code=201)
def register_first_admin(data: AdminSignup,request: Request,response: Response):
    """Local bootstrap: each company can enrol exactly one administrator."""
    client=throttle(request,'admin-signup')
    if data.password!=data.confirm_password: raise HTTPException(422,'Passwords do not match')
    try:
        with connection() as db:
            db.execute('BEGIN IMMEDIATE')
            company=db.execute('SELECT id FROM companies WHERE name=?',(data.company,)).fetchone()
            if db.execute("SELECT 1 FROM users WHERE company_id=? AND role='admin'",(company['id'],)).fetchone():
                raise HTTPException(409,'This company already has an administrator. Use Login.')
            if db.execute('SELECT 1 FROM users WHERE email=? OR (company_id=? AND employee_id=?)',(data.email,company['id'],data.employee_id)).fetchone():
                raise HTTPException(409,'Email or employee ID is already registered')
            uid=str(uuid.uuid4()); now=int(time.time())
            db.execute("INSERT INTO users(email,password_hash,created_at,id,name,employee_id,role,company_id) VALUES (?,?,?,?,?,?, 'admin', ?)",
                (data.email,hasher.hash(data.password),now,uid,data.name,data.employee_id,company['id']))
            row=db.execute('SELECT u.*,c.name AS company_name FROM users u JOIN companies c ON c.id=u.company_id WHERE u.id=?',(uid,)).fetchone()
    except sqlite3.IntegrityError as exc: raise HTTPException(409,'Email or employee ID is already registered') from exc
    return start_session(row,request,response,client)

@router.post('/login')
def login(data: EmployeeLogin,request: Request,response: Response):
    client=throttle(request)
    with connection() as db:
        company=verify_code(db,data.company,data.code)
        row=db.execute("SELECT u.*,c.name AS company_name FROM users u JOIN companies c ON c.id=u.company_id WHERE email=? AND role='employee' AND u.company_id=?",(data.email,company['id'])).fetchone()
    valid=password_valid(row['password_hash'] if row else DUMMY_HASH,data.password)
    if not row or not valid: raise HTTPException(401,'Invalid employee credentials or company')
    return start_session(row,request,response,client)

@router.post('/signup/verify')
def verify_signup(data: VerifySignup,request: Request):
    throttle(request,'verification'); token=secrets.token_urlsafe(32); now=int(time.time())
    with connection() as db:
        company=verify_code(db,data.company,data.code)
        if db.execute('SELECT 1 FROM users WHERE email=? OR (company_id=? AND employee_id=?)',(data.email,company['id'],data.employee_id)).fetchone():
            raise HTTPException(409,'Email or employee ID is already registered')
        db.execute('DELETE FROM signup_tickets WHERE expires<=?',(now,))
        db.execute('INSERT INTO signup_tickets VALUES (?,?,?,?,?,?)',(digest(token),data.name,data.email,data.employee_id,company['id'],now+600))
    return {'verification_token':token,'expires_in':600}

@router.post('/signup',status_code=201)
def signup(data: Signup,request: Request,response: Response):
    client=throttle(request,'signup')
    if data.password!=data.confirm_password: raise HTTPException(422,'Passwords do not match')
    encoded=hasher.hash(data.password)
    try:
        with connection() as db:
            db.execute('BEGIN IMMEDIATE')
            ticket=db.execute('SELECT * FROM signup_tickets WHERE token_hash=? AND expires>?',(digest(data.verification_token),int(time.time()))).fetchone()
            if not ticket: raise HTTPException(401,'Verification expired. Verify your company again.')
            uid=str(uuid.uuid4())
            db.execute("INSERT INTO users(email,password_hash,created_at,id,name,employee_id,role,company_id) VALUES (?,?,?,?,?,?,'employee',?)",(ticket['email'],encoded,int(time.time()),uid,ticket['name'],ticket['employee_id'],ticket['company_id']))
            db.execute('DELETE FROM signup_tickets WHERE token_hash=?',(digest(data.verification_token),))
            row=db.execute('SELECT u.*,c.name AS company_name FROM users u JOIN companies c ON c.id=u.company_id WHERE u.id=?',(uid,)).fetchone()
    except sqlite3.IntegrityError as exc: raise HTTPException(409,'Email or employee ID is already registered') from exc
    return start_session(row,request,response,client)

@router.get('/me')
def me(user=Depends(current_user)): return user

@router.post('/logout',status_code=204)
def logout(request: Request,response: Response):
    with connection() as db: db.execute('DELETE FROM sessions WHERE token_hash=?',(digest(request.cookies.get(COOKIE,'')),))
    response.delete_cookie(COOKIE,path='/',secure=settings.cookie_secure,httponly=True,samesite='lax')
