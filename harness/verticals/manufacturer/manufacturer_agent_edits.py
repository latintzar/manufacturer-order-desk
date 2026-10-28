"""Bounded agent views and server-side edits of the existing complete snapshot."""
from __future__ import annotations

import copy
import hashlib
import math

from manufacturer_store import Conflict, Invalid, dump


def label(value, language='en'):
    if isinstance(value, dict):
        value = value.get(language) or value.get('en') or next(iter(value.values()), '')
    return value[:300] if isinstance(value, str) else ''


def bounded(value, depth=0):
    """Source attributes are data; keep an unusually large source field out of chat."""
    if depth > 3:
        return '[truncated]'
    if isinstance(value, str):
        return value[:300]
    if isinstance(value, list):
        return [bounded(item, depth + 1) for item in value[:20]]
    if isinstance(value, dict):
        return {key: bounded(item, depth + 1) for key, item in list(value.items())[:32]}
    return value


def receipt(value):
    publication = value.get('publication', {})
    result = {key: value[key] for key in ('revision', 'version_id', 'state', 'published')}
    result.update(sha256=hashlib.sha256(dump(value['document']).encode()).hexdigest(),
                  preview_url=value['settings']['preview_url'])
    result['publication'] = {key: publication[key] for key in ('state', 'published', 'updated_at') if key in publication}
    if publication.get('receipt', {}).get('message'):
        result['publication']['message'] = str(publication['receipt']['message'])[:500]
    return result


def summary(value, *, question_id=None, language='en', questions_offset=0, options_offset=0, categories_offset=0):
    document = value['document']
    cats = document['catalogue'].get('cats', [])
    questions = document['configuration'].get('questionnaire', {}).get('questions', [])
    result = receipt(value)
    result['settings'] = value['settings']
    result['languages'] = document['configuration'].get('languages', [document['configuration'].get('defaultLanguage', 'en')])
    result['catalogue'] = {
        'article_count': sum(len(cat.get('items', [])) for cat in cats),
        'category_count': len(cats),
        'currency': document['catalogue'].get('currency', document['configuration'].get('currency')),
        'categories': [{'code': cat.get('code'), 'name': label(cat.get(language) or cat.get('en') or cat.get('bg'), language),
                        'article_count': len(cat.get('items', []))} for cat in cats[categories_offset:categories_offset + 20]],
        'next_offset': categories_offset + 20 if categories_offset + 20 < len(cats) else None,
    }
    result['questions'] = {'total': len(questions), 'items': [
        {'id': item['id'], 'title': label(item.get('title'), language), 'kind': item.get('kind', 'single'),
         'option_count': len(item.get('options', []))} for item in questions[questions_offset:questions_offset + 20]],
        'next_offset': questions_offset + 20 if questions_offset + 20 < len(questions) else None}
    if question_id:
        question = next((item for item in questions if item['id'] == question_id), None)
        if question is None:
            raise Invalid('Choose a question identifier in the current configuration.')
        options = question.get('options', [])
        result['question'] = {'id': question_id, 'kind': question.get('kind', 'single'),
            **{field: label(question[field], language) for field in ('title', 'help', 'short') if field in question},
            'options': [{'id': item['id'], 'label': label(item.get('label'), language),
                         **({'sub': label(item['sub'], language)} if 'sub' in item else {})}
                        for item in options[options_offset:options_offset + 20]],
            'option_count': len(options), 'next_offset': options_offset + 20 if options_offset + 20 < len(options) else None}
    attachments = document.get('attachments', [])
    result['attachments'] = {'total': len(attachments), 'items': [
        {key: item[key] for key in ('file_id', 'name', 'purpose') if key in item} for item in attachments[:20]]}
    return result


def find_products(value, *, query='', code=None, category=None, limit=10, offset=0):
    document = value['document']
    catalogue = document['catalogue']
    query = query.strip().casefold()
    overrides = {item['item_id']: item['amount'] for item in catalogue.get('price_overrides', []) if item.get('basis') == 'p'}
    matches = []
    for cat in catalogue.get('cats', []):
        if category and cat.get('code') != category:
            continue
        for item in cat.get('items', []):
            if code is not None and item.get('c') != code:
                continue
            text = ' '.join(str(v) for v in (item.get('c', ''), cat.get('en', ''), cat.get('bg', ''),
                                            item.get('se', ''), item.get('s', ''), item.get('a', {}))).casefold()
            if query and query not in text:
                continue
            matches.append((cat, item))
    products = []
    for cat, item in matches[offset:offset + limit]:
        price = overrides.get(item.get('c'), item.get('p'))
        priced = (item.get('c') in overrides or not item.get('q')) and type(price) in (int, float) and math.isfinite(price) and price >= 0
        attrs = item.get('a', {})
        compact_attrs = bounded(attrs)
        products.append({'code': item.get('c'), 'name': label(cat.get('en') or cat.get('bg')),
                         'description': label(item.get('se') or item.get('s')), 'category': cat.get('code'),
                         'unit': item.get('u'), 'price': price if priced else None, 'on_request': not priced,
                         'attributes': compact_attrs, 'attributes_truncated': attrs != compact_attrs,
                         'source': bounded(cat.get('url') or catalogue.get('source') or document['configuration'].get('source'))})
    return {'revision': value['revision'], 'version_id': value['version_id'],
            'currency': catalogue.get('currency', document['configuration'].get('currency')),
            'total': len(matches), 'products': products, 'next_offset': offset + limit if offset + limit < len(matches) else None}


def localized(target, field, changes, language):
    previous = target.get(field, {})
    target[field] = {**(previous if isinstance(previous, dict) else {language: previous}), **changes}


def unique(rows, key):
    values = [row[key] for row in rows]
    if len(set(values)) != len(values):
        raise Invalid('Include each identifier once in this change.')


def edit(workspace, actor, arguments, evidence):
    workspace.member(actor, write=True)
    current = workspace.configurator(actor, retry_publication=False)
    if arguments['expected_revision'] != current['revision']:
        raise Conflict('This configuration changed. Review the latest version and save again.')
    document = copy.deepcopy(current['document'])
    changes = arguments['changes']
    configuration, catalogue = document['configuration'], document['catalogue']
    configuration.update(changes.get('appearance', {}))
    prices = changes.get('prices', [])
    unique(prices, 'code')
    for row in prices:
        found = [item for cat in catalogue.get('cats', []) for item in cat.get('items', []) if item.get('c') == row['code']]
        if len(found) != 1:
            raise Invalid('Choose one existing article identifier from the current catalogue.')
        amount = row['price']
        if amount not in (None, '') and (type(amount) not in (int, float) or not math.isfinite(amount) or not 0 <= amount <= 1e12):
            raise Invalid('Use a finite unit price from zero to 1,000,000,000,000.')
        on_request = amount is None or amount == ''
        found[0].update(p=0 if on_request else amount, q=1 if on_request else 0)
        if isinstance(catalogue.get('price_overrides'), list):
            catalogue['price_overrides'] = [item for item in catalogue['price_overrides']
                                           if item.get('item_id') != row['code'] or item.get('basis') != 'p']
    questions = changes.get('questions', [])
    unique(questions, 'id')
    by_id = {item['id']: item for item in configuration.get('questionnaire', {}).get('questions', [])}
    language = configuration.get('defaultLanguage', 'en')
    for row in questions:
        target = by_id.get(row['id'])
        if target is None:
            raise Invalid('Choose an existing question identifier.')
        for field in ('title', 'help', 'short'):
            if field in row:
                localized(target, field, row[field], language)
        options = row.get('options', [])
        unique(options, 'id')
        by_option = {item['id']: item for item in target.get('options', [])}
        for option in options:
            if option['id'] not in by_option:
                raise Invalid('Choose an existing answer identifier.')
            for field in ('label', 'sub'):
                if field in option:
                    localized(by_option[option['id']], field, option[field], language)
    attachments = changes.get('attachments', [])
    unique(attachments, 'file_id')
    by_file = {item['file_id']: item for item in document['attachments']}
    for item in attachments:
        if item['file_id'] in by_file:
            by_file[item['file_id']].update(item)
        else:
            document['attachments'].append(copy.deepcopy(item))
    if document == current['document']:
        raise Invalid('Supply a change to the current configuration.')
    values = {key: arguments[key] for key in ('expected_revision', 'label', 'summary') if key in arguments}
    values['document'] = document
    return receipt(workspace.save_configurator(actor, values, evidence, actor_type='agent'))
