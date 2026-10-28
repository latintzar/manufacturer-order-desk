#!/usr/bin/env python3
"""Prepare a condition-only update for an existing versioned configurator configuration.

This command writes a local review plan. The owning platform applies its configuration through
its existing expected-revision save operation; this helper performs no service or provider writes.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def plan(configuration, definition):
    """Merge only explicitly supplied question/option when fields; retain every other edit."""
    updated = copy.deepcopy(configuration)
    questions = updated.get('questionnaire', {}).get('questions', [])
    by_id = {question['id']: question for question in questions}
    changes = []

    def condition(target, source, question_id, option_id=None):
        if 'when' not in source:
            return
        wanted = source['when']
        if wanted is not None:
            if not isinstance(wanted, dict):
                raise ValueError('Question conditions must be a mapping.')
            for dependency, choices in wanted.items():
                parent = by_id.get(dependency)
                allowed = {option['id'] for option in (parent or {}).get('options', [])}
                if parent and parent.get('unsure'):
                    allowed.add('?')
                if not parent or not isinstance(choices, list) or not choices or set(choices) - allowed:
                    raise ValueError('Reconcile the existing choices for condition ' + dependency + '.')
        if target.get('when') == wanted:
            return
        changes.append({'question_id': question_id, **({'option_id': option_id} if option_id else {}),
                        'before': copy.deepcopy(target.get('when')), 'after': copy.deepcopy(wanted)})
        if wanted is None:
            target.pop('when', None)
        else:
            target['when'] = copy.deepcopy(wanted)

    for source in definition.get('questions', []):
        if 'when' not in source and not any('when' in option for option in source.get('options', [])):
            continue
        target = by_id.get(source['id'])
        if target is None:
            raise ValueError('Reconcile the existing question ' + source['id'] + '.')
        condition(target, source, source['id'])
        options = {option['id']: option for option in target.get('options', [])}
        for option in source.get('options', []):
            if 'when' not in option:
                continue
            if option['id'] not in options:
                raise ValueError('Reconcile the existing option ' + option['id'] + '.')
            condition(options[option['id']], option, source['id'], option['id'])
    return {'expected_configuration_sha256': digest(configuration),
            'configuration_sha256': digest(updated), 'changes': changes, 'configuration': updated}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--configuration', type=Path, required=True)
    parser.add_argument('--definition', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = plan(json.loads(args.configuration.read_text()), json.loads(args.definition.read_text()))
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: value for key, value in result.items() if key != 'configuration'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
