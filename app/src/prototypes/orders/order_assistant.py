"""Bounded Responses requests for customer specification and proposal text.

Commission the private call ledger explicitly:
    python3 order_assistant.py commission --state /absolute/private/orders-state
The 300 calls/month allowance is independent for each route. Missing/corrupt ledgers,
provider errors and the off switch all leave the deterministic catalogue path available.
"""
from __future__ import annotations

import argparse
import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from places import Ledger

LEDGER_NAME = 'orders-assistant-ledger.json'
CEILINGS = {'spec': (300, 300), 'propose': (300, 300)}
ENDPOINT = 'https://api.openai.com/v1/responses'
MAX_INPUT = 120_000
MAX_RESPONSE = 180_000


class Assistant:
    def __init__(self, key='', *, state=None, model='gpt-5.6-terra', enabled=True, transport=None):
        self._key = key
        self.model = model
        self.enabled = enabled
        self.ledger = Ledger(Path(state) / LEDGER_NAME if state else None, CEILINGS)
        self.transport = transport or self._request
        self._slots = threading.BoundedSemaphore(2)
        self._rest_until = 0.0

    def _request(self, payload):
        request = urllib.request.Request(ENDPOINT, data=json.dumps(payload).encode(), headers={
            'Authorization': 'Bearer ' + self._key, 'Content-Type': 'application/json'}, method='POST')
        # Redirects never receive the provider credential.
        class Direct(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                raise urllib.error.HTTPError(req.full_url, code, 'redirect', headers, fp)
        with urllib.request.build_opener(Direct).open(request, timeout=24) as response:
            body = response.read(MAX_RESPONSE + 1)
        if len(body) > MAX_RESPONSE:
            raise ValueError('Provider response limit')
        result = json.loads(body)
        if result.get('status') != 'completed':
            raise ValueError('Provider response incomplete')
        output = ''.join(part.get('text', '') for item in result.get('output', [])
                         if item.get('type') == 'message' for part in item.get('content', [])
                         if part.get('type') == 'output_text')
        return json.loads(output)

    def structured(self, route, instruction, data, schema, *, image=None):
        if (route not in CEILINGS or not self.enabled or not self._key
                or time.monotonic() < self._rest_until or not self._slots.acquire(blocking=False)):
            return None
        try:
            content = json.dumps(data, ensure_ascii=False, allow_nan=False)
            if len(content.encode()) > MAX_INPUT or not self.ledger.reserve(route):
                return None
            inputs = [{'type': 'input_text', 'text': content}]
            if image:
                inputs.append({'type': 'input_image', 'image_url': image, 'detail': 'high'})
            payload = {'model': self.model, 'store': False, 'instructions': instruction,
                       'input': [{'role': 'user', 'content': inputs}], 'max_output_tokens': 3500,
                       'text': {'format': {'type': 'json_schema', 'name': 'orders_' + route,
                                           'strict': True, 'schema': schema}}}
            if self.model.startswith('gpt-5'):
                payload['reasoning'] = {'effort': 'low'}
            result = self.transport(payload)
            return result if isinstance(result, dict) else None
        except (OSError, ValueError, TypeError, KeyError, TimeoutError):
            self._rest_until = time.monotonic() + 60
            return None
        finally:
            self._slots.release()


def from_environment(state):
    key = os.environ.pop('ROCOTO_ORDERS_OPENAI_API_KEY', '')
    return Assistant(key, state=state, model=os.environ.get('ROCOTO_ORDERS_OPENAI_MODEL', 'gpt-5.6-terra'),
                     enabled=os.environ.get('ROCOTO_ORDERS_LLM', 'on').lower() != 'off')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['commission', 'used'])
    parser.add_argument('--state', type=Path, required=True)
    args = parser.parse_args()
    ledger = Ledger(args.state / LEDGER_NAME, CEILINGS)
    if args.action == 'commission':
        ledger.commission()
        print('Specification and proposal call ledger commissioned.')
    else:
        print(json.dumps({route: dict(zip(('day', 'month'), ledger.used(route))) for route in CEILINGS}))


if __name__ == '__main__':
    main()
