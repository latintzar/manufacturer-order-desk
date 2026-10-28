"""Authenticated staff intake into the same authoritative company order store."""
from __future__ import annotations

import base64
import binascii
import hashlib
import re
from datetime import date

import customer_details
import order_files
import quote as pricing_quote
from supply import public_ready

MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_REQUEST_BYTES = 6 * 1024 * 1024
CUSTOMER_FIELDS = frozenset({'company', 'name', 'email', 'phone', 'language', 'poNumber',
    'warehouseId', 'line1', 'zip', 'city', 'coName', 'eik', 'vatNo', 'bline1', 'bzip', 'bcity',
    'website', 'trade', 'notes', 'mol', 'kind', 'project', 'needBy'})


def create(store, data, catalogue, config):
    if not isinstance(data, dict) or set(data) - {'idempotency_key', 'customer', 'lines', 'fulfilment', 'original_file', 'actor'}:
        raise ValueError('Check the order details.')
    key = data.get('idempotency_key')
    if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,128}', key):
        raise ValueError('Refresh the form and try again.')
    actor = data.get('actor')
    if (not isinstance(actor, dict) or set(actor) != {'id', 'name'}
            or any(not isinstance(actor[k], str) or not 1 <= len(actor[k].strip()) <= 200
                   or any(ord(c) < 32 for c in actor[k]) for k in ('id', 'name'))):
        raise ValueError('Sign in to your workspace account.')
    source_actor = 'platform:' + actor['id']
    # Resolve an already committed operation before catalogue changes or file staging.
    replay = store.replay('orders.submit', {'request': data}, source_actor, key)
    if replay is not None:
        return {'ok': True, **replay, 'ready': public_ready(replay['ready']),
                'order_id': replay['id']}, True
    raw_customer = data.get('customer')
    if not isinstance(raw_customer, dict) or set(raw_customer) - CUSTOMER_FIELDS:
        raise ValueError('Check the customer details.')
    requested_date = raw_customer.get('needBy', '')
    try:
        if not isinstance(requested_date, str):
            raise ValueError()
        if requested_date.strip():
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', requested_date.strip()):
                raise ValueError()
            date.fromisoformat(requested_date.strip())
    except ValueError:
        raise ValueError('Enter a valid date in YYYY-MM-DD format.') from None
    customer = customer_details.validate(raw_customer,
        {**config, 'checkout': {**config.get('checkout', {}), 'companyRequired': True}}, allow_phone=True)
    if not customer.get('name'):
        raise ValueError('Enter a contact name.')
    fulfilment = data.get('fulfilment')
    if fulfilment not in {'delivery', 'pickup'}:
        raise ValueError('Choose delivery or warehouse collection.')
    if fulfilment == 'delivery' and not all(customer.get(k) for k in ('line1', 'zip', 'city')):
        raise ValueError('Enter the delivery address.')
    lines = data.get('lines')
    if not isinstance(lines, list) or not 1 <= len(lines) <= 100:
        raise ValueError('Add between 1 and 100 items.')
    items = {item['c']: item for cat in catalogue.get('cats', []) for item in cat.get('items', [])}
    prepared, seen = [], set()
    for line in lines:
        if not isinstance(line, dict) or set(line) != {'article', 'quantity'}:
            raise ValueError('Choose an item and quantity.')
        code, quantity = line['article'], line['quantity']
        if not isinstance(code, str) or code not in items or code in seen:
            raise ValueError('Choose distinct catalogue items.')
        if type(quantity) is not int or not 1 <= quantity <= 9999:
            raise ValueError('Enter a whole number from 1 to 9999.')
        seen.add(code)
        item = items[code]
        if item.get('r', {}).get('k') not in {'whole', 'len'} or item.get('a', {}).get('article_status') == 'request':
            raise ValueError('Specify this item’s dimensions in the configurator.')
        # Staff enters complete catalogue pieces; cutting stays in the configurator.
        length = item.get('L', 0) * 1000
        rows = []
        remaining = quantity
        while remaining:
            count = min(remaining, 999)
            rows.append({'x': length, 'n': count})
            remaining -= count
        prepared.append({'code': code, 'rows': rows})
    priced = pricing_quote.quote(catalogue, prepared)
    priced['quote']['fulfilment'] = fulfilment
    customer.update(entry_source='staff', entered_by=actor['name'], language=customer.get('language') or 'en')
    original = data.get('original_file')
    if original is not None:
        if not isinstance(original, dict) or set(original) != {'filename', 'content_type', 'content_base64'}:
            raise ValueError('Choose the original document.')
        if any(not isinstance(original[k], str) for k in original) or len(original['content_base64']) > (MAX_FILE_BYTES + 2) // 3 * 4:
            raise ValueError('Choose a document up to 4 MB.')
        try:
            body = base64.b64decode(original['content_base64'], validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError('Choose the original document again.') from exc
        if not body or len(body) > MAX_FILE_BYTES:
            raise ValueError('Choose a document up to 4 MB.')
        # Content type is derived from validated bytes, never trusted from the caller.
        upload_key = hashlib.sha256(('platform-order:' + source_actor + ':' + key).encode()).hexdigest()
        metadata = order_files.stage(store, original['filename'], body, upload_key)
        customer.update(specification_file=metadata['id'], capture={
            'schema': 'rocoto.orders.capture.v1', 'entry_path': 'specification', 'language': customer['language'],
            'specification': {'text': '', 'lines': [], 'file_id': metadata['id']}})
    result = store.submit_order(customer, priced['lines'], priced['quote'], key,
                                source_actor, 'company staff order entry', request=data)
    # Entry persists a request. Sending and accepting are separate, explicit commands.
    return {'ok': True, **result, 'ready': public_ready(result['ready']), 'order_id': result['id']}, False
