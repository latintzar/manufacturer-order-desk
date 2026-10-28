#!/usr/bin/env python3
"""Native CRM drive against an explicitly seeded demo workspace.

Run with URL and a private Playwright storage-state path. Sends no messages or provider calls.
"""
from pathlib import Path
import json,sys
from playwright.sync_api import sync_playwright
BASE=sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8824'
STATE=sys.argv[2] if len(sys.argv)>2 else '/tmp/manufacturer-crm-browser.json'
OUT=Path('/tmp/manufacturer-crm-customers-qa');OUT.mkdir(exist_ok=True,mode=0o700)
checks=[];errors=[]
def check(label,value):
 checks.append({'name':label,'passed':bool(value)});assert value,label
def shot(page,name):
 f=OUT/(name+'.png');page.screenshot(path=str(f));f.chmod(0o600)
with sync_playwright() as p:
 b=p.chromium.launch(args=['--no-sandbox','--disable-gpu','--disable-dev-shm-usage']);c=b.new_context(storage_state=STATE,viewport={'width':1600,'height':1000});page=c.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
 try:
  page.goto(BASE+'/?view=customers',wait_until='domcontentloaded');page.locator('.mc-row[data-customer-id]').first.wait_for(timeout=30000)
  check('Customers primary navigation',page.locator('[data-manufacturer-nav=customers]').count()==1)
  check('One Customers heading',page.get_by_role('heading',name='Клиенти',exact=True).count()==1)
  bld=page.get_by_role('link',name='Отворете клиент BLD',exact=True);check('BLD company profile exists',bld.count()==1);shot(page,'01-customers-desktop')
  search=page.get_by_role('searchbox',name='Търсене на клиенти');search.fill('bld.bg');page.wait_for_timeout(550);check('Company domain search',page.get_by_role('link',name='Отворете клиент BLD',exact=True).count()==1)
  search.fill('unmatched-company-query');page.get_by_text('Потърсете по фирма, сайт или контакт.',exact=True).wait_for();check('Search empty state',True);search.fill('');bld.wait_for();bld.click();page.get_by_role('heading',name='История на поръчките',exact=True).wait_for()
  check('Sample requests merged into one company',page.locator('.mc-timeline-item').count()>=2)
  check('Company research has official source',page.locator('.mc-sources a[href="https://bld.bg/en/about-us"]').count()==1)
  check('Demonstration provenance visible',page.get_by_text('Демо профил с публични данни за фирмата и примерни запитвания.',exact=True).is_visible())
  check('Customer metrics retain request terminology',page.locator('.mc-metrics').inner_text().find('Revenue')<0)
  shot(page,'02-customer-profile-desktop');customer_url=page.url
  page.locator('.mc-timeline-card').first.click();page.get_by_role('heading',name='Проект',exact=True).wait_for();check('Timeline opens native order detail','view=orders' in page.url and 'order=' in page.url)
  page.go_back();page.get_by_role('heading',name='История на поръчките',exact=True).wait_for();check('Browser Back returns to customer timeline',page.url==customer_url)
  for width in (390,320):
   page.set_viewport_size({'width':width,'height':844});page.wait_for_timeout(100);check(f'Customer profile fits {width}',not page.evaluate('document.documentElement.scrollWidth>innerWidth'));shot(page,'03-profile-'+str(width))
  page.set_viewport_size({'width':1600,'height':1000});page.evaluate("document.body.style.zoom='2'");page.wait_for_timeout(100);check('Customer profile fits200percentzoom',not page.evaluate('document.documentElement.scrollWidth>innerWidth'));shot(page,'04-profile-zoom200');page.evaluate("document.body.style.zoom=''")
  page.locator('.mc-profile-heading').get_by_role('button',name='Клиенти',exact=True).click();bld.wait_for();check('Profile back button returns to list',True)
  page.set_viewport_size({'width':320,'height':844});check('Customer list fits320',not page.evaluate('document.documentElement.scrollWidth>innerWidth'));shot(page,'05-customers-320')
  check('Zero browser exceptions',not errors)
 finally:
  report={'checks':checks,'errors':errors};(OUT/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2));b.close()
