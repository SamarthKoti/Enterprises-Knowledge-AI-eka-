import csv
import io
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from app.api.auth import employee_user
from app.models.contracts import BatchRequest, Question
from app.services.activity import answer_question

router=APIRouter(tags=['Batch'])

def process(questions,user):
    results=[]
    for question in questions:
        try:
            answer=answer_question(question,user)
            results.append({'question':question.question,'answer':answer.model_dump(mode='json'),'error':None})
        except HTTPException as exc:
            results.append({'question':question.question,'answer':None,'error':str(exc.detail)})
    return {'results':results}

@router.post('/batches')
def batch(request: BatchRequest,user=Depends(employee_user)):
    return process(request.questions,user)

@router.post('/batches/upload')
def batch_upload(file: UploadFile=File(...),user=Depends(employee_user)):
    try:
        if not (file.filename or '').lower().endswith('.csv'): raise HTTPException(415,'Upload a CSV with a question column')
        data=file.file.read(1024*1024+1)
        if len(data)>1024*1024: raise HTTPException(413,'Question CSV must be under 1 MiB')
        try:
            reader=csv.DictReader(io.StringIO(data.decode('utf-8-sig')))
            if not reader.fieldnames or 'question' not in reader.fieldnames: raise ValueError('Missing question column')
            rows=[]
            for row in reader:
                if len(rows)>=100: raise ValueError('Limit 100 questions per batch')
                rows.append(Question(question=row.get('question') or ''))
            if not rows: raise ValueError('CSV contains no questions')
        except (ValueError,UnicodeError,csv.Error) as exc: raise HTTPException(422,str(exc)) from exc
        return process(rows,user)
    finally: file.file.close()
