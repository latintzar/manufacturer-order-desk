"""Manufacturer vertical installation, native admission and company-scoped HTTP routes."""
from __future__ import annotations

import copy
import re
from decimal import Decimal, ROUND_HALF_UP
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from host import BareWorkspace
from manufacturer_publish import Publisher
from manufacturer_source_http import source_for
from manufacturer_store import (
    Conflict,
    Invalid,
    ManufacturerStore,
    ORIGIN,
    Missing,
    SourceUnavailable,
)
from starlette.concurrency import run_in_threadpool



class ManufacturerPageImages:
    """Allow the company's fixed Orders image origin on the workspace page only."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get('type') != 'http' or scope.get('path') != '/' or scope.get('method') not in {'GET', 'HEAD'}:
            return await self.app(scope, receive, send)
        from starlette.datastructures import MutableHeaders

        async def page_send(message):
            if message.get('type') == 'http.response.start' and message.get('status') == 200:
                headers = MutableHeaders(scope=message)
                policy = headers.get('content-security-policy', '')
                if headers.get('content-type', '').split(';', 1)[0] == 'text/html':
                    directives = policy.split(';')
                    for index, directive in enumerate(directives):
                        tokens = directive.split()
                        if tokens and tokens[0] == 'img-src' and ORIGIN not in tokens:
                            directives[index] = directive + ' ' + ORIGIN
                    headers['content-security-policy'] = ';'.join(directives)
            await send(message)
        await self.app(scope, receive, page_send)


def preview_url(version_id):
    return '/api/manufacturer/preview/' + version_id


class ManufacturerWorkspace(BareWorkspace):
    def __init__(self, selected):
        super().__init__(selected)
        self.company_id = selected['business_scope'].company_id
        self.source = source_for(selected['state'], self.company_id)
        # A bound source must initialize its original snapshot successfully.
        # Existing snapshots remain usable during a later source outage.
        if (Path(selected['state']) / 'manufacturer-platform.sqlite').is_file():
            original = None
        else:
            original = self.source.document()
        self.platform = ManufacturerStore(selected['state'], self.company_id, original)
        self.publisher = Publisher(self.platform, self.source)
        self.research = None
        from manufacturer_conversations import ManufacturerConversations
        self.conversations = ManufacturerConversations(selected["state"], self.company_id)
        from manufacturer_fulfillment import ManufacturerFulfillment
        self.fulfillment = ManufacturerFulfillment(self.conversations)
        self._customers_lock = threading.Lock()
        self._customers_cache = None

    def member(self, actor, *, write=False, owner=False):
        member = self.selected['business_scope'].member(actor)
        roles = {'owner'} if owner else {'owner', 'operator'} if write else {'owner', 'operator', 'browse'}
        if not member or member.get('role') not in roles:
            raise ValueError('Continue with current company access.')
        return member

    def actor(self, actor):
        member = self.member(actor)
        return {'id': actor, 'role': member['role'], 'name': member.get('display_name') or actor,
                'can_create_orders': member['role'] in {'owner', 'operator'},
                'can_edit_settings': member['role'] == 'owner', 'can_manage_team': member['role'] == 'owner'}

    def authorized(self, actor, *, owner=False):
        try:
            return bool(self.member(actor, write=True, owner=owner))
        except ValueError:
            return False

    def agent_editing_enabled(self):
        checkout = self.platform.configurator()['document']['configuration'].get('checkout', {})
        return checkout.get('agentEditing', True) is not False

    def capabilities(self):
        return {'customer_research': self.research_enabled(), 'agent_editing': self.agent_editing_enabled()}

    def research_enabled(self):
        cached = getattr(self, '_research_capability', None)
        if cached and cached[2] is self.source and time.monotonic() - cached[0] < 5:
            return cached[1]
        checkout = self.platform.configurator()['document']['configuration'].get('checkout', {})
        enabled = checkout.get('customerResearch', True) is not False
        self._research_capability = (time.monotonic(), enabled, self.source)
        return enabled

    def _enrichment(self, order_id, *, is_demo=False):
        if not self.research_enabled():
            return {'status': 'disabled', 'summary': '', 'facts': [], 'sources': [], 'has_findings': False, 'complete': False}
        value = self.platform.demo_research(order_id) if is_demo else None
        if value is None:
            value = self.research.get(self.company_id, order_id) if self.research else None
        if value is None:
            return {'status': 'queued', 'summary': '', 'email_snippet': '', 'facts': [], 'sources': [], 'coverage': {}, 'updated_at': None, 'has_findings': False, 'complete': False}
        value = copy.deepcopy(value)
        for fact in value.get('facts', []):
            fact.setdefault('value', fact.get('text', ''))
            fact.setdefault('source_url', (fact.get('source_urls') or [''])[0])
        value.setdefault('coverage', {})
        value['has_findings'] = bool(value.get('facts') and value.get('sources'))
        value['complete'] = value.get('status') == 'enriched' and value['has_findings']
        return value

    def _order_context(self, order):
        from manufacturer_source import catalogue_labels, customer_id, localize_catalogue_lines, localize_demo, present_order
        index = catalogue_labels(self.platform)
        localize_catalogue_lines(order, index)
        order.update(present_order(order, locale=index["locale"]))
        order['customer_id'] = customer_id(order, self.company_id)
        order['capabilities'] = self.capabilities()
        enrichment = order['enrichment'] = self._enrichment(order['id'], is_demo=order['is_demo'])
        if index['locale'] == 'bg' and order['is_demo'] and order.get('customer', {}).get('company') == 'BLD':
            enrichment = order['enrichment'] = localize_demo(enrichment)
        customer = order.setdefault('customer', {})
        customer['display_company'] = customer.get('company') or ''
        customer['company_display_source'] = 'submitted' if customer['display_company'] else ''
        if enrichment['complete']:
            sources = {source.get('url') for source in enrichment.get('sources', [])}
            for fact in enrichment.get('facts', []):
                label = str(fact.get('label', '')).lower().replace('_', ' ').replace('-', ' ').strip()
                value = fact.get('value', fact.get('text'))
                supported = sources.intersection(fact.get('source_urls', []) or [fact.get('source_url')])
                if label in {'company name', 'business name', 'legal name', 'organization name', 'фирма', 'име на фирмата'} and isinstance(value, str) and 0 < len(value.strip()) <= 200 and supported:
                    customer['display_company'] = value.strip()
                    customer['company_display_source'] = 'research'
                    customer['company_source_url'] = next(url for url in fact.get('source_urls', []) or [fact.get('source_url')] if url in supported)
                    break
        customer['company_details_needed'] = not bool(customer['display_company'])
        customer['display_name'] = customer['display_company'] or customer.get('name') or customer.get('email') or 'Customer'
        return order

    def present_request(self, original):
        """Read-only CRM list projection; never used as the upstream source snapshot."""
        order = copy.deepcopy(original)
        try:
            review = self.conversations.order_review(order['customer_id'], order['id'])
            progress = self.fulfillment.read(order['customer_id'], order['id'])
        except Missing:
            return order
        order['source_status'] = original['status']
        order['status'] = 'cancelled' if original['status'] == 'cancelled' else review['review_status'] if review['review_status'] in {'review_pending','changes_requested'} else progress['status'] if progress['status'] != 'requested' else review['review_status']
        if review.get('current_version_id'):
            proposal = self.conversations.proposal(order['customer_id'], order['id'], review['current_version_id'])
            lines = proposal['document']['lines']
            priced = [line for line in lines if line.get('unit_price') is not None]
            total = round(sum(line.get('line_total', line.get('total', 0)) or 0 for line in priced), 2)
            order.update(proposal_version_id=proposal['id'], priced_total=total,
                pricing_state='priced' if len(priced)==len(lines) else 'partially_priced' if priced else 'to_quote',
                total=total if len(priced)==len(lines) else None)
        return order

    def present_customer(self, original):
        """Project current commercial metrics without changing submitted quantities or cached source."""
        from manufacturer_source import number
        profile = copy.deepcopy(original)
        profile['orders'] = [self.present_request(order) for order in original['orders']]
        totals = {}
        for order in profile['orders']:
            currency, amount = order.get('currency', 'EUR'), number(order.get('total'))
            if order.get('pricing_state') == 'priced' and amount is not None and isinstance(currency, str) and re.fullmatch(r'[A-Z]{3}', currency):
                totals[currency] = totals.get(currency, Decimal('0')) + Decimal(str(amount))
        profile['metrics']['quote_requests'] = sum(order.get('pricing_state') != 'priced' for order in profile['orders'])
        profile['metrics']['priced_totals'] = [
            {'currency': currency, 'total': float(total.quantize(Decimal('.01'), rounding=ROUND_HALF_UP))}
            for currency, total in sorted(totals.items())]
        return profile

    def overview(self, actor, *, limit=100, offset=0):
        self.member(actor)
        source_status = self.source.status()
        try:
            orders = self.source.orders(limit=limit, offset=offset)
        except SourceUnavailable:
            orders = []
            source_status = self.source.status()
        orders = [self.present_request(self._order_context(order)) for order in orders]
        for order in orders:
            order.pop('lines', None)
            order.pop('quote', None)
        result = {'company': self.source.company(), 'orders': orders, 'revision': self.platform.configurator()['revision'],
                  'source': source_status, 'actor': self.actor(actor), 'offset': offset, 'limit': limit}
        result['company']['capabilities'] = self.capabilities()
        self.member(actor)
        return result

    def order(self, actor, order_id):
        self.member(actor)
        order = self.source.order(order_id)
        self._order_context(order)
        result = {'order': order, 'actor': self.actor(actor)}
        self.member(actor)
        return result

    def _customer_snapshot(self, actor):
        from manufacturer_source import customer_profiles
        self.member(actor)
        with self._customers_lock:
            cached = self._customers_cache
            if cached and cached['source'] is self.source and time.monotonic() - cached['at'] < 5:
                self.member(actor)
                return copy.deepcopy(cached['value'])
            orders, maximum = [], 2000
            for offset in range(0, maximum, 200):
                page = self.source.orders(limit=200, offset=offset)
                orders.extend(self._order_context(order) for order in page)
                if len(page) < 200:
                    break
            truncated = len(orders) == maximum and bool(self.source.orders(limit=1, offset=maximum))
            source_status = self.source.status()
            if source_status.get('status') == 'unavailable':
                raise SourceUnavailable('The company order source is temporarily unavailable.')
            value = (customer_profiles(orders, self.company_id),
                {'scanned_orders': len(orders), 'limit': maximum, 'complete': not truncated, 'truncated': truncated}, source_status)
            self.member(actor)
            self._customers_cache = {'source': self.source, 'at': time.monotonic(), 'value': value}
            return copy.deepcopy(value)

    def customers(self, actor, *, limit=50, offset=0, q=''):
        if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or not 0 <= offset <= 1000000 or not isinstance(q, str) or len(q) > 150:
            raise Invalid('Choose a bounded customer page and search.')
        profiles, coverage, source_status = self._customer_snapshot(actor)
        query = q.strip().casefold()
        if query:
            profiles = [profile for profile in profiles if query in ' '.join(str(profile.get(key) or '') for key in ('display_name', 'company', 'website', 'trade')).casefold()
                        or any(query in ' '.join(contact.values()).casefold() for contact in profile['contacts'])]
        result = {'customers': [{key: value for key, value in self.present_customer(profile).items() if key != 'orders'} for profile in profiles[offset:offset + limit]],
                  'total': len(profiles), 'has_more': offset + limit < len(profiles), 'offset': offset, 'limit': limit,
                  'coverage': coverage, 'source': source_status, 'actor': self.actor(actor)}
        self.member(actor)
        return result

    def customer(self, actor, customer_id, *, limit=50, offset=0):
        if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or not 0 <= offset <= 1000000:
            raise Invalid('Choose a bounded customer timeline page.')
        profiles, coverage, source_status = self._customer_snapshot(actor)
        profile = next((value for value in profiles if value['id'] == customer_id), None)
        if profile is None:
            raise Missing('Choose a customer in this company.')
        profile = self.present_customer(profile)
        timeline = profile['orders']
        result = {'customer': {key: value for key, value in profile.items() if key != 'orders'},
                  'orders': [{key: value for key, value in order.items() if key not in {'lines', 'quote'}} for order in timeline[offset:offset + limit]],
                  'total_orders': len(timeline), 'has_more': offset + limit < len(timeline), 'offset': offset, 'limit': limit,
                  'coverage': coverage, 'source': source_status, 'actor': self.actor(actor)}
        self.member(actor)
        return result

    def import_demo_research(self, actor, order_id, findings, *, as_of, evidence):
        self.member(actor, owner=True)
        order = self.source.order(order_id)
        result = self.platform.import_demo_research(self.company_id, order, findings, actor=actor, as_of=as_of,
            evidence=evidence, current=lambda: self.authorized(actor, owner=True))
        with self._customers_lock:
            self._customers_cache = None
        return result

    def configurator(self, actor, *, retry_publication=True):
        self.member(actor)
        value = self.platform.configurator()
        publication = self.publisher.status(value['version_id'])
        if retry_publication and publication['state'] == 'pending' and self.authorized(actor):
            self.publisher.publish(lambda: self.authorized(actor))
            value = self.platform.configurator()
            publication = self.publisher.status(value['version_id'])
        value.update(state=publication['state'], published=publication['published'], publication=publication)
        value['settings']['preview_url'] = preview_url(value['version_id'])
        value['actor'] = self.actor(actor)
        value['company_id'] = self.company_id
        value['capabilities'] = self.capabilities()
        return value

    def versions(self, actor):
        self.member(actor)
        result = self.platform.versions()
        self.member(actor)
        return result

    def version(self, actor, version_id):
        self.member(actor)
        result = self.platform.version(version_id)
        result['version']['preview_url'] = preview_url(version_id)
        result['version']['settings']['preview_url'] = preview_url(version_id)
        self.member(actor)
        return result

    def _attachments(self, actor, document):
        previous = self.platform.configurator()['document']
        retained = {item['file_id'] for item in previous.get('attachments', [])}
        from manufacturer_source_files import read_record
        for attachment in document.get('attachments', []):
            if not isinstance(attachment, dict):
                raise Invalid('Reference a native saved file by its identifier.')
            if attachment.get('file_id') in retained:
                original = next(item for item in previous['attachments'] if item['file_id'] == attachment['file_id'])
                for field in ('name', 'content_type', 'sha256'):
                    if field in original:
                        attachment[field] = original[field]
                continue
            record = read_record(self, actor, attachment.get('file_id', ''))
            attachment.update(name=record['name'], content_type=record['media_type'], sha256=record['sha256'])

    def save_configurator(self, actor, arguments, evidence, *, actor_type='user'):
        if actor_type == 'agent' and not self.agent_editing_enabled():
            raise ValueError('Use the manual configurator editor for this workspace.')
        member = self.member(actor, owner=True)
        if not isinstance(arguments, dict) or set(arguments) - {'document', 'settings', 'expected_revision', 'label', 'summary'}:
            raise Invalid('Save the configurator document and the revision being edited.')
        if 'document' not in arguments and 'settings' not in arguments:
            raise Invalid('Supply configurator changes.')
        document = copy.deepcopy(arguments.get('document', self.platform.configurator()['document']))
        if not isinstance(document, dict) or not isinstance(document.get('configuration'), dict):
            raise Invalid('Supply the complete configurator document.')
        if 'settings' in arguments:
            settings = arguments['settings']
            if not isinstance(settings, dict) or not settings or set(settings) - {'accent', 'headline', 'description', 'button_label'}:
                raise Invalid('Use the editable appearance fields.')
            document['configuration'].update(settings)
        self._attachments(actor, document)
        self.platform.save_document(document, arguments.get('expected_revision'), actor, evidence,
                                    lambda: self.authorized(actor, owner=True), actor_name=member.get('display_name') or actor,
                                    actor_type=actor_type, label=arguments.get('label', ''), summary=arguments.get('summary', ''))
        self.publisher.publish(lambda: self.authorized(actor, owner=True))
        return self.configurator(actor, retry_publication=False)

    def restore(self, actor, version_id, expected_revision, evidence, *, actor_type='user'):
        if actor_type == 'agent' and not self.agent_editing_enabled():
            raise ValueError('Use the manual configurator editor for this workspace.')
        member = self.member(actor, owner=True)
        self.platform.restore(version_id, expected_revision, actor, evidence, lambda: self.authorized(actor, owner=True),
                              actor_name=member.get('display_name') or actor, actor_type=actor_type)
        self.publisher.publish(lambda: self.authorized(actor, owner=True))
        return self.configurator(actor, retry_publication=False)

    def team(self, actor):
        self.member(actor)
        company = self.source.company()
        value = self.platform.team(company['domain'])
        rows = self.selected['business_scope'].members()
        value.update(company=company, members=[{'id': row['id'], 'name': row.get('display_name') or row['id'],
                                              'role': row['role'], 'state': 'active'} for row in rows], actor=self.actor(actor))
        self.member(actor)
        return value

    def update_team(self, actor, arguments, evidence):
        self.member(actor, owner=True)
        self.platform.update_team(arguments, actor, evidence, lambda: self.authorized(actor, owner=True), self.source.company()['domain'])
        return self.team(actor)

    def available_credit(self):
        from company_usage import CompanyUsage
        return CompanyUsage.agent_pool(self.selected['state']).summary()['available_usd']

    def catalogue(self):
        from agent_catalogue import catalogue
        return catalogue()

    def draft_agent(self, template_id, collection, principal):
        if not self.agent_editing_enabled():
            raise ValueError('Use the service conversation for this workspace.')
        self.member(principal, write=True)
        if collection != 'company':
            raise ValueError('Create the research agent in the company collection.')
        from agent_catalogue import draft
        values = draft(template_id, collection)
        fields = self.selected['agents'].definition_model.model_fields
        return {key: value for key, value in values.items() if key in fields}

    def status_fields(self):
        return {'manufacturer_source': self.source.status()}


def install_workspace(host, selected):
    extension = ManufacturerWorkspace(selected)
    from research_queue import install_research
    install_research(host, selected, extension)
    return extension


def read_workspace(host, selected):
    return install_workspace(host, selected)


def register_routes(app, host, http):
    from manufacturer_source_files import UploadRequestLimit
    app.add_middleware(UploadRequestLimit)
    app.add_middleware(ManufacturerPageImages)
    assets = {
        '/static/manufacturer/manufacturer-new-order.js': ('manufacturer-new-order.js', 'application/javascript'),
        '/static/manufacturer/manufacturer-new-order.css': ('manufacturer-new-order.css', 'text/css'),
        '/static/manufacturer/manufacturer-order-files.js': ('manufacturer-order-files.js', 'application/javascript'),
        '/static/manufacturer/manufacturer-order-files.css': ('manufacturer-order-files.css', 'text/css'),
        '/static/manufacturer/manufacturer-products.js': ('manufacturer-products.js', 'application/javascript'),
        '/static/manufacturer/manufacturer-products.css': ('manufacturer-products.css', 'text/css'),
        '/static/manufacturer/manufacturer-customers.js': ('manufacturer-customers.js', 'application/javascript'),
        '/static/manufacturer/manufacturer-customers.css': ('manufacturer-customers.css', 'text/css'),
        '/static/manufacturer/manufacturer-files.js': ('manufacturer-files.js', 'application/javascript'),
        '/static/manufacturer/manufacturer-order-review.js': ('manufacturer-order-review.js', 'application/javascript'),
        '/static/manufacturer/manufacturer-order-review.css': ('manufacturer-order-review.css', 'text/css'),
        '/static/manufacturer/manufacturer-conversations.js': ('manufacturer-conversations.js', 'application/javascript'),
        '/static/manufacturer/manufacturer-conversations.css': ('manufacturer-conversations.css', 'text/css'),
        '/static/manufacturer/manufacturer-shell.js': ('manufacturer-shell.js', 'application/javascript'),
        '/static/manufacturer/manufacturer-tabs.js': ('manufacturer-tabs.js', 'application/javascript'),
        '/static/manufacturer/manufacturer.css': ('manufacturer.css', 'text/css'),
        '/static/manufacturer/manufacturer-chrome.css': ('manufacturer-chrome.css', 'text/css'),
    }
    host.options['page_assets'] = {'scripts': [path for path, (_, mime) in assets.items() if mime == 'application/javascript'], 'styles': [path for path, (_, mime) in assets.items() if mime == 'text/css']}
    host.options['public_request'] = lambda request: request.method in {'GET', 'HEAD'} and request.url.path in assets
    def admit_member_request(request):
        if request.state.session.get('role') == 'owner' and request.state.workspace['vertical'].agent_editing_enabled():
            return True
        path = request.url.path
        internal = path in {'/api/chat','/api/search','/api/attachments'} or path.startswith(
            ('/api/chats','/api/agents','/api/organization/chats','/api/usage/settings','/api/connections','/api/hooks','/api/mcp','/api/files','/api/inspection-previews','/api/manufacturer/files'))
        return not internal
    host.options['admit_member_request'] = admit_member_request
    host.options['member_status'] = lambda request: None if request.state.session.get('role') == 'owner' else {
        'connection': {}, 'operator': {'name':'Питър','mode':'service'},
        'agent': {'authenticated':False,'active_chats':{}}, 'mode':'human_service'}

    def asset_handler(filename, media_type):
        async def serve():
            return FileResponse(Path(__file__).parent / 'web' / filename, media_type=media_type)
        return serve
    for path, (filename, media_type) in assets.items():
        app.add_api_route(path, asset_handler(filename, media_type), methods=['GET', 'HEAD'])

    def context(request, writable=False):
        actor, _ = http.connection_identity(request, writable=writable)
        selected = request.state.workspace
        extension = selected['vertical']
        try:
            extension.member(actor, write=writable)
        except ValueError as error:
            raise HTTPException(403, str(error)) from None
        return actor, extension

    def invoke(function, *args, **kwargs):
        try:
            return function(*args, **kwargs)
        except Conflict as error:
            raise HTTPException(409, str(error)) from None
        except Missing as error:
            raise HTTPException(404, str(error)) from None
        except Invalid as error:
            raise HTTPException(400, str(error)) from None
        except SourceUnavailable as error:
            raise HTTPException(503, str(error)) from None
        except ValueError as error:
            raise HTTPException(403, str(error)) from None

    async def body(request):
        try:
            size = int(request.headers.get('content-length', 0) or 0)
        except ValueError:
            raise HTTPException(400, 'Supply a valid request length.') from None
        if size > 8_100_000:
            raise HTTPException(413, 'Keep the configurator within 8 MB.')
        raw = await request.body()
        if len(raw) > 8_100_000:
            raise HTTPException(413, 'Keep the configurator within 8 MB.')
        try:
            value = await request.json()
        except ValueError:
            raise HTTPException(400, 'Supply a JSON object.') from None
        if not isinstance(value, dict):
            raise HTTPException(400, 'Supply a JSON object.')
        return value

    @app.post('/api/manufacturer/files')
    async def upload_source(file: UploadFile, request: Request):
        from manufacturer_source_files import MAX_UPLOAD, upload
        actor, extension = context(request, writable=True)
        try:
            raw = await file.read(MAX_UPLOAD + 1)
            if len(raw) > MAX_UPLOAD:
                raise HTTPException(413, 'Upload a source file up to 16 MiB.')
            return await run_in_threadpool(invoke, upload, extension, actor, raw, file.filename or '')
        finally:
            await file.close()

    @app.get('/api/manufacturer/overview')
    @app.get('/api/manufacturer/orders')
    async def overview(request: Request, limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0, le=1_000_000)):
        actor, extension = context(request)
        return await run_in_threadpool(invoke, extension.overview, actor, limit=limit, offset=offset)

    @app.post('/api/manufacturer/orders')
    async def create_order(request: Request):
        from manufacturer_manual_orders import create
        actor, extension = context(request, writable=True)
        value = await body(request)
        result = await run_in_threadpool(invoke, create, extension, actor, value)
        return JSONResponse(result, headers={'Cache-Control': 'private, no-store'})

    @app.get('/api/manufacturer/orders/{order_id}')
    async def order(request: Request, order_id: str):
        actor, extension = context(request)
        return await run_in_threadpool(invoke, extension.order, actor, order_id)

    @app.get('/api/manufacturer/orders/{order_id}/files')
    async def order_files(request: Request, order_id: str):
        from manufacturer_order_files import files
        actor, extension = context(request)
        result = await run_in_threadpool(invoke, files, extension, actor, order_id)
        return JSONResponse(result, headers={'Cache-Control': 'private, no-store'})

    @app.get('/api/manufacturer/orders/{order_id}/files/{file_id}')
    async def order_file(request: Request, order_id: str, file_id: str, download: bool = False):
        from manufacturer_order_files import original
        actor, extension = context(request)
        raw, mime, headers = await run_in_threadpool(invoke, original, extension, actor, order_id, file_id, download)
        return Response(raw, media_type=mime, headers=headers)

    @app.get('/api/manufacturer/orders/{order_id}/files/{file_id}/page/{page}')
    async def order_file_page(request: Request, order_id: str, file_id: str, page: int):
        from manufacturer_order_files import pdf_page
        actor, extension = context(request)
        raw, headers = await run_in_threadpool(invoke, pdf_page, extension, actor, order_id, file_id, page)
        return Response(raw, media_type='image/png', headers=headers)

    from manufacturer_conversation_routes import register_conversations
    register_conversations(app, context=context, body=body, invoke=invoke, host=host)
    from manufacturer_fulfillment import register_fulfillment
    register_fulfillment(app, context=context, body=body, invoke=invoke)
    from manufacturer_customer_portal import register_customer_portal
    register_customer_portal(app, host, context=context, invoke=invoke)

    @app.get('/api/manufacturer/customers')
    async def customers(request: Request, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0, le=1000000), q: str = Query('', max_length=150)):
        actor, extension = context(request)
        return await run_in_threadpool(invoke, extension.customers, actor, limit=limit, offset=offset, q=q)

    @app.get('/api/manufacturer/customers/{customer_id}')
    async def customer(request: Request, customer_id: str, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0, le=1000000)):
        actor, extension = context(request)
        return await run_in_threadpool(invoke, extension.customer, actor, customer_id, limit=limit, offset=offset)

    @app.get('/api/manufacturer/configurator')
    async def configurator(request: Request):
        actor, extension = context(request)
        return await run_in_threadpool(invoke, extension.configurator, actor)

    @app.post('/api/manufacturer/configurator')
    async def save_configurator(request: Request):
        actor, extension = context(request, True)
        value = await body(request)
        return await run_in_threadpool(invoke, extension.save_configurator, actor, value, 'Saved through the company configurator editor.')

    @app.get('/api/manufacturer/configurator/versions')
    async def versions(request: Request):
        actor, extension = context(request)
        return await run_in_threadpool(invoke, extension.versions, actor)

    @app.get('/api/manufacturer/configurator/versions/{version_id}')
    async def version(request: Request, version_id: str):
        actor, extension = context(request)
        return await run_in_threadpool(invoke, extension.version, actor, version_id)

    @app.post('/api/manufacturer/configurator/versions/{version_id}/restore')
    async def restore_version(request: Request, version_id: str):
        actor, extension = context(request, True)
        value = await body(request)
        if set(value) != {'expected_revision'}:
            raise HTTPException(400, 'Supply the current revision.')
        return await run_in_threadpool(invoke, extension.restore, actor, version_id, value['expected_revision'], 'Restored through version history.')

    @app.post('/api/manufacturer/configurator/restore')
    async def restore(request: Request):
        actor, extension = context(request, True)
        value = await body(request)
        if set(value) != {'version_id', 'expected_revision'}:
            raise HTTPException(400, 'Supply the version and current revision.')
        return await run_in_threadpool(invoke, extension.restore, actor, value['version_id'], value['expected_revision'], 'Restored through version history.')

    @app.get('/api/manufacturer/preview/{version_id}')
    async def preview(request: Request, version_id: str):
        actor, extension = context(request)
        saved = invoke(extension.version, actor, version_id)['version']
        from manufacturer_preview import html
        try:
            content, headers = await run_in_threadpool(html, extension.selected['state'], saved['document']['configuration']['slug'], saved['document'], saved['settings'])
        except (OSError, ValueError):
            raise HTTPException(503, 'The saved configurator preview is being prepared. Try again shortly.') from None
        invoke(extension.member, actor)
        return HTMLResponse(content, headers=headers)

    @app.get('/api/manufacturer/team')
    async def team(request: Request):
        actor, extension = context(request)
        return await run_in_threadpool(invoke, extension.team, actor)

    @app.post('/api/manufacturer/team')
    async def update_team(request: Request):
        actor, extension = context(request, True)
        value = await body(request)
        return await run_in_threadpool(invoke, extension.update_team, actor, value, 'Saved through company membership settings.')


@asynccontextmanager
async def lifespan(app, host):
    yield
