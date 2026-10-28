#!/usr/bin/env python3
"""Human service, private drafts and account UI in an isolated local manufacturer app.

Uses real local sessions and stores local service messages. Hosted-login and workspace
chooser responses are UI fixtures; no provider login, paid call or external email runs.
"""
import argparse
import json
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--base-url', default='http://127.0.0.1:8824')
parser.add_argument('--state', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
origin = urlsplit(args.base_url)
if origin.hostname not in {'127.0.0.1', 'localhost', '::1'} or origin.scheme != 'http':
    parser.error('Use an isolated local HTTP runtime.')
if origin.path not in {'', '/'} or origin.query or origin.fragment or not args.state.resolve().is_relative_to('/tmp'):
    parser.error('Use a local origin and an isolated /tmp state directory.')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from layout import install
install('manufacturer')
from access import AccessStore

BASE = args.base_url.rstrip('/')
OUT = args.output
OUT.mkdir(mode=0o700, parents=True, exist_ok=True)
store = AccessStore(args.state)
checks, errors = [], []
marker = uuid.uuid4().hex[:8]
HEADERS = {'X-Rocoto-Page': '1'}


def check(name, value):
    checks.append({'name': name, 'passed': bool(value)})
    assert value, name


def screenshot(page, name):
    path = OUT / (name + '.png')
    page.screenshot(path=str(path))
    path.chmod(0o600)


def login(context, principal):
    code = store.issue('demo', principal_id=principal, display_name='Екип Метал АД')
    response = context.request.post(BASE + '/api/session', data={'code': code}, headers=HEADERS)
    check('Local client login ' + principal, response.status == 200)


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(args=['--no-sandbox', '--disable-dev-shm-usage'])
    context = browser.new_context(viewport={'width': 1600, 'height': 1000}, locale='bg-BG')
    page = context.new_page()
    page.on('pageerror', lambda error: errors.append(str(error)))
    try:
        page.goto(BASE + '/', wait_until='domcontentloaded')
        page.locator('#session-form').wait_for()
        page.wait_for_function("()=>document.querySelector('label[for=session-code]').textContent==='Демо код'")
        check('Demo code label', True)
        for width in (1600, 390, 320):
            page.set_viewport_size({'width': width, 'height': 1000 if width == 1600 else 844})
            screenshot(page, 'login-' + str(width))
        # Hosted-login fixture tests mount idempotence without commissioning a provider.
        context.route('**/api/auth/config', lambda route: route.fulfill(json={
            'enabled': True, 'provider': 'workos', 'login_url': '/auth/login',
            'workspaces': [{'id': 'demo', 'name': 'Метал АД', 'slug': 'sample-hardware'}]}))
        page.evaluate('Promise.all([RocotoWorkspaceAccount.mountLogin(),RocotoWorkspaceAccount.mountLogin()])')
        check('Hosted login mounts once', page.locator('#workspace-sign-in').count() == 1)
        check('Hosted sign-in has one primary entry', not page.locator('#explore-demo').is_visible())
        screenshot(page, 'hosted-login-320-fixture')
        context.unroute('**/api/auth/config')

        login(context, 'service-qa-a')
        page.set_viewport_size({'width': 1600, 'height': 1000})
        loading = []
        def initial_history(route):
            loading.append(page.locator('.mh-history[aria-busy=true] .mh-history-skeleton').count())
            screenshot(page, 'service-loading-1600')
            route.fulfill(response=route.fetch())
        context.route('**/api/manufacturer/service-conversation', initial_history, times=1)
        page.goto(BASE + '/?view=service', wait_until='domcontentloaded')
        page.locator('.mh-history[aria-busy=false]').wait_for()
        check('Initial conversation skeleton', any(count == 3 for count in loading))
        def empty_history(route):
            response=route.fetch();data=response.json();data['messages']=[];route.fulfill(response=response,json=data)
        context.route('**/api/manufacturer/service-conversation',empty_history)
        page.reload(wait_until='domcontentloaded');page.locator('.mh-empty').wait_for()
        check('Human empty conversation state',page.locator('.mh-empty h3').inner_text()=='Чат с Питър')
        screenshot(page,'service-empty-1600')
        page.set_viewport_size({'width':390,'height':844});screenshot(page,'service-empty-390')
        page.set_viewport_size({'width':1600,'height':1000});context.unroute('**/api/manufacturer/service-conversation')
        page.reload(wait_until='domcontentloaded');page.locator('.mh-history[aria-busy=false]').wait_for()
        composer = page.locator('.mh-compose textarea')
        composer.fill('Лична чернова ' + marker)
        keys = page.evaluate("Object.keys(sessionStorage).filter(key=>key.startsWith('manufacturer-human-draft:')&&key.endsWith(':service'))")
        check('Service draft names exact member', any('service-qa-a' in key for key in keys))
        login(context, 'service-qa-b')
        page.goto(BASE + '/?view=service', wait_until='domcontentloaded')
        page.locator('.mh-history[aria-busy=false]').wait_for()
        check('Another member sees own draft', composer.input_value() == '')
        login(context, 'service-qa-a')
        page.goto(BASE + '/?view=service', wait_until='domcontentloaded')
        page.locator('.mh-history[aria-busy=false]').wait_for()
        check('Original member draft restored', composer.input_value() == 'Лична чернова ' + marker)

        # Complete a real local send while the person starts typing the next message.
        message = 'Въпрос за срока на доставка ' + marker
        next_draft = 'Следващ въпрос ' + marker
        def pending_send(route):
            response = route.fetch()
            composer.fill(next_draft)
            route.fulfill(response=response)
        context.route('**/api/manufacturer/service-conversation/messages', pending_send, times=1)
        composer.fill(message)
        page.locator('.mh-compose button[type=submit]').click()
        page.get_by_text(message, exact=True).wait_for()
        check('Real human message saved', True)
        check('Typing during send is retained', composer.input_value() == next_draft)
        screenshot(page, 'service-1600')
        for width in (390, 320):
            page.set_viewport_size({'width': width, 'height': 844})
            check('Service fits ' + str(width), page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
            screenshot(page, 'service-' + str(width))

        # A response lost after server commit must retry with the same idempotency key.
        attempts = []
        retry_text = 'Проверка на потвърждението ' + marker
        def retry_send(route):
            attempts.append(route.request.post_data_json)
            response = route.fetch()
            if len(attempts) == 1:
                route.abort('failed')
            else:
                route.fulfill(response=response)
        context.route('**/api/manufacturer/service-conversation/messages', retry_send)
        composer.fill(retry_text)
        page.locator('.mh-compose button[type=submit]').click()
        page.locator('.mh-notice:not([hidden])').wait_for()
        page.locator('.mh-compose button[type=submit]').click()
        page.wait_for_function("()=>document.querySelector('.mh-compose textarea').value===''")
        check('Retry reuses admitted operation', len(attempts) == 2 and attempts[0] == attempts[1])
        page.get_by_text(retry_text, exact=True).wait_for()
        check('Retry produces one human message', page.get_by_text(retry_text, exact=True).count() == 1)
        context.unroute('**/api/manufacturer/service-conversation/messages')

        page.set_viewport_size({'width': 1600, 'height': 1000})
        page.goto(BASE + '/?view=orders', wait_until='domcontentloaded')
        page.locator('.mf-order-row[data-order-id]').first.wait_for()
        page.locator('.mf-order-row[data-order-id]').first.click()
        page.get_by_role('button', name='Свържи се с клиента', exact=True).click()
        page.locator('.mh-panel .mh-order-card').first.wait_for()
        check('Customer history includes all sample orders', page.locator('.mh-panel .mh-order-card').count() >= 3)
        check('Current order is identified', page.locator('.mh-panel .mh-order-card[aria-current=true]').count() >= 1)
        check('Email remains an honest draft', page.locator('.mh-panel button[type=submit]').is_disabled())
        check('Close receives focus', page.get_by_role('button', name='Затваряне', exact=True).evaluate('(el)=>el===document.activeElement'))
        screenshot(page, 'customer-1600')
        page.get_by_role('button', name='Разширяване', exact=True).click()
        check('Expansion communicates state', page.locator('.mh-expand').get_attribute('aria-expanded') == 'true')
        screenshot(page, 'customer-expanded-1600')
        for width in (390, 320):
            page.set_viewport_size({'width': width, 'height': 844})
            page.wait_for_function("()=>document.querySelector('.mh-panel').getAttribute('role')==='dialog'")
            check('Modal fits ' + str(width), page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
            check('Mobile keyboard stays closed ' + str(width), not composer.evaluate('(el)=>el===document.activeElement'))
            check('Meaningless mobile expand hidden ' + str(width), not page.locator('.mh-expand').is_visible())
            check('Background is inert ' + str(width), page.locator('body>.workspace').evaluate('(el)=>el.inert'))
            screenshot(page, 'customer-' + str(width))
        page.keyboard.press('Escape')
        check('Escape closes panel', page.locator('.mh-panel').is_hidden())

        page.goto(BASE + '/?settings=billing', wait_until='domcontentloaded')
        page.locator('.wa-billing[aria-busy=false]').wait_for()
        for width in (1600, 390, 320):
            page.set_viewport_size({'width': width, 'height': 1000 if width == 1600 else 844})
            check('Billing fits ' + str(width), page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
            check('Billing controls stay inside cards ' + str(width), page.locator('.wa-card button').evaluate_all('(items)=>items.every(el=>{const a=el.getBoundingClientRect(),b=el.closest(".wa-card").getBoundingClientRect();return a.left>=b.left&&a.right<=b.right+1})'))
            screenshot(page, 'billing-' + str(width))

        # The chooser receives only authenticated fixture membership metadata.
        context.route('**/api/workspaces', lambda route: route.fulfill(json={'workspaces': [
            {'id': 'demo', 'name': 'Метал АД', 'selected': True},
            {'id': 'qa-other', 'name': 'Друго работно пространство с дълго име'}]}))
        page.evaluate("async()=>{history.replaceState({},'', '/?workspaces=1');const session=await(await fetch('/api/session')).json();await Promise.all([RocotoWorkspaceAccount.sessionReady(session),RocotoWorkspaceAccount.sessionReady(session)]);}")
        check('Workspace chooser opens once', page.locator('.wa-workspace-dialog[open]').count() == 1)
        check('Current workspace is identified', page.locator('.wa-workspace-option[aria-current=true]').count() == 1)
        check('Long workspace names fit phone', page.locator('.wa-workspace-dialog').evaluate('(el)=>el.scrollWidth<=el.clientWidth'))
        screenshot(page, 'workspace-chooser-320-fixture')
        page.keyboard.press('Escape')
        page.locator('.wa-workspace-dialog').wait_for(state='detached')
        check('Chooser closes cleanly', page.locator('.wa-workspace-dialog').count() == 0 and 'workspaces=1' not in page.url)
        check('Zero browser exceptions', not errors)
    finally:
        report = {'checks': checks, 'errors': errors, 'external_messages': 0, 'provider_calls': 0,
                  'boundary': 'Local real service messages; hosted identity and chooser use browser fixtures.'}
        path = OUT / 'report.json'
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        path.chmod(0o600)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        browser.close()
