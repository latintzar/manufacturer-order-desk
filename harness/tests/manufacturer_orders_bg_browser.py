"""Bulgarian native order presentation; browser intercepts keep source state unchanged."""
from pathlib import Path
from playwright.sync_api import sync_playwright
import copy
import json
import sys
out=Path('/tmp/manufacturer-bg-orders-qa');out.mkdir(exist_ok=True)
base_url=sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8824'
storage=sys.argv[2] if len(sys.argv)>2 else '/tmp/manufacturer-crm-browser.json'
with sync_playwright() as p:
 b=p.chromium.launch(headless=True,args=['--no-sandbox','--disable-gpu','--disable-dev-shm-usage'])
 c=b.new_context(storage_state=storage,viewport={'width':1600,'height':1100})
 page=c.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(base_url+'/?view=orders',wait_until='domcontentloaded',timeout=25000)
 page.locator('a.mf-order-row').first.wait_for(timeout=15000)
 rows=page.locator('a.mf-order-row');print('rows',rows.count(),flush=True)
 assert page.locator('.mf-orders-page h1').inner_text()=='Поръчки'
 page.screenshot(path=str(out/'orders-1600.png'))
 row=rows.filter(has_text='96').first
 order_id=row.get_attribute('data-order-id')
 row.click();page.locator('.mo-items').first.wait_for()
 page.locator('.mo-needs-known-loading').wait_for(state='detached')
 assert page.locator('.mo-detail-main > section').first.get_attribute('class').find('mo-items')>=0
 assert page.locator('.mo-detail-main .mo-delivery').count()==1
 assert page.locator('.mo-detail-side .mo-delivery').count()==0
 assert page.locator('.mo-customer a.mo-company-name').inner_text()=='BLD'
 assert page.locator('.mo-customer details').count()==0
 assert 'Customer needs' not in page.locator('.mf-orders-page').inner_text()
 assert page.locator('.mo-product-copy').first.inner_text().find('Норма')>=0
 assert 'Обков за 96' in page.locator('.mo-needs-summary').inner_text()
 page.wait_for_function("() => [...document.querySelectorAll('.mo-product-image img')].every(i=>i.complete&&i.naturalWidth>0)",timeout=20000)
 page.screenshot(path=str(out/'order-1600.png'))
 for width in [390,320]:
  page.set_viewport_size({'width':width,'height':844});page.wait_for_timeout(200)
  page.evaluate("document.getElementById('workspace-tab-view').scrollTop=0")
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),f'Page overflow {width}'
  assert page.evaluate("document.querySelector('.mf-orders-page').scrollWidth<=document.querySelector('.mf-orders-page').clientWidth"),f'Order overflow {width}'
  page.screenshot(path=str(out/f'order-{width}.png'))
  page.locator('.mo-needs').screenshot(path=str(out/f'project-{width}.png'))
 # Exercise commercial states through read-only intercepted responses.
 saved=page.request.get(base_url+'/api/manufacturer/orders/'+order_id).json()
 payload=copy.deepcopy(saved)
 def respond(route):route.fulfill(json=payload)
 page.route('**/api/manufacturer/orders/'+order_id,respond)
 for line in payload['order']['lines']:line.update(pricing_state='priced',unit_price=0,total=0)
 payload['order'].update(pricing_state='priced',total=0,priced_total=0)
 page.reload(wait_until='domcontentloaded');page.locator('.mo-items[data-pricing=priced]').wait_for()
 assert page.locator('.mo-items[data-pricing=to_quote]').count()==0
 assert '0,00' in page.locator('.mo-totals').inner_text()
 assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
 payload['order']['lines'][1].update(pricing_state='to_quote',unit_price=None,total=None)
 payload['order'].update(pricing_state='partially_priced',total=None)
 payload['order']['enrichment']={'status':'needs_review','summary':'Internal search process and long review notes','facts':[],'sources':[]}
 page.reload(wait_until='domcontentloaded');page.locator('.mo-items[data-pricing=to_quote]').wait_for()
 assert page.locator('.mo-items[data-pricing=priced]').count()==1
 assert '0,00' in page.locator('.mo-totals').inner_text()
 assert 'Internal search process' not in page.locator('.mo-customer').inner_text()
 assert 'име на фирмата и уебсайт' in page.locator('.mo-customer').inner_text()
 page.unroute('**/api/manufacturer/orders/'+order_id)
 page.set_viewport_size({'width':1600,'height':1100});page.get_by_role('button',name='Попитай агента',exact=True).click()
 page.wait_for_timeout(500)
 assert not errors,errors
 print(json.dumps({'passed':True,'screens':str(out),'errors':errors}),flush=True)
 b.close()
