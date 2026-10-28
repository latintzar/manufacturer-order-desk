"""Admitted staff orders: deterministic validation and the company's Orders command."""
from __future__ import annotations

import base64
import copy
import re
from pathlib import Path

from manufacturer_store import Invalid, SourceUnavailable

MAX_ORIGINAL = 4 * 1024 * 1024
CUSTOMER_FIELDS = {'company', 'name', 'email', 'phone', 'poNumber', 'warehouseId', 'line1', 'zip', 'city',
                   'coName', 'eik', 'vatNo', 'bline1', 'bzip', 'bcity', 'notes', 'project', 'needBy'}
CUSTOMER_LIMITS = {'company': 200, 'poNumber': 100, 'notes': 2000, 'project': 2000}


def validate(arguments):
    if not isinstance(arguments, dict) or set(arguments) - {'idempotency_key', 'customer', 'lines', 'fulfilment', 'original_file'}:
        raise Invalid('Enter the new order details.')
    value = copy.deepcopy(arguments)
    if not isinstance(value.get('idempotency_key'), str) or not re.fullmatch(r'[a-zA-Z0-9_-]{16,100}', value['idempotency_key']):
        raise Invalid('Reopen the new order form.')
    customer = value.get('customer')
    if not isinstance(customer, dict) or set(customer) - CUSTOMER_FIELDS:
        raise Invalid('Enter the company and contact details.')
    for key, text in customer.items():
        if not isinstance(text, str) or len(text) > CUSTOMER_LIMITS.get(key, 300) or '\x00' in text:
            raise Invalid('Check the field lengths and contents.')
        customer[key] = text.strip()
    if not customer.get('company') or not customer.get('name') or not (customer.get('email') or customer.get('phone')):
        raise Invalid('Enter a company, contact name and email or phone number.')
    if customer.get('email') and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', customer['email']):
        raise Invalid('Enter a valid contact email.')
    if not customer.get('email') and not re.fullmatch(r'\+?[0-9][0-9 ()-]{5,30}', customer.get('phone', '')):
        raise Invalid('Enter a valid contact phone number.')
    lines = value.get('lines')
    if not isinstance(lines, list) or not 1 <= len(lines) <= 100:
        raise Invalid('Add between 1 and 100 items.')
    seen = set()
    for line in lines:
        if (not isinstance(line, dict) or set(line) != {'article', 'quantity'}
                or not isinstance(line['article'], str) or not 1 <= len(line['article']) <= 100
                or line['article'] in seen or type(line['quantity']) is not int
                or not 1 <= line['quantity'] <= 9999):
            raise Invalid('Choose distinct items and whole-number quantities from 1 to 9999.')
        seen.add(line['article'])
    if value.get('fulfilment', 'delivery') not in {'delivery', 'pickup'}:
        raise Invalid('Choose delivery or warehouse collection.')
    if value.get('fulfilment', 'delivery') == 'delivery' and not all(customer.get(key) for key in ('line1', 'city', 'zip')):
        raise Invalid('Enter the delivery address, city and postcode.')
    attachment = value.get('original_file')
    if attachment is not None:
        if not isinstance(attachment, dict) or set(attachment) != {'filename', 'content_type', 'content_base64'}:
            raise Invalid('Attach the original document again.')
        name = attachment['filename']
        if not isinstance(name, str) or len(name) > 200 or Path(name).name != name or Path(name).suffix.lower() not in {'.pdf', '.csv', '.xlsx', '.docx', '.txt'}:
            raise Invalid('Choose a PDF, spreadsheet or text document.')
        if not isinstance(attachment['content_type'], str) or len(attachment['content_type']) > 100:
            raise Invalid('Check the original document format.')
        try:
            encoded = attachment['content_base64']
            if not isinstance(encoded, str) or len(encoded) > ((MAX_ORIGINAL + 2) // 3) * 4:
                raise ValueError()
            raw = base64.b64decode(encoded, validate=True)
            if not 0 < len(raw) <= MAX_ORIGINAL:
                raise ValueError()
        except (ValueError, TypeError):
            raise Invalid('Attach an original document up to 4 MB.') from None
    return value


def create(workspace, actor, arguments):
    member = workspace.member(actor, write=True)
    value = validate(arguments)
    command = getattr(workspace.source, 'create_order', None)
    if command is None:
        raise SourceUnavailable('Connect the company order service.')
    # The native identity supplies attribution. The browser cannot nominate another actor.
    value['actor'] = {'id': actor, 'name': member.get('display_name') or actor}
    workspace.member(actor, write=True)
    result = command(value)
    with workspace._customers_lock:
        workspace._customers_cache = None
    workspace.member(actor, write=True)
    return result
