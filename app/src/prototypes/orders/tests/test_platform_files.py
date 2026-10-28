"""A company connection reads only original files attached to its selected order."""
import hashlib
import http.client
import json
import threading
from urllib.parse import urlencode

import pytest
from configurator_versions import Bridge
from platform_source import read
from store import CompanyStore
from test_order_api import order, request, upload

import serve

pytest_plugins = ['test_order_api']
PDF = b'%PDF-1.4\n1 0 obj <</Type /Catalog>> endobj\n%%EOF\n'
TOKEN = 'f' * 32


@pytest.fixture
def platform_api(order_api):
    database, root = order_api[1:]
    state = database.parents[2]
    server = serve.server(root, 0, state, bridge=Bridge(state, token=TOKEN, company='example', scope='native-a'))
    # Each fixture represents a separate service, with its own request budget.
    server.RequestHandlerClass.requests = {}
    server.RequestHandlerClass.relay_requests = {}
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1], database, root
    server.shutdown()
    server.server_close()


def platform_get(api, resource, order_id, file_id='', *, scope='native-a', token=TOKEN, company='example'):
    connection = http.client.HTTPConnection('127.0.0.1', api[0], timeout=10)
    query = urlencode({'resource': resource, 'id': order_id, 'file_id': file_id})
    connection.request('GET', f'/{company}/rocoto/api/platform-state?{query}', headers={
        'Authorization': 'Bearer ' + token, 'X-Rocoto-Company': scope})
    response = connection.getresponse()
    result = response.status, dict(response.getheaders()), response.read()
    connection.close()
    return result


def attached(api, key='attached-specification'):
    status, staged = upload(api, 'Door schedule.pdf', PDF, key=key + '-upload')
    assert status == 201
    metadata = {k: v for k, v in staged['upload'].items() if k != 'discard_token'}
    payload = order()
    payload['customer'].update(specification_file=metadata['id'], capture={
        'schema': 'rocoto.orders.capture.v1', 'entry_path': 'specification', 'language': 'en',
        'specification': {'text': 'Replacement locks', 'lines': [], 'file_id': metadata['id']}})
    status, saved = request(api, 'orders', payload, key=key + '-order')
    assert status == 201, saved
    return saved['id'], metadata, payload


def test_original_pdf_metadata_is_authoritative_durable_and_replayed(platform_api):
    order_id, metadata, payload = attached(platform_api)
    store = CompanyStore(platform_api[1])
    try:
        snapshot = store.read_order(order_id)['customer']['capture']['specification']
        assert snapshot['file'] == metadata
        assert metadata['sha256'] == hashlib.sha256(PDF).hexdigest()
        assert read(store, 'order_files', order_id=order_id)['files'] == [metadata]
    finally:
        store.close()
    # Identical retry replays even though the upload is now claimed; callback enrichment
    # must not mutate the original idempotency input.
    assert request(platform_api, 'orders', payload, key='attached-specification-order')[1]['id'] == order_id
    status, headers, body = platform_get(platform_api, 'file', order_id, metadata['id'])
    assert status == 200 and body == PDF
    assert headers['Content-Type'] == 'application/octet-stream'
    assert headers['X-File-Content-Type'] == 'application/pdf'
    assert headers['X-Content-SHA256'] == metadata['sha256']
    assert headers['Cache-Control'] == 'private, no-store'
    assert headers['X-Content-Type-Options'] == 'nosniff'
    assert headers['Content-Disposition'].startswith('attachment;')
    status, _, body = platform_get(platform_api, 'order_files', order_id)
    assert status == 200 and json.loads(body)['files'] == [metadata]
    assert b'discard_token' not in body and b'upload_key' not in body


@pytest.mark.parametrize('access', [
    {'scope': 'foreign-company'}, {'token': 'wrong-token'}, {'company': 'foreign'}])
def test_file_reads_require_existing_native_company_binding(platform_api, access):
    order_id, metadata, _ = attached(platform_api)
    for resource in ('file', 'order_files'):
        assert platform_get(platform_api, resource, order_id, metadata['id'], **access)[0] == 403


def test_pending_other_order_and_invalid_file_references_are_inaccessible(platform_api):
    order_id, metadata, _ = attached(platform_api)
    status, second = request(platform_api, 'orders', order(), key='another-real-order')
    assert status == 201
    status, pending = upload(platform_api, 'Pending.pdf', PDF, key='pending-platform-pdf')
    assert status == 201
    for requested_order, file_id in ((second['id'], metadata['id']), (order_id, pending['upload']['id']),
                                     ('a' * 32, metadata['id']), (order_id, '../company.db')):
        assert platform_get(platform_api, 'file', requested_order, file_id)[0] == 404
    assert platform_get(platform_api, 'order_files', 'a' * 32)[0] == 404
    status, _, body = platform_get(platform_api, 'order_files', second['id'])
    assert status == 200 and json.loads(body)['files'] == []


def test_changed_or_missing_original_file_fails_custody_check(platform_api):
    order_id, metadata, _ = attached(platform_api)
    path = platform_api[1].parent / 'order-files' / metadata['id']
    path.write_bytes(PDF + b'changed')
    assert platform_get(platform_api, 'file', order_id, metadata['id'])[0] == 404
    path.unlink()
    assert platform_get(platform_api, 'file', order_id, metadata['id'])[0] == 404


def test_public_capture_cannot_assert_trusted_file_metadata(platform_api):
    payload = order()
    payload['customer']['capture'] = {'schema': 'rocoto.orders.capture.v1',
        'entry_path': 'specification', 'language': 'en', 'specification': {
            'text': '', 'lines': [], 'file': {'id': 'a' * 32, 'name': 'Forged.pdf'}}}
    assert request(platform_api, 'orders', payload, key='forged-file-metadata')[0] == 400


def test_database_company_must_match_bound_route(platform_api):
    order_id, metadata, _ = attached(platform_api)
    store = CompanyStore(platform_api[1])
    try:
        store.db.execute("UPDATE company SET id='another-company'")
    finally:
        store.close()
    assert platform_get(platform_api, 'file', order_id, metadata['id'])[0] == 403
    assert platform_get(platform_api, 'order_files', order_id)[0] == 403


def test_failed_original_file_custody_rolls_back_order_and_claim(platform_api):
    status, staged = upload(platform_api, 'Missing.pdf', PDF, key='missing-upload-original')
    assert status == 201
    identifier = staged['upload']['id']
    path = platform_api[1].parent / 'order-files' / identifier
    path.write_bytes(PDF + b'changed')
    payload = order()
    payload['customer']['specification_file'] = identifier
    assert request(platform_api, 'orders', payload, key='missing-original-order')[0] == 400
    store = CompanyStore(platform_api[1])
    try:
        assert store.one('SELECT count(*) AS count FROM orders')['count'] == 0
        assert store.one('SELECT count(*) AS count FROM customers')['count'] == 0
        assert store.one('SELECT order_id FROM order_files WHERE id=?', (identifier,))['order_id'] is None
    finally:
        store.close()
