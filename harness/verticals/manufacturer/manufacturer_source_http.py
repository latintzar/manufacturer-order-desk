"""Company-bound read transport to the owning Orders service, without database file access."""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from manufacturer_store import (
    ORIGIN,
    CompanySource,
    Conflict,
    Invalid,
    Missing,
    SourceUnavailable,
    website,
)

TOKEN_ENV = 'ROCOTO_MANUFACTURER_ORDERS_TOKEN'
MAX_RESPONSE = 12_000_000


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise SourceUnavailable('Use the commissioned company order source directly.')


class RemoteCompanySource:
    def __init__(self, state, company_id):
        self.state, self.company_id = Path(state), company_id

    def binding(self):
        path = self.state / 'manufacturer-source.json'
        try:
            if path.is_symlink() or path.stat().st_size > 8192:
                raise ValueError()
            value = json.loads(path.read_text())
            if (set(value) != {'company_id', 'company_slug', 'transport'}
                    or value['company_id'] != self.company_id or value['transport'] != 'orders-api'
                    or not re.fullmatch(r'[a-z][a-z0-9-]{1,40}', value['company_slug'])):
                raise ValueError()
            return value
        except (KeyError, OSError, TypeError, ValueError):
            raise SourceUnavailable('Connect this workspace’s company order source.') from None

    def _read(self, resource, **arguments):
        binding = self.binding()
        token = os.environ.get(TOKEN_ENV, '')
        if len(token) < 32:
            raise SourceUnavailable('Connect this workspace’s company order source.')
        query = urllib.parse.urlencode({'resource': resource, **arguments})
        url = f"{ORIGIN}/{binding['company_slug']}/rocoto/api/platform-state?{query}"
        request = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + token,
            'X-Rocoto-Company': self.company_id, 'Accept': 'application/json'})
        try:
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=15) as response:
                body = response.read(MAX_RESPONSE + 1)
            if len(body) > MAX_RESPONSE:
                raise ValueError()
            value = json.loads(body)
            if not isinstance(value, dict) or value.get('ok') is not True:
                raise ValueError()
            return value
        except urllib.error.HTTPError as error:
            if error.code == 404 and resource in {'order', 'order_files', 'file'}:
                raise Missing('Choose a company order.') from None
            raise SourceUnavailable('The company order source is temporarily unavailable.') from None
        except (OSError, ValueError):
            raise SourceUnavailable('The company order source is temporarily unavailable.') from None

    def create_order(self, value):
        """Write only through the fixed company receiver; retries retain their command key."""
        binding = self.binding()
        token = os.environ.get(TOKEN_ENV, '')
        if len(token) < 32:
            raise SourceUnavailable('Connect the company order service.')
        request = urllib.request.Request(
            f"{ORIGIN}/{binding['company_slug']}/rocoto/api/platform-orders",
            data=json.dumps(value, ensure_ascii=False, allow_nan=False).encode(), method='POST',
            headers={'Authorization': 'Bearer ' + token, 'X-Rocoto-Company': self.company_id,
                     'Content-Type': 'application/json', 'Accept': 'application/json'})
        try:
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=25) as response:
                raw = response.read(MAX_RESPONSE + 1)
            result = json.loads(raw) if len(raw) <= MAX_RESPONSE else None
            if not isinstance(result, dict) or result.get('ok') is not True or not isinstance(result.get('order_id'), str):
                raise ValueError()
            return result
        except urllib.error.HTTPError as error:
            if error.code in {400, 409, 422}:
                try:
                    detail = json.loads(error.read(4096)).get('detail', '')
                except (ValueError, OSError):
                    detail = ''
                message = detail if (isinstance(detail, str) and len(detail) <= 4096
                    and not any(ord(char) < 32 or ord(char) == 127 for char in detail)
                    and '<' not in detail and '>' not in detail
                    and re.search('[A-Za-zА-Яа-я]', detail)) else 'Check the company, warehouse and order items.'
                raise (Conflict if error.code == 409 else Invalid)(message) from None
            raise SourceUnavailable('Choose “Try again” to confirm the save. Your details are saved.') from None
        except (OSError, ValueError):
            raise SourceUnavailable('Choose “Try again” to confirm the save. Your details are saved.') from None

    def status(self):
        try:
            self._read('company')
            return {'status': 'connected', 'label': 'Company order service', 'read_only': True}
        except SourceUnavailable:
            return {'status': 'unavailable', 'label': 'Company order source needs attention', 'read_only': True}

    def company(self):
        config = self._read('company')['company']
        slug = self.binding()['company_slug']
        if config.get('slug') != slug:
            raise SourceUnavailable('Connect this workspace’s company order source.')
        name = config.get('name', {})
        name = (name.get('en') or name.get('bg') or 'Sample Hardware') if isinstance(name, dict) else str(name)
        try:
            source = website(config.get('source', ''))
        except Invalid:
            source = 'https://sample-hardware.example.test/'
        logo = config.get('logo', '')
        return {'id': self.company_id, 'slug': slug, 'name': name, 'website': source,
                'domain': urllib.parse.urlparse(source).hostname,
                'logo': f'{ORIGIN}/{slug}{logo}' if str(logo).startswith('/') else '',
                'configurator_url': f'{ORIGIN}/{slug}/#order',
                'capabilities': {'customer_research': config.get('checkout', {}).get('customerResearch', True) is not False,
                                 'agent_editing': config.get('checkout', {}).get('agentEditing', True) is not False},
                'warehouses': config.get('checkout', {}).get('warehouses', [])}

    def document(self):
        document = self._read('document')['document']
        if document.get('configuration', {}).get('slug') != self.binding()['company_slug']:
            raise SourceUnavailable('Connect this workspace’s company order source.')
        return document

    def orders(self, limit=100, offset=0):
        if type(limit) is not int or not 1 <= limit <= 200 or type(offset) is not int or not 0 <= offset <= 1000000:
            raise Invalid('Choose a bounded order page.')
        return self._read('orders', limit=limit, offset=offset)['orders']

    def order(self, order_id):
        if not isinstance(order_id, str) or not order_id or len(order_id) > 200:
            raise Missing('Choose a company order.')
        return self._read('order', id=order_id)['order']


    def order_files(self, order_id):
        self.order(order_id)
        return self._read('order_files', id=order_id)['files']

    def order_file(self, order_id, file_id):
        from manufacturer_order_files import MAX_FILE, validate_metadata
        files = [validate_metadata(item) for item in self.order_files(order_id)]
        selected = next((item for item in files if item['id'] == file_id), None)
        if selected is None:
            raise Missing('Choose a file attached to this order.')
        binding = self.binding()
        query = urllib.parse.urlencode({'resource': 'file', 'id': order_id, 'file_id': file_id})
        request = urllib.request.Request(f"{ORIGIN}/{binding['company_slug']}/rocoto/api/platform-state?{query}",
            headers={'Authorization': 'Bearer ' + os.environ.get(TOKEN_ENV, ''),
                     'X-Rocoto-Company': self.company_id, 'Accept': 'application/octet-stream'})
        try:
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=15) as response:
                body = response.read(MAX_FILE + 1)
            if len(body) != selected['size'] or hashlib.sha256(body).hexdigest() != selected['sha256']:
                raise ValueError()
            return selected, body
        except urllib.error.HTTPError as error:
            if error.code == 404:
                raise Missing('Choose a file attached to this order.') from None
            raise SourceUnavailable('The original file is temporarily unavailable.') from None
        except (OSError, ValueError):
            raise SourceUnavailable('The original file is temporarily unavailable.') from None


def source_for(state, company_id):
    path = Path(state) / 'manufacturer-source.json'
    try:
        if path.is_file() and not path.is_symlink() and path.stat().st_size <= 8192:
            value = json.loads(path.read_text())
            if value.get('transport') == 'orders-api':
                source = RemoteCompanySource(state, company_id)
                source.binding()
                return source
    except (OSError, ValueError, AttributeError):
        raise SourceUnavailable('Connect this workspace’s company order source.') from None
    return CompanySource(state, company_id)
