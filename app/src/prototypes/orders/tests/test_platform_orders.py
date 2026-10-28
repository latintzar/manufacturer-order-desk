"""Staff intake uses source prices, scoped access and durable retry identity."""
import base64
import copy
import http.client
import json
from pathlib import Path

import pytest
from store import CompanyStore
from test_platform_files import PDF, TOKEN
from test_platform_files import platform_api as platform_api_fixture

platform_api = platform_api_fixture

pytest_plugins = ['test_platform_files']


def payload():
    return {'idempotency_key': 'staff-order-request-0001',
            'customer': {'company': 'Example Installer', 'name': 'Buyer', 'phone': '+359888123456'},
            'lines': [{'article': 'A', 'quantity': 2}], 'fulfilment': 'pickup',
            'actor': {'id': 'operator-1', 'name': 'Office'}}


def post(api, body, *, scope='native-a', token=TOKEN):
    conn = http.client.HTTPConnection('127.0.0.1', api[0], timeout=10)
    conn.request('POST', '/example/rocoto/api/platform-orders', json.dumps(body), {
        'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token, 'X-Rocoto-Company': scope})
    result = conn.getresponse()
    status, raw = result.status, result.read()
    conn.close()
    return status, json.loads(raw) if raw.startswith(b'{') else {}


def test_staff_order_recomputes_price_persists_once_and_holds_mail(platform_api):
    status, first = post(platform_api, payload())
    assert status == 201, first
    store = CompanyStore(platform_api[1])
    order = store.read_order(first['order_id'])
    assert order['quote']['gross'] == 40
    assert order['customer']['company'] == 'Example Installer'
    assert order['customer']['entry_source'] == 'staff'
    assert order['customer']['phone'] == '+359888123456'
    assert order['state'] == 'requested'
    store.set_price('A', 30, 'test', 'new catalogue')
    status, again = post(platform_api, payload())
    assert status == 200 and again['order_id'] == first['order_id']
    assert again['quote']['gross'] == 40
    assert store.one('SELECT COUNT(*) AS n FROM orders')['n'] == 1
    assert store.one('SELECT SUM(reserved) AS n FROM stock')['n'] in (0, None)
    assert not store.one("SELECT name FROM sqlite_master WHERE type='table' AND name='customer_mail_outbox'") or store.one('SELECT COUNT(*) AS n FROM customer_mail_outbox')['n'] == 0
    changed = payload()
    changed['lines'][0]['quantity'] = 3
    assert post(platform_api, changed)[0] == 400
    store.close()


@pytest.mark.parametrize('access', [{'scope': 'foreign'}, {'token': ''}])
def test_staff_order_is_company_scoped(platform_api, access):
    assert post(platform_api, payload(), **access)[0] == 403


@pytest.mark.parametrize('change', [
    {'lines': [{'article': 'invented', 'quantity': 1}]},
    {'lines': [{'article': 'A', 'quantity': True}]},
    {'lines': [{'article': 'A', 'quantity': 0}]},
    {'lines': [{'article': 'A', 'quantity': 1, 'price': .01}]},
    {'customer': {'company': 'X', 'name': 'Y', 'phone': 'abc'}},
    {'customer': {'company': '', 'name': 'Y', 'email': 'y@example.test'}},
    {'customer': {'company': 'X', 'name': 'Y', 'email': 'y@example.test', 'warehouseId': 'invented'}},
    {'fulfilment': 'delivery'},
    {'customer': {'company': 'X', 'name': 'Y', 'email': 'y@example.test', 'is_demo': 'true'}},
    {'actor': {'id': '', 'name': 'Office'}}])
def test_invalid_staff_submission_leaves_order_store_unchanged(platform_api, change):
    body = {**payload(), **change}
    assert post(platform_api, body)[0] == 400
    store = CompanyStore(platform_api[1])
    assert store.one('SELECT COUNT(*) AS n FROM orders')['n'] == 0
    store.close()


def test_original_file_claimed_once_and_retry_validated(platform_api):
    body = payload()
    body['original_file'] = {'filename': 'Order.pdf', 'content_type': 'application/pdf',
                             'content_base64': base64.b64encode(PDF).decode()}
    status, first = post(platform_api, body)
    assert status == 201, first
    assert post(platform_api, body)[1]['order_id'] == first['order_id']
    store = CompanyStore(platform_api[1])
    files = store.rows('SELECT id,order_id,name FROM order_files')
    assert len(files) == 1 and files[0]['order_id'] == first['order_id']
    assert store.read_order(first['order_id'])['customer']['capture']['specification']['file']['name'] == 'Order.pdf'
    bad = copy.deepcopy(body)
    bad['original_file']['content_base64'] = base64.b64encode(PDF + b'changed').decode()
    assert post(platform_api, bad)[0] == 400
    store.close()


@pytest.mark.parametrize('requested_date', ['', '2026-11-20'])
def test_complete_native_drawer_payload_retains_optional_date_and_replays(platform_api, requested_date):
    body = json.loads((Path(__file__).parent / 'fixtures/native-staff-order.json').read_text())
    body['actor'] = {'id': 'native-operator', 'name': 'QA operator'}
    body['customer']['needBy'] = requested_date
    store = CompanyStore(platform_api[1])
    catalogue = store.export_catalog()
    catalogue['cats'][0]['items'][0]['c'] = '101081'
    configuration = json.loads(store.one('SELECT config FROM company')['config'])
    configuration['checkout'] = {'warehouses': [{'id': 'varna-main', 'name': 'QA warehouse', 'erpCode': 'QA-VARNA'}]}
    store.ingest_catalog(catalogue, configuration, 'test', 'synthetic native contract')
    status, first = post(platform_api, body)
    assert status == 201, first
    order = store.read_order(first['order_id'])
    assert order['customer']['needBy'] == requested_date
    assert order['customer']['warehouseId'] == 'varna-main'
    assert order['customer']['capture']['specification']['file']['name'] == 'native-release-qa.txt'
    assert order['state'] == 'requested' and order['quote']['fulfilment'] == 'pickup'
    assert post(platform_api, body)[1]['order_id'] == first['order_id']
    assert store.one('SELECT COUNT(*) AS n FROM orders')['n'] == 1
    assert store.one('SELECT COUNT(*) AS n FROM order_files')['n'] == 1
    assert store.one('SELECT SUM(reserved) AS n FROM stock')['n'] in (0, None)
    assert not store.one("SELECT name FROM sqlite_master WHERE type='table' AND name='customer_mail_outbox'")
    store.close()


@pytest.mark.parametrize('requested_date', ['2026-02-30', '20261120', '20/11/2026', 'soon'])
def test_invalid_requested_date_returns_native_field_error_before_writes(platform_api, requested_date):
    body = payload()
    body['customer']['needBy'] = requested_date
    status, result = post(platform_api, body)
    assert status == 400
    assert result['detail'] == result['message']
    assert 'date' in result['detail']
    store = CompanyStore(platform_api[1])
    assert store.one('SELECT COUNT(*) AS n FROM orders')['n'] == 0
    store.close()


def test_quantity_error_uses_native_detail_envelope(platform_api):
    body = payload()
    body['lines'][0]['quantity'] = 1.5
    status, result = post(platform_api, body)
    assert status == 400
    assert result['detail'] == result['message']
    assert 'whole number' in result['detail']
