#!/usr/bin/env python3
"""Prove literal specification quantities and deliberate proposal choices in disposable local state.

Pass --root <built-site> --state <temporary-state>. The drive starts its own loopback server
with model and Places transports disabled, then saves two synthetic local orders.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import configurator_versions  # noqa: E402
import order_assistant  # noqa: E402
from store import CompanyStore  # noqa: E402

import places  # noqa: E402
import serve  # noqa: E402
from pipeline.check import CHROMIUM  # noqa: E402


def run(base: str, state: Path, out: Path) -> None:
    from playwright.sync_api import sync_playwright

    if urlsplit(base).hostname not in {'127.0.0.1', 'localhost', '::1'}:
        raise ValueError('Choose a loopback disposable QA server.')
    state = state.resolve()
    if not state.is_relative_to(Path(tempfile.gettempdir()).resolve()):
        raise ValueError('Choose disposable state under the system temporary directory.')
    database = state / 'companies/sample-hardware/company.db'
    if not database.is_file():
        raise ValueError('Commission the disposable company database first.')
    out.mkdir(parents=True, exist_ok=True)
    evidence, errors = {}, []
    with sync_playwright() as driver:
        browser = driver.chromium.launch(headless=True, args=CHROMIUM)
        page = browser.new_page(viewport={'width': 1600, 'height': 1000}, reduced_motion='reduce')
        page.on('pageerror', lambda error: errors.append(str(error)))
        # This drive's outbound network is confined to its declared local service.
        page.route('**/*', lambda route: route.continue_() if urlsplit(route.request.url).hostname
                   in {'127.0.0.1', 'localhost', '::1'} else route.abort())

        def reset():
            page.goto(base + '/sample-hardware/#order', wait_until='load')
            page.evaluate('localStorage.clear()')
            page.reload(wait_until='load')
            page.locator('#pick .pick-pair').wait_for()

        def press(action):
            page.locator('[data-pick="' + action + '"]').first.click()

        reset()
        code = '101937'
        assert page.evaluate('(code)=>!!RocotoCore.C.items[code]', code)
        press('spec')
        page.locator('[data-pick-text]').fill(code + ' | 24')
        with page.expect_response(lambda response: response.url.endswith('/api/spec')) as pending:
            press('read')
        assert pending.value.json()['lines'][0]['qty'] == 24
        page.locator('.pick-spec-row').wait_for()
        press('add-spec')
        assert page.evaluate('RocotoConfigurator.state.basket[0].rows[0].n') == 24
        reset()
        press('spec')
        page.locator('[data-pick-text]').fill(code + ' | 1000')
        with page.expect_response(lambda response: response.url.endswith('/api/spec')) as pending:
            press('read')
        parsed = pending.value.json()
        assert parsed['engine'] == 'rules' and parsed['lines'][0]['qty'] == 1000, parsed
        page.locator('.pick-spec-row').wait_for()
        press('add-spec')
        basket = page.evaluate('RocotoConfigurator.state.basket')
        assert sum(row['n'] for line in basket for row in line['rows']) == 1000, basket
        assert all(1 <= row['n'] <= 999 for line in basket for row in line['rows'])
        page.locator('[data-act="checkout"]').click()
        for key, value in {'name': 'Synthetic business flow QA', 'email': 'flow-qa@example.invalid',
                           'phone': '+359881234567', 'company': 'Synthetic QA company',
                           'website': 'example.invalid', 'trade': 'Door installation'}.items():
            page.locator('[data-co="' + key + '"]').fill(value)
        with page.expect_response(lambda response: response.url.endswith('/api/orders')
                                  and response.request.method == 'POST') as pending:
            page.locator('[data-act="next"]').click()
        receipt = pending.value.json()
        assert receipt.get('ok'), receipt
        store = CompanyStore(database)
        try:
            saved = store.read_order(receipt['id'])
            capture = saved['customer']['capture']['specification']['lines'][0]
            assert capture['quantity'] == 1000 and capture['selected_code'] == code, capture
            assert saved['customer']['company'] == 'Synthetic QA company'
            assert saved['customer']['website'] == 'https://example.invalid'
        finally:
            store.close()
        evidence['specification'] = {'order_id': receipt['id'], 'article': code, 'literal_quantity': 1000,
                                      'basket_lines': len(basket), 'provider': 'rules'}
        page.screenshot(path=str(out / 'specification-receipt.png'))

        reset()
        press('choose')
        press('help')
        with page.expect_response(lambda response: response.url.endswith('/api/propose')) as pending:
            press('propose')
        empty = pending.value.json()
        assert empty['lines'] == [] and empty['choices'][0]['unresolved'] == ['parts']
        page.locator('.pick-choice-group').wait_for()
        press('request-proposal')
        assert page.evaluate('RocotoConfigurator.state.basket[0].custom')
        page.locator('[data-act="checkout"]').click()
        for key, value in {'name': 'Synthetic needs QA', 'email': 'needs-qa@example.invalid',
                           'phone': '+359881234567', 'company': 'Synthetic needs company'}.items():
            page.locator('[data-co="' + key + '"]').fill(value)
        with page.expect_response(lambda response: response.url.endswith('/api/orders')
                                  and response.request.method == 'POST') as pending:
            page.locator('[data-act="next"]').click()
        request_receipt = pending.value.json()
        assert request_receipt.get('ok'), request_receipt
        store = CompanyStore(database)
        try:
            capture = store.read_order(request_receipt['id'])['customer']['capture']
            assert capture['entry_path'] == 'questionnaire'
            assert capture['proposal']['selected'] == []
            assert all(question['status'] == 'unanswered' for question in capture['questionnaire']['questions'])
        finally:
            store.close()
        evidence['unresolved_request'] = {'order_id': request_receipt['id'], 'capture': 'unanswered questions preserved'}

        reset()
        press('choose')
        press('help')
        page.locator('[data-question="parts"][data-answer="lock"]').click()
        with page.expect_response(lambda response: response.url.endswith('/api/propose')) as pending:
            press('propose')
        proposal = pending.value.json()
        assert proposal['engine'] == 'rules' and proposal['lines'] == [] and not proposal['ready'], proposal
        choice = proposal['choices'][0]
        assert choice['count'] > 20 and len(choice['matches']) == 20
        assert len(choice['matching_codes']) == choice['count']
        page.locator('.pick-choice-group').wait_for()
        assert page.locator('.pick-proposal-line').count() == 0
        press('choice-catalogue')
        last_code = choice['matching_codes'][-1]
        page.locator('[data-pick-query]').fill(last_code)
        selection = page.locator('[data-pick="select-choice"][data-code="' + last_code + '"]')
        if not selection.count():
            selection = page.locator('[data-pick="choose-article"][data-code="' + last_code + '"]')
        selection.click()
        if page.locator('.pick-clarify').count():
            press('clarify')
        page.locator('.pick-proposal-line').wait_for()
        press('add-proposal')
        selected = page.evaluate('RocotoConfigurator.state.basket')
        assert len(selected) == 1 and selected[0]['code'] == last_code, selected
        evidence['proposal'] = {'candidate_count': choice['count'], 'selected_article': last_code,
                                 'implicit_selections': 0, 'provider': 'rules'}
        page.screenshot(path=str(out / 'explicit-proposal-selection.png'))
        reset()
        keyhole_code = page.evaluate("""() => {
            const clause=RocotoConfig.picker.clarify.find(q=>q.enabled!==false);
            return RocotoCore.C.cats.flatMap(cat=>cat.items).find(row=>RocotoPick.matches(row,clause.when)).c;
        }""")
        press('spec')
        page.locator('[data-pick-text]').fill('2 pcs ' + keyhole_code)
        press('read')
        page.locator('.pick-spec-row').wait_for()
        press('add-spec')
        page.locator('.pick-clarify').wait_for()
        assert page.evaluate('RocotoConfigurator.state.basket.length') == 0
        assert page.locator('[data-pick="clarify"]').count() == 2
        press('clarify')
        assert page.evaluate('RocotoConfigurator.state.basket[0].rows[0].n') == 2
        evidence['bulk_keyhole'] = {'article': keyhole_code, 'confirmation_before_add': True}
        assert not errors, errors
        evidence['browser_errors'] = errors
        browser.close()
    (out / 'evidence.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n')
    print('Specification quantities, exact saved capture and explicit full-catalogue proposal selection passed: ' + str(out))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--out', type=Path, default=Path('/tmp/orders-business-flow'))
    args = parser.parse_args()
    httpd = serve.server(args.root, 0, args.state, service=places.Places(None, enabled=False),
                          assistant=order_assistant.Assistant(enabled=False),
                          bridge=configurator_versions.Bridge(None))
    worker = threading.Thread(target=httpd.serve_forever, daemon=True)
    worker.start()
    try:
        run('http://127.0.0.1:' + str(httpd.server_address[1]), args.state, args.out)
    finally:
        httpd.shutdown()
        httpd.server_close()
        worker.join(timeout=5)


if __name__ == '__main__':
    main()
