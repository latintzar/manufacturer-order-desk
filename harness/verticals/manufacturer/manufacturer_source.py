"""Deterministic manufacturer request briefs and company-scoped customer records."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

PERSONAL_DOMAINS = {'gmail.com', 'googlemail.com', 'outlook.com', 'hotmail.com', 'live.com', 'yahoo.com',
                    'icloud.com', 'me.com', 'aol.com', 'proton.me', 'protonmail.com', 'mail.com', 'gmx.com',
                    'gmx.de', 'yandex.com', 'qq.com', '163.com', 'abv.bg', 'mail.bg', 'example.invalid'}


def text(value, maximum=2000):
    return value.strip()[:maximum] if isinstance(value, str) else ''


def heading(value, maximum=100):
    value = text(value)
    if len(value) <= maximum:
        return value
    words = value[:maximum - 1].rsplit(' ', 1)
    return (words[0] if len(words) > 1 else value[:maximum - 1]).rstrip(' .,;:-') + '…'


def number(value):
    return value if type(value) in {int, float} and math.isfinite(value) and value >= 0 else None



@lru_cache(maxsize=1)
def demo_translations():
    return json.loads((Path(__file__).parent / 'fixtures/bld-demo-bg.json').read_text())


def localize_demo(value):
    if isinstance(value, str):
        return demo_translations().get(value, value)
    if isinstance(value, list):
        return [localize_demo(item) for item in value]
    if isinstance(value, dict):
        return {key: localize_demo(item) for key, item in value.items()}
    return value


def catalogue_labels(platform):
    """Read one label index per immutable version; quote values stay in the order."""
    with platform.connect() as db:
        current = db.execute('SELECT version_id FROM manufacturer_current WHERE company_id=?', (platform.company_id,)).fetchone()
    cached = getattr(platform, '_order_label_index', None)
    if cached and cached['version_id'] == current['version_id']:
        return cached
    value = platform.configurator()
    document = value['document']
    locale = document['configuration'].get('defaultLanguage', 'en')
    items = {}
    for category in document['catalogue'].get('cats', []):
        for item in category.get('items', []):
            items[item.get('c')] = {'name': category.get(locale) or category.get('en') or category.get('bg'),
                'description': item.get('s') if locale == 'bg' else item.get('se'),
                'source_name': category.get('en'), 'source_description': item.get('se')}
    result = {'version_id': value['version_id'], 'locale': locale, 'items': items}
    platform._order_label_index = result
    return result


def localize_catalogue_lines(order, index):
    for line in order.get('lines', []):
        item = index['items'].get(line.get('code'))
        if not item:
            continue
        if item['name'] and line.get('name') in (item['source_name'], item['name']):
            line['name'] = item['name']
        if item['description'] and line.get('description') in (item['source_description'], item['description'], ''):
            line['description'] = item['description']
    return order


BRIEF_BG = {'Confirm: ': 'За уточняване: ', 'Requested product': 'Заявен артикул', 'Specification review': 'Спецификация', 'Customer requirements': 'Изисквания на клиента', 'Product enquiry': 'Избор от каталога', 'Type of work': 'Дейност', 'Required date': 'Желана дата', 'Confirm products and quantities from the customer’s requirements.': 'Уточнете артикулите и количествата.', 'Match the specification: ': 'Уточнете по спецификацията: ', 'Confirm the outstanding specifications with the customer.': 'Уточнете оставащите изисквания с клиента.', 'Prepare prices for the requested products and quantities.': 'Подгответе цени за заявените артикули и количества.', 'Confirm availability and lead time for the requested quantities.': 'Потвърдете наличностите и срока за доставка.', 'Prepare a product selection for the customer’s review.': 'Подгответе избор на продукти за клиента.', 'Review the supplied specification against the selected articles.': 'Сверете спецификацията с избраните артикули.', 'Confirm the customer’s company details before issuing the offer.': 'Уточнете фирмените данни за офертата.', 'These requested products require manufacturer pricing. Prepare unit prices and lead time for the requested quantities.': 'Единичните цени се определят в офертата.', 'Some requested articles require manufacturer pricing. The confirmed item subtotal is shown separately.': 'Артикулите с цена и тези за оферта са показани отделно.', 'Confirm the complete order price before issuing the offer.': 'Потвърдете общата стойност на поръчката.', 'Prices reflect the customer’s submitted quote.': 'Цените са от подадената заявка.', 'Review the customer’s request and prepare the next response.': 'Прегледайте заявката на клиента.', 'Submitted customer requirements and saved order selections': 'Изисквания и артикули, подадени от клиента', 'Demo request': 'Демо поръчка'}


def present_order(value, *, locale="en"):
    """Use persisted answers and selected lines; never infer customer requirements."""
    order = copy.deepcopy(value)
    if locale == 'bg' and order.get('customer', {}).get('is_demo') is True and order.get('customer', {}).get('company') == 'BLD' and company_domain(order.get('customer', {}).get('website', '')) == 'bld.bg':
        order = localize_demo(order)
    customer = order.get('customer') if isinstance(order.get('customer'), dict) else {}
    capture = customer.get('capture', order.get('request_context'))
    capture = capture if isinstance(capture, dict) and capture.get('schema') == 'rocoto.orders.capture.v1' else {}
    questionnaire = capture.get('questionnaire') if isinstance(capture.get('questionnaire'), dict) else {}
    specification = capture.get('specification') if isinstance(capture.get('specification'), dict) else {}
    questions = questionnaire.get('questions') if isinstance(questionnaire.get('questions'), list) else []
    tr = (lambda value: BRIEF_BG.get(value, value)) if locale == 'bg' else (lambda value: value)
    facts, open_questions, answers = [], [], []
    project_answer = ''
    for question in questions[:100]:
        if not isinstance(question, dict):
            continue
        label, state = text(question.get('label'), 300), question.get('status')
        choices = question.get('answers') if isinstance(question.get('answers'), list) else []
        values = [text(choice.get('label'), 300) for choice in choices[:30] if isinstance(choice, dict) and text(choice.get('label'))]
        if not label:
            continue
        answers.append({'id': text(question.get('id'), 100), 'label': label, 'status': state, 'answers': copy.deepcopy(choices[:30])})
        if state == 'answered' and values:
            facts.append({'label': label, 'value': ', '.join(values), 'source': 'questionnaire'})
            if question.get('id') == 'project' and not project_answer:
                project_answer = ', '.join(values)
        elif state in {'unknown', 'unanswered'}:
            open_questions.append(tr('Confirm: ') + label)
    project = text(questionnaire.get('project') or customer.get('project') or customer.get('project_description') or customer.get('business_description'))
    spec_text = text(specification.get('text') or customer.get('specification'), 12000)
    entry = capture.get('entry_path')
    source = 'questionnaire' if entry == 'questionnaire' and (answers or project) else 'specification' if spec_text or specification.get('file_id') or customer.get('specification_file') else 'selection'
    lines = order.get('lines') if isinstance(order.get('lines'), list) else []
    selections = []
    quantities = {}
    for line in lines:
        quantity = number(line.get('quantity'))
        name = text(line.get('name') or line.get('description'), 200) or tr('Requested product')
        selections.append(f'{quantity:g} × {name}' if quantity is not None else name)
        unit = text(line.get('unit'), 30) or 'pc'
        if quantity is not None:
            quantities[unit] = quantities.get(unit, 0) + quantity
    project_title = heading(project_answer or project.split('\n', 1)[0].split('. ', 1)[0]).rstrip(' .')
    summary = project or ('. '.join(f"{fact['label']}: {fact['value']}" for fact in facts[:3]))
    if not summary:
        summary = spec_text[:500] if source == 'specification' and spec_text else '; '.join(selections[:3])
    if len(selections) > 3 and not project and not facts and source == 'selection':
        summary += f'; {len(selections) - 3} more product lines'
    title = project_title or (tr('Specification review') if source == 'specification' else tr('Customer requirements') if source == 'questionnaire' else tr('Product enquiry'))
    if source == 'selection' and len(lines) == 1 and not project_title:
        title = text(lines[0].get('name'), 100) or title
    for label, raw in [(tr('Type of work'), customer.get('trade') or customer.get('work_type')), (tr('Required date'), customer.get('date') or customer.get('requested_date'))]:
        if text(raw):
            facts.append({'label': label, 'value': text(raw), 'source': 'checkout'})
    if not lines:
        open_questions.append(tr('Confirm products and quantities from the customer’s requirements.'))
    for line in specification.get('lines', [])[:100] if isinstance(specification.get('lines'), list) else []:
        if isinstance(line, dict) and line.get('status') in {'choose', 'unknown'}:
            source_line = text(line.get('source'), 300)
            if source_line:
                open_questions.append(tr('Match the specification: ') + source_line)
    next_steps = []
    if open_questions:
        next_steps.append(tr('Confirm the outstanding specifications with the customer.'))
    unpriced = [line for line in lines if line.get('pricing_state') != 'priced']
    if order.get('pricing_state') != 'priced':
        next_steps.append(tr('Prepare prices for the requested products and quantities.'))
    next_steps.append(tr('Confirm availability and lead time for the requested quantities.') if lines else tr('Prepare a product selection for the customer’s review.'))
    if source == 'specification':
        next_steps.insert(0, tr('Review the supplied specification against the selected articles.'))
    if not text(customer.get('company')):
        next_steps.append(tr('Confirm the customer’s company details before issuing the offer.'))
    if unpriced and len(unpriced) == len(lines):
        pricing_note = tr('These requested products require manufacturer pricing. Prepare unit prices and lead time for the requested quantities.')
    elif unpriced:
        pricing_note = tr('Some requested articles require manufacturer pricing. The confirmed item subtotal is shown separately.')
    elif order.get('pricing_state') != 'priced':
        pricing_note = tr('Confirm the complete order price before issuing the offer.')
    else:
        pricing_note = tr('Prices reflect the customer’s submitted quote.')
    order['brief'] = {'title': title, 'summary': summary or tr('Review the customer’s request and prepare the next response.'),
        'facts': facts[:20], 'open_questions': list(dict.fromkeys(open_questions)), 'next_steps': list(dict.fromkeys(next_steps)),
        'source': source, 'answers': answers, 'project': project, 'specification_text': spec_text,
        'quantities': [{'unit': unit, 'quantity': quantity} for unit, quantity in sorted(quantities.items())],
        'provenance': tr('Submitted customer requirements and saved order selections')}
    order['pricing_note'] = pricing_note
    order['pricing_summary'] = {'priced_lines': len(lines) - len(unpriced), 'unpriced_lines': len(unpriced),
                                'all_to_quote': bool(lines) and len(unpriced) == len(lines)}
    order['source_customer_id'] = text(order.get('source_customer_id') or order.get('customer_id'), 200)
    order['is_demo'] = customer.get('is_demo') is True
    if order['is_demo']:
        order['demo_label'] = text(customer.get('demo_label'), 100) or tr('Demo request')
    order['request_context'] = copy.deepcopy(capture)
    return order


def company_domain(value):
    try:
        parsed = urlsplit(value if '://' in value else 'https://' + value)
        domain = (parsed.hostname or '').lower().rstrip('.')
        if parsed.scheme not in {'http', 'https'} or parsed.username or parsed.password or '.' not in domain:
            return ''
        domain = domain[4:] if domain.startswith('www.') else domain
        return domain.encode('idna').decode('ascii')
    except (ValueError, UnicodeError, TypeError):
        return ''


def customer_id(order, company_id):
    customer = order.get('customer') or {}
    domain = company_domain(text(customer.get('website')))
    email = text(customer.get('email'), 254).casefold()
    if text(customer.get('company')) and domain and domain not in PERSONAL_DOMAINS:
        identity = 'company:' + domain
    elif re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
        identity = 'email:' + email
    else:
        identity = 'source:' + str(order.get('source_customer_id') or order.get('customer_id') or order['id'])
    # Demonstration demand remains separate from any real request from that business.
    identity = ('demo:' if order.get('is_demo') is True else 'customer:') + identity
    return 'customer-' + hashlib.sha256((company_id + '\0' + identity).encode()).hexdigest()[:24]


def customer_profiles(orders, company_id):
    groups = {}
    for order in orders:
        identifier = customer_id(order, company_id)
        order['customer_id'] = identifier
        groups.setdefault(identifier, []).append(order)
    profiles = []
    for identifier, timeline in groups.items():
        timeline.sort(key=lambda order: (str(order.get('created_at', '')), order['id']), reverse=True)
        customers = [order.get('customer') or {} for order in timeline]
        profile = {key: next((customer.get(key) for customer in customers if customer.get(key)), '')
                   for key in ('company', 'display_company', 'website', 'trade', 'display_name')}
        profile['trade'] = profile['trade'] or next((text(c.get('work_type')) for c in customers if text(c.get('work_type'))), '')
        profile['display_name'] = profile['display_company'] or profile['company'] or profile['display_name'] or next((c.get('name') or c.get('email') for c in customers if c.get('name') or c.get('email')), 'Customer')
        contacts = {}
        for customer in customers:
            contact = {key: text(customer.get(key), 300) for key in ('name', 'email', 'phone')}
            key = contact['email'].casefold() or contact['phone'] or contact['name']
            if key:
                current = contacts.setdefault(key, contact)
                for field, value in contact.items():
                    if value and not current[field]:
                        current[field] = value
        totals, requested_quantities = {}, {}
        for order in timeline:
            for row in order.get('brief', {}).get('quantities', []):
                quantity, unit = number(row.get('quantity')), text(row.get('unit'), 30)
                if quantity is not None and unit:
                    requested_quantities[unit] = requested_quantities.get(unit, 0) + quantity
            if order.get('pricing_state') == 'priced' and number(order.get('total')) is not None:
                currency = order.get('currency', 'EUR')
                if not isinstance(currency, str) or not re.fullmatch(r'[A-Z]{3}', currency):
                    continue
                totals[currency] = totals.get(currency, 0) + order['total']
        enrichment = next((copy.deepcopy(order['enrichment']) for order in timeline if order.get('enrichment', {}).get('has_findings')), None)
        profiles.append({**profile, 'id': identifier, 'contacts': list(contacts.values()), 'is_demo': timeline[0].get('is_demo') is True,
            'last_request_at': timeline[0].get('created_at'), 'first_request_at': timeline[-1].get('created_at'),
            'enrichment': enrichment, 'capabilities': timeline[0].get('capabilities', {}), 'metrics': {'requests': len(timeline), 'items': sum(order.get('items_count', 0) for order in timeline),
                'quote_requests': sum(order.get('pricing_state') != 'priced' for order in timeline),
                'requested_quantities': [{'unit': unit, 'quantity': quantity} for unit, quantity in sorted(requested_quantities.items())],
                'priced_totals': [{'currency': currency, 'total': round(total, 2)} for currency, total in sorted(totals.items())]},
            'orders': timeline})
    return sorted(profiles, key=lambda profile: (str(profile['last_request_at'] or ''), profile['id']), reverse=True)
