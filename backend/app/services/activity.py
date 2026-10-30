import re
import time
import uuid
from app.core.database import connection
from app.services import answering

CATEGORIES=('Finance','Health Insurance','Rules and Regulations','Other')

def classify(question):
    text=question.casefold()
    patterns={
        'Health Insurance':r'\b(health insurance|medical insurance|insurance|coverage|claim|hospital|premium|beneficiar\w*)\b',
        'Finance':r'\b(salary|payroll|tax|reimburse\w*|expense|finance|budget|bonus|allowance|payment|pension)\b',
        'Rules and Regulations':r'\b(rule\w*|regulation\w*|policy|policies|leave|conduct|compliance|working hours|attendance|dress code|disciplin\w*)\b',
    }
    matches=[category for category,pattern in patterns.items() if re.search(pattern,text)]
    return matches[0] if len(matches)==1 else 'Other'

def answer_question(question,user):
    now=int(time.time()); event_id=str(uuid.uuid4())
    with connection() as db:
        db.execute('INSERT INTO access_events VALUES (?,?,?,?,?)',(event_id,user['id'],user['company_id'],'knowledge',now))
        db.execute('INSERT INTO question_events VALUES (?,?,?,?,?,?)',(event_id,user['id'],user['company_id'],classify(question.question),'pending',now))
    try:
        answer=answering.ask(question,user['company_id'])
    except Exception:
        with connection() as db: db.execute("UPDATE question_events SET answer_status='error' WHERE id=?",(event_id,))
        raise
    with connection() as db: db.execute('UPDATE question_events SET answer_status=? WHERE id=?',(answer.status,event_id))
    return answer
