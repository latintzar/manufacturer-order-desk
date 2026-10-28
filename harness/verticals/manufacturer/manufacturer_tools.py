"""Native manufacturer tools use the same admitted document store as manual editing."""
import sys
from pathlib import Path

READ_NAMES = frozenset({'manufacturer_overview', 'manufacturer_orders', 'manufacturer_order', 'manufacturer_configurator', 'manufacturer_configurator_summary', 'manufacturer_find_products', 'manufacturer_versions', 'manufacturer_version', 'manufacturer_team'})
WRITE_NAMES = frozenset({'manufacturer_save_configurator', 'manufacturer_edit_configurator', 'manufacturer_restore_configurator', 'manufacturer_draft_invitation', 'manufacturer_update_team_policy'})


def specs(write=True):
    def spec(name, description, properties=None, required=None):
        schema = {'type': 'object', 'properties': properties or {}, 'additionalProperties': False}
        if required:
            schema['required'] = required
        return {'name': name, 'description': description, 'inputSchema': schema}
    identifier = {'type': 'string', 'minLength': 1, 'maxLength': 160}
    revision = {'type': 'integer', 'minimum': 0}
    evidence = {'type': 'string', 'minLength': 1, 'maxLength': 2000}
    offset = {'type': 'integer', 'minimum': 0, 'maximum': 20000}
    localized = {'type': 'object', 'minProperties': 1, 'maxProperties': 8,
                 'patternProperties': {'^[a-z]{2}(?:-[A-Za-z]{2,4})?$': {'type': 'string', 'minLength': 1, 'maxLength': 1000}},
                 'additionalProperties': False}
    option = {'type': 'object', 'properties': {'id': identifier, 'label': localized, 'sub': localized},
              'required': ['id'], 'minProperties': 2, 'additionalProperties': False}
    question = {'type': 'object', 'properties': {'id': identifier, 'title': localized, 'help': localized, 'short': localized,
                'options': {'type': 'array', 'items': option, 'minItems': 1, 'maxItems': 100}},
                'required': ['id'], 'minProperties': 2, 'additionalProperties': False}
    changes = {'type': 'object', 'minProperties': 1, 'additionalProperties': False, 'properties': {
        'appearance': {'type': 'object', 'minProperties': 1, 'additionalProperties': False, 'properties': {
            'accent': {'type': 'string', 'pattern': '^#[0-9a-fA-F]{6}$'},
            'headline': {'type': 'string', 'minLength': 1, 'maxLength': 160},
            'description': {'type': 'string', 'maxLength': 1000},
            'button_label': {'type': 'string', 'minLength': 1, 'maxLength': 80}}},
        'prices': {'type': 'array', 'minItems': 1, 'maxItems': 200, 'items': {
            'type': 'object', 'additionalProperties': False, 'required': ['code', 'price'], 'properties': {
                'code': identifier, 'price': {'oneOf': [{'type': 'number', 'minimum': 0, 'maximum': 1e12},
                                                     {'type': 'null'}, {'const': ''}]}}}},
        'questions': {'type': 'array', 'minItems': 1, 'maxItems': 20, 'items': question},
        'attachments': {'type': 'array', 'minItems': 1, 'maxItems': 20, 'items': {
            'type': 'object', 'additionalProperties': False, 'required': ['file_id'], 'properties': {
                'file_id': identifier, 'purpose': {'type': 'string', 'minLength': 1, 'maxLength': 160}}}},
    }}
    result = [spec('manufacturer_overview', 'Read this company’s incoming orders and research coverage.'),
              spec('manufacturer_orders', 'Read a page of this company’s incoming orders.', {'limit': {'type': 'integer', 'minimum': 1, 'maximum': 200}, 'offset': {'type': 'integer', 'minimum': 0, 'maximum': 1000000}}),
              spec('manufacturer_order', 'Read one order with its lines, customer information and sourced research.', {'order_id': identifier}, ['order_id']),
              spec('manufacturer_configurator', 'Read the complete current configurator document and its revision. The same document powers manual edits and history.'),
              spec('manufacturer_configurator_summary', 'Read current revision, appearance, catalogue counts and question IDs in a compact view. Use question_id for a question and its first 20 answer labels; page with the offset fields. Prefer this before ordinary edits.',
                   {'question_id': identifier, 'language': {'type': 'string', 'pattern': '^[a-z]{2}(?:-[A-Za-z]{2,4})?$'},
                    'questions_offset': offset, 'options_offset': offset, 'categories_offset': offset}),
              spec('manufacturer_find_products', 'Find individual current catalogue articles by exact code, search text or category. Returns effective unit price and source attributes, at most 20 articles per page.',
                   {'query': {'type': 'string', 'maxLength': 150}, 'code': identifier, 'category': identifier,
                    'limit': {'type': 'integer', 'minimum': 1, 'maximum': 20}, 'offset': offset}),
              spec('manufacturer_versions', 'Read the shared configurator version history, with authors, timestamps and content hashes.'),
              spec('manufacturer_version', 'Read the exact complete document saved in a configurator version.', {'version_id': identifier}, ['version_id']),
              spec('manufacturer_team', 'Read current native members, invitation drafts and domain policy.')]
    if write:
        result += [spec('manufacturer_edit_configurator', 'Apply bounded changes to the current company document server-side. Appearance, existing article prices, existing question/answer text and native source attachments share the same immutable manual/agent history. Preserve other languages, article attributes and matching rules. A null or empty price sets on-request pricing; zero is a real price. Use source-backed prices in the existing currency and selling unit. Report the compact publication receipt and preview.',
                        {'changes': changes, 'expected_revision': revision, 'label': {'type': 'string', 'maxLength': 160}, 'summary': {'type': 'string', 'maxLength': 1000}, 'evidence': evidence}, ['changes', 'expected_revision', 'evidence']),
                   spec('manufacturer_save_configurator', 'Save a complete company configurator document as a new immutable version and apply it through the commissioned company connection. Report the returned publication receipt. Use a current revision, source-backed catalogue prices and native file references. This preserves the shared manual and agent history.',
                        {'document': {'type': 'object'}, 'expected_revision': revision, 'label': {'type': 'string', 'maxLength': 160}, 'summary': {'type': 'string', 'maxLength': 1000}, 'evidence': evidence}, ['document', 'expected_revision', 'evidence']),
                   spec('manufacturer_restore_configurator', 'Restore the exact content of a previous version into a new current revision, retaining all history.', {'version_id': identifier, 'expected_revision': revision, 'evidence': evidence}, ['version_id', 'expected_revision', 'evidence']),
                   spec('manufacturer_draft_invitation', 'Save an owner-reviewed invitation draft. Native verified identity grants access separately.', {'email': {'type': 'string', 'maxLength': 320}, 'role': {'enum': ['operator', 'browse']}, 'expected_revision': revision, 'evidence': evidence}, ['email', 'role', 'expected_revision', 'evidence']),
                   spec('manufacturer_update_team_policy', 'Save the owner’s company-domain access preference for the verified identity flow.', {'domain': {'type': 'string', 'maxLength': 253}, 'allow_domain_join': {'type': 'boolean'}, 'expected_revision': revision, 'evidence': evidence}, ['domain', 'allow_domain_join', 'expected_revision', 'evidence'])]
    return result


def extension(context):
    context.require_current()
    selected = context.extension.selected
    if (context.collection != 'company' or context.company_id != selected['business_scope'].company_id
            or Path(context.state).absolute() != Path(selected['state']).absolute()):
        raise ValueError('Use the current company workspace and collection.')
    context.extension.member(context.actor)
    return context.extension


def read(context, name, arguments):
    workspace = extension(context)
    actor = context.actor
    if name in {'manufacturer_overview', 'manufacturer_orders'}:
        result = workspace.overview(actor, **arguments)
    elif name == 'manufacturer_order':
        result = workspace.order(actor, arguments['order_id'])
    elif name == 'manufacturer_configurator':
        result = workspace.configurator(actor)
    elif name in {'manufacturer_configurator_summary', 'manufacturer_find_products'}:
        from manufacturer_agent_edits import find_products, summary
        value = workspace.configurator(actor)
        result = (summary if name == 'manufacturer_configurator_summary' else find_products)(value, **arguments)
    elif name == 'manufacturer_versions':
        result = workspace.versions(actor)
    elif name == 'manufacturer_version':
        result = workspace.version(actor, arguments['version_id'])
    elif name == 'manufacturer_team':
        result = workspace.team(actor)
    else:
        raise ValueError('Choose a declared company read tool.')
    context.require_current()
    return result


def call(context, name, arguments):
    workspace = extension(context)
    values = dict(arguments)
    evidence = values.pop('evidence')
    if name == 'manufacturer_save_configurator':
        result = workspace.save_configurator(context.actor, values, evidence, actor_type='agent')
    elif name == 'manufacturer_edit_configurator':
        from manufacturer_agent_edits import edit
        result = edit(workspace, context.actor, values, evidence)
    elif name == 'manufacturer_restore_configurator':
        from manufacturer_agent_edits import receipt
        result = receipt(workspace.restore(context.actor, values['version_id'], values['expected_revision'], evidence, actor_type='agent'))
    elif name in {'manufacturer_draft_invitation', 'manufacturer_update_team_policy'}:
        values['action'] = 'invite' if name == 'manufacturer_draft_invitation' else 'policy'
        result = workspace.update_team(context.actor, values, evidence)
    else:
        raise ValueError('Choose a declared company draft tool.')
    context.require_current()
    return result


FAMILY = sys.modules[__name__]
