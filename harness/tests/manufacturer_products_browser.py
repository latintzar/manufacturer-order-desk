"""Native Products proof. Supply a private local browser state; --edit exercises price/history/restore in a local unpublished fixture."""
from pathlib import Path
import argparse
import json
import re
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright
parser=argparse.ArgumentParser()
parser.add_argument('--base-url',default='http://127.0.0.1:8824')
parser.add_argument('--storage-state',type=Path,required=True)
parser.add_argument('--output',type=Path,default=Path('/tmp/manufacturer-products-proof'))
parser.add_argument('--edit',action='store_true')
args=parser.parse_args()
out=args.output;out.mkdir(exist_ok=True)
mutate=args.edit
if mutate and urlsplit(args.base_url).hostname not in {'127.0.0.1','localhost'}:
 raise ValueError('Price-edit proofs require an isolated local fixture.')
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True)
 context=browser.new_context(storage_state=str(args.storage_state),viewport={'width':1600,'height':1000},device_scale_factor=1)
 page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 base=args.base_url.rstrip('/');api=base+'/api/manufacturer/configurator'
 baseline=context.request.get(api).json()
 if mutate: assert baseline['state']=='draft','This proof edits an isolated unpublished local workspace only.'
 def row(document,code):return next(item for cat in document['catalogue']['cats'] for item in cat['items'] if item['c']==code)
 def save():
  with page.expect_response(lambda response: response.url==api and response.request.method=='POST') as event:
   page.get_by_role('button',name='Запазване на цената',exact=True).click()
  page.wait_for_timeout(200);return event.value
 try:
  page.goto(base+'/?view=products');page.wait_for_selector('.mp-row[data-article]');page.wait_for_timeout(400)
  assert page.locator('.mp-row[data-article]').count()==50
  assert int(re.sub(r'\D', '', page.locator('.mp-count').inner_text())) == 1558
  page.get_by_role('button',name='Следващи продукти',exact=True).click();assert page.locator('.mp-pagination > span').inner_text().startswith('51')
  page.get_by_role('button',name='Предишни продукти',exact=True).click()
  page.get_by_label('Продуктова група',exact=True).select_option('rosettes');assert page.locator('.mp-row[data-article]').count()>0
  page.get_by_label('Продуктова група',exact=True).select_option('')
  for width in (1600,390,320):
   page.set_viewport_size({'width':width,'height':1000 if width==1600 else 844});page.locator('#workspace-tab-view').evaluate('(el)=>el.scrollTop=0');page.wait_for_timeout(150)
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
   page.screenshot(path=str(out/f'list-{width}.png'))
  page.get_by_label('Търсене на продукти',exact=True).fill('101081');assert page.locator('.mp-row[data-article]').count()==1
  page.locator('.mp-row[data-article]').click();page.wait_for_timeout(300)
  for width in (1600,390,320):
   page.set_viewport_size({'width':width,'height':1000 if width==1600 else 844});page.wait_for_timeout(150)
   assert page.locator('.mp-product-dialog').evaluate('(el)=>el.scrollWidth<=el.clientWidth')
   page.screenshot(path=str(out/f'detail-{width}.png'))
  if mutate:
   price=page.locator('.mp-price-form input')
   for value,expected_q in [('12.5',0),('0',0),('',1)]:
    price.fill(value);response=save();assert response.status==200,response.text()
    saved=response.json();item=row(saved['document'],'101081');assert item['p']==(float(value) if value else 0) and item['q']==expected_q
   history=context.request.get(api+'/versions').json()['versions'];assert any('101081' in (v.get('name') or v.get('label') or '') for v in history),history[0]
   price.fill('17')
   current=context.request.get(api).json()
   parallel=context.request.post(api,headers={'X-Rocoto-Page':'1'},data={'settings':{'accent':'#445566'},'expected_revision':current['revision']});assert parallel.status==200,parallel.text()
   response=save();assert response.status==409,response.text()
   assert price.input_value()=='17'
   page.get_by_role('button',name='Зареждане на актуалната версия',exact=True).click();page.wait_for_timeout(500)
   assert price.input_value()=='17'
   response=save();assert response.status==200,response.text()
   assert row(response.json()['document'],'101081')['p']==17
  page.get_by_role('button',name='Затваряне на продукта',exact=True).click()
  page.go_back();page.wait_for_timeout(150);assert page.locator('.mp-product-dialog').is_visible()
  page.go_forward();page.wait_for_timeout(150);assert page.locator('.mp-product-dialog').is_hidden()
  page.get_by_role('link',name='История на версиите',exact=True).click();page.wait_for_timeout(700)
  assert 'view=configurator' in page.url and page.locator('.mf-version-history').is_visible()
  assert not errors,errors
  print(json.dumps({'widths':[1600,390,320],'articles':1558,'browser_errors':errors,'local_price_writes':mutate,'history':True}))
 finally:
  if mutate:
   current=context.request.get(api).json()
   restored=context.request.post(api+'/restore',headers={'X-Rocoto-Page':'1'},data={'version_id':baseline['version_id'],'expected_revision':current['revision']})
   assert restored.status==200,restored.text()
   assert restored.json()['document']==baseline['document'],'Restored complete catalogue/configuration snapshot differs'
   print('Complete local baseline document restored exactly.')
  browser.close()
