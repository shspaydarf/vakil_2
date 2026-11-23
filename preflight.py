"""Local preflight checks for LegalBot Core V2.
Run: python preflight.py
This does not contact Telegram or any external AI service.
"""
import ast
import json
import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
errors=[]

for p in ROOT.rglob('*.py'):
    if any(part in {'.pytest_cache','__pycache__'} for part in p.parts):
        continue
    try:
        ast.parse(p.read_text(encoding='utf8'), filename=str(p))
        py_compile.compile(str(p), doraise=True)
    except Exception as e:
        errors.append(f'PYTHON {p}: {type(e).__name__}: {e}')

for p in (ROOT/'legal_bot'/'data').rglob('*.json'):
    try:
        json.loads(p.read_text(encoding='utf8'))
    except Exception as e:
        errors.append(f'JSON {p}: {type(e).__name__}: {e}')

required = [
    ROOT/'legal_bot'/'main.py', ROOT/'legal_bot'/'handlers.py',
    ROOT/'legal_bot'/'db.py', ROOT/'legal_bot'/'document_facts.py', ROOT/'legal_bot'/'laws.py',
    ROOT/'legal_bot'/'glossary.py', ROOT/'legal_bot'/'knowledge.py',
    ROOT/'legal_bot'/'data'/'iran'/'laws.json',
    ROOT/'legal_bot'/'data'/'iran'/'legal_glossary.json',
    ROOT/'legal_bot'/'data'/'iran'/'official_sources.json',
    ROOT/'legal_bot'/'ocr_lexicon.json',
    ROOT/'persian_case_search.py',
]
for p in required:
    if not p.exists(): errors.append(f'MISSING {p}')

main=(ROOT/'legal_bot'/'main.py').read_text(encoding='utf8')
handlers=(ROOT/'legal_bot'/'handlers.py').read_text(encoding='utf8')
for name in ['start','contact','text','document','photo','case_text_cb','new_case_cb','law_cb','glossary_cb','unhandled_callback']:
    if not (f'def {name}(' in handlers or f'async def {name}(' in handlers):
        errors.append(f'HANDLER MISSING {name}')
if 'CallbackQueryHandler(unhandled_callback)' not in main:
    errors.append('CALLBACK FALLBACK MISSING')

if errors:
    print('PREFLIGHT: FAIL')
    print('\n'.join(errors))
    raise SystemExit(1)
print('PREFLIGHT: PASS')
print('Python syntax: PASS')
print('JSON parse: PASS')
print('Core files/data: PASS')
print('Callback fallback: PASS')
