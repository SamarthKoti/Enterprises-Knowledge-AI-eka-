import re
import threading
from dataclasses import dataclass
from statistics import median
from app.core.config import settings

PDF_LOCK = threading.Lock()

@dataclass
class Block:
    text: str
    section: str | None = None
    page: int | None = None
    is_table: bool = False

def text_blocks(text, page=None, initial_section=None):
    section, lines, blocks = initial_section, [], []
    def flush():
        if lines:
            blocks.append(Block('\n'.join(lines).strip(), section, page, '|' in lines[0] and len(lines)>1))
            lines.clear()
    for line in text.splitlines():
        heading = re.match(r'^#{1,6}\s+(.+?)\s*#*$', line.strip())
        plain = line.strip()
        if heading or (plain and len(plain)<100 and plain.isupper() and not '|' in plain):
            flush()
            section = heading.group(1) if heading else plain
        elif not plain:
            flush()
        else:
            lines.append(line)
    flush()
    return blocks

def parse(data: bytes, extension: str):
    if extension != 'pdf':
        try:
            text = data.decode('utf-8-sig')
        except UnicodeDecodeError as exc:
            raise ValueError('Text files must be UTF-8 encoded') from exc
        if '\x00' in text:
            raise ValueError('Binary data is not a valid text document')
        blocks, warnings = text_blocks(text), []
    else:
        import pymupdf
        blocks, warnings = [], []
        with PDF_LOCK:
            try:
                with pymupdf.open(stream=data, filetype='pdf') as doc:
                    if doc.needs_pass:
                        raise ValueError('Encrypted PDFs are not supported')
                    if len(doc)>settings.max_pdf_pages:
                        raise ValueError('PDF exceeds page limit')
                    section = None
                    char_count = 0
                    for number, page in enumerate(doc, 1):
                        content = page.get_text('dict', sort=True)['blocks']
                        sizes = [s['size'] for b in content if 'lines' in b for l in b['lines'] for s in l['spans'] if s['text'].strip()]
                        body_size = median(sizes) if sizes else 12
                        tables = []
                        try:
                            for table in page.find_tables().tables:
                                rows = table.extract()
                                rendered = '\n'.join('| ' + ' | '.join((c or '').replace('\n',' / ').replace('|','\|') for c in row) + ' |' for row in rows)
                                tables.append((pymupdf.Rect(table.bbox), rendered))
                        except Exception:
                            warnings.append(f'Page {number}: table detection failed; inspect extracted text')
                        items = [(rect.y0, 'table', value, None) for rect,value in tables]
                        for b in content:
                            if 'lines' not in b:
                                continue
                            for line in b['lines']:
                                rect = pymupdf.Rect(line['bbox'])
                                if any(t.contains((rect.tl+rect.br)/2) for t,_ in tables):
                                    continue
                                text = ''.join(s['text'] for s in line['spans']).strip()
                                if not text:
                                    continue
                                heading = len(text)<120 and any(s['size']>body_size*1.18 for s in line['spans'])
                                items.append((rect.y0, 'heading' if heading else 'text', text, None))
                        page_text = []
                        def flush():
                            if page_text:
                                blocks.append(Block('\n'.join(page_text),section,number))
                                page_text.clear()
                        for _,kind,text,_ in sorted(items,key=lambda item:item[0]):
                            if kind=='heading':
                                flush(); section=text
                            elif kind=='table':
                                flush(); blocks.append(Block(text,section,number,True))
                            else:
                                page_text.append(text)
                        flush()
                        if not items:
                            warnings.append(f'Page {number}: no extractable text (OCR is not implemented)')
                        char_count += sum(len(x[2]) for x in items)
                        if char_count>settings.max_extracted_chars:
                            raise ValueError('Extracted content exceeds limit')
            except ValueError:
                raise
            except Exception as exc:
                raise ValueError('PDF parsing failed: invalid or damaged PDF') from exc
    if not blocks:
        raise ValueError('No extractable text; scanned PDFs require OCR')
    if sum(len(b.text) for b in blocks)>settings.max_extracted_chars:
        raise ValueError('Extracted content exceeds limit')
    return blocks, warnings
