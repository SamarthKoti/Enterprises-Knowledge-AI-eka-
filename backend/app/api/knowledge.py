import json
from pathlib import Path
from fastapi.responses import FileResponse
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Response
from pydantic import ValidationError
from app.api.auth import current_user, admin_user, employee_user
from app.core.config import settings
from app.core.database import connection
from app.models.contracts import Answer, Document, Question, UploadMetadata
from app.services import ingestion, answering

router=APIRouter(dependencies=[Depends(current_user)],tags=['Knowledge'])

@router.post('/documents/upload')
def upload(response: Response, files: list[UploadFile]=File(...), metadata: str=Form('{}'), user=Depends(admin_user)):
    """metadata is a JSON object applied to all files or a list aligned with files."""
    try:
        if len(files)>settings.max_upload_files:
            raise HTTPException(413,'Too many files in one request')
        try:
            values=json.loads(metadata)
            values=values if isinstance(values,list) else [values]*len(files)
            if len(values)!=len(files):
                raise ValueError('Metadata count must match files')
            metas=[UploadMetadata.model_validate(v) for v in values]
        except (ValueError,ValidationError,TypeError) as exc:
            raise HTTPException(422,'metadata must be a valid policy object or one object per file') from exc
        results=[]
        for file,meta in zip(files,metas):
            try:
                data=file.file.read(settings.max_file_bytes+1)
                document,duplicate=ingestion.ingest(file.filename or 'unnamed',data,meta,user['company_id'])
                results.append({'document':document.model_dump(mode='json'),'duplicate':duplicate,'error':None})
            except HTTPException as exc:
                results.append({'document':None,'duplicate':False,'error':{'status':exc.status_code,'detail':exc.detail}})
        errors=[r['error'] for r in results if r['error']]
        response.status_code=(errors[0]['status'] if len(results)==1 else 207) if errors else (200 if all(r['duplicate'] for r in results) else 201)
        return {'results':results}
    finally:
        for file in files:
            file.file.close()

@router.get('/documents',response_model=list[Document])
def documents(user=Depends(admin_user)):
    with connection() as db:
        return [ingestion.document_model(r) for r in db.execute('SELECT * FROM documents WHERE company_id=? ORDER BY filename,id',(user['company_id'],))]

@router.get('/documents/{document_id}',response_model=Document)
def document(document_id: str,user=Depends(admin_user)):
    return ingestion.get_document(document_id,user['company_id'])

@router.post('/ask',response_model=Answer)
@router.post('/answers',response_model=Answer,include_in_schema=False)
def ask(question: Question,user=Depends(employee_user)):
    from app.services.activity import answer_question
    return answer_question(question,user)

@router.get('/sources/{chunk_id}')
def source(chunk_id: str,user=Depends(current_user)):
    with connection() as db:
        row=db.execute('SELECT p.*,d.filename,d.version FROM passages p JOIN documents d ON d.id=p.document_id WHERE p.id=? AND d.company_id=?',(chunk_id,user['company_id'])).fetchone()
    if not row: raise HTTPException(404,'Source not found')
    return dict(row)

@router.patch('/documents/{document_id}',response_model=Document)
def update_document(document_id: str,metadata: UploadMetadata,user=Depends(admin_user)):
    with ingestion.INGEST_LOCK:
        with connection() as db:
            row=db.execute('SELECT * FROM documents WHERE id=? AND company_id=?',(document_id,user['company_id'])).fetchone()
            if not row: raise HTTPException(404,'Document not found')
            if metadata.superseded_by:
                target=db.execute('SELECT * FROM documents WHERE id=? AND company_id=?',(metadata.superseded_by,user['company_id'])).fetchone()
                if not target or target['id']==document_id or target['policy_family']!=metadata.policy_family:
                    raise HTTPException(422,'Replacement must be another company document in the same policy family')
            if metadata.status=='current' and not metadata.policy_family: raise HTTPException(422,'Current documents require a policy family')
            values=metadata.model_dump(mode='json')
            db.execute('UPDATE documents SET policy_family=?,version=?,effective_date=?,status=?,superseded_by=? WHERE id=? AND company_id=?',(*values.values(),document_id,user['company_id']))
    return ingestion.get_document(document_id,user['company_id'])

@router.get('/documents/{document_id}/download')
def download_document(document_id: str,user=Depends(admin_user)):
    document=ingestion.get_document(document_id,user['company_id'])
    folder=(Path(settings.data_dir)/'uploads').resolve()
    path=(folder/(document.id+'.'+document.format)).resolve()
    if path.parent!=folder or not path.is_file(): raise HTTPException(404,'Original source not available')
    return FileResponse(path,filename=document.filename,media_type='application/octet-stream')
