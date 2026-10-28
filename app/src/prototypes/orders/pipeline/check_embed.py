#!/usr/bin/env python3
"""Copy the public script onto a separate origin; inspect the real chooser without order writes."""
from __future__ import annotations

import argparse
import html
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import common  # noqa: E402
from pipeline.check import CHROMIUM  # noqa: E402


def run(company: str, base: str, out: Path) -> dict:
    from playwright.sync_api import sync_playwright

    out.mkdir(parents=True, exist_ok=True)
    source = f'{base.rstrip("/")}/{company}/rocoto/configurator.js'
    markup = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
              '<meta name="viewport" content="width=device-width,initial-scale=1">'
              '<style>body{margin:24px;font-family:serif}h1{color:rgb(60,70,80)}</style></head>'
              '<body><h1>Independent installer website</h1><p>The installer’s own page.</p>'
              f'<script src="{html.escape(source, quote=True)}" data-rocoto="{company}" defer></script>'
              '</body></html>').encode()

    class Host(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(200 if self.path == '/' else 404)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            if self.path == '/':
                self.wfile.write(markup)

        def log_message(self, *args):
            pass

    host = ThreadingHTTPServer(('127.0.0.1', 0), Host)
    threading.Thread(target=host.serve_forever, daemon=True).start()
    evidence = {'checks': [], 'order_requests': [], 'errors': []}
    try:
        with sync_playwright() as driver:
            browser = driver.chromium.launch(headless=True, args=CHROMIUM)
            page = browser.new_page(viewport={'width': 1280, 'height': 900}, reduced_motion='reduce')
            page.on('pageerror', lambda error: evidence['errors'].append(str(error)))

            def block_orders(route):
                evidence['order_requests'].append(route.request.url)
                route.abort()

            page.route('**/api/orders', block_orders)
            page.goto(f'http://127.0.0.1:{host.server_port}/', wait_until='load')
            button = page.locator('#rocoto-embed button')
            button.wait_for()
            assert page.locator('h1').evaluate('e=>getComputedStyle(e).color') == 'rgb(60, 70, 80)'
            button.click()
            frame = page.frame_locator('#rocoto-embed iframe')
            frame.locator('#pick .pick-pair').wait_for(timeout=30000)
            child = next(f for f in page.frames if '/rocoto/embed.html' in f.url)
            assert child.evaluate('RocotoCore.C.ready')
            assert child.evaluate('RocotoCore.L.lang') == 'en'
            evidence['catalogue_rows'] = child.evaluate('Object.keys(RocotoCore.C.items).length')
            assert evidence['catalogue_rows'] > 0
            evidence['checks'].append('copied tag loads real catalogue on its own origin')
            page.evaluate("postMessage({type:'rocoto:close'},'*')")
            assert page.locator('#rocoto-embed dialog[open]').count() == 1
            frame.locator('[data-pick="choose"]').first.click()
            frame.locator('[data-pick="families"]').first.click()
            frame.locator('[data-family="mortise"]').click()
            with page.expect_response(lambda r: r.url.endswith('/api/quote') and r.request.method == 'POST') as pending:
                frame.locator('.pick-add').first.click()
            quote = pending.value
            assert quote.status == 200 and quote.json().get('ok')
            assert quote.request.headers.get('origin', base) == base
            evidence['checks'].append('embedded catalogue selection receives same-origin quote')
            page.screenshot(path=str(out / '01-embedded-desktop.png'), animations='disabled')
            frame.locator('#back').click()
            frame.locator('#back').click()
            frame.locator('#back').click()
            frame.locator('[data-pick="spec"]').first.click()
            frame.locator('[data-pick-text]').fill('24 locks for the saved project')
            frame.locator('[data-act="close"]').first.click()
            page.locator('#rocoto-embed dialog').wait_for(state='hidden')
            assert button.evaluate('e=>e.getRootNode().activeElement===e')
            evidence['checks'].append('verified close message restores host focus; spoof ignored')
            page.set_viewport_size({'width': 320, 'height': 844})
            button.click()
            frame = page.frame_locator('#rocoto-embed iframe')
            frame.locator('[data-pick-text]').wait_for(timeout=30000)
            assert frame.locator('[data-pick-text]').input_value() == '24 locks for the saved project'
            assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
            child = next(f for f in page.frames if '/rocoto/embed.html' in f.url)
            assert not child.evaluate('document.documentElement.scrollWidth>innerWidth')
            page.screenshot(path=str(out / '02-embedded-320.png'), animations='disabled')
            evidence['checks'].append('reopen preserves specification text and 320px host/frame layout')
            assert not evidence['errors'], evidence['errors']
            assert not evidence['order_requests'], evidence['order_requests']
            browser.close()
    finally:
        host.shutdown()
        host.server_close()
    (out / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    return evidence


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('company', choices=common.slugs())
    parser.add_argument('--base', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.company, args.base.rstrip('/'), args.out), indent=2))
