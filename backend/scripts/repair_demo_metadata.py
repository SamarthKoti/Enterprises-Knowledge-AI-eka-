import json, sqlite3
from pathlib import Path
from datetime import date
# One-time maintenance: only explicit document-control fields, never filenames.
assert not Path('../verification/rag-quality/metadata-repair.json').exists(), 'Repair already audited; do not overwrite its rollback record'
db=sqlite3.connect('knowledge.sqlite3');db.row_factory=sqlite3.Row
fields=['policy_family','version','effective_date','status','superseded_by']
changes=[]; controls={}
for d in db.execute("SELECT * FROM documents WHERE company_id='infosys'").fetchall():
 for p in db.execute('SELECT id,text FROM passages WHERE document_id=?',(d['id'],)):
  lines=[s.strip() for s in p['text'].splitlines()]
  if 'Policy family:' not in lines or 'Policy ID:' not in lines: continue
  def value(label):
   i=lines.index(label);return lines[i-1]
  family=value('Policy family:');version=value('Version:');effective=value('Effective date:');status=value('Status:')
  date.fromisoformat(effective)
  assert status in ('CURRENT','SUPERSEDED - HISTORICAL ONLY')
  assert version.isdigit() and len(version)==4
  controls[d['id']]={'policy_id':value('Policy ID:'),'replacement':value('Superseded by:') if 'Superseded by:' in lines else None,'source':p['id'],'after':{'policy_family':family,'version':version,'effective_date':effective,'status':'current' if status=='CURRENT' else 'superseded','superseded_by':None},'before':{k:d[k] for k in fields}}
for doc_id,c in controls.items():
 if c['replacement']:
  targets=[i for i,v in controls.items() if v['policy_id']==c['replacement'] and v['after']['policy_family']==c['after']['policy_family']]
  assert len(targets)==1
  c['after']['superseded_by']=targets[0]
 changes.append({'document_id':doc_id,**c})
Path('../verification/rag-quality/metadata-repair.json').write_text(json.dumps(changes,indent=2))
# Audit manifest is written before this atomic, tenant-scoped correction.
with db:
 for c in changes:
  db.execute('UPDATE documents SET policy_family=?,version=?,effective_date=?,status=?,superseded_by=? WHERE id=? AND company_id=?',(*[c['after'][k] for k in fields],c['document_id'],'infosys'))
print('Corrected explicit document-control metadata for',len(changes),'Infosys documents. Audit manifest saved; source passages and tenant ownership unchanged.')
