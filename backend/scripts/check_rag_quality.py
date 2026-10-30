import json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi import HTTPException
from app.services import answering,retrieval
from app.models.contracts import Question
from app.core.database import connection
queries=['How many medical leaves are allowed in 2026?','medical leaves','What was the medical leave allowance in 2024?','Compare the 2024 and 2026 medical leave policies.',"What are the company's workplace rules?",'Does the company provide unlimited international vacations?']
results=[]
for company in ['infosys','tcs']:
 for text in queries:
  start=time.monotonic();query=Question(question=text)
  evidence,diagnostics=retrieval.retrieve(query,company)
  row={'company':company,'question':text,'retrieved':[{'id':c.chunk_id,'document':c.document_name,'version':c.version,'text':c.text} for c in evidence],'diagnostics':diagnostics}
  try:
   answer=answering.ask(query,company);row['response']=answer.model_dump()
   allowed={c.chunk_id:c for c in evidence}
   with connection() as db:
    row['citation_integrity']=all(c.chunk_id in allowed and db.execute('SELECT 1 FROM passages p JOIN documents d ON d.id=p.document_id WHERE p.id=? AND d.company_id=?',(c.chunk_id,company)).fetchone() for c in answer.citations)
  except HTTPException as e: row['error']={'status':e.status_code,'detail':e.detail}
  row['seconds']=round(time.monotonic()-start,2);results.append(row)
  Path('../verification/rag-quality/live-results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
  print(json.dumps({k:v for k,v in row.items() if k not in ('retrieved','diagnostics')},ensure_ascii=True),flush=True)
