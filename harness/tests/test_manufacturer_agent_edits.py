"""Compact managed tools retain exact documents and the existing admission boundary."""
# ruff: noqa: E402 - Install the selected vertical before importing its modules.
from __future__ import annotations

import asyncio
import copy
import json
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'verticals/manufacturer'))
import manufacturer_tools
from manufacturer_store import Conflict
from test_manufacturer_platform import extension
from tool_families import ToolContext, ToolRegistry


@pytest.fixture
def workspace(tmp_path):
    ext, people = extension(tmp_path)
    document = ext.configurator('alice')['document']
    document['configuration']['defaultLanguage'] = 'en'
    document['configuration']['questionnaire'] = {'mode': 'sections', 'questions': [{
        'id': 'door', 'kind': 'single', 'title': {'en': 'Door type', 'bg': 'Врата'},
        'unsure': True, 'options': [{'id': 'entrance', 'label': {'en': 'Entrance', 'bg': 'Входна'},
                                   'match': {'use': ['entrance']}, 'drawing': 'door-entrance'}]}]}
    document['catalogue']['cats'] = [{'code': 'locks', 'en': 'Locks', 'url': 'https://sample-hardware.example.test/',
        'items': [{'c': '101', 'p': 12.5, 'q': 0, 'u': 'pc', 'cut': 3.5, 'r': {'k': 'whole'}, 'a': {'finish': ['nickel']}},
                  {'c': '102', 'p': 0, 'q': 1, 'u': 'pc'}]}]
    document['catalogue']['currency'] = 'EUR'
    document['catalogue']['price_overrides'] = [{'item_id': '101', 'basis': 'p', 'amount': 15},
                                               {'item_id': '101', 'basis': 'cut', 'amount': 2}]
    initial = ext.save_configurator('alice', {'document': document, 'expected_revision': 0}, 'Test source')
    run = {'cancel': asyncio.Event()}
    ctx = ToolContext(state=tmp_path, company_id='workspace-a', actor='alice', data_owner='alice',
                      collection='company', extension=ext, admission=ext.read_admission('alice', 'company'),
                      run=run, chat_id='org', agent=SimpleNamespace(active={'org': run}),
                      record={'dataset': 'company', 'owner_principal_id': 'alice'})
    return ext, people, ctx, initial


def invoke(ctx, name, **arguments):
    return asyncio.run(ToolRegistry([manufacturer_tools]).invoke(ctx, name, arguments))


def edit(ctx, **changes):
    return invoke(ctx, 'manufacturer_edit_configurator', expected_revision=1,
                  evidence='Owner instruction and supplied price list', changes=changes, label='Reviewed changes')


def test_compact_summary_find_and_receipt_share_full_history(workspace):
    ext, _, ctx, initial = workspace
    summary = invoke(ctx, 'manufacturer_configurator_summary')
    assert summary['revision'] == 1 and summary['catalogue']['article_count'] == 2
    assert 'document' not in summary and 'options' not in summary['questions']['items'][0]
    question = invoke(ctx, 'manufacturer_configurator_summary', question_id='door')
    assert question['question']['options'][0]['id'] == 'entrance'
    found = invoke(ctx, 'manufacturer_find_products', code='101')
    assert found['products'][0]['price'] == 15 and found['products'][0]['unit'] == 'pc'
    assert found['products'][0]['attributes']['finish'] == ['nickel']
    saved = edit(ctx, appearance={'accent': '#112233'}, prices=[{'code': '101', 'price': 0}],
                 questions=[{'id': 'door', 'title': {'en': 'Which entrance?'},
                             'options': [{'id': 'entrance', 'label': {'en': 'Main entrance'}}]}])
    assert saved['revision'] == 2 and 'document' not in saved and len(json.dumps(saved)) < 2000
    changed = ext.configurator('alice')['document']
    expected = copy.deepcopy(initial['document'])
    expected['configuration']['accent'] = '#112233'
    expected['configuration']['questionnaire']['questions'][0]['title']['en'] = 'Which entrance?'
    expected['configuration']['questionnaire']['questions'][0]['options'][0]['label']['en'] = 'Main entrance'
    expected['catalogue']['cats'][0]['items'][0].update(p=0, q=0)
    expected['catalogue']['price_overrides'] = expected['catalogue']['price_overrides'][1:]
    assert changed == expected
    assert ext.versions('alice')['versions'][0]['author']['type'] == 'agent'
    restored = invoke(ctx, 'manufacturer_restore_configurator', version_id=initial['version_id'],
                      expected_revision=2, evidence='Restore reviewed original')
    assert 'document' not in restored and restored['revision'] == 3
    assert ext.configurator('alice')['document'] == initial['document']
    assert restored['sha256'] == ext.version('alice', initial['version_id'])['version']['sha256']


@pytest.mark.parametrize('price', [None, ''])
def test_quote_price_clears_only_selected_price_override(workspace, price):
    ext, _, ctx, _ = workspace
    edit(ctx, prices=[{'code': '101', 'price': price}])
    doc = ext.configurator('alice')['document']
    assert doc['catalogue']['cats'][0]['items'][0]['q'] == 1
    assert doc['catalogue']['cats'][0]['items'][0]['p'] == 0
    assert doc['catalogue']['price_overrides'] == [{'item_id': '101', 'basis': 'cut', 'amount': 2}]


@pytest.mark.parametrize('changes', [
    {'prices': [{'code': 'missing', 'price': 12}]},
    {'prices': [{'code': '101', 'price': -1}]},
    {'prices': [{'code': '101', 'price': float('nan')}]},
    {'prices': [{'code': '101', 'price': True}]},
    {'prices': [{'code': '101', 'price': 1}, {'code': '101', 'price': 2}]},
    {'questions': [{'id': 'door', 'options': [{'id': 'missing', 'label': {'en': 'New'}}]}]},
    {'questions': [{'id': 'missing', 'title': {'en': 'New'}}]},
    {'questions': [{'id': 'door', 'options': [{'id': 'entrance', 'match': {'use': ['other']}}]}]},
    {'appearance': {'slug': 'other'}},
    {'attachments': [{'file_id': 'file-' + 'a' * 32}]},
    {},
])
def test_invalid_edit_is_atomic(workspace, changes):
    ext, _, ctx, initial = workspace
    with pytest.raises(ValueError):
        edit(ctx, **changes)
    assert ext.configurator('alice')['document'] == initial['document']
    assert ext.configurator('alice')['revision'] == 1


def test_stale_revision_and_admission_block_changes(workspace):
    ext, people, ctx, _ = workspace
    edit(ctx, appearance={'headline': 'Choose your hardware'})
    with pytest.raises(Conflict):
        edit(ctx, appearance={'headline': 'Stale'})
    with pytest.raises(ValueError):
        invoke(replace(ctx, company_id='other'), 'manufacturer_configurator_summary')
    reader = replace(ctx, actor='reader', admission=ext.read_admission('reader', 'company'))
    with pytest.raises(ValueError):
        invoke(reader, 'manufacturer_edit_configurator', expected_revision=2, evidence='Browse member',
               changes={'appearance': {'headline': 'Blocked'}})
    del people['alice']
    with pytest.raises(ValueError):
        invoke(ctx, 'manufacturer_find_products', query='lock')
    assert ext.platform.configurator()['revision'] == 2


def test_summary_and_product_pages_stay_bounded(workspace):
    ext, _, ctx, _ = workspace
    current = ext.configurator('alice')
    document = current['document']
    document['catalogue']['cats'][0]['items'] = [{'c': str(i), 'se': 'Article ' + str(i), 'p': 0, 'q': 1, 'u': 'pc'} for i in range(1600)]
    ext.save_configurator('alice', {'document': document, 'expected_revision': 1}, 'Full source')
    summary = invoke(ctx, 'manufacturer_configurator_summary')
    assert summary['catalogue']['article_count'] == 1600 and len(json.dumps(summary)) < 6000
    found = invoke(ctx, 'manufacturer_find_products', query='Article', limit=20, offset=20)
    assert found['total'] == 1600 and len(found['products']) == 20 and found['next_offset'] == 40
    with pytest.raises(ValueError):
        invoke(ctx, 'manufacturer_find_products', limit=21)


def test_pending_publication_receipt_keeps_saved_state(workspace, monkeypatch):
    ext, _, ctx, _ = workspace
    monkeypatch.setattr(ext.publisher, 'configured', lambda: True)
    monkeypatch.setattr(ext.publisher, 'transport', lambda payload: {'ok': False})
    saved = edit(ctx, appearance={'accent': '#224466'})
    assert saved['state'] == 'pending' and saved['published'] is False
    assert saved['publication']['state'] == 'pending'
    assert saved['sha256'] == ext.version('alice', saved['version_id'])['version']['sha256']
