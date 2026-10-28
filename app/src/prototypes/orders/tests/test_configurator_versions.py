"""The native version bridge changes the public document and the server-priced catalogue together."""
import hashlib
import json

import pytest
from configurator_versions import Bridge, Conflict, dump, script
from test_order_api import (  # noqa: F401 - shared isolated API fixture
    get_json,
    order,
    request,
)

pytest_plugins = ["test_order_api"]


def document():
    return {'schema': 'rocoto.manufacturer.configurator.v1', 'configuration': {'slug': 'example',
            'accent': '#123456', 'questionnaire': {'questions': []}},
            'catalogue': {'currency': 'EUR', 'vat': .2, 'services': [], 'rules': {}, 'cats': [{'code': 'square',
                'shape': 'sq_tube', 'items': [{'c': 'A', 'p': 30, 's': '40x40x3', 'w': 6, 'L': 6,
                'cut': 1, 'd': [40, 40, 3], 'r': {'k': 'len', 'l': [6]}}]}]}, 'attachments': []}


def payload(revision=1, doc=None):
    doc = doc or document()
    return {'company_id': 'native-a', 'company_slug': 'example', 'version': {
        'id': str(revision).zfill(32), 'revision': revision, 'document': doc,
        'sha256': hashlib.sha256(dump(doc).encode()).hexdigest()}}


def test_exact_snapshot_replay_monotonicity_and_restore(tmp_path):
    bridge = Bridge(tmp_path, token='t'*32, company='example', scope='native-a')
    first = bridge.publish('example', payload())
    assert bridge.publish('example', payload()) == first
    changed = document()
    changed['configuration']['accent'] = '#654321'
    bridge.publish('example', payload(2, changed))
    with pytest.raises(Conflict):
        bridge.publish('example', payload())
    restored = bridge.publish('example', payload(3))
    assert restored['sha256'] == first['sha256']
    assert bridge.active('example')['document'] == document()
    assert bridge.active('foreign') is None
    assert bridge.authorized('example', 'Bearer '+'t'*32, 'native-a')
    assert not bridge.authorized('example', 'Bearer '+'t'*32, 'native-b')


@pytest.mark.parametrize('change', [lambda d: d['configuration'].update(accent='red;background:red'),
    lambda d: d['configuration'].update(headline='<script>alert(1)</script>'),
    lambda d: d['configuration'].update(drawings={'bad':'<svg><script>alert(1)</script></svg>'}),
    lambda d: d['configuration'].update(logo='javascript:alert(1)')])
def test_receiver_rejects_active_content(tmp_path, change):
    bridge = Bridge(tmp_path, company='example', scope='native-a')
    doc = document()
    change(doc)
    with pytest.raises(ValueError):
        bridge.publish('example', payload(doc=doc))
    assert bridge.active('example') is None


def test_dynamic_script_preserves_renderer_and_json_boundaries():
    source = '/* built */\nwindow.RocotoConfig={"accent":"#000000","base":"/example/rocoto/","strings":{}};\nREAL_RENDERER();'
    changed = script(source, document())
    assert changed.endswith(';\nREAL_RENDERER();')
    config, _ = json.JSONDecoder().raw_decode(changed.split('window.RocotoConfig=',1)[1])
    assert config['accent'] == '#123456'
    assert config['base'] == '/example/rocoto/'
    assert config['questionnaire'] == {'questions': []}


def test_api_catalogue_and_quote_share_active_version(order_api):
    import http.client

    import serve
    # Fixture server's handler is reachable through its class instance only in a new listener.
    database, root = order_api[1], order_api[2]
    state = database.parents[2]
    bridge = Bridge(state, token='s'*32, company='example', scope='native-a')
    server = serve.server(root, 0, state, bridge=bridge)
    import threading
    threading.Thread(target=server.serve_forever, daemon=True).start()
    api = (server.server_address[1], database, root)
    def post(body, scope='native-a'):
        conn = http.client.HTTPConnection('127.0.0.1', api[0])
        conn.request('POST','/example/rocoto/api/configurator-version',json.dumps(body),{
            'Content-Type':'application/json','Authorization':'Bearer '+'s'*32,'X-Rocoto-Company':scope})
        response = conn.getresponse()
        result = response.status, json.loads(response.read())
        conn.close()
        return result
    try:
        assert post(payload(), 'foreign')[0] == 403
        assert post(payload())[0] == 200
        assert get_json(api, '/example/rocoto/catalog.json')[1]['cats'][0]['items'][0]['p'] == 30
        assert request(api, 'quote', order())[1]['quote']['gross'] == 30
        assert post(payload(0))[0] == 409
    finally:
        server.shutdown()
        server.server_close()


def test_native_source_price_overrides_keep_their_basis():
    from configurator_versions import catalogue
    doc = document()
    doc['catalogue']['price_overrides'] = [{'item_id':'A','basis':'p','amount':45},
                                         {'item_id':'A','basis':'cut','amount':3.5}]
    row = catalogue(doc)['cats'][0]['items'][0]
    assert row['p'] == 45 and row['cut'] == 3.5
    assert doc['catalogue']['cats'][0]['items'][0]['p'] == 30
