#!/usr/bin/env python3
"""Check the owned local first result with Playwright, without calling external services."""
from pathlib import Path
from urllib.parse import urlsplit
import argparse,json

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--browser-executable',help='Optional installed Chromium executable');p.add_argument('--workspace',default='http://127.0.0.1:18580');p.add_argument('--orders',default='http://127.0.0.1:18581');p.add_argument('--code-file',type=Path);p.add_argument('--guest',action='store_true');p.add_argument('--output',type=Path,default=Path('.local/browser-proof'));a=p.parse_args()
 if not a.guest and a.code_file is None:p.error('Supply the owned local code file, or select native guest mode.')
 a.workspace=a.workspace.rstrip('/');a.orders=a.orders.rstrip('/')
 for origin in [a.workspace,a.orders]:
  if urlsplit(origin).hostname not in {'localhost','127.0.0.1','::1'}:p.error('Use this check with the owned loopback first result.')
 from playwright.sync_api import sync_playwright
 a.output.mkdir(parents=True,exist_ok=True);errors=[];console_errors=[];bad=[];external=[];views=[]
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path=a.browser_executable,args=['--no-sandbox'] if a.browser_executable else []);ctx=browser.new_context()
  if a.guest:
   r=ctx.request.get(a.workspace+'/api/session');assert r.status==200 and r.json().get('role')=='browse','Start the actual native guest mode.'
   before=ctx.request.get(a.workspace+'/api/manufacturer/orders').json()['orders']
   for path in ['/api/manufacturer/orders','/api/manufacturer/configurator','/api/observer','/api/session','/api/chat','/orders/sample-hardware/rocoto/api/orders']:
    denied=ctx.request.post(a.workspace+path,data={},headers={'X-Rocoto-Page':'1'})
    assert denied.status==403,'The native visitor must retain read-only authority.'
   quote=ctx.request.post(a.orders+'/sample-hardware/rocoto/api/quote',data={'lines':[{'code':'SH-LV-01','rows':[{'x':0,'n':2}]}]})
   assert quote.status==200 and quote.json().get('ok') is True,'The original local quote handler must remain available.'
   assert ctx.request.get(a.workspace+'/api/manufacturer/orders').json()['orders']==before,'The read-only workflow preserves saved orders.'
  else:
   code=a.code_file.read_text().strip();r=ctx.request.post(a.workspace+'/api/session',data={'code':code},headers={'X-Rocoto-Page':'1'});del code
   assert r.status==200,'Use an unused local one-use sign-in code.'
  def route(r):
   u=urlsplit(r.request.url)
   if u.scheme in {'data','blob'} or u.hostname in {'localhost','127.0.0.1','::1'}:return r.continue_()
   external.append(u.hostname);r.abort()
  ctx.route('**/*',route);page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.on('console',lambda m:console_errors.append(m.text) if m.type=='error' else None);page.on('response',lambda r:bad.append({'path':urlsplit(r.url).path,'status':r.status}) if r.status>=400 else None)
  for width in [1600,390,320]:
   page.set_viewport_size({'width':width,'height':1000 if width==1600 else 844})
   for view in (['orders','customers','products','service','configurator'] if a.guest else ['orders','customers','products','configurator']):
    page.goto(a.workspace+'/?'+('' if a.guest else 'operator=1&')+'view='+view,wait_until='networkidle');page.screenshot(path=str(a.output/f'{view}-{width}.png'))
    metric=page.evaluate('''() => ({overflow:document.documentElement.scrollWidth>innerWidth,brokenImages:[...document.images].filter(i=>i.complete&&!i.naturalWidth).map(i=>new URL(i.src).pathname)})''');metric.update(view=view,width=width);views.append(metric)
  page.goto(a.orders+'/sample-hardware/#order',wait_until='networkidle');page.screenshot(path=str(a.output/'public.png'));browser.close()
 report={'views':views,'page_errors':errors,'console_errors':console_errors,'failed_requests':bad,'external_requests':external};(a.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 assert not(errors or console_errors or bad or external or any(v['overflow'] or v['brokenImages'] for v in views)),'Inspect the local browser report.'
 print('Passed native desktop/mobile views and the public configurator. Report: '+str(a.output/'report.json'))
if __name__=='__main__':main()
