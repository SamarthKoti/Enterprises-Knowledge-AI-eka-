import concurrent.futures
import json
import time
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.api.auth import provision_admins
from app.core.config import settings
from app.core.database import connection, initialize
from app.core.password import hasher
from app.services import embeddings, vector_store, llm
from app.models.contracts import Draft, Claim, Verification

@pytest.fixture
def clients(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'database_path',str(tmp_path/'company.sqlite3'))
    monkeypatch.setattr(settings,'data_dir',str(tmp_path/'data'))
    monkeypatch.setattr(settings,'company_code_secret','test-secret-'*4)
    for company in ('infosys','tcs'):
        monkeypatch.setattr(settings,f'{company}_admin_email',f'admin@{company}.local')
        monkeypatch.setattr(settings,f'{company}_admin_password_hash',hasher.hash('Admin123'))
    initialize();provision_admins()
    # Deterministic local retrieval double; separate RAG tests exercise real Chroma.
    vectors={}
    monkeypatch.setattr(embeddings,'encode',lambda texts:[[1.0,0.0] for _ in texts])
    monkeypatch.setattr(vector_store,'upsert',lambda chunks,values:vectors.update({c.chunk_id:c for c in chunks}))
    monkeypatch.setattr(vector_store,'remove',lambda document_id:None)
    def search(vector,ids,count,company_id=None): return [(cid,1.0) for cid,c in vectors.items() if c.document_id in ids and c.company_id==company_id][:count]
    monkeypatch.setattr(vector_store,'search',search)
    def generate(schema,prompt,payload):
        if schema is Draft:
            c=payload['evidence'][0]
            return Draft(claims=[Claim(text=c['text'],quote=c['text'],chunk_id=c['chunk_id'])])
        return Verification(supported_claims=[0],supported_parts=['medical leave allowance'],unsupported_parts=[],all_parts_covered=True)
    monkeypatch.setattr(llm,'generate',generate)
    with TestClient(app) as first,TestClient(app) as second:
        yield first,second

def admin(client,company='infosys'):
    response=client.post('/api/auth/admin/login',json={'email':f'admin@{company}.local','password':'Admin123'})
    assert response.status_code==200,response.text
    assert response.json()['role']=='admin'
    return response

def code(client,company='infosys'):
    admin(client,company)
    response=client.post('/api/company/code')
    assert response.status_code==201,response.text
    return response.json()['code']

def register(client,company,company_code,email='employee@example.com',employee_id='00123'):
    verified=client.post('/api/auth/signup/verify',json={'name':'Test Employee','email':email,'employee_id':employee_id,'company':company,'code':company_code})
    assert verified.status_code==200,verified.text
    response=client.post('/api/auth/signup',json={'verification_token':verified.json()['verification_token'],'password':'Pass1234','confirm_password':'Pass1234'})
    assert response.status_code==201,response.text
    return response

def upload(client,text):
    r=client.post('/api/documents/upload',files={'files':('leave.txt',text.encode())},data={'metadata':json.dumps({'policy_family':'leave','version':'2026','status':'current','effective_date':'2026-01-01'})})
    assert r.status_code==201,r.text
    return r.json()['results'][0]['document']['id']

def test_admins_codes_and_persistence(clients):
    a,b=clients; first=code(a); second=code(b,'tcs')
    assert len(first)==4 and first.isdigit() and first!=second
    assert a.post('/api/company/code').status_code==409
    initialize();provision_admins()
    a.post('/api/auth/logout');admin(a)
    assert a.get('/api/company').json()['code_generated']
    assert 'code' not in a.get('/api/company').json()
    assert a.post('/api/company/code').status_code==409
    register(a,'Infosys',first)
    assert a.get('/api/auth/me').json()['company_id']=='infosys'

def test_concurrent_code_generation(clients):
    a,b=clients;admin(a);admin(b)
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        results=list(pool.map(lambda client:client.post('/api/company/code'),[a,b]))
    assert sorted(r.status_code for r in results)==[201,409]

def test_signup_validation_and_role_injection(clients):
    a,b=clients;c=code(a);other=code(b,'tcs')
    payload={'name':'Person','email':'person@example.com','employee_id':'00001','company':'Infosys','code':c}
    assert a.post('/api/auth/signup/verify',json={**payload,'code':other}).status_code==401
    for bad in ('1234','123456','abcde','１２３４５'):
        assert a.post('/api/auth/signup/verify',json={**payload,'employee_id':bad}).status_code==422
    assert a.post('/api/auth/signup/verify',json={**payload,'role':'admin'}).status_code==422
    ticket=a.post('/api/auth/signup/verify',json=payload).json()['verification_token']
    signup={'verification_token':ticket,'password':'Pass1234','confirm_password':'Pass1234'}
    assert a.post('/api/auth/signup',json={**signup,'confirm_password':'Wrong123'}).status_code==422
    assert a.post('/api/auth/signup',json={**signup,'role':'admin'}).status_code==422
    assert a.post('/api/auth/signup',json={**signup,'company_id':'tcs'}).status_code==422
    for value in ('short','ninechars'):
        assert a.post('/api/auth/signup',json={**signup,'password':value,'confirm_password':value}).status_code==422
    result=a.post('/api/auth/signup',json=signup)
    assert result.status_code==201
    assert result.json()['role']=='employee' and result.json()['employee_id']=='00001'
    assert a.post('/api/auth/signup',json=signup).status_code==401
    with connection() as db:
        stored=db.execute("SELECT password_hash FROM users WHERE email='person@example.com'").fetchone()[0]
    assert stored!='Pass1234' and hasher.verify(stored,'Pass1234')

def test_employee_login_and_permissions(clients):
    a,b=clients;c=code(a);tc=code(b,'tcs');register(a,'Infosys',c)
    a.post('/api/auth/logout')
    payload={'email':'employee@example.com','password':'Pass1234','company':'Infosys','code':c}
    for change in ({'password':'Wrong123'},{'company':'TCS','code':tc},{'code':tc}):
        assert a.post('/api/auth/login',json={**payload,**change}).status_code==401
    result=a.post('/api/auth/login',json=payload)
    assert result.status_code==200
    assert 'httponly' in result.headers['set-cookie'].lower()
    for path in ('/api/documents','/api/employees','/api/analytics','/api/company'):
        assert a.get(path).status_code==403
    assert a.post('/api/documents/upload',files={'files':('secret.txt',b'secret')}).status_code==403
    assert a.post('/api/company/code').status_code==403
    assert a.post('/api/auth/admin/login',json={'email':payload['email'],'password':payload['password']}).status_code==401
    assert a.post('/api/auth/login',json=payload,headers={'origin':'https://evil.example'}).status_code==403
    token=a.cookies.get('ekai_session');a.post('/api/auth/logout');a.cookies.set('ekai_session',token)
    assert a.get('/api/auth/me').status_code==401


def test_common_login_routes_by_stored_role(clients):
    a,b=clients; company_code=code(a); register(a,'Infosys',company_code)
    a.post('/api/auth/logout')
    response=a.post('/api/auth/sign-in',json={'email':'employee@example.com','password':'Pass1234'})
    assert response.status_code==200 and response.json()['role']=='employee' and response.json()['company_id']=='infosys'
    a.post('/api/auth/logout')
    response=a.post('/api/auth/sign-in',json={'email':'admin@infosys.local','password':'Admin123'})
    assert response.status_code==200 and response.json()['role']=='admin' and response.json()['company_id']=='infosys'
    assert b.post('/api/auth/sign-in',json={'email':'employee@example.com','password':'wrong'}).status_code==401


def test_first_admin_registration_locks_company(clients):
    a,b=clients
    with connection() as db:
        db.execute("DELETE FROM users WHERE role='admin'")
    payload={'name':'New Admin','email':'new-admin@example.com','employee_id':'00099','company':'Infosys','password':'Pass1234','confirm_password':'Pass1234'}
    result=a.post('/api/auth/admin/register',json=payload)
    assert result.status_code==201,result.text
    assert result.json()['role']=='admin' and result.json()['company_id']=='infosys'
    assert b.post('/api/auth/admin/register',json={**payload,'email':'again@example.com','employee_id':'00098'}).status_code==409
    assert a.post('/api/auth/admin/register',json={**payload,'company':'TCS','email':'bad@example.com','employee_id':'1234'}).status_code==422

def test_tenant_retrieval_citations_batches_and_analytics(clients):
    a,b=clients;ic=code(a);tc=code(b,'tcs')
    infosys=upload(a,'Employees receive 12 days of medical leave per year.')
    tcs=upload(b,'Employees receive 15 days of medical leave per year.')
    assert a.get('/api/documents/'+tcs).status_code==404
    assert a.get('/api/documents/'+tcs+'/download').status_code==404
    assert a.patch('/api/documents/'+infosys,json={'status':'superseded','policy_family':'leave','superseded_by':tcs}).status_code==422
    assert len(a.get('/api/documents').json())==1
    register(a,'Infosys',ic,'i@example.com');register(b,'TCS',tc,'t@example.com')
    for client,expected,forbidden,doc in ((a,'12','15',infosys),(b,'15','12',tcs)):
        result=client.post('/api/ask',json={'question':'What is the medical leave allowance?'}).json()
        assert expected in result['answer'] and forbidden not in result['answer']
        assert result['citations'][0]['document_id']==doc
        assert client.get('/api/sources/'+result['citations'][0]['chunk_id']).status_code==200
    assert a.get('/api/sources/'+tcs+':0').status_code==404
    result=a.post('/api/batches/upload',files={'file':('questions.csv',b'question\nWhat is the medical leave allowance?\n')})
    assert result.status_code==200
    assert result.json()['results'][0]['answer']['citations'][0]['document_id']==infosys
    assert a.post('/api/batches',json={'questions':[{'question':'Leave?'}],'company_id':'tcs'}).status_code==422
    personal=a.get('/api/reports/me').json()
    assert personal['company']=='Infosys' and personal['question_count']>=2
    admin(a);admin(b,'tcs')
    assert [u['email'] for u in a.get('/api/employees').json()]==['i@example.com']
    assert [u['email'] for u in b.get('/api/employees').json()]==['t@example.com']
    for period in ('week','month','year'):
        stats=a.get('/api/analytics',params={'period':period}).json()
        assert stats['company']=='Infosys' and stats['unique_employees']==1
        assert stats['successful_logins']==1 and stats['total_employees']==1
        assert sum(stats['categories'].values())==stats['question_count']
    assert a.get('/api/reports/me').status_code==403

def test_rate_limits_and_empty_metrics(clients):
    a,b=clients;c=code(a)
    stats=a.get('/api/analytics').json()
    assert stats['question_count']==0 and stats['unique_employees']==0
    assert all(n==0 for n in stats['categories'].values())
    payload={'name':'Person','email':'person@example.com','employee_id':'00001','company':'Infosys','code':'9999' if c!='9999' else '9998'}
    for _ in range(10): assert b.post('/api/auth/signup/verify',json=payload).status_code==401
    assert b.post('/api/auth/signup/verify',json={**payload,'code':c}).status_code==429

def test_identical_documents_are_company_local(clients):
    a,b=clients;code(a);code(b,'tcs')
    content='Both companies have an independently uploaded policy.'
    assert upload(a,content)!=upload(b,content)

def test_categories_are_conservative():
    from app.services.activity import classify
    assert classify('How is payroll tax calculated?')=='Finance'
    assert classify('What does health insurance cover?')=='Health Insurance'
    assert classify('What are the attendance rules?')=='Rules and Regulations'
    assert classify('What color is the moon?')=='Other'


def test_analytics_windows_and_personal_scope(clients):
    a,b=clients;ic=code(a);tc=code(b,'tcs')
    first=register(a,'Infosys',ic,'first@example.com').json()
    second=register(a,'Infosys',ic,'second@example.com','00124').json()
    other=register(b,'TCS',tc,'other@example.com').json()
    now=int(time.time())
    with connection() as db:
        for i,(user,days) in enumerate([(first,0),(first,10),(first,40),(first,400),(second,0),(other,0)]):
            stamp=now-days*86400
            db.execute('INSERT INTO question_events VALUES (?,?,?,?,?,?)',(str(i),user['id'],user['company_id'],'Finance','answered',stamp))
            db.execute('INSERT INTO access_events VALUES (?,?,?,?,?)',(str(i),user['id'],user['company_id'],'knowledge',stamp))
    personal=a.get('/api/reports/me').json()
    assert personal['question_count']==1 and personal['all_time_question_count']==1
    admin(a)
    for period,expected in [('week',2),('month',3),('year',4)]:
        stats=a.get('/api/analytics',params={'period':period}).json()
        assert stats['question_count']==expected and stats['total_access_events']==expected
        assert stats['unique_employees']==2 and stats['categories']['Finance']==expected
        assert sum(item['accesses'] for item in stats['trend'])==expected
