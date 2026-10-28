"""Read-only native original PDF drawer proof, using an explicitly supplied private session."""
from pathlib import Path
import argparse
from playwright.sync_api import sync_playwright
parser=argparse.ArgumentParser();parser.add_argument('--base-url',default='http://127.0.0.1:8824');parser.add_argument('--storage-state',required=True);parser.add_argument('--order',required=True);parser.add_argument('--file',required=True);parser.add_argument('--output',default='/tmp/manufacturer-order-file-qa');args=parser.parse_args();BASE=args.base_url.rstrip('/');OUT=Path(args.output);OUT.mkdir(exist_ok=True)
with sync_playwright() as p:
 b=p.chromium.launch(args=['--no-sandbox','--disable-gpu','--disable-dev-shm-usage']);c=b.new_context(storage_state=args.storage_state,viewport={'width':1600,'height':1000});page=c.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(BASE+'/?view=orders&order='+args.order);file=page.get_by_role('button',name='Преглед на BLD-door-schedule-demo.pdf');file.wait_for();file.click();page.locator('.mof-page').wait_for();page.wait_for_timeout(1200);page.screenshot(path=str(OUT/'desktop.png'))
 assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
 assert page.locator('.mof-page').evaluate('(el)=>el.complete&&el.naturalWidth>500')
 resp=c.request.get(BASE+'/api/manufacturer/orders/'+args.order+'/files/'+args.file);assert resp.status==200 and resp.body().startswith(b'%PDF-')
 page.get_by_role('button',name='Затваряне на прегледа',exact=True).click();assert file.evaluate('(el)=>el===document.activeElement')
 for width in [390,320]:
  page.set_viewport_size({'width':width,'height':844});file.click();page.locator('.mof-page').wait_for();page.wait_for_timeout(600);assert not page.evaluate('document.documentElement.scrollWidth>innerWidth');page.screenshot(path=str(OUT/f'phone-{width}.png'));page.keyboard.press('Escape')
 listing=c.request.get(BASE+'/api/manufacturer/orders/'+args.order+'/files');assert listing.headers.get('cache-control')=='private, no-store'
 assert not errors,errors
 print('PASS original PDF bytes, native drawer, desktop390320, close focus, Escape; zero exceptions')
 b.close()
