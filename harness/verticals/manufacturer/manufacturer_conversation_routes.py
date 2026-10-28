"""Authenticated human service/customer conversations for a manufacturer workspace."""
import copy
import math
from datetime import datetime
import hashlib
from decimal import Decimal, ROUND_HALF_UP
from fastapi import HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool


def register_conversations(app, *, context, body, invoke, host=None):
    from manufacturer_chatwoot_routes import install_chatwoot, register_chatwoot

    def communication(extension):
        return install_chatwoot(host, extension.selected, extension)

    if host is not None:
        register_chatwoot(app, host, context=context, invoke=invoke)

    def demo_origin(extension, customer_id):
        with extension.conversations._transaction() as db:
            conversation = extension.conversations._conversation(db, customer_id)
            return db.execute(
                "SELECT 1 FROM messages WHERE conversation_id=? AND kind='order_submitted' "
                "AND (json_type(data,'$.order.is_demo')='true' "
                "OR json_type(data,'$.order.customer.is_demo')='true') LIMIT 1",
                (conversation['id'],),
            ).fetchone() is not None

    def timeline(messages):
        for message in messages:
            created = message.get('created_at')
            try:
                seconds = datetime.fromisoformat(created.replace('Z', '+00:00')).timestamp() if isinstance(created, str) else float(created)
            except (ValueError, TypeError):
                seconds = 0
            # A UI sort key only; the provider's message ID remains the page cursor.
            tie = int(hashlib.sha256(message['id'].encode()).hexdigest()[:6], 16) % 1000
            message['sequence'] = int(seconds * 1000) * 1000 + tie
        return sorted(messages, key=lambda message: (message['sequence'], message['id']))

    def actor_context(extension, actor, *, writable=True):
        def current():
            try:
                return extension.authorized(actor) if writable else bool(extension.member(actor))
            except ValueError:
                return False
        return {'actor':actor, 'current':current}

    def authors(extension, result, actor, profile=None):
        result['can_send'] = extension.authorized(actor)
        members = {p['id']: p.get('display_name') or 'Team' for p in extension.selected['business_scope'].members()}
        contacts = {p.get('email', '').casefold(): p.get('name') or p.get('email') for p in (profile or {}).get('contacts', []) if p.get('email')}
        for message in result['messages']:
            author = message['author_id']
            if message['author_type'] == 'system':
                name = 'System'
            elif message['author_type'] == 'customer':
                contact = message.get('data', {}).get('evidence', {}).get('contact') or author
                name = contacts.get(str(contact).casefold()) or ((profile or {}).get('display_name') or 'Customer')
            else:
                name = members.get(author) or 'Team'
            message['author_name'] = name
            message['direction'] = ('inbound' if message['author_type'] == 'customer' else 'outbound') if profile else ('outbound' if author == actor else 'inbound')

    def service(extension, actor, before=None):
        extension.member(actor)
        extension.conversations.ensure_service(**actor_context(extension, actor, writable=False))
        adapter = communication(extension)
        status = adapter.status()
        if status['selected']:
            current = actor_context(extension, actor, writable=False)['current']
            adapter.ensure_thread('service', channel='service', name='Company service', current=current)
            result = adapter.history('service', channel='service', current=current, before=before)
            result['messages'] = timeline(result['messages'])
            result['archive'] = {'provider': 'native', 'url': '/api/manufacturer/service-conversation/archive'}
        else:
            result = extension.conversations.service_conversation(before=before)
        result['title'] = 'Team chat'
        result['delivery_ready'] = status['service_ready'] if status['selected'] else True
        result['can_send'] = extension.authorized(actor)
        authors(extension, result, actor)
        extension.member(actor)
        return result

    def customer(extension, actor, customer_id, order_id=None, before=None, writable=False):
        profile = extension.customer(actor, customer_id)['customer']
        permission = actor_context(extension, actor, writable=writable)
        extension.conversations.ensure_customer(customer_id, contacts=profile.get('contacts', []), **permission)
        # The exact source binding owns both customer grouping and order membership.
        snapshot, _, _ = extension._customer_snapshot(actor)
        source_profile = next(p for p in snapshot if p['id'] == customer_id)
        if order_id and not any(order['id'] == order_id for order in source_profile['orders']):
            raise HTTPException(404, 'Choose an order belonging to this customer.')
        for order in reversed(source_profile['orders']):
            extension.conversations.record_source_order(customer_id, order, **permission)
        adapter = communication(extension)
        status = adapter.status()
        cutover = status['selected'] and 'email_inbox' not in status['missing']
        result = extension.conversations.conversation(customer_id, before=None if cutover else before)
        if cutover:
            addresses = [contact['email'] for contact in profile.get('contacts', []) if contact.get('email')]
            if addresses:
                adapter.ensure_thread(customer_id, channel='email', name=profile.get('display_name') or 'Customer',
                    recipient=addresses[0], current=permission['current'])
                history = adapter.history(customer_id, channel='email', current=permission['current'], before=before)
                business = [message for message in result['messages'] if message['kind'] in {
                    'order_submitted', 'order_updated', 'proposal', 'customer_confirmation', 'customer_change_requested'}]
                result.update(history)
                result['messages'] = timeline(business + history['messages'])
                result['archive'] = {'provider': 'native', 'url': '/api/manufacturer/conversations/' + customer_id + '/archive'}
        result['customer'] = profile
        result['delivery_ready'] = bool(cutover and status['email_ready'] and profile.get('is_demo') is not True
            and not demo_origin(extension, customer_id))
        orders = {order['id']: order for order in source_profile['orders']}
        versions = {}
        for message in result['messages']:
            data = message['data']
            if message['kind'] in {'order_submitted','order_updated'}:
                message['order'] = data.get('order', data)
            related_id = data.get('order_id') or message.get('order', {}).get('id')
            if related_id in orders:
                order = message.get('order') or orders[related_id]
                message['order_id'] = related_id
                message['order_number'] = order.get('display_number') or order.get('number') or 'Поръчка'
                if data.get('version_id'):
                    key = (related_id, data['version_id'])
                    if key not in versions:
                        versions[key] = extension.conversations.proposal(customer_id, *key)
                    message['version'] = versions[key]['version']
        authors(extension, result, actor, profile)
        extension.member(actor)
        return result

    def review_context(extension, actor, order_id, writable=False):
        order = extension.order(actor, order_id)['order']
        customer_id = order['customer_id']
        profile = extension.customer(actor, customer_id)['customer']
        permission = actor_context(extension, actor, writable=writable)
        extension.conversations.ensure_customer(customer_id, contacts=profile.get('contacts', []), **permission)
        extension.conversations.record_source_order(customer_id, order, **permission)
        review = extension.conversations.order_review(customer_id, order_id)
        proposal = extension.conversations.proposal(customer_id, order_id, review['current_version_id']) if review.get('current_version_id') else None
        return {'order':order,'review':review,'proposal':proposal,'customer':profile,'delivery_ready':False,'actor':extension.actor(actor)}

    @app.get('/api/manufacturer/orders/{order_id}/review')
    async def get_review(order_id: str, request: Request):
        actor, extension = context(request)
        return await run_in_threadpool(invoke, review_context, extension, actor, order_id)

    @app.post('/api/manufacturer/orders/{order_id}/review')
    async def prepare_review(order_id: str, request: Request):
        actor, extension = context(request, True)
        value = await body(request)
        if set(value) != {'lines','delivery','notes','expected_revision','idempotency_key'}:
            raise HTTPException(400, 'Provide the proposed request and its current revision.')
        current = await run_in_threadpool(invoke, review_context, extension, actor, order_id, True)
        original = current['order']
        if not isinstance(value['lines'], list) or len(value['lines']) != len(original.get('lines', [])):
            raise HTTPException(400, 'Review the existing requested articles.')
        lines = []
        total = Decimal('0')
        priced = True
        for source, change in zip(original['lines'], value['lines']):
            if not isinstance(change, dict) or set(change) != {'quantity','unit_price'}:
                raise HTTPException(400, 'Provide the requested quantity and unit price.')
            quantity, price = change['quantity'], change['unit_price']
            if type(quantity) not in {int, float} or not math.isfinite(quantity) or not 0 < quantity <= 1000000:
                raise HTTPException(400, 'Use a positive quantity.')
            if price is not None and (type(price) not in {int, float} or not math.isfinite(price) or not 0 <= price <= 10000000):
                raise HTTPException(400, 'Use a finite unit price.')
            line = {key:copy.deepcopy(source[key]) for key in ('code','name','unit','image_url','description') if key in source}
            line['quantity'] = quantity
            if price is not None:
                amount = (Decimal(str(quantity)) * Decimal(str(price))).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
                line['unit_price'], line['line_total'] = price, float(amount)
                total += amount
            else:
                priced = False
            lines.append(line)
        delivery = value['delivery']
        if not isinstance(delivery, dict) or set(delivery) - {'address','method','date','notes'} or any(
            not isinstance(item,str) or len(item)>1000 or any(ord(c)<32 and c not in '\n\r\t' for c in item) for item in delivery.values()):
            raise HTTPException(400, 'Provide the delivery details.')
        if not isinstance(value['notes'],str) or len(value['notes'])>4000:
            raise HTTPException(400, 'Use a short note for the customer.')
        recipients=[p['email'] for p in current['customer'].get('contacts',[]) if p.get('email')]
        if not recipients:
            raise HTTPException(400, 'Add the customer’s email before preparing a review.')
        proposal={'id':order_id,'customer_id':original['customer_id'],'number':original.get('display_number'),
            'currency':original.get('currency') or 'EUR','lines':lines,'delivery':delivery,'notes':value['notes']}
        if priced:
            proposal['subtotal']=float(total)
        result=await run_in_threadpool(invoke,extension.conversations.propose_request,
            original['customer_id'],order_id,proposal=proposal,recipient=recipients[0],
            expected_revision=value['expected_revision'],idempotency_key=value['idempotency_key'],
            **actor_context(extension,actor))
        result.update(customer_id=original['customer_id'],recipient=recipients[0],delivery_ready=False)
        return result

    @app.get('/api/manufacturer/service-conversation')
    async def get_service(request: Request, before: int | None = Query(None, ge=1, le=9223372036854775807)):
        actor, extension = context(request)
        return await run_in_threadpool(invoke, service, extension, actor, before)

    @app.post('/api/manufacturer/service-conversation/messages')
    async def send_service(request: Request):
        actor, extension = context(request, True)
        value = await body(request)
        if set(value) != {'text', 'idempotency_key'}:
            raise HTTPException(400, 'Provide a message.')
        extension.conversations.ensure_service(**actor_context(extension, actor))
        side = 'provider' if extension.member(actor)['role'] == 'owner' else 'client'
        adapter = communication(extension)
        if adapter.status()['selected']:
            permission = actor_context(extension, actor)
            await run_in_threadpool(invoke, adapter.ensure_thread, 'service', channel='service',
                name='Company service', current=permission['current'])
            result = await run_in_threadpool(invoke, adapter.send, 'service', channel='service',
                text=value['text'], idempotency_key=value['idempotency_key'],
                side='outgoing' if side == 'provider' else 'incoming', **permission)
            if result['status'] == 'uncertain':
                raise HTTPException(503, 'Проверяваме изпращането на съобщението.')
            return result
        return await run_in_threadpool(invoke, extension.conversations.send_service_message,
            text=value['text'], idempotency_key=value['idempotency_key'], side=side, **actor_context(extension, actor))

    @app.get('/api/manufacturer/conversations/{customer_id}')
    async def get_customer(customer_id: str, request: Request, order_id: str | None = Query(None, max_length=160),
                           before: int | None = Query(None, ge=1, le=9223372036854775807)):
        actor, extension = context(request)
        return await run_in_threadpool(invoke, customer, extension, actor, customer_id, order_id, before)

    @app.post('/api/manufacturer/conversations/{customer_id}/messages')
    async def send_customer(customer_id: str, request: Request):
        actor, extension = context(request, True)
        value = await body(request)
        if set(value) - {'text', 'idempotency_key', 'order_id'} or not {'text', 'idempotency_key'} <= set(value):
            raise HTTPException(400, 'Provide a message and its send identifier.')
        current = await run_in_threadpool(invoke, customer, extension, actor, customer_id,
            order_id=value.get('order_id'), writable=True)
        if not current['delivery_ready']:
            raise HTTPException(503, 'Company email setup is in progress.')
        adapter = communication(extension)
        def admission(message_context):
            if not extension.authorized(actor) or demo_origin(extension, customer_id):
                return False
            profile = extension.customer(actor, customer_id)['customer']
            return profile.get('is_demo') is not True and message_context['recipient'] in {
                person.get('email', '').lower() for person in profile.get('contacts', [])}
        result = await run_in_threadpool(invoke, adapter.send, customer_id, channel='email',
            text=value['text'], idempotency_key=value['idempotency_key'], send_admission=admission,
            **actor_context(extension, actor))
        if result['status'] == 'uncertain':
            raise HTTPException(503, 'Проверяваме изпращането на съобщението.')
        return result

    @app.get('/api/manufacturer/service-conversation/archive')
    async def service_archive(request: Request, before: int | None = Query(None, ge=1)):
        actor, extension = context(request)
        extension.member(actor)
        result = await run_in_threadpool(invoke, extension.conversations.service_conversation, before=before)
        result.update(provider='native', archive=True, delivery_ready=False)
        authors(extension, result, actor)
        return result

    @app.get('/api/manufacturer/conversations/{customer_id}/archive')
    async def customer_archive(customer_id: str, request: Request, before: int | None = Query(None, ge=1)):
        actor, extension = context(request)
        profile = extension.customer(actor, customer_id)['customer']
        result = await run_in_threadpool(invoke, extension.conversations.conversation, customer_id, before=before)
        result.update(provider='native', archive=True, delivery_ready=False, customer=profile)
        authors(extension, result, actor, profile)
        return result
