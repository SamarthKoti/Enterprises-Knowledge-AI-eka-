import secrets
import hmac
import time
from datetime import datetime, timedelta, timezone
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from app.api.auth import admin_user, employee_user, code_record
from app.core.database import connection
from app.services.activity import CATEGORIES

router=APIRouter(tags=['Company'])

def display_code(record):
    if not record:
        return None
    # Existing installations store keyed digests of four-digit invite codes.
    # Resolve that bounded domain only for the authenticated company admin;
    # retain the original code and hashed storage without rotating invitations.
    for number in range(10000):
        code=f'{number:04d}'
        if hmac.compare_digest(code_record(code),record):
            return code
    raise HTTPException(503,'The existing company code cannot be displayed with the configured code secret.')

@router.get('/company')
def company(user=Depends(admin_user)):
    with connection() as db:
        row=db.execute('SELECT name,verification_code_record,verification_code_generated_at FROM companies WHERE id=?',(user['company_id'],)).fetchone()
    return {'company_id':user['company_id'],'name':row['name'],'code_generated':row['verification_code_generated_at'] is not None,'generated_at':row['verification_code_generated_at'],'code':display_code(row['verification_code_record'])}

@router.post('/company/code',status_code=201)
def generate_code(user=Depends(admin_user)):
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT verification_code_record FROM companies WHERE id=?',(user['company_id'],)).fetchone()
        if row['verification_code_record']: raise HTTPException(409,'Company verification code already generated.')
        for _ in range(100):
            code=f'{secrets.randbelow(10000):04d}'; record=code_record(code)
            if not db.execute('SELECT 1 FROM companies WHERE verification_code_record=?',(record,)).fetchone(): break
        else: raise HTTPException(503,'Unable to allocate a unique company code')
        db.execute('UPDATE companies SET verification_code_record=?,verification_code_generated_at=? WHERE id=? AND verification_code_record IS NULL',(record,int(time.time()),user['company_id']))
    return {'code':code,'message':'Your company code is available on the admin dashboard. Share it only with your employees.'}

@router.get('/employees')
def employees(user=Depends(admin_user)):
    with connection() as db:
        return [dict(row) for row in db.execute('''SELECT u.id,u.name,u.email,u.employee_id,u.created_at,u.last_login_at,c.name AS company,
            (SELECT MAX(a.created_at) FROM access_events a WHERE a.user_id=u.id AND a.company_id=u.company_id AND a.event_type='knowledge') AS last_knowledge_access
            FROM users u JOIN companies c ON c.id=u.company_id WHERE u.company_id=? AND u.role='employee' ORDER BY u.created_at DESC''',(user['company_id'],))]

def statistics(user,period,personal=False):
    now=datetime.now(timezone.utc); days={'week':7,'month':30,'year':365}[period]
    start=(now-timedelta(days=days-1)).replace(hour=0,minute=0,second=0,microsecond=0)
    start_ts=int(start.timestamp()); end_ts=int(now.timestamp())
    scope='company_id=?'+(' AND user_id=?' if personal else '')
    args=[user['company_id']]+([user['id']] if personal else [])
    with connection() as db:
        events=[dict(r) for r in db.execute(f'SELECT * FROM access_events WHERE {scope} AND created_at BETWEEN ? AND ? ORDER BY created_at',(*args,start_ts,end_ts))]
        questions=[dict(r) for r in db.execute(f'SELECT * FROM question_events WHERE {scope} AND created_at BETWEEN ? AND ?',(*args,start_ts,end_ts))]
        total_questions=db.execute(f'SELECT COUNT(*) FROM question_events WHERE {scope}',args).fetchone()[0]
        employee_count=db.execute("SELECT COUNT(*) FROM users WHERE company_id=? AND role='employee'",(user['company_id'],)).fetchone()[0] if not personal else None
        docs={r['processing_status']:r['n'] for r in db.execute('SELECT processing_status,COUNT(*) n FROM documents WHERE company_id=? GROUP BY processing_status',(user['company_id'],))}
    access=[e for e in events if e['event_type']=='knowledge']; logins=[e for e in events if e['event_type']=='login']
    categories={category:sum(q['category']==category for q in questions) for category in CATEGORIES}
    statuses={s:sum(q['answer_status']==s for q in questions) for s in ('answered','partially_answered','not_covered','pending','error')}
    bucket=lambda dt:dt.strftime('%Y-%m') if period=='year' else dt.strftime('%Y-%m-%d')
    trend={bucket(start+timedelta(days=i)):{'accesses':0,'logins':0} for i in range(days)}
    for e in events:
        key=bucket(datetime.fromtimestamp(e['created_at'],timezone.utc))
        if key in trend: trend[key]['accesses' if e['event_type']=='knowledge' else 'logins']+=1
    return {'company':user['company_name'],'period':period,'period_days':days,'timezone':'UTC','total_employees':employee_count,
        'total_access_events':len(access),'unique_employees':len({e['user_id'] for e in access}),'successful_logins':len(logins),
        'question_count':len(questions),'all_time_question_count':total_questions,'categories':categories,'answer_statuses':statuses,
        'top_category':max(categories,key=categories.get) if questions else None,
        'trend':[{'date':key,**value} for key,value in trend.items()],
        'knowledge_ready':docs.get('ready',0)>0,'documents':docs if not personal else None,
        'category_method':'Conservative keyword classification; ambiguous questions use Other.'}

@router.get('/analytics')
def analytics(period: Literal['week','month','year']='week',user=Depends(admin_user)):
    return statistics(user,period)

@router.get('/reports/me')
def personal_reports(period: Literal['week','month','year']='week',user=Depends(employee_user)):
    return statistics(user,period,True)
