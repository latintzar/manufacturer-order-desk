"""Sparse spreadsheet quantities stay tied to their source destination cells."""
import io
import zipfile
from xml.sax.saxutils import escape

import pytest
import spec
from test_spec_proposal import catalog as catalog
from test_store import store as store


def workbook(rows):
    body = io.BytesIO()
    with zipfile.ZipFile(body, 'w') as zipped:
        zipped.writestr('[Content_Types].xml', '<Types/>')
        zipped.writestr('xl/workbook.xml', '<workbook/>')
        cells = []
        for number, values in rows:
            cells.append('<row r="' + str(number) + '">' + ''.join(
                '<c r="' + address + '" t="inlineStr"><is><t>' + escape(str(value)) + '</t></is></c>'
                for address, value in values.items()) + '</row>')
        zipped.writestr('xl/worksheets/sheet1.xml', '<worksheet><sheetData>' + ''.join(cells) + '</sheetData></worksheet>')
    return body.getvalue()


def test_sparse_cells_preserve_column_addresses():
    body = workbook([(1, {'A1': 'SKU', 'C1': 'Практикер Варна', 'E1': 'Практикер София'}),
                     (2, {'A2': '101353R', 'E2': '7'})])
    text, _ = spec.extract('order.xlsx', body)
    assert text.splitlines()[0] == 'SKU |  | Практикер Варна |  | Практикер София'
    assert text.splitlines()[1] == '101353R |  |  |  | 7'


def test_unknown_suffixed_sku_never_matches_known_prefix(catalog):
    for code in ['101353R-X', '101353R/2', '101353RZZ', '101353R‑X']:
        result = spec.read({'text': 'Мега 50/72 ' + code + ' 4 бр.'}, catalog)
        assert result['lines'][0]['status'] == 'unknown'
        assert result['lines'][0]['matches'] == []


def read_file(rows, catalog, store, assistant=None):
    import order_files
    uploaded = order_files.stage(store, 'allocation.xlsx', workbook(rows), 'workbook-intake-test-0001')
    return spec.read({'upload': uploaded['id']}, catalog, store=store, assistant=assistant)


def test_matrix_keeps_sparse_destinations_and_reconciles_totals(catalog, store):
    class ExactOnly:
        def structured(self, *args, **kwargs):
            raise AssertionError('Exact matrix arithmetic stays local')
    result = read_file([
        (1, {'A1': 'SKU', 'C1': 'Практикер Варна', 'E1': 'Практикер София', 'G1': 'Общо'}),
        (2, {'A2': '101353R', 'E2': '7', 'G2': '7'}),
        (3, {'A3': '101353L', 'C3': '5', 'G3': '5'}),
        (4, {'A4': 'Общо', 'C4': '5', 'E4': '7', 'G4': '12'}),
    ], catalog, store, ExactOnly())
    assert result['engine'] == 'rules'
    assert [line['qty'] for line in result['lines']] == [7, 5]
    review = result['review']
    assert review['schema'] == 'rocoto.orders.allocations.v1' and review['upload_id']
    assert review['requires_confirmation'] is True and review['issues'] == []
    assert review['totals']['declared'] == review['totals']['calculated'] == 12
    assert [(a['line'], a['destination_id'], a['quantity'], a['source_cell']) for a in review['allocations']] == [
        (0, 'sheet1:E', 7, 'sheet1!E2'), (1, 'sheet1:C', 5, 'sheet1!C3')]


@pytest.mark.parametrize('quantity,total,expected', [('3', '5', 'line_total_mismatch'),
    ('2.5', '2', 'whole_quantity'), ('-2', '2', 'whole_quantity'), ('0', '5', 'line_total_mismatch')])
def test_matrix_invalid_quantities_or_totals_block_review(catalog, store, quantity, total, expected):
    result = read_file([(1, {'A1': 'SKU', 'B1': 'Практикер Варна', 'C1': 'Общо'}),
                        (2, {'A2': '101353R', 'B2': quantity, 'C2': total})], catalog, store)
    assert expected in {issue['code'] for issue in result['review']['issues']}
    assert all(issue['blocking'] is True for issue in result['review']['issues'])


def test_matrix_rejects_unlabelled_quantity_column(catalog, store):
    result = read_file([(1, {'A1': 'SKU', 'B1': 'Варна', 'D1': 'София'}),
                        (2, {'A2': '101353R', 'B2': '2', 'C2': '30', 'D2': '4'})], catalog, store)
    assert {'code': 'unmapped_cell', 'source_cell': 'sheet1!C2', 'blocking': True} in result['review']['issues']


def test_normal_sparse_excel_quantity_list_is_local(catalog, store):
    result = read_file([(1, {'A1': 'Артикул', 'C1': 'Количество'}),
                        (2, {'A2': '101353R', 'C2': '24'})], catalog, store)
    assert result['engine'] == 'rules' and 'review' not in result
    assert result['lines'][0]['matches'] == ['101353R'] and result['lines'][0]['qty'] == 24


def test_unknown_matrix_sku_remains_visible_and_unmatched(catalog, store):
    result = read_file([(1, {'A1': 'SKU', 'B1': 'Варна', 'C1': 'София'}),
                        (2, {'A2': '101353R-X', 'B2': '3', 'C2': '4'})], catalog, store)
    assert result['lines'][0]['status'] == 'unknown' and result['lines'][0]['matches'] == []
    assert result['lines'][0]['qty'] == 7
    assert result['review']['allocations'][0]['sku'] == '101353R-X'


def test_unclear_spreadsheet_never_defaults_each_row_to_one(catalog, store):
    result = read_file([(1, {'A1': 'unknown heading', 'B1': 'North', 'C1': 'South'}),
                        (2, {'A2': '101353R', 'B2': '3', 'C2': '4'})], catalog, store)
    assert result['lines'] == []
    assert 'identify_columns' in {issue['code'] for issue in result['review']['issues']}


def test_explicit_approved_alias_is_local_and_unknown_alias_is_preserved(catalog):
    class ExactOnly:
        def structured(self, *args, **kwargs):
            raise AssertionError('Approved exact alias stays local')
    config = {'specification': {'articleAliases': {'101353R-X': '101353R', '999999X': 'MISSING'}}}
    result = spec.read({'text': '4 pcs 101353R-X'}, catalog, config, assistant=ExactOnly())
    assert result['lines'][0]['matches'] == ['101353R']
    assert result['lines'][0]['qty'] == 4
    assert spec.read({'text': '4 pcs 999999X'}, catalog, config)['lines'][0]['matches'] == []


def test_model_cannot_repair_unknown_literal_suffix(catalog):
    class Guesser:
        def structured(self, *args, **kwargs):
            return {'lines': [{'source': '101353R-X 4 бр.', 'qty': 4, 'family': 'mortise',
                              'type': 'mega', 'filters': [{'key': 'hand', 'value': 'R'}]}]}
    line = spec.read({'text': '101353R-X 4 бр.'}, catalog, assistant=Guesser())['lines'][0]
    assert line['status'] == 'unknown' and line['matches'] == []


def test_terra_payload_uses_supported_reasoning_and_existing_ledger(tmp_path):
    import order_assistant
    captured = []
    assistant = order_assistant.Assistant('synthetic-key', state=tmp_path, transport=lambda payload: captured.append(payload) or {'lines': []})
    assistant.ledger.commission()
    assert assistant.structured('spec', 'Parse a specification', {'text': 'sample'}, spec.SCHEMA) == {'lines': []}
    assert captured[0]['model'] == 'gpt-5.6-terra'
    assert captured[0]['reasoning'] == {'effort': 'low'}
    assert captured[0]['text']['format']['strict'] is True
    assert assistant.ledger.used('spec')[1] == 1


def test_image_layout_requires_original_review_instead_of_flat_model_guesses(catalog, store):
    import order_files
    class Guesser:
        def structured(self, *args, **kwargs):
            raise AssertionError('A flat vision response cannot establish allocation columns')
    uploaded = order_files.stage(store, 'branches.png', b'\x89PNG\r\n\x1a\nfixture', 'image-intake-test-0001')
    result = spec.read({'upload': uploaded['id']}, catalog, store=store, assistant=Guesser())
    assert result['lines'] == []
    assert result['review']['issues'][0]['code'] == 'image_layout_review'
    assert result['review']['upload_id'] == uploaded['id']
    assert order_files.read_pending(store, uploaded['id']).endswith(b'fixture')


@pytest.mark.parametrize('text', ['SKU | Варна | София\n101353R | 3 | 4',
    'Артикул     Практикер Варна     Практикер София\n101353R         3       4',
    '101353R | 3 | 4'])
def test_pasted_or_pdf_layout_matrix_is_never_flattened(catalog, text):
    result = spec.read({'text': text}, catalog)
    assert result['lines'] == []
    assert result['review']['issues'][0]['code'] == 'document_table_review'


def test_word_table_preserves_cells_for_matrix_detection(catalog, store):
    import order_files
    document = '<document><tbl><tr><tc><p><t>SKU</t></p></tc><tc><p><t>Варна</t></p></tc><tc><p><t>София</t></p></tc></tr><tr><tc><p><t>101353R</t></p></tc><tc><p><t>3</t></p></tc><tc><p><t>4</t></p></tc></tr></tbl></document>'
    body = io.BytesIO()
    with zipfile.ZipFile(body, 'w') as zipped:
        zipped.writestr('[Content_Types].xml', '<Types/>')
        zipped.writestr('word/document.xml', document)
    assert spec.extract('table.docx', body.getvalue())[0] == 'SKU | Варна | София\n101353R | 3 | 4'
    uploaded = order_files.stage(store, 'table.docx', body.getvalue(), 'word-intake-test-0001')
    result = spec.read({'upload': uploaded['id']}, catalog, store=store)
    assert result['review']['issues'][0]['code'] == 'document_table_review'


def test_plain_text_upload_and_readable_pdf_spacing_preserve_quantity(catalog, store):
    import order_files
    uploaded = order_files.stage(store, 'request.txt', b'101353R 24', 'text-intake-test-0001')
    assert spec.read({'upload': uploaded['id']}, catalog, store=store)['lines'][0]['qty'] == 24
    assert spec.read({'text': '101353R      24'}, catalog)['lines'][0]['qty'] == 24


def test_csv_matrix_preserves_blank_destinations_and_totals(catalog, store):
    import order_files
    source = 'SKU;Варна;София;Общо\n101353R;;7;7\n101353L;5;;5\nОбщо;5;7;12'
    uploaded = order_files.stage(store, 'request.csv', source.encode(), 'csv-intake-test-0001')
    result = spec.read({'upload': uploaded['id']}, catalog, store=store)
    assert [line['qty'] for line in result['lines']] == [7, 5]
    assert result['review']['issues'] == []
    assert result['review']['allocations'][0]['source_cell'] == 'csv!C2'


def test_duplicate_row_coordinates_are_rejected(catalog, store):
    with pytest.raises(ValueError, match='distinct spreadsheet row'):
        read_file([(1, {'A1': 'SKU', 'B1': 'Варна'}),
                   (2, {'A2': '101353R', 'B2': '3'}),
                   (2, {'A2': '101353R', 'B2': '3'})], catalog, store)


def test_headerless_list_obeys_same_article_limit(catalog, store):
    with pytest.raises(ValueError, match='100 articles'):
        read_file([(i, {'A' + str(i): '101353R', 'B' + str(i): '2'}) for i in range(1, 102)], catalog, store)


def test_formula_allocation_is_explicit_review_even_with_cached_number(catalog):
    import spec_workbook
    with spec.archive(workbook([(1, {'A1': 'SKU', 'B1': 'Варна'}),
                                (2, {'A2': '101353R', 'B2': '3'})])) as zipped:
        tables = spec_workbook.extract(zipped, spec._xml)
    tables[0]['rows'][1]['cells'][2]['formula'] = True
    result = spec_workbook.parse(tables, lambda source, fragment, **kw: spec._resolve(source, fragment, spec.index(catalog), **kw))
    assert result['lines'][0]['qty'] == 3
    assert result['review']['issues'][0]['code'] == 'formula_quantity'


def test_mixed_list_and_matrix_sheets_require_review(catalog):
    import spec_workbook
    tables = []
    for i, header in enumerate(('Quantity', 'Практикер Варна')):
        with spec.archive(workbook([(1, {'A1': 'SKU', 'B1': header}),
                                    (2, {'A2': '101353R', 'B2': '3'})])) as zipped:
            sheet = spec_workbook.extract(zipped, spec._xml)[0]
            sheet['id'] = 'sheet' + str(i + 1)
            tables.append(sheet)
    result = spec_workbook.parse(tables, lambda source, fragment, **kw: spec._resolve(source, fragment, spec.index(catalog), **kw))
    assert 'mixed_layouts' in {issue['code'] for issue in result['review']['issues']}


def test_sparse_matrix_allocation_limit_is_explicit(catalog, monkeypatch):
    import spec_workbook
    monkeypatch.setattr(spec_workbook, 'MAX_ALLOCATIONS', 1)
    with spec.archive(workbook([(1, {'A1': 'SKU', 'B1': 'Варна', 'C1': 'София'}),
                                (2, {'A2': '101353R', 'B2': '3', 'C2': '4'})])) as zipped:
        tables = spec_workbook.extract(zipped, spec._xml)
    with pytest.raises(ValueError, match='2,000 destination'):
        spec_workbook.parse(tables, lambda source, fragment, **kw: spec._resolve(source, fragment, spec.index(catalog), **kw))


def test_single_destination_word_table_still_needs_allocation_review(catalog):
    result = spec.read({'text': 'SKU | Практикер Варна\n101353R | 24'}, catalog)
    assert result['lines'] == []
    assert result['review']['issues'][0]['code'] == 'document_table_review'


def test_empty_workbook_requires_readable_article_rows(catalog, store):
    result = read_file([], catalog, store)
    assert result['review']['issues'][0]['code'] == 'article_rows_required'


def test_unreadable_pdf_has_explicit_review_instead_of_quantity_one(catalog, store, monkeypatch):
    import order_files
    uploaded = order_files.stage(store, 'scan.pdf', b'%PDF-1.4\n%%EOF', 'scan-intake-test-0001')
    monkeypatch.setattr(spec, 'extract', lambda *args: ('', None))
    result = spec.read({'upload': uploaded['id']}, catalog, store=store)
    assert result['lines'] == []
    assert result['review']['issues'][0]['code'] == 'document_text_review'


def test_model_can_parse_quantity_words_but_candidate_needs_selection(catalog):
    class Parser:
        def structured(self, *args, **kwargs):
            return {'lines': [{'source': 'seven bespoke latching assemblies', 'qty': 7, 'family': '',
                              'type': 'mega', 'filters': [{'key': 'hand', 'value': 'R'}]}]}
    line = spec.read({'text': 'seven bespoke latching assemblies'}, catalog, assistant=Parser())['lines'][0]
    assert line['qty'] == 7 and line['matches'] == ['101353R']
    assert line['status'] == 'choose' and line['engine'] == 'llm'
