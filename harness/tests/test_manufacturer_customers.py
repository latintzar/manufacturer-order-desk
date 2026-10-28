"""Persisted customer requirements, conservative CRM identities and truthful demo provenance."""
# ruff: noqa: E402
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'verticals/manufacturer'))
from manufacturer_source import customer_id, customer_profiles, present_order, heading
from manufacturer_store import Invalid, Missing, SourceUnavailable
from test_manufacturer_platform import extension


def order(identifier='one', *, email='buyer@build.test', company='Builder', website='https://build.test', demo=False, priced=False):
    return {'id': identifier, 'customer_id': 'source-' + identifier, 'number': '#1001', 'display_number': '#1001',
            'created_at': '2026-10-14T12:00:00Z', 'status': 'requested', 'currency': 'EUR',
            'customer': {'name': 'Buyer', 'email': email, 'company': company, 'website': website, 'is_demo': demo},
            'lines': [{'code': '101037', 'name': 'Norma 50/70', 'quantity': 24, 'unit': 'pc',
                       'pricing_state': 'priced' if priced else 'to_quote', 'total': 240 if priced else None}],
            'items_count': 1, 'pricing_state': 'priced' if priced else 'to_quote', 'total': 240 if priced else None}


def capture():
    return {'schema': 'rocoto.orders.capture.v1', 'entry_path': 'questionnaire', 'language': 'en',
            'questionnaire': {'title': 'Help me choose', 'project': 'Door hardware for an apartment building',
                'questions': [
                    {'id': 'door', 'label': 'Door type', 'status': 'answered', 'answers': [{'id': 'entrance', 'label': 'Entrance door'}]},
                    {'id': 'material', 'label': 'Door material', 'status': 'answered', 'answers': [{'id': 'timber', 'label': 'Timber'}]},
                    {'id': 'backset', 'label': 'Backset', 'status': 'unknown', 'answers': []},
                    {'id': 'hand', 'label': 'Opening direction', 'status': 'unanswered', 'answers': []}]}}


def test_saved_questionnaire_becomes_factual_brief_without_inventing_requirements():
    original = order()
    original['customer']['capture'] = capture()
    before = copy.deepcopy(original)
    result = present_order(original)
    assert original == before
    assert result['brief']['title'] == 'Door hardware for an apartment building'
    assert result['brief']['facts'][0] == {'label': 'Door type', 'value': 'Entrance door', 'source': 'questionnaire'}
    assert result['brief']['answers'] == capture()['questionnaire']['questions']
    assert result['brief']['open_questions'] == ['Confirm: Backset', 'Confirm: Opening direction']
    assert result['brief']['quantities'] == [{'unit': 'pc', 'quantity': 24}]
    assert '24 apartments' not in json.dumps(result['brief'])
    assert result['brief']['source'] == 'questionnaire'
    assert result['pricing_summary']['all_to_quote'] and 'manufacturer pricing' in result['pricing_note']
    assert result['source_customer_id'] == 'source-one'
    original['customer']['capture']['questionnaire']['questions'].insert(0, {
        'id': 'project', 'label': 'Project', 'status': 'answered',
        'answers': [{'id': 'phase-one', 'label': 'First installation phase'}]})
    result = present_order(original)
    assert result['brief']['title'] == 'First installation phase'
    assert result['brief']['summary'] == capture()['questionnaire']['project']


def test_specification_and_legacy_selection_keep_sources_and_missing_details():
    original = order(company='', website='', email='buyer@network.rca.ac.uk')
    result = present_order(original)
    assert result['brief']['source'] == 'selection'
    assert result['brief']['summary'] == '24 × Norma 50/70'
    assert result['customer']['company'] == ''
    assert any('company details' in value for value in result['brief']['next_steps'])
    original['customer']['capture'] = {'schema': 'rocoto.orders.capture.v1', 'entry_path': 'specification',
        'specification': {'text': '24 entrance locks. Confirm left/right split.',
                          'lines': [{'source': 'Entrance lock', 'status': 'choose', 'quantity': 24}]}}
    result = present_order(original)
    assert result['brief']['source'] == 'specification'
    assert result['brief']['specification_text'] == '24 entrance locks. Confirm left/right split.'
    assert result['brief']['open_questions'] == ['Match the specification: Entrance lock']
    assert 'left' not in str(result['brief']['facts'])


def test_customer_identity_is_scoped_stable_conservative_and_demo_separated():
    first = present_order(order())
    second = present_order(order('two', email='second@build.test', company='Builder updated name', website='https://www.build.test/projects/'))
    assert customer_id(first, 'scope-a') == customer_id(second, 'scope-a')
    assert customer_id(first, 'scope-a') != customer_id(first, 'scope-b')
    assert customer_id(first, 'scope-a') != customer_id(present_order(order(demo=True)), 'scope-a')
    personal_a = present_order(order(email='person@gmail.com', website='https://gmail.com'))
    personal_b = present_order(order(email='other@gmail.com', website='https://gmail.com'))
    assert customer_id(personal_a, 'scope-a') != customer_id(personal_b, 'scope-a')
    personal_a['customer']['company'] = 'A different display name'
    assert customer_id(personal_a, 'scope-a') == customer_id(present_order(order(email='PERSON@GMAIL.COM', company='', website='')), 'scope-a')


def test_profile_timeline_metrics_keep_quotes_separate_from_confirmed_totals():
    first, second = present_order(order('first')), present_order(order('second', priced=True))
    first['created_at'] = '2026-10-13T12:00:00Z'
    second['customer']['email'] = 'second@build.test'
    profiles = customer_profiles([first, second], 'scope-a')
    assert len(profiles) == 1
    profile = profiles[0]
    assert [value['id'] for value in profile['orders']] == ['second', 'first']
    assert profile['metrics'] == {'requests': 2, 'items': 2, 'quote_requests': 1, 'priced_totals': [{'currency': 'EUR', 'total': 240}], 'requested_quantities': [{'unit': 'pc', 'quantity': 48}]}
    assert len(profile['contacts']) == 2
    assert all(item['customer_id'] == profile['id'] for item in profile['orders'])
    assert 'revenue' not in json.dumps(profile)



def test_profile_contact_keeps_older_phone_and_newest_nonempty_details():
    older, newer = present_order(order('older')), present_order(order('newer'))
    older['created_at'] = '2026-10-13T12:00:00Z'
    older['customer'].update(name='Old name', phone='+359888123456')
    newer['customer'].update(name='Current name', phone='', email='BUYER@BUILD.TEST')
    before = copy.deepcopy([older, newer])
    profile = customer_profiles([older, newer], 'scope-a')[0]
    assert profile['contacts'] == [{'name': 'Current name', 'email': 'BUYER@BUILD.TEST', 'phone': '+359888123456'}]
    assert [older['customer'], newer['customer']] == [row['customer'] for row in before]
    newer['customer']['phone'] = '+359888654321'
    assert customer_profiles([older, newer], 'scope-a')[0]['contacts'][0]['phone'] == '+359888654321'


def source_for_orders(orders):
    return SimpleNamespace(orders=lambda limit=100, offset=0: copy.deepcopy(orders[offset:offset + limit]),
                           order=lambda identifier: copy.deepcopy(next(value for value in orders if value['id'] == identifier)),
                           status=lambda: {'status': 'connected'})


def test_customer_api_projection_search_pagination_membership_and_bounded_coverage(tmp_path):
    ext, members = extension(tmp_path)
    values = [order('one'), order('two', email='second@build.test'), order('three', company='Other Works', website='https://other.test')]
    ext.source = source_for_orders(values)
    result = ext.customers('alice', limit=1)
    assert result['total'] == 2 and result['has_more'] and result['actor']['id'] == 'alice'
    assert result['coverage']['complete']
    matched = ext.customers('alice', q='SECOND@BUILD.TEST')
    assert matched['total'] == 1 and matched['customers'][0]['metrics']['requests'] == 2
    identifier = matched['customers'][0]['id']
    detail = ext.customer('alice', identifier, limit=1)
    assert detail['total_orders'] == 2 and detail['has_more'] and len(detail['orders']) == 1
    assert detail['orders'][0]['customer_id'] == identifier and 'brief' in detail['orders'][0]
    with pytest.raises(Missing):
        ext.customer('alice', 'customer-from-other-company')
    with pytest.raises(ValueError):
        ext.customers('outsider')
    with pytest.raises(Invalid):
        ext.customers('alice', q='x' * 151)
    ext.source = source_for_orders([order(str(index)) for index in range(2001)])
    bounded = ext.customers('alice')
    assert bounded['coverage'] == {'complete': False, 'truncated': True, 'scanned_orders': 2000, 'limit': 2000}


def test_demo_research_requires_real_source_marker_owner_scope_and_supported_facts(tmp_path):
    ext, _ = extension(tmp_path)
    demo, real = order('demo', demo=True), order('real')
    ext.source = source_for_orders([demo, real])
    source = 'https://bld.bg/en/about-us'
    findings = {'status': 'enriched', 'summary': 'Residential property developer.', 'email_snippet': '', 'review_notes': '',
                'facts': [{'label': 'Company name', 'text': 'BLD', 'source_urls': [source]}],
                'sources': [{'url': source, 'title': 'BLD about us'}]}
    saved = ext.import_demo_research('alice', 'demo', findings, as_of='2026-10-14', evidence='Explicit demonstration research')
    assert saved['basis'] == 'operator_demo_research' and saved['as_of'] == '2026-10-14'
    result = ext.order('alice', 'demo')['order']
    assert result['is_demo'] and result['enrichment']['complete'] and result['customer']['display_company'] == 'BLD'
    with pytest.raises(Invalid):
        ext.import_demo_research('alice', 'real', findings, as_of='2026-10-14', evidence='Test')
    with pytest.raises(ValueError):
        ext.import_demo_research('bob', 'demo', findings, as_of='2026-10-14', evidence='Test')
    with pytest.raises(Invalid):
        ext.platform.import_demo_research('other-company', demo, findings, actor='alice', as_of='2026-10-14', evidence='Test', current=lambda: True)
    assert not ext.order('alice', 'real')['order']['enrichment']['has_findings']
    assert ext.platform.demo_research('real') is None


def test_customer_routes_use_native_membership_and_company_scope(tmp_path):
    harness = Path(__file__).resolve().parents[1]
    script = r'''
import sys,copy
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,sys.argv[1]);sys.path.insert(0,sys.argv[3])
import layout
layout.install('manufacturer')
import server
from fastapi.testclient import TestClient
from test_manufacturer_customers import order,source_for_orders
app=server.create_app(Path(sys.argv[2]));app.state.access.create_environment('other','Other')
headers={'X-Rocoto-Page':'1'}
with TestClient(app) as client:
    assert client.get('/api/manufacturer/customers').status_code==401
    def login(env,person):
        code=app.state.access.issue(env,principal_id=person)
        assert client.post('/api/session',json={'code':code},headers=headers).status_code==200
    login('demo','alice')
    app.state.workspaces['demo']['vertical'].source=source_for_orders([order()])
    response=client.get('/api/manufacturer/customers?q=builder')
    assert response.status_code==200,response.text
    identifier=response.json()['customers'][0]['id']
    detail=client.get('/api/manufacturer/customers/'+identifier)
    assert detail.status_code==200 and detail.json()['total_orders']==1,detail.text
    assert client.get('/api/manufacturer/customers?limit=101').status_code==422
    assert client.get('/api/manufacturer/customers?q='+'x'*151).status_code==422
    from manufacturer_store import SourceUnavailable
    def unavailable(**kwargs):
        raise SourceUnavailable('Temporary source outage')
    workspace=app.state.workspaces['demo']['vertical']
    workspace._customers_cache=None
    workspace.source.orders=unavailable
    assert client.get('/api/manufacturer/customers').status_code==503
    assert client.get('/api/manufacturer/customers/'+identifier).status_code==503
    login('other','bob')
    assert client.get('/api/manufacturer/customers/'+identifier).status_code==404
print('native customer routes verified')
'''
    result = subprocess.run([sys.executable, '-c', script, str(harness), str(tmp_path), str(harness / 'tests')],
                            env={**os.environ, 'ROCOTO_VERTICAL': 'manufacturer'}, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


def test_actual_company_store_capture_survives_sqlite_and_remote_projection(tmp_path, monkeypatch):
    import hashlib
    import importlib.util
    from manufacturer_source_http import RemoteCompanySource
    from manufacturer_store import CompanySource
    from test_manufacturer_platform import bind, company_store
    database = tmp_path / 'orders.sqlite'
    store = company_store(database)
    catalogue = {'currency': 'EUR', 'vat': .2, 'rules': {}, 'services': [], 'cats': [{'code': 'norma', 'en': 'Norma 50/70',
        'items': [{'c': '101037', 'p': 0, 'q': 1, 'u': 'pc', 'r': {'k': 'whole'}}]}]}
    store.ingest_catalog(catalogue, {'slug': 'sample-hardware', 'source': 'https://sample-hardware.example.test/'}, 'test', 'Synthetic catalogue')
    store.db.executemany('INSERT INTO calendar VALUES(?,?,?,?)', [(day, 480, 1020, 900) for day in range(1, 6)])
    path = Path(__file__).resolve().parents[2] / 'app/src/prototypes/orders/quote.py'
    monkeypatch.syspath_prepend(str(path.parent))
    spec = importlib.util.spec_from_file_location('brief_quote_contract', path)
    quoting = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(quoting)
    quote = quoting.quote(store.export_catalog(), [{'code': '101037', 'rows': [{'x': 0, 'n': 24}]}])
    customer = order()['customer']
    customer['capture'] = capture()
    submitted = store.submit_order(customer, quote['lines'], quote['quote'], 'captured-request', 'test', 'Saved questionnaire fixture')
    store.close()
    state = tmp_path / 'workspace'
    bind(state, database)
    local = CompanySource(state, 'workspace-a')
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    saved = local.order(submitted['id'])
    assert saved['customer']['capture'] == capture() and saved['customer_id']
    remote = RemoteCompanySource(state, 'workspace-a')
    monkeypatch.setattr(remote, '_read', lambda resource, **kwargs: {'order': copy.deepcopy(saved), 'orders': [copy.deepcopy(saved)]})
    ext, _ = extension(state)
    ext.source = local
    local_result = ext.order('alice', submitted['id'])['order']
    ext.source = remote
    remote_result = ext.order('alice', submitted['id'])['order']
    assert local_result['brief'] == remote_result['brief']
    assert local_result['customer_id'] == remote_result['customer_id']
    assert local_result['source_customer_id'] == saved['customer_id']
    assert local_result['total'] is None and local_result['pricing_summary']['all_to_quote']
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before


def test_customer_snapshot_cache_is_bounded_scoped_and_fails_visibly_after_expiry(tmp_path, monkeypatch):
    ext, members = extension(tmp_path)
    clock = [100.0]
    monkeypatch.setattr('manufacturer_host.time.monotonic', lambda: clock[0])
    calls = []
    data = [order()]
    def orders(limit=100, offset=0):
        calls.append(offset)
        return copy.deepcopy(data[offset:offset + limit])
    ext.source = SimpleNamespace(orders=orders, status=lambda: {'status': 'connected'})
    first = ext.customers('alice')
    identifier = first['customers'][0]['id']
    first['customers'][0]['display_name'] = 'Changed response only'
    assert ext.customer('alice', identifier)['customer']['display_name'] == 'Builder'
    assert ext.customers('bob', q='builder')['total'] == 1
    assert calls == [0]
    members.pop('bob')
    with pytest.raises(ValueError):
        ext.customers('bob')
    clock[0] += 6
    def failed(**kwargs):
        raise SourceUnavailable('Temporary source outage')
    ext.source.orders = failed
    with pytest.raises(SourceUnavailable):
        ext.customers('alice')
    with pytest.raises(SourceUnavailable):
        ext.customer('alice', identifier)
    # A status-only failure is also an error, even if a source returns an empty page.
    ext.source.orders = lambda **kwargs: []
    ext.source.status = lambda: {'status': 'unavailable'}
    with pytest.raises(SourceUnavailable):
        ext.customers('alice')


def test_brief_heading_and_customer_quantities_keep_full_text_and_distinct_units():
    original = order()
    original['customer']['project'] = 'Door hardware for ' + 'a residential installation phase ' * 8
    result = present_order(original)
    assert result['brief']['title'] == heading(original['customer']['project'])
    assert len(result['brief']['title']) <= 100 and result['brief']['title'].endswith('…')
    assert result['brief']['summary'] == original['customer']['project'].strip()
    other = order('other')
    other['lines'][0].update(quantity=10, unit='m')
    profile = customer_profiles([result, present_order(other)], 'scope-a')[0]
    assert profile['metrics']['requested_quantities'] == [{'unit': 'm', 'quantity': 10}, {'unit': 'pc', 'quantity': 24}]


def test_bulgarian_projection_uses_catalogue_labels_and_preserves_customer_text(tmp_path):
    from manufacturer_source import catalogue_labels, localize_catalogue_lines
    ext, _ = extension(tmp_path)
    document = ext.configurator('alice')['document']
    document['configuration']['defaultLanguage'] = 'bg'
    document['catalogue']['cats'] = [{'code': 'norma', 'en': 'Norma 50/70', 'bg': 'Норма 50/70',
        'items': [{'c': '101037', 'p': 0, 'q': 1, 's': 'Никел', 'se': 'Nickel', 'u': 'pc'}]}]
    ext.save_configurator('alice', {'document': document, 'expected_revision': 0}, 'Bulgarian source')
    original = order(priced=True)
    original['lines'][0]['description'] = 'Nickel'
    original['customer']['project'] = 'Customer original project text'
    before = copy.deepcopy(original)
    index = catalogue_labels(ext.platform)
    assert catalogue_labels(ext.platform) is index
    result = present_order(localize_catalogue_lines(copy.deepcopy(original), index), locale='bg')
    assert result['lines'][0]['name'] == 'Норма 50/70'
    assert result['lines'][0]['description'] == 'Никел'
    assert result['lines'][0]['total'] == 240 and result['total'] == 240
    assert result['brief']['project'] == 'Customer original project text'
    assert original == before
    original['lines'][0]['description'] = 'A custom customer description'
    assert localize_catalogue_lines(original, index)['lines'][0]['description'] == 'A custom customer description'
    document['catalogue']['cats'][0]['bg'] = 'Нова Норма'
    ext.save_configurator('alice', {'document': document, 'expected_revision': 1}, 'Updated catalogue label')
    assert catalogue_labels(ext.platform)['items']['101037']['name'] == 'Нова Норма'
    assert catalogue_labels(ext.platform) is not index




def test_customer_response_metrics_use_current_proposals_and_preserve_source_quantities(tmp_path):
    ext, _ = extension(tmp_path)
    values = [order('quoted'), order('already-priced', priced=True), order('usd'), order('outstanding')]
    values[2]['currency'] = 'USD'
    ext.source = source_for_orders(values)
    snapshot, _, _ = ext._customer_snapshot('alice')
    before = copy.deepcopy(snapshot)
    identifier = snapshot[0]['id']
    store = ext.conversations
    store.ensure_customer(identifier, contacts=snapshot[0]['contacts'], actor='alice', current=lambda: True)
    for original in snapshot[0]['orders']:
        store.record_source_order(identifier, original, actor='alice', current=lambda: True)
    for order_id, quantity, price, amount in [('quoted', 6, 2.675, 16.05), ('usd', 2, 10, 20)]:
        original = next(row for row in snapshot[0]['orders'] if row['id'] == order_id)
        document = {'id': order_id, 'customer_id': identifier, 'currency': original['currency'],
                    'lines': [{'code': '101037', 'quantity': quantity, 'unit_price': price, 'line_total': amount}]}
        proposal = store.propose_request(identifier, order_id, proposal=document, recipient='buyer@build.test',
            actor='alice', expected_revision=0, idempotency_key='proposal-'+order_id, current=lambda: True)
        if order_id == 'quoted':
            store.confirm_proposal(identifier, order_id, version_id=proposal['proposal']['id'],
                customer_actor='customer', evidence={'method': 'review_link'}, current=lambda: True)
    detail = ext.customer('alice', identifier, limit=1)
    listed = ext.customers('alice')['customers'][0]
    expected = {'requests': 4, 'items': 4, 'quote_requests': 1,
                'requested_quantities': [{'unit': 'pc', 'quantity': 96}],
                'priced_totals': [{'currency': 'EUR', 'total': 256.05}, {'currency': 'USD', 'total': 20}]}
    assert detail['customer']['metrics'] == listed['metrics'] == expected
    assert detail['has_more'] and len(detail['orders']) == 1
    timeline = ext.customer('alice', identifier)['orders']
    assert next(row for row in timeline if row['id'] == 'quoted')['status'] == 'customer_confirmed'
    assert next(row for row in timeline if row['id'] == 'usd')['status'] == 'review_pending'
    assert ext._customer_snapshot('alice')[0] == before
    assert values[0]['lines'][0]['quantity'] == 24 and values[0]['total'] is None


def test_cancelled_source_stays_visible_above_staff_and_review_progress(tmp_path):
    ext, _ = extension(tmp_path)
    values = [order('cancelled')]
    ext.source = source_for_orders(values)
    source = ext.order('alice', 'cancelled')['order']
    identifier = source['customer_id']
    ext.conversations.ensure_customer(identifier, contacts=[{'email': 'buyer@build.test'}],
        actor='alice', current=lambda: True)
    ext.conversations.record_source_order(identifier, source, actor='alice', current=lambda: True)
    before = ext.fulfillment.read(identifier, 'cancelled')
    ext.fulfillment.transition(identifier, 'cancelled', status='accepted', version_id=before['current_version_id'],
        expected_revision=0, actor='alice', evidence={'method': 'staff_action'}, idempotency_key='accepted',
        current=lambda: True)
    values[0]['status'] = 'cancelled'
    cancelled = ext.order('alice', 'cancelled')['order']
    assert ext.present_request(cancelled)['status'] == 'cancelled'
    assert ext.customer('alice', identifier)['orders'][0]['status'] == 'cancelled'
    assert ext.fulfillment.read(identifier, 'cancelled')['status'] == 'accepted'
