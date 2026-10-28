"""Customer text and uploads resolve only to source catalogue articles."""
import io
import zipfile

import customer_details
import order_assistant
import propose
import pytest
import spec

pytest_plugins = ["test_order_api"]


@pytest.fixture
def catalog():
    def item(code, **attrs):
        return {'c': code, 's': code, 'p': 0, 'q': 1, 'a': attrs}
    return {'cats': [
        {'code': 'mega', 'name': {'bg': 'Мега 50/72', 'en': 'Mega 50/72'}, 'form': 'mortise', 'items': [
            item('101353L', kind='lock', model='mega', fn=['PZ'], hand=['L'], backset=50, centres=72, finish=['nickel']),
            item('101353R', kind='lock', model='mega', fn=['PZ'], hand=['R'], backset=50, centres=72, finish=['nickel'])]},
        {'code': 'handle', 'name': {'en': 'Athena'}, 'form': 'handles', 'items': [
            item('151001', kind='handle', purpose=['B'], hand=['R'], centres=72),
            item('151002', kind='handle', purpose=['B'], hand=['R'], centres=90)]}]}


def test_varna_request_splits_hands_and_preserves_unknowns(catalog):
    result = spec.read({'text': 'Мега 50/72 секретна никел: 12 леви, 12 десни\n777999 4 бр.'}, catalog)
    assert [r['qty'] for r in result['lines']] == [12, 12, 4]
    assert [r['matches'] for r in result['lines']] == [['101353L'], ['101353R'], []]
    assert [r['status'] for r in result['lines']] == ['exact', 'exact', 'unknown']
    assert result['engine'] == 'rules'


def test_exact_code_and_unknown_or_conflicting_dimensions(catalog):
    assert spec.read({'text': '24 pcs 101353R'}, catalog)['lines'][0]['matches'] == ['101353R']
    assert spec.read({'text': 'Mega 60/90 PZ right'}, catalog)['lines'][0]['matches'] == []
    assert spec.read({'text': 'Please deliver on Tuesday'}, catalog)['lines'][0]['status'] == 'unknown'


def test_provider_cannot_invent_or_override_article_constraints(catalog):
    class Malicious:
        def structured(self, *args, **kwargs):
            return {'lines': [{'source': 'Mega 60/90 PZ', 'qty': 2, 'family': 'mortise',
                               'type': 'mega', 'filters': [], 'matches': ['101353R', 'FAKE']}]}
    result = spec.read({'text': 'Mega 60/90 PZ'}, catalog, assistant=Malicious())
    assert result['lines'][0]['matches'] == []


def test_office_extraction_and_zip_bomb_bounds():
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w') as z:
        z.writestr('[Content_Types].xml', '<Types/>')
        z.writestr('word/document.xml', '<document><p><t>Мега 50/72</t><t>24 бр.</t></p></document>')
    assert '24 бр.' in spec.extract('schedule.docx', out.getvalue())[0]
    with zipfile.ZipFile(out := io.BytesIO(), 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('word/document.xml', ' ' * 9_000_000)
    with pytest.raises(ValueError):
        spec.extract('large.docx', out.getvalue())


def test_proposal_requires_shared_dimensions_and_ignores_model_article_edits(catalog):
    config = {'questionnaire': {'questions': [{'id': 'hand', 'options': [
        {'id': 'right', 'match': {'hand': ['R']}}]}], 'result': {'groups': [
            {'category': ['mortise'], 'title': {'en': 'Lock', 'bg': 'Брава'}},
            {'category': ['handles'], 'title': {'en': 'Handle', 'bg': 'Дръжка'}}]}}}
    class Narrator:
        def structured(self, *args, **kwargs):
            return {'title': {'en': 'Your set', 'bg': 'Вашият комплект'},
                    'text': {'en': 'Chosen from the catalogue.', 'bg': 'Избрано от каталога.'},
                    'lines': [{'c': 'FAKE'}]}
    result = propose.read({'answers': {'hand': ['right']}}, catalog, config, assistant=Narrator())
    assert [r['c'] for r in result['lines']] == ['101353R', '151001']
    assert all(r['qty'] == 1 for r in result['lines'])


def test_customer_company_and_website_normalization():
    config = {'checkout': {'companyRequired': True}}
    with pytest.raises(ValueError):
        customer_details.validate({'name': 'A', 'email': 'a@example.test'}, config)
    value = customer_details.validate({'name': 'A', 'email': 'a@example.test', 'company': 'Varna Doors',
                                       'website': 'varna-doors.bg', 'trade': 'installer'}, config)
    assert value['website'] == 'https://varna-doors.bg'
    with pytest.raises(ValueError):
        customer_details.validate({'name': 'A', 'email': 'a@example.test', 'kind': 'private'}, config)
    with pytest.raises(ValueError):
        customer_details.validate({**value, 'website': 'javascript:alert(1)'}, config)


def test_provider_ledger_stops_at_monthly_limit_and_survives_restart(tmp_path):
    path = tmp_path / order_assistant.LEDGER_NAME
    ledger = order_assistant.Ledger(path, {'spec': (300, 300), 'propose': (300, 300)})
    ledger.commission()
    for _ in range(300):
        assert ledger.reserve('spec')
    assert not ledger.reserve('spec')
    assert ledger.reserve('propose')
    assert not order_assistant.Ledger(path, {'spec': (300, 300), 'propose': (300, 300)}).reserve('spec')



def test_spec_upload_api_and_order_custody(order_api):
    from store import CompanyStore
    from test_order_api import order, request, upload
    body = io.BytesIO()
    with zipfile.ZipFile(body, 'w') as zipped:
        zipped.writestr('[Content_Types].xml', '<Types/>')
        zipped.writestr('word/document.xml', '<document><p><t>3 pcs A</t></p></document>')
    status, staged = upload(order_api, 'specification.docx', body.getvalue())
    assert status == 201
    identifier = staged['upload']['id']
    status, extracted = request(order_api, 'spec', {'upload': identifier})
    assert status == 200 and extracted['lines'][0]['matches'] == ['A']
    assert extracted['lines'][0]['qty'] == 3
    customer_order = order()
    customer_order['customer'].update(kind='company', company='Varna Doors', website='varna-doors.bg',
                                      trade='installer', project='Door renovation', specification_file=identifier)
    status, saved = request(order_api, 'orders', customer_order, key='specification-order-0001')
    assert status == 201
    database = CompanyStore(order_api[1])
    try:
        stored = database.read_order(saved['id'])
        assert stored['customer']['website'] == 'https://varna-doors.bg'
        assert database.one('SELECT order_id FROM order_files WHERE id=?', (identifier,))['order_id'] == saved['id']
    finally:
        database.close()
    assert request(order_api, 'spec', {'upload': identifier})[0] == 400


def test_model_partial_quote_preserves_original_explicit_dimensions(catalog):
    class Partial:
        def structured(self, *args, **kwargs):
            return {'lines': [{'source': 'Mega', 'qty': 2, 'family': '', 'type': 'mega', 'filters': []}]}
    assert spec.read({'text': 'Mega 60/90 PZ'}, catalog, assistant=Partial())['lines'][0]['matches'] == []


def test_proposal_narrative_receives_customer_labels_and_article_codes(catalog):
    import json

    catalog['cats'][0]['code'] = 'p566'
    catalog['cats'][0]['items'][0]['a'].update(model='p566', strike='with')
    catalog['cats'][0]['items'] = catalog['cats'][0]['items'][:1]
    config = {'questionnaire': {'questions': [{'id': 'hand', 'title': {'en': 'Door handing'},
        'options': [{'id': 'right', 'label': {'en': 'Right'}}]}],
        'result': {'groups': [{'category': ['mortise']}]}},
        'picker': {'families': [{'id': 'mortise', 'title': {'en': 'Mortise locks'},
            'match': {'kind': ['lock']}, 'facets': [
                {'key': 'fn', 'title': {'en': 'Lock function'}, 'options': [
                    {'value': 'PZ', 'label': {'en': 'Profile cylinder'}}]},
                {'key': 'strike', 'title': {'en': 'Strike plate'}, 'options': [
                    {'value': 'with', 'label': {'en': 'Strike plate included'}}]}]}]}}

    class Narrator:
        def structured(self, route, instructions, data, schema):
            encoded = json.dumps(data)
            assert '101353L' in encoded and 'Mega 50/72' in encoded
            assert 'Profile cylinder' in encoded and 'Strike plate included' in encoded
            assert 'To confirm' in encoded
            for internal in ('p566', 'PZ', 'attributes', '"strike"', '"with"', '"hand"'):
                assert internal not in encoded
            return {'title': {'en': 'Door lock', 'bg': 'Брава за врата'},
                    'text': {'en': 'Check the door handing.', 'bg': 'Проверете посоката на вратата.'}}

    result = propose.read({'answers': {'hand': ['?']}}, catalog, config, assistant=Narrator())
    assert result['engine'] == 'llm' and result['lines'][0]['c'] == '101353L'


def test_spreadsheet_article_quantity_is_literal_and_out_of_range_is_not_clamped(catalog):
    for source in ('101353R | 24', '24\t101353R'):
        result = spec.read({'text': source}, catalog)['lines'][0]
        assert result['matches'] == ['101353R'] and result['qty'] == 24
    for source in ('0 pcs 101353R', '10000 pcs 101353R', '100000 pcs 101353R',
                   '-5 pcs 101353R', '2.5 pcs 101353R', '101353R | -5'):
        with pytest.raises(ValueError):
            spec.read({'text': source}, catalog)


def test_cylinder_half_lengths_are_distinct_from_lock_backset_and_centres():
    catalogue = {'cats': [{'code': 'cylinder', 'form': 'cylinders', 'items': [
        {'c': '111001', 'a': {'kind': 'cylinder', 'A': 31.5, 'B': 31.5}},
        {'c': '111002', 'a': {'kind': 'cylinder', 'A': 31.5, 'B': 40}},
    ]}]}
    result = spec.read({'text': '24 бр. патрон 31,5/31,5'}, catalogue)['lines'][0]
    assert result['matches'] == ['111001'] and result['qty'] == 24
    assert result['filters'] == {'kind': 'cylinder', 'A': 31.5, 'B': 31.5}


def test_model_preserves_explicit_quantities_and_every_unresolved_customer_line(catalog):
    class Partial:
        def structured(self, *args, **kwargs):
            return {'lines': [{'source': 'bespoke latching assembly', 'qty': 1, 'family': '',
                              'type': 'mega', 'filters': [{'key': 'hand', 'value': 'R'}]}]}
    result = spec.read({'text': '24 pcs bespoke latching assembly\n7 pcs unlisted fittings'},
                       catalog, assistant=Partial())
    assert len(result['lines']) == 2
    assert result['lines'][0]['qty'] == 24 and result['lines'][0]['matches'] == ['101353R']
    assert result['lines'][1]['qty'] == 7 and result['lines'][1]['status'] == 'unknown'


def test_spec_line_limit_is_explicit_instead_of_silently_dropping_customer_work(catalog):
    with pytest.raises(ValueError):
        spec.read({'text': '\n'.join('1 pcs 101353R' for _ in range(101))}, catalog)


def test_proposal_preserves_ambiguous_articles_as_explicit_choices(catalog):
    config = {'questionnaire': {'questions': [
        {'id': 'parts', 'options': [{'id': 'lock', 'label': {'en': 'Lock'}}, {'id': 'handles'}, {'id': 'set'}]},
        {'id': 'hand', 'options': [{'id': 'left', 'match': {'hand': ['L']}},
                                    {'id': 'right', 'match': {'hand': ['R']}}]}]}}
    for answer in ({}, {'parts': ['?']}):
        result = propose.read({'answers': answer}, catalog, config)
        assert result['lines'] == [] and result['ready'] is False
        assert result['choices'][0]['unresolved'] == ['parts']
    result = propose.read({'answers': {'parts': ['lock']}}, catalog, config)
    assert result['lines'] == [] and result['ready'] is False
    assert result['choices'] == [{'part': 'lock', 'title': {'en': 'Lock'}, 'count': 2,
        'matches': ['101353L', '101353R'], 'matching_codes': ['101353L', '101353R'],
        'family': 'mortise', 'filters': {}, 'source_unconfirmed': False, 'qty': 1, 'unresolved': ['hand']}]
    resolved = propose.read({'answers': {'parts': ['lock'], 'hand': ['right']}}, catalog, config)
    assert resolved['ready'] is True and resolved['lines'][0]['c'] == '101353R'


def test_proposal_handles_include_rosettes_and_empty_match_remains_visible(catalog):
    catalog['cats'][1]['items'][0]['a']['kind'] = 'rosette'
    config = {'questionnaire': {'questions': [{'id': 'parts', 'options': [{'id': 'handles'}, {'id': 'cylinder'}]}]}}
    result = propose.read({'answers': {'parts': ['handles', 'cylinder']}}, catalog, config)
    assert result['ready'] is False
    assert result['choices'][0]['matches'] == ['151001', '151002']
    assert result['choices'][1]['part'] == 'cylinder' and result['choices'][1]['count'] == 0


def test_cylinder_compatibility_is_symmetric(catalog):
    lock = spec.index(catalog)[0]
    cylinder = {'a': {'kind': 'cylinder', 'cam': ['euro']}}
    assert not propose.compatible(cylinder, [lock])
    assert not propose.compatible(lock, [cylinder])
    lock['a']['cam'] = ['euro']
    assert propose.compatible(cylinder, [lock]) and propose.compatible(lock, [cylinder])


def test_handle_model_answer_preserves_lock_in_complete_set(catalog):
    catalog['cats'][1]['items'][0]['a']['model'] = 'athena'
    catalog['cats'][1]['items'][1]['a']['model'] = 'other'
    config = {'questionnaire': {'questions': [
        {'id': 'parts', 'options': [{'id': 'set'}, {'id': 'lock'}, {'id': 'handles'}]},
        {'id': 'model', 'options': [{'id': 'athena', 'match': {'model': ['athena']}}]},
        {'id': 'hand', 'options': [{'id': 'right', 'match': {'hand': ['R']}}]}]}}
    result = propose.read({'answers': {'parts': ['set'], 'model': ['athena'], 'hand': ['right']}}, catalog, config)
    assert result['ready'] is True
    assert [line['c'] for line in result['lines']] == ['101353R', '151001']


def test_customer_capture_preserves_large_literal_spec_quantity():
    capture = {'schema': 'rocoto.orders.capture.v1', 'entry_path': 'specification', 'language': 'bg',
        'specification': {'text': '9999 pcs 101353R', 'lines': [
            {'source': '9999 pcs 101353R', 'quantity': 9999, 'selected_code': '101353R', 'status': 'exact'}]}}
    assert customer_details.capture(capture)['specification']['lines'][0]['quantity'] == 9999
    capture['specification']['lines'][0]['quantity'] = 10000
    with pytest.raises(ValueError):
        customer_details.capture(capture)


def test_unique_article_missing_requested_dimension_stays_for_review(catalog):
    catalog['cats'] = catalog['cats'][:1]
    catalog['cats'][0]['items'] = catalog['cats'][0]['items'][:1]
    del catalog['cats'][0]['items'][0]['a']['centres']
    config = {'questionnaire': {'questions': [
        {'id': 'parts', 'options': [{'id': 'lock'}]},
        {'id': 'size', 'options': [{'id': '50-72', 'match': {'backset': [50], 'centres': [72]}}]}]}}
    result = propose.read({'answers': {'parts': ['lock'], 'size': ['50-72']}}, catalog, config)
    assert result['ready'] is False and result['lines'] == []
    assert result['choices'][0]['source_unconfirmed'] is True
    assert result['choices'][0]['unresolved'] == []


def test_office_overflow_is_explicit_and_exact_codes_skip_model(catalog):
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w') as zipped:
        zipped.writestr('word/document.xml', '<document><p><t>' + 'a' * 24001 + '</t></p></document>')
    with pytest.raises(ValueError, match='24,000'):
        spec.extract('large.docx', out.getvalue())

    class UnneededProvider:
        def structured(self, *args, **kwargs):
            raise AssertionError('Exact source article resolution needs no provider request')
    result = spec.read({'text': '24 pcs 101353R'}, catalog, assistant=UnneededProvider())
    assert result['engine'] == 'rules' and result['lines'][0]['qty'] == 24


def test_pdf_overflow_is_explicit_before_any_partial_extraction(monkeypatch):
    from types import SimpleNamespace

    calls = []
    def run(command, **kwargs):
        calls.append(command[0])
        return SimpleNamespace(stdout=b'Pages: 31\n')
    monkeypatch.setattr(spec.subprocess, 'run', run)
    with pytest.raises(ValueError, match='30 pages'):
        spec.extract('long.pdf', b'%PDF-local-test')
    assert calls == ['pdfinfo']
