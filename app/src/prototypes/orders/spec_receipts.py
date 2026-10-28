"""Server-retained allocation readings bind confirmation to the submitted original."""
from __future__ import annotations

import json
import re
import time
import uuid
from collections import Counter


def record(store, data, result):
    review = result.get('review')
    if not isinstance(review, dict) or review.get('schema') != 'rocoto.orders.allocations.v1':
        return result
    store.db.execute('CREATE TABLE IF NOT EXISTS specification_readings(id TEXT PRIMARY KEY, upload_id TEXT, source TEXT NOT NULL, result TEXT NOT NULL, created_at REAL NOT NULL)')
    # Readings expire with unclaimed uploads; accepted orders retain their full snapshot.
    store.db.execute('DELETE FROM specification_readings WHERE created_at<?', (time.time()-86400,))
    if store.one('SELECT COUNT(*) AS n FROM specification_readings')['n'] >= 2000:
        raise ValueError('Опитайте прочитането на документа по-късно.')
    identifier = uuid.uuid4().hex
    payload = json.dumps({'review': review, 'lines': result['lines']}, ensure_ascii=False, allow_nan=False)
    if len(payload.encode()) > 512000:
        raise ValueError('Разделете документа на по-малки поръчки.')
    store.db.execute('INSERT INTO specification_readings VALUES(?,?,?,?,?)',
        (identifier, data.get('upload'), data.get('text', ''), payload, time.time()))
    store.db.commit()
    return {**result, 'reading_id': identifier}


def validate(store, customer, lines):
    capture = customer.get('capture', {}).get('specification', {})
    identifier = capture.get('reading_id')
    upload = customer.get('specification_file')
    exists = store.one("SELECT 1 FROM sqlite_master WHERE type='table' AND name='specification_readings'")
    latest = None
    if exists:
        if upload:
            latest = store.one('SELECT id FROM specification_readings WHERE upload_id=? ORDER BY created_at DESC LIMIT 1', (upload,))
        elif capture.get('text'):
            latest = store.one('SELECT id FROM specification_readings WHERE upload_id IS NULL AND source=? ORDER BY created_at DESC LIMIT 1', (capture['text'],))
    if not identifier:
        if latest:
            raise ValueError('Проверете разпределението по обекти и го потвърдете.')
        return customer
    if not isinstance(identifier, str) or not re.fullmatch(r'[a-f0-9]{32}', identifier) or not exists:
        raise ValueError('Прочетете спецификацията отново.')
    receipt = store.one('SELECT * FROM specification_readings WHERE id=?', (identifier,))
    if (not receipt or receipt['created_at'] < time.time()-86400 or receipt['upload_id'] != upload
            or receipt['source'] != capture.get('text', '') or capture.get('allocations_confirmed') is not True):
        raise ValueError('Проверете разпределението по обекти и го потвърдете.')
    saved = json.loads(receipt['result'])
    review = saved['review']
    if review.get('issues'):
        raise ValueError('Уточнете отбелязаните клетки в оригиналния документ.')
    selected = capture.get('lines', [])
    if len(selected) != len(saved['lines']):
        raise ValueError('Потвърдете всички редове от спецификацията.')
    required, actual = Counter(), Counter()
    allocations = []
    for original, chosen in zip(saved['lines'], selected):
        if (chosen['source'] != original['source'] or chosen['quantity'] != original['qty']
                or not chosen['selected_code'] or chosen['selected_code'] not in original.get('matches', [])):
            raise ValueError('Проверете артикулите и количествата от спецификацията.')
        required[chosen['selected_code']] += chosen['quantity']
    for line in lines:
        actual[line['item_id']] += line.get('requested_quantity', line['quantity'])
    if actual != required:
        raise ValueError('Съгласувайте количествата в поръчката с разпределението по обекти.')
    for allocation in review.get('allocations', []):
        index = allocation.get('line')
        if type(index) is not int or not 0 <= index < len(selected):
            raise ValueError('Прочетете разпределението отново.')
        allocations.append({**allocation, 'selected_code': selected[index]['selected_code']})
    # This field is server-owned; customer_details rejects it on incoming requests.
    result = json.loads(json.dumps(customer))
    result['capture']['specification']['allocation_review'] = {**review, 'allocations': allocations}
    return result
