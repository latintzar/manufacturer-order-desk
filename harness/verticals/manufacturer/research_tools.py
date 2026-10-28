"""Admitted company research tools for the Organization and its saved agents."""
import hashlib
import json
from pathlib import Path
import sys

from managed_turn import current_managed_call

READ_NAMES = frozenset({'get_order_research', 'list_order_research'})
WRITE_NAMES = frozenset({'claim_order_research', 'record_order_research', 'fail_order_research'})
SURFACE_READS = {'public': frozenset(), 'local': READ_NAMES, 'native': READ_NAMES}


def _schema(properties, required=()):
    return {'type': 'object', 'properties': properties, 'required': list(required), 'additionalProperties': False}


def specs(write=True):
    identity = {'order_id': {'type': 'string', 'minLength': 1, 'maxLength': 160}}
    lease = {**identity, 'lease_token': {'type': 'string', 'minLength': 1, 'maxLength': 100}}
    rows = [
        {'name': 'get_order_research', 'description': 'Read this company’s submitted customer context and saved source-supported research for one order.',
         'inputSchema': _schema(identity, ['order_id'])},
        {'name': 'list_order_research', 'description': 'Read this company’s research backlog and progress. Queued orders wait for an active funded customer research agent.',
         'inputSchema': _schema({'limit': {'type': 'integer', 'minimum': 1, 'maximum': 100}})},
    ]
    if write:
        rows.extend([
            {'name': 'claim_order_research', 'description': 'Reserve one queued order for this admitted conversation. Scheduled customer research runs receive their order and lease in their input.',
             'inputSchema': _schema({})},
            {'name': 'record_order_research', 'description': 'Save this reserved order’s business research, linked facts and internal email snippet. Mark uncertain company matches needs_review.',
             'inputSchema': _schema({**lease,
                 'status': {'type': 'string', 'enum': ['enriched', 'needs_review']},
                 'summary': {'type': 'string', 'maxLength': 3000},
                 'email_snippet': {'type': 'string', 'maxLength': 1500},
                 'review_notes': {'type': 'string', 'maxLength': 2000},
                 'sources': {'type': 'array', 'maxItems': 30, 'items': _schema({
                     'url': {'type': 'string', 'minLength': 1, 'maxLength': 2048},
                     'title': {'type': 'string', 'minLength': 1, 'maxLength': 300}}, ['url', 'title'])},
                 'facts': {'type': 'array', 'maxItems': 30, 'items': _schema({
                     'label': {'type': 'string', 'minLength': 1, 'maxLength': 100},
                     'text': {'type': 'string', 'minLength': 1, 'maxLength': 1500},
                     'source_urls': {'type': 'array', 'minItems': 1, 'maxItems': 5,
                         'items': {'type': 'string', 'maxLength': 2048}}}, ['label', 'text', 'source_urls'])}},
                 [*lease, 'status', 'summary', 'email_snippet', 'review_notes', 'sources', 'facts'])},
            {'name': 'fail_order_research', 'description': 'Release a reserved order after a transient research failure. Durable bounded retry uses the same native agent schedule.',
             'inputSchema': _schema({**lease, 'reason': {'type': 'string', 'minLength': 1, 'maxLength': 500}},
                                    [*lease, 'reason'])},
        ])
    return rows


def _store(context):
    context.require_current()
    extension = context.extension
    selected = extension.selected
    store = extension.research
    if (context.company_id != store.company_id or context.collection != 'company'
            or Path(context.state) != Path(selected['state'])
            or selected['business_scope'].company_id != context.company_id):
        raise ValueError('Use the selected company’s research workspace.')
    return store


def read(context, name, arguments):
    store = _store(context)
    if name == 'list_order_research':
        return store.list(context.company_id, limit=arguments.get('limit', 25))
    if name == 'get_order_research':
        return {'research': store.get(context.company_id, arguments['order_id'])}
    raise ValueError('Choose a declared research tool.')


def call(context, name, arguments):
    context.require_parent()
    store = _store(context)
    context.extension.member(context.actor, write=True)
    if name == 'claim_order_research':
        managed = current_managed_call()
        if managed is None:
            raise ValueError('Claim customer research from the current managed agent call.')
        claim_key = hashlib.sha256(json.dumps({'chat': context.chat_id, 'call': managed}, sort_keys=True).encode()).hexdigest()
        result = store.claim_next(context.company_id, context.chat_id, claim_key)
    elif name == 'record_order_research':
        findings = {key: value for key, value in arguments.items() if key not in {'order_id', 'lease_token'}}
        result = store.complete(context.company_id, arguments['order_id'], context.chat_id,
                                arguments['lease_token'], findings)
    elif name == 'fail_order_research':
        result = store.fail(context.company_id, arguments['order_id'], context.chat_id,
                            arguments['lease_token'], arguments['reason'])
    else:
        raise ValueError('Choose a declared research tool.')
    context.require_current()
    return {'research': result}


FAMILY = sys.modules[__name__]
