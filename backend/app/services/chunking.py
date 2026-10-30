import re
from app.core.config import settings
from app.models.contracts import Chunk

TOKEN = re.compile(r'\w+|[^\w\s]', re.UNICODE)

def windows(text, size, overlap):
    spans = list(TOKEN.finditer(text))
    for start in range(0,len(spans),size-overlap):
        end = min(start+size,len(spans))
        yield text[spans[start].start():spans[end-1].end()]
        if end == len(spans):
            break

def chunk(blocks, document):
    size, overlap = settings.chunk_tokens, settings.chunk_overlap
    if not 0<=overlap<size:
        raise ValueError('chunk_overlap must be smaller than chunk_tokens')
    parts = []
    # Merge nearby paragraphs only within the same real section and page.
    grouped = []
    for block in blocks:
        if grouped and not block.is_table and not grouped[-1].is_table and (block.section,block.page)==(grouped[-1].section,grouped[-1].page):
            grouped[-1].text += '\n\n'+block.text
        else:
            from dataclasses import replace
            grouped.append(replace(block))
    for block in grouped:
        if block.is_table:
            rows = block.text.splitlines()
            header = rows[0]
            if len(TOKEN.findall(header))>=size//2:
                raise ValueError('Table header too large to preserve safely')
            batch = [header]
            for row in rows[1:]:
                if len(TOKEN.findall(header+'\n'+row))>size:
                    raise ValueError('Table row exceeds chunk limit; split source table')
                if len(TOKEN.findall('\n'.join(batch+[row])))>size:
                    parts.append((block,'\n'.join(batch)))
                    batch=[header]
                batch.append(row)
            if batch:
                parts.append((block,'\n'.join(batch)))
        else:
            parts.extend((block,text) for text in windows(block.text,size,overlap))
    return [Chunk(chunk_id=f"{document['id']}:{i}",document_id=document['id'],document_name=document['filename'],policy_family=document['policy_family'],version=document['version'],version_status=document['status'],section=b.section,page=b.page,text=t,is_table=b.is_table) for i,(b,t) in enumerate(parts)]
