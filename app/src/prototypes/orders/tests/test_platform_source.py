"""Company platform reads preserve the complete order and exact active document."""
import copy

import pytest
from platform_source import read
from test_store import store as store
from test_store import submit


def test_orders_include_company_information_and_exact_lines(store):
    created = submit(store)
    value = read(store, 'orders')['orders'][0]
    full = read(store, 'order', order_id=created['id'])['order']
    assert value == full
    assert full['id'] == created['id'] and full['items_count'] == 1
    assert full['customer']['email']
    assert full['lines'] and full['quote']
    assert full['status'] == 'requested'
    with pytest.raises(LookupError):
        read(store, 'order', order_id='another-company-order')


def test_active_snapshot_replaces_configuration_and_catalogue_together(store):
    document = read(store, 'document')['document']
    active = copy.deepcopy(document)
    active['configuration']['headline'] = 'Saved version'
    active['catalogue']['cats'][0]['items'][0]['p'] = 42
    assert read(store, 'document', document=active)['document'] == active
    assert read(store, 'company', document=active)['company']['headline'] == 'Saved version'
    active['configuration']['slug'] = 'somebody-else'
    with pytest.raises(ValueError):
        read(store, 'document', document=active)


def hardware_catalogue(store):
    catalog = {'company': {'en': 'Example'}, 'source': 'https://example.test/catalogue',
        'currency': 'EUR', 'vat': 0.2, 'rules': {}, 'services': [], 'cats': [{
            'code': 'mortise', 'en': 'Mortise lock 55/72', 'img': '/wp-content/lock.jpg',
            'url': {'en': 'https://example.test/locks/5572'}, 'items': [
                {'c': code, 'p': price, 'q': pending, 'u': 'pc', 'r': {'k': 'whole'},
                 'se': 'Nickel, with strike plate', 'a': {'backset': 55, 'centres': 72}}
                for code, price, pending in [('Q', 0, 1), ('P', 10, 0), ('F', 0, 0)]]
        }]}
    store.ingest_catalog(catalog, {'slug': 'example'}, 'test', 'Source-backed hardware fixture')


def hardware_order(store, codes, key):
    from quote import quote
    priced = quote(store.export_catalog(), [{'code': code, 'rows': [{'x': 0, 'n': 2}]} for code in codes])
    return store.submit_order({'name': 'Alex Buyer', 'email': 'alex@network.rca.ac.uk',
        'trade': 'Door installation', 'project': 'Six apartment doors'}, priced['lines'], priced['quote'],
        key, 'test', 'Submitted checkout')


def test_quote_request_uses_real_products_and_keeps_price_missing(store):
    hardware_catalogue(store)
    made = hardware_order(store, ['Q'], 'request')
    result = read(store, 'order', order_id=made['id'])['order']
    assert result['display_number'] == result['number'] == '#1001'
    assert result['id'] == made['id']
    assert result['pricing_state'] == 'to_quote' and result['total'] is None and result['priced_total'] is None
    line = result['lines'][0]
    assert line['name'] == 'Mortise lock 55/72' and line['code'] == 'Q'
    assert line['description'] == 'Nickel, with strike plate' and line['attributes']['backset'] == 55
    assert line['quantity'] == 2 and line['unit'] == 'pc'
    assert line['total'] is None and line['unit_price'] is None
    assert line['image_url'] == 'https://orders.example.test/example/wp-content/lock.jpg'
    assert result['customer']['company'] == result['customer']['display_company'] == ''
    assert result['customer']['company_details_needed'] is True
    assert result['customer']['trade'] == 'Door installation' and result['customer']['project'] == 'Six apartment doors'


def test_mixed_request_and_confirmed_zero_price_remain_distinct(store):
    hardware_catalogue(store)
    mixed = hardware_order(store, ['P', 'Q'], 'mixed')
    result = read(store, 'order', order_id=mixed['id'])['order']
    assert result['pricing_state'] == 'partially_priced' and result['total'] is None
    assert result['priced_total'] == 20 and result['lines'][0]['unit_price'] == 10
    assert result['lines'][1]['total'] is None
    free = hardware_order(store, ['F'], 'free')
    result = read(store, 'order', order_id=free['id'])['order']
    assert result['pricing_state'] == 'priced' and result['total'] == 0
    assert result['lines'][0]['unit_price'] == 0 and result['lines'][0]['total'] == 0


def test_order_references_survive_pagination_new_orders_and_database_restore(store, tmp_path):
    import sqlite3
    hardware_catalogue(store)
    first = hardware_order(store, ['Q'], 'first')
    second = hardware_order(store, ['P'], 'second')
    original = {row['id']: row['display_number'] for row in read(store, 'orders')['orders']}
    assert original == {first['id']: '#1001', second['id']: '#1002'}
    hardware_order(store, ['F'], 'third')
    page = read(store, 'orders', limit=1, offset=1)['orders'][0]
    assert page['display_number'] == original[page['id']]
    with sqlite3.connect(tmp_path / 'restored.db') as restored:
        store.db.backup(restored)
        restored.execute('VACUUM')
        restored.row_factory = sqlite3.Row
        from platform_source import project_order
        row = restored.execute('SELECT * FROM orders WHERE id=?', (first['id'],)).fetchone()
        assert project_order(restored, row)['display_number'] == '#1001'


def test_imported_order_without_estimate_cannot_collide_with_new_order(store):
    import json
    hardware_catalogue(store)
    store.db.execute('INSERT INTO customers VALUES(?,?)', ('legacy-customer', json.dumps({'name': 'Imported buyer', 'email': 'legacy@example.invalid'})))
    store.db.execute('INSERT INTO orders VALUES(?,?,?,?,?)', ('legacy-order', 'legacy-customer', 'requested', json.dumps({'gross': 0, 'confirmation': True}), '2026-10-01T00:00:00Z'))
    store.db.execute('INSERT INTO order_lines(order_id,item_id,quantity,data) VALUES(?,?,?,?)', ('legacy-order', 'Q', 2, json.dumps({'item_id': 'Q', 'quantity': 2, 'gross': 0, 'confirmation': True})))
    created = hardware_order(store, ['P'], 'new-after-import')
    legacy = read(store, 'order', order_id='legacy-order')['order']
    normal = read(store, 'order', order_id=created['id'])['order']
    assert legacy['display_number'] == '#L1001'
    assert normal['display_number'] == '#1001'
