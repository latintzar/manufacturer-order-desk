"""Read-only order presentation shared by the two independently packaged consumers.

Keep this projection identical in Orders/platform_source.py and the manufacturer's
manufacturer_order.py; their integration contract checks both against CompanyStore.
"""
from __future__ import annotations

import json
import math
from urllib.parse import urlsplit

from origin_config import configured_origin
ORIGIN = configured_origin()


def amount(value):
    return value if not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) else None


def title(value):
    if isinstance(value, dict):
        value = value.get('en') or value.get('bg') or ''
    return value.strip() if isinstance(value, str) else ''


def image_url(value, slug):
    if not isinstance(value, str) or not value:
        return ''
    if value.startswith('/') and not value.startswith('//'):
        value = ORIGIN + ('' if value.startswith('/' + slug + '/') else '/' + slug) + value
    try:
        parsed = urlsplit(value)
        return value if parsed.scheme in {'http', 'https'} and parsed.hostname and not parsed.username and not parsed.password else ''
    except ValueError:
        return ''


def project_order(db, record):
    record = dict(record)
    customer_row = db.execute('SELECT data FROM customers WHERE id=?', (record['customer_id'],)).fetchone()
    customer = json.loads(customer_row['data']) if customer_row else {}
    quote = json.loads(record['quote'])
    company = db.execute('SELECT id FROM company').fetchone()
    slug = company['id'] if company else ''
    # The first immutable estimate event is a durable source sequence, including
    # after VACUUM/backup restore. Missing-estimate legacy rows have a distinct
    # reference namespace; their rowid fallback carries only its original DB scope.
    has_estimates = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='estimates'").fetchone()
    sequence = db.execute("SELECT MIN(id) AS sequence FROM estimates WHERE order_id=? AND kind='estimate'", (record['id'],)).fetchone()['sequence'] if has_estimates else None
    legacy = sequence is None
    if legacy:
        sequence = db.execute('SELECT rowid AS sequence FROM orders WHERE id=?', (record['id'],)).fetchone()['sequence']
    explicit_number = title(record.get('order_number') or quote.get('order_number'))
    display_number = explicit_number if explicit_number.startswith('#') else '#' + explicit_number if explicit_number else '#' + ('L' if legacy else '') + str(1000 + sequence)
    lines = []
    for row in db.execute('''SELECT l.item_id,l.quantity,l.data,i.data AS item_data,t.data AS type_data
            FROM order_lines l LEFT JOIN items i ON i.id=l.item_id
            LEFT JOIN product_types t ON t.id=i.type_id WHERE l.order_id=? ORDER BY l.id''', (record['id'],)):
        line = json.loads(row['data'])
        item = json.loads(row['item_data']) if row['item_data'] else {}
        category = json.loads(row['type_data']) if row['type_data'] else {}
        quantity = amount(line.get('quantity', row['quantity']))
        plan = line.get('plan') if isinstance(line.get('plan'), dict) else {}
        raw_total = amount(line.get('gross', line.get('total')))
        needs_quote = bool(line.get('needs_quote') or line.get('quote_requested') or line.get('pricing_state') == 'to_quote'
            or line.get('confirmation', item.get('q', False)) or plan.get('ask') or plan.get('pending') or raw_total is None)
        total = None if needs_quote else raw_total
        unit_price = amount(line.get('unit_price')) if total is not None else None
        if unit_price is None and total is not None and quantity and quantity > 0:
            unit_price = total / quantity
        name = title(line.get('name') or line.get('title') or line.get('product_name'))
        category_name = title(category.get('en') or category.get('bg'))
        description = title(line.get('description') or line.get('custom') or item.get('se') or item.get('s'))
        if not name:
            name = category_name or ('Custom request' if line.get('custom') or line.get('kind') == 'custom' else 'Product request')
        unit = title(line.get('unit') or item.get('u')) or ('kg' if line.get('stock_basis') == 'kilogram' else 'm' if line.get('stock_basis') == 'metre' else 'pc')
        lines.append({**line, 'name': name, 'code': item.get('c') or row['item_id'] or '',
            'quantity': quantity, 'unit': unit, 'unit_price': unit_price, 'total': total,
            'pricing_state': 'to_quote' if needs_quote else 'priced',
            'description': description, 'category_name': category_name,
            'attributes': item.get('a', {}), 'image_url': image_url(item.get('img') or category.get('img'), slug),
            'source_url': title(category.get('url') or line.get('source'))})
    priced = [line for line in lines if line['pricing_state'] == 'priced']
    unpriced = len(priced) != len(lines)
    quote_total = amount(quote.get('gross', quote.get('total')))
    incomplete = unpriced or bool(quote.get('needs_quote') or quote.get('quote_requested') or quote.get('confirmation')) or quote_total is None
    pricing_state = ('partially_priced' if priced else 'to_quote') if incomplete else 'priced'
    company_name = title(customer.get('company') or customer.get('company_name') or customer.get('coName'))
    return {'id': record['id'], 'customer_id': record['customer_id'], 'number': display_number, 'display_number': display_number,
        'created_at': record['created_at'], 'status': record['state'],
        'customer': {**customer, 'name': title(customer.get('name')), 'company': company_name,
            'display_company': company_name, 'company_details_needed': not bool(company_name),
            'email': title(customer.get('email')), 'website': title(customer.get('website') or customer.get('company_website')),
            'trade': title(customer.get('trade') or customer.get('work_type') or customer.get('business_type') or customer.get('activity')),
            'project': title(customer.get('project') or customer.get('project_description') or customer.get('business_description') or customer.get('nature'))},
        'items_count': len(lines), 'total': None if incomplete else quote_total,
        'priced_total': round(sum(line['total'] for line in priced), 2) if priced else None,
        'pricing_state': pricing_state, 'currency': quote.get('currency', 'EUR'),
        'fulfilment': quote.get('fulfilment', customer.get('fulfilment', 'pickup')),
        'lines': lines, 'quote': quote}
