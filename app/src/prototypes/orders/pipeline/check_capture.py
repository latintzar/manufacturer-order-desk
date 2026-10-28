#!/usr/bin/env python3
"""Prove questionnaire needs survive a real checkout in a disposable local store."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.check import CHROMIUM  # noqa: E402


def run(base, company, database, out):
    from playwright.sync_api import sync_playwright

    if urlsplit(base).hostname not in {'localhost', '127.0.0.1', '::1'}:
        raise ValueError('Use a disposable loopback order store for this checkout proof.')
    out.mkdir(parents=True, exist_ok=True)
    evidence = {'orders': [], 'errors': []}
    with sync_playwright() as driver:
        browser = driver.chromium.launch(headless=True, args=CHROMIUM)
        page = browser.new_page(viewport={'width': 1600, 'height': 1000}, reduced_motion='reduce')
        page.on('pageerror', lambda error: evidence['errors'].append(str(error)))

        def press(action):
            page.locator(f'[data-pick="{action}"]').first.click()

        def start():
            page.goto(f'{base}/{company}/en/#order', wait_until='load')
            page.evaluate('localStorage.clear()')
            page.reload(wait_until='load')
            page.locator('#pick .pick-pair').wait_for()
            press('choose')
            press('help')
            page.locator('[data-question="parts"][data-answer="lock"]').click()
            page.locator('[data-section="hand"]').click()
            page.locator('[data-question="hand"][data-answer="?"]').click()
            page.locator('[data-pick-project]').fill('Twelve replacement doors; confirm existing dimensions.')

        def checkout(expected_path):
            page.locator('[data-act="checkout"]').click()
            for key, value in {'name': 'Local capture proof', 'email': 'capture-qa@example.invalid',
                               'phone': '+359881234567', 'company': 'Synthetic capture QA company',
                               'project': 'Disposable local proof'}.items():
                page.locator(f'[data-co="{key}"]').fill(value)
            with page.expect_response(lambda response: response.url.endswith('/api/orders') and response.request.method == 'POST') as pending:
                page.locator('[data-act="next"]').click()
            response = pending.value
            receipt = response.json()
            assert response.ok and receipt['ok'], receipt
            sent = response.request.post_data_json['customer']['capture']
            assert sent['entry_path'] == expected_path
            with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as db:
                raw = db.execute('SELECT c.data FROM customers c JOIN orders o ON o.customer_id=c.id WHERE o.id=?', (receipt['id'],)).fetchone()[0]
            stored = json.loads(raw)
            snapshot = copy.deepcopy(stored['capture'])
            if expected_path == 'specification':
                metadata = snapshot['specification'].pop('file')
                assert metadata['id'] == sent['specification']['file_id']
                original = database.parent / 'order-files' / metadata['id']
                assert original.read_bytes() == pdf
                assert metadata['size'] == len(pdf) and metadata['sha256'] == hashlib.sha256(pdf).hexdigest()
                assert metadata['content_type'] == 'application/pdf' and metadata['name'] == 'Door schedule.pdf'
            assert snapshot == sent
            evidence['orders'].append({'id': receipt['id'], 'capture': stored['capture']})
            assert page.evaluate('RocotoConfigurator.state.capture') is None
            return stored

        start()
        page.screenshot(path=str(out / '01-questionnaire-needs.png'))
        press('propose')
        page.locator('.pick-proposal').wait_for(timeout=30000)
        press('add-proposal')
        stored = checkout('questionnaire')
        capture = stored['capture']
        questions = {q['id']: q for q in capture['questionnaire']['questions']}
        assert questions['parts']['status'] == 'answered' and questions['parts']['answers'][0]['label']
        assert questions['hand']['status'] == 'unknown' and questions['hand']['answers'][0]['id'] == '?'
        assert questions['size']['status'] == 'unanswered' and questions['size']['answers'] == []
        assert capture['questionnaire']['project'].startswith('Twelve replacement doors')
        assert capture['proposal']['summary'] and capture['proposal']['selected']
        start()
        page.locator('#back').click()
        press('families')
        page.locator('[data-family="mortise"]').click()
        page.locator('.pick-add').first.click()
        stored = checkout('catalogue')
        assert set(stored['capture']) == {'schema', 'entry_path', 'language'}
        assert 'questionnaire' not in stored and 'specification' not in stored
        page.goto(f'{base}/{company}/en/#order', wait_until='load')
        page.evaluate('localStorage.clear()')
        page.reload(wait_until='load')
        page.locator('#pick .pick-pair').wait_for()
        press('spec')
        code = page.evaluate('RocotoCore.C.cats[0].items[0].c')
        document = browser.new_page()
        document.set_content('<h1>Door schedule</h1><p>12 pcs ' + str(code) + '</p>')
        pdf = document.pdf()
        document.close()
        with page.expect_response(lambda response: response.url.endswith('/api/uploads')) as uploading:
            page.locator('[data-pick-file]').set_input_files({'name': 'Door schedule.pdf',
                                                            'mimeType': 'application/pdf', 'buffer': pdf})
        assert uploading.value.status == 201
        page.locator('[data-pick="read"]').wait_for(state='visible')
        with page.expect_response(lambda response: response.url.endswith('/api/spec')) as reading:
            press('read')
        assert reading.value.ok, reading.value.text()
        page.locator('[data-pick="add-spec"]').wait_for()
        page.screenshot(path=str(out / '02-specification-file.png'))
        press('add-spec')
        stored = checkout('specification')
        assert any(line['selected_code'] == str(code) for line in stored['capture']['specification']['lines'])
        assert not evidence['errors'], evidence['errors']
        browser.close()
    (out / 'evidence.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n')
    print('Saved questionnaire needs, clean switched-path catalogue context, and original PDF with verified metadata; local orders only.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('company')
    parser.add_argument('--base', required=True)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    run(args.base.rstrip('/'), args.company, args.database.absolute(), args.out)


if __name__ == '__main__':
    main()
