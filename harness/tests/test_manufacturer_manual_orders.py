"""Staff order admission and retry contracts; no model or mail provider calls."""
import copy
import io
import json
import urllib.error
from types import SimpleNamespace

import pytest

from test_manufacturer_platform import extension
from test_manufacturer_source_http import binding
from manufacturer_manual_orders import create, validate
from manufacturer_source_http import RemoteCompanySource
from manufacturer_store import Conflict, Invalid, SourceUnavailable


def payload():
    return {'idempotency_key': 'manual-order-12345678', 'customer': {
        'company': 'Example Works', 'name': 'Buyer', 'phone': '+35912345678',
        'line1': '1 Main St', 'zip': '1000', 'city': 'Sofia', 'warehouseId': 'sofia'},
        'lines': [{'article': '101081', 'quantity': 2}], 'fulfilment': 'delivery'}


def test_staff_command_uses_native_actor_and_invalidates_customer_cache(tmp_path):
    ext, _ = extension(tmp_path)
    calls = []
    ext.source = SimpleNamespace(create_order=lambda value: calls.append(value) or {'ok': True, 'order_id': 'order-1'})
    ext._customers_cache = 'stale'
    assert create(ext, 'bob', payload())['order_id'] == 'order-1'
    assert calls[0]['actor'] == {'id': 'bob', 'name': 'bob'}
    assert calls[0]['idempotency_key'] == payload()['idempotency_key']
    assert ext._customers_cache is None
    with pytest.raises(ValueError):
        create(ext, 'reader', payload())
    with pytest.raises(Invalid):
        create(ext, 'bob', {**payload(), 'actor': {'id': 'alice'}})
    assert len(calls) == 1


@pytest.mark.parametrize('change', [
    lambda value: value['customer'].update(company=''),
    lambda value: value['customer'].update(phone='', email=''),
    lambda value: value['customer'].update(phone='letters'),
    lambda value: value['customer'].update(email='bad'),
    lambda value: value['customer'].update(line1=''),
    lambda value: value['customer'].update(company='x' * 201),
    lambda value: value['customer'].update(poNumber='x' * 101),
    lambda value: value['customer'].update(notes='x' * 2001),
    lambda value: value['lines'][0].update(quantity=True),
    lambda value: value['lines'][0].update(quantity=1.5),
    lambda value: value['lines'][0].update(quantity=10000),
    lambda value: value['lines'][0].update(quantity=float('nan')),
    lambda value: value['lines'].append(copy.deepcopy(value['lines'][0])),
    lambda value: value.update(original_file={'filename':'../../secret.txt', 'content_type':'text/plain', 'content_base64':'eA=='}),
    lambda value: value.update(original_file={'filename':'source.txt', 'content_type':'text/plain', 'content_base64':'invalid'}),
    lambda value: value.update(original_file={'filename':'source.tsv', 'content_type':'text/tab-separated-values', 'content_base64':'eA=='}),
])
def test_invalid_staff_orders_stop_before_source(change):
    value = payload()
    change(value)
    with pytest.raises(Invalid):
        validate(value)


def test_pickup_and_original_document_preserve_values():
    value = payload()
    value['fulfilment'] = 'pickup'
    value['customer'].pop('line1')
    value['original_file'] = {'filename':'source.txt', 'content_type':'text/plain', 'content_base64':'eA=='}
    assert validate(value) == value


def test_receiver_transport_keeps_company_scope_command_identity_and_actor(tmp_path, monkeypatch):
    binding(tmp_path)
    monkeypatch.setenv('ROCOTO_MANUFACTURER_ORDERS_TOKEN', 'x' * 40)
    calls = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self, maximum): return b'{"ok":true,"order_id":"order-1"}'
    class Opener:
        def open(self, request, timeout):
            calls.append(request)
            return Response()
    monkeypatch.setattr('urllib.request.build_opener', lambda *_: Opener())
    source = RemoteCompanySource(tmp_path, 'a' * 64)
    assert source.create_order(payload()) == source.create_order(payload()) == {'ok': True, 'order_id': 'order-1'}
    assert calls[0].full_url == 'https://orders.example.test/sample-hardware/rocoto/api/platform-orders'
    assert calls[0].get_header('X-rocoto-company') == 'a' * 64
    assert calls[0].get_header('Authorization') == 'Bearer ' + 'x' * 40
    assert calls[0].data == calls[1].data


@pytest.mark.parametrize('status,error', [(400, Invalid), (409, Conflict), (503, SourceUnavailable)])
def test_receiver_errors_keep_retry_semantics(tmp_path, monkeypatch, status, error):
    binding(tmp_path)
    monkeypatch.setenv('ROCOTO_MANUFACTURER_ORDERS_TOKEN', 'x' * 40)
    class Opener:
        def open(self, request, timeout):
            raise urllib.error.HTTPError(request.full_url, status, 'error', {}, io.BytesIO(json.dumps({'detail':'Проверете склада.'}).encode()))
    monkeypatch.setattr('urllib.request.build_opener', lambda *_: Opener())
    with pytest.raises(error):
        RemoteCompanySource(tmp_path, 'a' * 64).create_order(payload())


def test_workspace_capability_keeps_manual_editor_and_blocks_agent_mutations(tmp_path):
    ext, _ = extension(tmp_path)
    assert ext.agent_editing_enabled() is True
    document = ext.platform.configurator()['document']
    document['configuration']['checkout'] = {'agentEditing': False, 'customerResearch': False}
    ext.save_configurator('alice', {'document': document, 'expected_revision': 0}, 'Requested manual workspace')
    assert ext.configurator('alice')['capabilities'] == {'agent_editing': False, 'customer_research': False}
    assert ext.actor('bob')['can_create_orders'] is True
    assert ext.actor('reader')['can_create_orders'] is False
    with pytest.raises(ValueError):
        ext.save_configurator('alice', {'settings': {'headline': 'AI edit'}, 'expected_revision': 1}, 'Agent', actor_type='agent')
    with pytest.raises(ValueError):
        ext.draft_agent('customer-research', 'company', 'alice')
    assert ext.save_configurator('alice', {'settings': {'headline': 'Manual edit'}, 'expected_revision': 1}, 'Manual')['revision'] == 2


def test_manual_command_stream_stops_before_oversized_chunk():
    import asyncio
    from manufacturer_source_files import UploadRequestLimit
    forwarded, sent = [], []
    chunks = iter([b'x' * 1_000_000] * 7)
    async def receive():
        return {'type': 'http.request', 'body': next(chunks), 'more_body': True}
    async def send(message):
        sent.append(message)
    async def parser(scope, incoming, outgoing):
        while True:
            forwarded.append(await incoming())
    scope = {'type': 'http', 'method': 'POST', 'path': '/api/manufacturer/orders', 'headers': []}
    asyncio.run(UploadRequestLimit(parser)(scope, receive, send))
    assert sent[0]['status'] == 413
    assert len(forwarded) == 6


def test_native_http_creation_rechecks_membership_and_page_marker(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path
    script = r'''
import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import layout
layout.install('manufacturer')
import server
from fastapi.testclient import TestClient
app=server.create_app(Path(sys.argv[2]))
command=json.loads(sys.argv[3])
with TestClient(app) as client:
    assert client.post('/api/manufacturer/orders',json=command,headers={'X-Rocoto-Page':'1'}).status_code==401
    code=app.state.access.issue('demo',principal_id='office',owner=False)
    assert client.post('/api/session',json={'code':code},headers={'X-Rocoto-Page':'1'}).status_code==200
    extension=app.state.workspaces['demo']['vertical']
    writes=[]
    extension.source.create_order=lambda value: writes.append(value) or {'ok':True,'order_id':'new-order'}
    assert client.post('/api/manufacturer/orders',json=command).status_code==403
    response=client.post('/api/manufacturer/orders',json=command,headers={'X-Rocoto-Page':'1'})
    assert response.status_code==200,response.text
    assert response.json()['order_id']=='new-order'
    assert writes[0]['actor']['id']=='office'
    with app.state.access.connect() as db:
        db.execute('DELETE FROM principal_environments WHERE principal_id=? AND environment=?',('office','demo'))
    assert client.post('/api/manufacturer/orders',json=command,headers={'X-Rocoto-Page':'1'}).status_code in {401,403}
    assert len(writes)==1
'''
    result = subprocess.run([sys.executable, '-B', '-c', script, str(Path(__file__).resolve().parents[1]),
                             str(tmp_path / 'state'), json.dumps(payload())],
                            env={**os.environ, 'ROCOTO_VERTICAL': 'manufacturer'},
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
