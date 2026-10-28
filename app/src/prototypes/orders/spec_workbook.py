"""Bounded XLSX cell extraction and arithmetic for customer allocation matrices.

Cell references remain source evidence. Branch labels describe destinations in the customer's
file; they never become ERP warehouse identifiers or shipping instructions automatically.
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata

MAX_CELLS = 20_000
MAX_ALLOCATIONS = 2_000
MAX_COLUMNS = 200
MAX_ROWS = 5_000


def normal(value):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', str(value)).casefold()).strip(' .:')


def col_number(letters):
    number = 0
    for letter in letters:
        number = number * 26 + ord(letter) - ord('A') + 1
    return number


def col_name(number):
    result = ''
    while number:
        number, digit = divmod(number - 1, 26)
        result = chr(65 + digit) + result
    return result


def extract(zipped, xml):
    shared = []
    if 'xl/sharedStrings.xml' in zipped.namelist():
        shared = [''.join(node.itertext()) for node in xml(zipped, 'xl/sharedStrings.xml')]
    tables, count = [], 0
    for filename in sorted(zipped.namelist()):
        if not re.fullmatch(r'xl/worksheets/sheet\d+\.xml', filename):
            continue
        rows, width, seen_rows = [], 0, set()
        for node in xml(zipped, filename).iter():
            if node.tag.rsplit('}', 1)[-1] != 'row':
                continue
            number = int(node.get('r', str(len(rows) + 1)))
            if not 1 <= number <= MAX_ROWS:
                raise ValueError('Use a spreadsheet containing up to 5,000 rows.')
            if number in seen_rows:
                raise ValueError('Use distinct spreadsheet row numbers.')
            seen_rows.add(number)
            cells, previous = {}, 0
            for cell in node:
                if cell.tag.rsplit('}', 1)[-1] != 'c':
                    continue
                reference = cell.get('r', col_name(previous + 1) + str(number))
                found = re.fullmatch(r'([A-Z]{1,3})([1-9]\d*)', reference)
                if not found or int(found[2]) != number:
                    raise ValueError('Check the spreadsheet cell references.')
                column = col_number(found[1])
                if column > MAX_COLUMNS or column in cells:
                    raise ValueError('Use distinct spreadsheet columns within the first 200 columns.')
                previous, width, count = column, max(width, column), count + 1
                if count > MAX_CELLS:
                    raise ValueError('Split the spreadsheet into files containing up to 20,000 cells.')
                parts = {part.tag.rsplit('}', 1)[-1]: part for part in cell}
                value = (parts['v'].text or '') if 'v' in parts else ''
                if cell.get('t') == 'inlineStr':
                    value = ''.join(parts['is'].itertext()) if 'is' in parts else ''
                elif cell.get('t') == 's':
                    try:
                        position = int(value)
                        if not 0 <= position < len(shared):
                            raise ValueError('shared_text_reference')
                        value = shared[position]
                    except (ValueError, IndexError):
                        raise ValueError('Check the spreadsheet shared text references.') from None
                cells[column] = {'value': value.strip(), 'reference': reference,
                                 'formula': 'f' in parts, 'type': cell.get('t', '')}
            if cells:
                rows.append({'number': number, 'cells': cells})
        if rows:
            tables.append({'id': filename.rsplit('/', 1)[-1][:-4], 'rows': rows, 'width': width})
    return tables


def delimited(body):
    try:
        source = body.decode('utf-8-sig')
    except UnicodeDecodeError as error:
        raise ValueError('Save the CSV using UTF-8 encoding.') from error
    if len(source) > 24_000:
        raise ValueError('Split the specification into documents of up to 24,000 characters.')
    try:
        dialect = csv.Sniffer().sniff(source[:4096], delimiters=',;\t|')
    except csv.Error:
        dialect = csv.excel
    rows, width, count = [], 0, 0
    try:
        for number, values in enumerate(csv.reader(io.StringIO(source), dialect, strict=True), 1):
            if number > MAX_ROWS or len(values) > MAX_COLUMNS:
                raise ValueError('Use a spreadsheet containing up to 5,000 rows and 200 columns.')
            count += len(values)
            if count > MAX_CELLS:
                raise ValueError('Split the spreadsheet into files containing up to 20,000 cells.')
            width = max(width, len(values))
            rows.append({'number': number, 'cells': {
                column: {'value': value.strip(), 'reference': col_name(column) + str(number),
                         'formula': value.lstrip().startswith('='), 'type': ''}
                for column, value in enumerate(values, 1)}})
    except csv.Error as error:
        raise ValueError('Check the CSV columns and quotation marks.') from error
    return [{'id': 'csv', 'rows': rows, 'width': width}] if rows else []


def text(tables):
    return '\n'.join(' | '.join(row['cells'].get(column, {}).get('value', '')
                                  for column in range(1, table['width'] + 1))
                     for table in tables for row in table['rows'])


SKU = {'sku', 'article', 'article number', 'article code', 'item code', 'product code',
       'артикул', 'артикулен номер', 'арт номер', 'арт. номер', 'код', 'код на артикул',
       'каталожен номер', 'код на доставчик'}
QUANTITY = {'qty', 'quantity', 'count', 'бр', 'брой', 'бройки', 'количество', 'кол'}
TOTAL = {'total', 'sum', 'общо', 'сума', 'общо бр', 'общо количество', 'total quantity'}
DESCRIPTIVE = {'description', 'name', 'product', 'product name', 'описание', 'наименование', 'продукт',
               'име', 'мерна единица', 'единица', 'unit', 'uom', 'ean', 'barcode', 'баркод',
               'price', 'unit price', 'цена', 'ед. цена', 'единична цена'}


def integer(cell, maximum=9999):
    if cell is None or not cell['value']:
        return None
    raw = cell['value'].strip()
    if cell.get('type') in {'b', 'e'} or not re.fullmatch(r'\d+(?:[.,]0+)?', raw):
        raise ValueError('whole_quantity')
    amount = int(raw.replace(',', '.').split('.')[0])
    if amount > maximum:
        raise ValueError('quantity_limit')
    return amount


def parse(tables, resolve):
    """Return ordinary parsed rows or an explicit, bounded allocation review."""
    lines, destinations, allocations, issues, totals_rows, zero_rows = [], [], [], [], [], []
    total_calculated, declared_rows, footer_totals, matrix = 0, [], [], False
    layouts = set()

    def issue(code, source_cell='', **extra):
        issues.append({'code': code, 'source_cell': source_cell, 'blocking': True, **extra})

    for table in tables:
        sheet = table['id']
        header = next((row for row in table['rows'][:25]
                       if any(normal(cell['value']) in SKU for cell in row['cells'].values())), None)
        if header is None:
            # A plain two-column list is safe only when every second cell is a literal quantity.
            pairs = []
            for row in table['rows']:
                populated = [(col, cell) for col, cell in sorted(row['cells'].items()) if cell['value']]
                try:
                    quantity = integer(populated[1][1]) if len(populated) == 2 else None
                except ValueError:
                    quantity = None
                if (len(populated) != 2 or quantity is None or quantity < 1
                        or populated[1][1]['formula']):
                    pairs = []
                    break
                pairs.append((row, populated[0][1]['value'], quantity))
            if pairs:
                layouts.add('list')
                for row, sku, quantity in pairs:
                    line = resolve(sku, sku, qty=quantity)
                    line['source_cell'] = sheet + '!' + next(cell['reference'] for cell in row['cells'].values() if cell['value'] == sku)
                    lines.append(line)
                    if len(lines) > 100:
                        raise ValueError('Split the spreadsheet into files containing up to 100 articles.')
                continue
            matrix = True
            issue('identify_columns', sheet)
            continue
        columns = {col: normal(cell['value']) for col, cell in header['cells'].items() if cell['value']}
        sku_cols = [col for col, label in columns.items() if label in SKU]
        quantity_cols = [col for col, label in columns.items() if label in QUANTITY]
        total_cols = [col for col, label in columns.items() if label in TOTAL]
        dest_cols = [col for col, label in columns.items() if label not in SKU | QUANTITY | TOTAL | DESCRIPTIVE]
        if len(sku_cols) != 1 or len(total_cols) > 1 or len(quantity_cols) > 1:
            matrix = True
            issue('identify_columns', sheet + '!' + str(header['number']))
            continue
        is_matrix = bool(dest_cols)
        matrix |= is_matrix
        layouts.add('matrix' if is_matrix else 'list')
        if (quantity_cols and is_matrix) or (not quantity_cols and not dest_cols):
            matrix = True
            issue('identify_quantity_columns', sheet)
            continue
        sku_col = sku_cols[0]
        total_col = total_cols[0] if total_cols else None
        quantity_columns = dest_cols if is_matrix else quantity_cols
        known = set(columns)
        destination_sums = {col: 0 for col in dest_cols}
        labels = [columns[col] for col in dest_cols]
        if len(set(labels)) != len(labels):
            issue('duplicate_destination', sheet)
        for col in dest_cols:
            destinations.append({'id': sheet + ':' + col_name(col),
                                 'label': header['cells'][col]['value'][:200],
                                 'source_cell': sheet + '!' + header['cells'][col]['reference']})
        for row in table['rows']:
            if row['number'] <= header['number']:
                continue
            cells = row['cells']
            sku = cells.get(sku_col, {}).get('value', '').strip()
            coordinate = sheet + '!' + col_name(sku_col) + str(row['number'])
            if normal(sku) in SKU:
                continue
            footer = normal(sku) in TOTAL
            quantities = []
            for col in quantity_columns:
                cell = cells.get(col)
                source_cell = sheet + '!' + col_name(col) + str(row['number'])
                try:
                    quantity = integer(cell, 999900 if footer else 9999)
                except ValueError as error:
                    issue(str(error), source_cell)
                    continue
                if cell and cell['formula'] and not footer:
                    issue('formula_quantity', source_cell)
                if quantity is not None:
                    quantities.append((col, quantity, source_cell))
                elif cell and cell['formula']:
                    issue('formula_value_required', source_cell)
            for col, cell in cells.items():
                if col not in known and cell['value']:
                    issue('unmapped_cell', sheet + '!' + cell['reference'])
            if not sku:
                if quantities:
                    issue('article_required', coordinate)
                continue
            if footer:
                for col, quantity, source_cell in quantities:
                    if is_matrix and quantity != destination_sums[col]:
                        issue('destination_total_mismatch', source_cell,
                              declared=quantity, calculated=destination_sums[col])
                if total_col:
                    try:
                        declared = integer(cells.get(total_col), 999900)
                    except ValueError:
                        declared = None
                        issue('invalid_total', sheet + '!' + col_name(total_col) + str(row['number']))
                    if declared is not None:
                        footer_totals.append(declared)
                continue
            amount = sum(quantity for _, quantity, _ in quantities)
            if amount == 0 and quantities:
                zero_rows.append(coordinate)
                if total_col:
                    try:
                        declared_zero = integer(cells.get(total_col), 999900)
                        if declared_zero not in (None, 0):
                            issue('line_total_mismatch', coordinate, declared=declared_zero, calculated=0)
                    except ValueError:
                        issue('invalid_total', coordinate)
                continue
            if not quantities or amount < 1 or amount > 9999:
                issue('check_line_quantity', coordinate)
            line = resolve(sku, sku, qty=amount) if amount > 0 else {
                'source': sku, 'qty': 0, 'family': '', 'filters': {}, 'matches': [], 'status': 'unknown'}
            line['qty'] = amount
            line['source_cell'] = coordinate
            line_number = len(lines)
            lines.append(line)
            for col, quantity, source_cell in quantities:
                if is_matrix and quantity > 0:
                    allocations.append({'line': line_number, 'sku': sku,
                                        'destination_id': sheet + ':' + col_name(col),
                                        'quantity': quantity, 'source_cell': source_cell})
                    destination_sums[col] += quantity
            total_calculated += amount
            declared = None
            if total_col:
                try:
                    declared = integer(cells.get(total_col), 999900)
                except ValueError:
                    issue('invalid_total', sheet + '!' + col_name(total_col) + str(row['number']))
                if declared is None:
                    issue('total_value_required', sheet + '!' + col_name(total_col) + str(row['number']))
                elif declared != amount:
                    issue('line_total_mismatch', coordinate, declared=declared, calculated=amount)
                if declared is not None:
                    declared_rows.append(declared)
            totals_rows.append({'line': line_number, 'declared': declared, 'calculated': amount,
                                'source_cell': coordinate})
            if len(lines) > 100 or len(allocations) > MAX_ALLOCATIONS:
                raise ValueError('Split the spreadsheet into 100 articles and 2,000 destination quantities per file.')
    if len(layouts) > 1:
        issue('mixed_layouts')
    if not lines:
        issue('article_rows_required')
    if not matrix and not issues:
        return {'lines': lines}
    declared = sum(footer_totals) if footer_totals else sum(declared_rows) if declared_rows else None
    if declared is not None and declared != total_calculated:
        issue('document_total_mismatch', declared=declared, calculated=total_calculated)
    return {'lines': lines, 'review': {
        'schema': 'rocoto.orders.allocations.v1', 'kind': 'allocation_matrix',
        'requires_confirmation': True, 'destinations': destinations, 'allocations': allocations,
        'totals': {'declared': declared, 'calculated': total_calculated,
                   'status': 'mismatch' if issues else 'matched' if declared is not None else 'not_provided',
                   'rows': totals_rows}, 'zero_rows': zero_rows, 'issues': issues}}
