"""Exercise the contextual panel through native upload, draft and send handlers.

Run against an isolated local manufacturer runtime with authenticated storage.
The upload is real; usage and the /api/chat stream are intercepted in-browser,
so this test exercises the native submission path without a provider call.
"""
import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--base-url', default='http://127.0.0.1:8824')
parser.add_argument('--storage-state', type=Path, required=True)
parser.add_argument('--order', required=True, help='Existing local questionnaire order ID')
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
origin = urlsplit(args.base_url)
if origin.hostname not in {'127.0.0.1', 'localhost', '::1'} or origin.scheme != 'http':
    parser.error('Use an isolated local HTTP runtime: this test uploads a source file.')
if origin.path not in {'', '/'} or origin.query or origin.fragment or origin.username:
    parser.error('--base-url must contain only the local origin.')
OUT = args.output
OUT.mkdir(parents=True, exist_ok=True)
checks, errors, sent, uploads = [], [], [], []
def check(name,value):
 checks.append({'name':name,'passed':bool(value)});assert value,name
with sync_playwright() as p:
 b=p.chromium.launch(args=['--no-sandbox','--disable-gpu','--disable-dev-shm-usage']);c=b.new_context(storage_state=str(args.storage_state),viewport={'width':1600,'height':1000})
 def usage(route):
  response=route.fetch();data=response.json();data.setdefault('company',{}).update(available_usd='20',monthly_available_usd='20');route.fulfill(response=response,json=data)
 c.route(re.compile(r'/api/usage(?:\?|$)'),usage)
 def chat(route):
  sent.append(route.request.post_data_json)
  events=[{'type':'delta','text':'Проверка на интерфейса — тестов поток.'},{'type':'done','status':'completed'}]
  route.fulfill(status=200,content_type='application/x-ndjson',body='\n'.join(json.dumps(event,ensure_ascii=False) for event in events)+'\n')
 c.route('**/api/chat',chat)
 page=c.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
 try:
  url=args.base_url.rstrip('/')+'/?'+urlencode({'view':'orders','order':args.order})
  page.goto(url,wait_until='domcontentloaded');page.locator('.mo-order-agent').wait_for();page.locator('.mo-order-agent').click();frame=page.frame_locator('.mf-context-frame');frame.locator('#message').wait_for(state='visible');check('Opening discussion never sends',not sent)
  frame.locator('#message').fill('Прегледай приложения файл за тази поръчка.');
  with page.expect_response(lambda r:'/api/manufacturer/files' in r.url and r.request.method=='POST') as upload:
   frame.locator('#manufacturer-file-input').set_input_files({'name':'sidebar-ui-verification.txt','mimeType':'text/plain','buffer':b'Local UI verification: document upload in the shared organization chat.'})
  response=upload.value;check('Real native upload succeeds',response.status==200);data=response.json();uploads.append({'chat_id':data['chat_id'],'file_id':data['file']['id'],'name':data['file']['name']})
  frame.locator('.mf-file-chip .mf-file-name',has_text='sidebar-ui-verification.txt').wait_for();page.wait_for_timeout(100)
  chat_id=data['chat_id'];check('Upload belongs to same shared chat',chat_id in page.locator('.mf-context-frame').get_attribute('src'))
  page.get_by_role('button',name='Затвори чата',exact=True).last.click();page.locator('.mo-order-agent').click();frame.locator('#message').wait_for(state='visible');check('Upload retained after closing panel',frame.locator('.mf-file-chip .mf-file-name',has_text='sidebar-ui-verification.txt').count()==1)
  page.get_by_role('button',name='Отвори целия чат',exact=True).click();page.wait_for_url('**/?chat='+chat_id);page.locator('#message').wait_for(state='visible');page.wait_for_function("() => document.querySelector('#message').value.includes('Прегледай приложения файл')", timeout=10000);check('Expand keeps exact org chat',page.url.endswith('?chat='+chat_id));check('Expand restores native draft','Прегледай приложения файл' in page.locator('#message').input_value());check('Expand restores uploaded file',page.locator('#manufacturer-file-drafts .mf-file-name',has_text='sidebar-ui-verification.txt').count()==1);check('Primary chat remains full page',not page.locator('.mf-context-frame').is_visible());check('Primary chat sidebar visible',page.locator('#sidebar').is_visible())
  page.goto(url,wait_until='domcontentloaded');page.locator('.mo-order-agent').wait_for();page.locator('.mo-order-agent').click();frame=page.frame_locator('.mf-context-frame');frame.locator('#message').wait_for(state='visible');frame.locator('#message').fill('Провери файла.');frame.locator('#send').click();frame.get_by_text('Проверка на интерфейса — тестов поток.',exact=True).wait_for(timeout=15000)
  check('Native send handler reaches chat API',len(sent)==1);check('Exact shared conversation submission',sent[0]['chat_id']==chat_id);check('Native file envelope included','<manufacturer-files>' in sent[0]['message'] and uploads[0]['file_id'] in sent[0]['message']);check('Native stream is rendered in sidebar',frame.get_by_text('Проверка на интерфейса — тестов поток.',exact=True).is_visible());check('Composer clears admitted draft',frame.locator('#message').input_value()=='');check('Order remains visible after send',page.locator('.mo-needs').is_visible());check('No browser exceptions',not errors)
 finally:
  report={'checks':checks,'errors':errors,'uploads':uploads,'intercepted_chat_requests':len(sent),'provider_calls':0,'test_boundary':'Local runtime only. Real native upload and actual native submit/event handlers. Usage response and chat stream intercepted in test browser; no funded provider request.'};(OUT/'native-path-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));b.close()
