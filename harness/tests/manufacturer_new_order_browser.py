#!/usr/bin/env python3
"""Staff drawer proof: narrow layouts, corrections, uncertain retries and saved detail."""
import copy
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / 'verticals/manufacturer/web'
OUT = Path('/tmp/manufacturer-new-order-proof')


def run(failure_status=503):
    OUT.mkdir(exist_ok=True)
    commands = []
    errors = []
    failures = 1
    configuration = {'company_id':'qa-company', 'actor':{'id':'office','role':'operator','can_create_orders':True},
        'capabilities':{'agent_editing':False}, 'revision':0,
        'settings':{'embed_url':'https://orders.example.test/sample-hardware/rocoto/configurator.js','company_slug':'sample-hardware'},
        'document':{'configuration':{'slug':'sample-hardware'}, 'catalogue':{'currency':'EUR','cats':[
            {'code':'locks','bg':'Брави за интериорни врати','items':[{'c':'101081','s':'Обикновена брава 55/72','u':'pc','p':12.5}, {'c':'101082','s':'Секретна брава 55/72','u':'pc','q':1}]},
            {'code':'handles','bg':'Дръжки за врати','items':[{'c':'201001','s':'Комплект дръжки — сатен','u':'set','p':24}]}]}}}
    company = {'id':'qa-company','name':'Метал АД','capabilities':{'agent_editing':False},'warehouses':[{'id':'sofia','name':'Склад София'}]}
    order = {'id':'created-order','display_number':'#1027','number':'#1027','created_at':'2026-10-19T10:00:00Z','status':'requested','customer':{'company':'Практикер','name':'Иван Петров','email':'buyer@example.com'},'customer_id':'qa-customer','items_count':1,'currency':'EUR','total':25,'pricing_state':'priced','lines':[{'name':'Брави за интериорни врати','code':'101081','quantity':2,'unit_price':12.5,'total':25}]}
    order['customer']['capture'] = {'specification':{'allocation_review':{'schema':'rocoto.orders.allocations.v1','destinations':[{'id':'sofia','label':'Практикер София'},{'id':'varna','label':'Практикер Варна'}],'allocations':[{'sku':'101081','selected_code':'101081','destination_id':'sofia','quantity':12,'source_cell':'B3'},{'sku':'101081','selected_code':'101081','destination_id':'varna','quantity':24,'source_cell':'C3'}]}}}
    def respond(route):
        nonlocal failures
        path = route.request.url.split('manufacturer.test', 1)[-1]
        if path == '/' or path.startswith('/?'):
            route.fulfill(content_type='text/html', body='''<!doctype html><html lang="bg"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Staff order proof</title>
            <style>:root{--ink:#222;--paper:#fff;--surface:#f6f6f6;--border:#ddd;--border-strong:#bbb;--muted:#666;--accent:#5751d6;--radius:6px;--radius-lg:10px;--radius-sm:4px;--font:system-ui;--font-code:monospace;--font-size-ui:14px}*{box-sizing:border-box}body{margin:0;font:14px/1.5 system-ui;color:var(--ink)}[hidden]{display:none!important}.icon{width:20px;height:20px;fill:none;stroke:currentColor}button,input,textarea,select{font:inherit}button{cursor:pointer;color:inherit}</style>
            <link rel="stylesheet" href="/manufacturer.css"><link rel="stylesheet" href="/manufacturer-new-order.css"><main id="root"></main>
            <script src="/workspace-tabs.js"></script><script src="/manufacturer-new-order.js"></script><script src="/manufacturer-tabs.js"></script>
            <script>window.tabs=RocotoWorkspaceTabs.create({root:document.getElementById('root'),context:{},defaultHome:{mount(){}}});tabs.configure({vertical:{id:'manufacturer',revision:'test'},surfaces:[{id:'orders'}]},'qa-company');tabs.setVisible(true);tabs.open('orders');</script>''')
        elif path.endswith('.js') or path.endswith('.css'):
            source = ROOT / 'web/workspace-tabs.js' if path == '/workspace-tabs.js' else WEB / path[1:]
            route.fulfill(content_type='application/javascript' if path.endswith('.js') else 'text/css', body=source.read_text())
        elif path == '/api/manufacturer/overview':
            route.fulfill(json={'company':company,'actor':configuration['actor'],'orders':[order] if commands and failures == 0 else []})
        elif path == '/api/manufacturer/configurator':
            route.fulfill(json=configuration)
        elif path == '/api/manufacturer/orders' and route.request.method == 'POST':
            commands.append(copy.deepcopy(route.request.post_data_json))
            if failures:
                failures -= 1
                route.fulfill(status=failure_status,json={'detail':'Потвърдете записа чрез „Опитайте отново“. Данните са запазени.'})
            else:
                route.fulfill(json={'ok':True,'order_id':'created-order'})
        elif path.endswith('/review'):
            route.fulfill(json={'order':order,'actor':configuration['actor']})
        elif path.endswith('/fulfillment'):
            route.fulfill(json={'status':'requested','allowed_actions':[]})
        else:
            route.fulfill(status=404,json={})
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True,args=['--no-sandbox','--disable-gpu'])
        page = browser.new_page(viewport={'width':1600,'height':1000})
        page.on('pageerror',lambda error: errors.append(str(error)))
        page.route('**/*',respond)
        page.goto('https://manufacturer.test/')
        page.get_by_role('button',name='Нова поръчка',exact=True).click()
        page.get_by_label('Фирма *',exact=True).fill('Практикер')
        page.get_by_label('Лице за контакт *').fill('Иван Петров')
        phone = page.get_by_label('Телефон', exact=True)
        phone.fill('letters')
        assert phone.evaluate('(element)=>!element.checkValidity()')
        phone.fill('+359 888 123 456')
        assert phone.evaluate('(element)=>element.checkValidity()')
        page.get_by_role('searchbox',name='Търсене по артикул или име').fill('10108')
        page.get_by_role('button',name='Добави 101081',exact=True).click()
        quantity = page.get_by_label('Количество за 101081')
        for invalid in ('1.5', '10000'):
            quantity.fill(invalid)
            assert quantity.evaluate('(element)=>!element.checkValidity()')
        quantity.fill('2')
        page.get_by_label('Експедиционен склад').select_option('sofia')
        page.get_by_label('Адрес за доставка',exact=True).fill('бул. България 100')
        page.get_by_label('Град',exact=True).fill('София')
        page.get_by_label('Пощенски код',exact=True).fill('1000')
        page.get_by_label('Номер на заявката на клиента (PO)').fill('PO-2026-184')
        page.get_by_label('Желана дата', exact=True).fill('2026-11-01')
        page.get_by_label('Оригинален документ',exact=True).set_input_files({'name':'request.txt','mimeType':'text/plain','buffer':b'Original buyer request'})
        for width in (1600,390,320):
            page.set_viewport_size({'width':width,'height':1000 if width==1600 else 844})
            page.locator('.mn-content').evaluate('(element)=>element.scrollTop=0')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert page.locator('.mn-dialog').evaluate('(element)=>element.scrollWidth <= element.clientWidth')
            assert page.locator('.mn-content').evaluate('(element)=>element.scrollWidth <= element.clientWidth')
            page.screenshot(path=str(OUT/f'new-order-{width}.png'))
        page.get_by_role('button',name='Създай поръчка',exact=True).click()
        page.get_by_role('button',name='Опитайте отново',exact=True).wait_for()
        assert page.get_by_label('Фирма *',exact=True).is_disabled()
        assert commands[0]['customer']['company']=='Практикер'
        assert commands[0]['customer']['needBy']=='2026-11-01'
        assert commands[0]['customer']['email']=='' and commands[0]['customer']['phone']=='+359 888 123 456'
        assert commands[0]['original_file']['filename']=='request.txt'
        assert commands[0]['lines']==[{'article':'101081','quantity':2}]
        page.reload()
        page.get_by_role('button',name='Нова поръчка',exact=True).click()
        page.get_by_role('button',name='Опитайте отново',exact=True).click()
        page.locator('.mo-detail-heading h1').filter(has_text='#1027').wait_for()
        assert len(commands)==2 and commands[0]==commands[1]
        assert page.locator('.mn-dialog').is_hidden()
        assert page.locator('.mo-allocation-table tbody tr').count() == 2
        assert page.locator('.mo-allocation-table').inner_text().find('Практикер Варна') >= 0
        for width in (1600,390,320):
            page.set_viewport_size({'width':width,'height':1000 if width==1600 else 844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.locator('.mo-allocations').scroll_into_view_if_needed()
            page.screenshot(path=str(OUT/f'allocations-{width}.png'))
        assert page.evaluate('Object.keys(sessionStorage).filter(key=>key.startsWith("manufacturer-new-order:")).length')==0
        assert not errors, errors
        browser.close()
    print(json.dumps({'ok':True,'viewports':[1600,390,320],'retry_same_payload':True,'interrupted_status':failure_status,'attachments':True,'detail':True,'screenshots':str(OUT)}))


if __name__=='__main__':
    for failure_status in (503, 403):
        run(failure_status)
