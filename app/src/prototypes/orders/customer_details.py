"""Validate public checkout context retained with the customer's order."""
from __future__ import annotations

import json
import re
from urllib.parse import urlsplit, urlunsplit


def capture(value):
    """Bound customer-provided context independently of authoritative order pricing."""
    def fields(obj, required, optional=()):
        if not isinstance(obj, dict) or set(obj) - set(required) - set(optional) or set(required) - set(obj):
            raise ValueError('Check the saved request details.')

    def text(value, maximum, empty=True):
        if (not isinstance(value, str) or len(value) > maximum or not empty and not value.strip()
                or any(ord(c) < 32 and c not in '\n\r\t' for c in value)):
            raise ValueError('Check the saved request details.')
        return value

    def rows(value, maximum):
        if not isinstance(value, list) or len(value) > maximum:
            raise ValueError('Check the saved request details.')
        return value

    def quantity(value):
        if type(value) is not int or not 1 <= value <= 9999:
            raise ValueError('Check the requested quantities.')

    fields(value, {'schema', 'entry_path', 'language'}, {'questionnaire', 'proposal', 'specification'})
    if (value['schema'] != 'rocoto.orders.capture.v1'
            or value['entry_path'] not in {'questionnaire', 'specification', 'catalogue'}
            or value['language'] not in {'en', 'bg'}):
        raise ValueError('Check the saved request details.')
    if len(json.dumps(value, ensure_ascii=False).encode()) > 256000:
        raise ValueError('Keep the request details within 256 KB.')
    if (value['entry_path'] != 'questionnaire' and any(key in value for key in ('questionnaire', 'proposal'))
            or value['entry_path'] != 'specification' and 'specification' in value):
        raise ValueError('Use the details for your selected order path.')
    if 'questionnaire' in value:
        item = value['questionnaire']
        fields(item, {'title', 'questions', 'project'})
        text(item['title'], 240)
        text(item['project'], 2000)
        seen = set()
        for question in rows(item['questions'], 40):
            fields(question, {'id', 'label', 'status', 'answers'})
            identifier = text(question['id'], 100, False)
            if identifier in seen or question['status'] not in {'answered', 'unknown', 'unanswered'}:
                raise ValueError('Check the saved questions.')
            seen.add(identifier)
            text(question['label'], 400, False)
            answers = rows(question['answers'], 30)
            for answer in answers:
                fields(answer, {'id', 'label'})
                text(answer['id'], 100, False)
                text(answer['label'], 400, False)
            if (question['status'] == 'unanswered' and answers
                    or question['status'] != 'unanswered' and not answers):
                raise ValueError('Check the saved question answers.')
            if (question['status'] == 'unknown' and (len(answers) != 1 or answers[0]['id'] != '?')
                    or question['status'] == 'answered' and any(answer['id'] == '?' for answer in answers)):
                raise ValueError('Keep unanswered and uncertain choices distinct.')
    if 'proposal' in value:
        item = value['proposal']
        fields(item, {'title', 'summary', 'selected'})
        text(item['title'], 240)
        text(item['summary'], 4000)
        for selected in rows(item['selected'], 100):
            fields(selected, {'code', 'quantity', 'reason'})
            text(selected['code'], 100, False)
            quantity(selected['quantity'])
            text(selected['reason'], 2000)
    if 'specification' in value:
        item = value['specification']
        fields(item, {'text', 'lines'}, {'file_id', 'reading_id', 'allocations_confirmed'})
        if 'reading_id' in item and not re.fullmatch(r'[a-f0-9]{32}', text(item['reading_id'], 32)):
            raise ValueError('Прочетете спецификацията отново.')
        if 'allocations_confirmed' in item and type(item['allocations_confirmed']) is not bool:
            raise ValueError('Потвърдете разпределението по обекти.')
        text(item['text'], 24000)
        if 'file_id' in item and not re.fullmatch(r'[a-f0-9]{32}', text(item['file_id'], 32)):
            raise ValueError('Choose the specification file again.')
        for line in rows(item['lines'], 100):
            fields(line, {'source', 'quantity', 'selected_code', 'status'})
            text(line['source'], 2000)
            quantity(line['quantity'])
            text(line['selected_code'], 100)
            if line['status'] not in {'exact', 'choose', 'unknown'}:
                raise ValueError('Check the specification choices.')
    return value


def validate(value, config, *, allow_phone=False):
    if not isinstance(value, dict) or any(key in value for key in ('is_demo', 'demo_scenario')) or any(not isinstance(v, str) or len(v) > (24000 if k == 'specification' else 2000) for k, v in value.items() if k != 'capture'):
        raise ValueError('Check your contact details.')
    result = {key: val.strip() for key, val in value.items() if key != 'capture'}
    if 'capture' in value:
        result['capture'] = capture(value['capture'])
        specification = result['capture'].get('specification', {})
        if specification.get('file_id', '') != result.get('specification_file', ''):
            raise ValueError('Choose the specification file for this request.')
    if (not (allow_phone and not result.get('email') and re.fullmatch(r'\+?[0-9][0-9 ()-]{5,30}', result.get('phone', '')))
            and not re.fullmatch(r'[^\s@]{1,64}@[^\s@]{1,190}\.[^\s@]{2,24}', result.get('email', ''))):
        raise ValueError('Enter your email address.')
    required = config.get('checkout', {}).get('companyRequired', False) or result.get('kind') == 'company'
    if required and not result.get('company'):
        raise ValueError('Enter your company name.')
    if len(result.get('company', '')) > 200 or len(result.get('trade', '')) > 200:
        raise ValueError('Use a company name and type of work up to 200 characters.')
    po_number = result.get('poNumber', '')
    if len(po_number) > 100 or any(ord(character) < 32 for character in po_number):
        raise ValueError('Използвайте номер на заявка до 100 знака.')
    warehouses = config.get('checkout', {}).get('warehouses', [])
    warehouse_id = result.get('warehouseId', '')
    if warehouse_id:
        warehouse = next((row for row in warehouses if row.get('id') == warehouse_id), None)
        if warehouse is None:
            raise ValueError('Изберете склад от списъка.')
        result.update(warehouseId=warehouse['id'], warehouseName=warehouse['name'],
                      warehouseErpCode=warehouse.get('erpCode', ''))
    elif warehouses:
        raise ValueError('Изберете склад за поръчката.')
    website = result.get('website', '')
    if website:
        if '://' not in website:
            website = 'https://' + website
        parsed = urlsplit(website)
        if (parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username
                or parsed.password or parsed.port not in (None, 80, 443)
                or not re.fullmatch(r'[A-Za-z0-9\u0080-\uffff.-]+', parsed.hostname)
                or '.' not in parsed.hostname or any(c.isspace() or c in '<>"\\' for c in website)):
            raise ValueError('Enter a company website, such as company.bg.')
        result['website'] = urlunsplit(('https', parsed.hostname.lower(), parsed.path, parsed.query, ''))
    return result
