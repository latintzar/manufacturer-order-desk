"""A condition-only migration preserves concurrent configurator edits and exact restore inputs."""
import copy

import pytest

from pipeline.questionnaire_conditions import plan


def test_plan_preserves_custom_questions_options_and_every_unrelated_setting():
    original = {'accent': '#123456', 'headline': {'bg': 'Custom headline'}, 'other': {'prices': [1, 2]},
        'questionnaire': {'title': 'Custom questionnaire', 'questions': [
            {'id': 'parts', 'unsure': True, 'options': [{'id': 'handles', 'label': 'Custom handle'}]},
            {'id': 'finish', 'title': 'Custom finish', 'options': [{'id': 'white', 'label': 'Custom white'},
                {'id': 'special', 'match': {'colour': ['custom']}}]},
            {'id': 'custom-project', 'when': {'parts': ['handles']}, 'options': []}]}}
    before = copy.deepcopy(original)
    definition = {'questions': [{'id': 'finish', 'when': {'parts': ['handles', '?']},
                                 'options': [{'id': 'white', 'when': {'parts': ['handles']}}]}]}
    result = plan(original, definition)
    assert original == before
    actual = result['configuration']
    assert len(result['changes']) == 2
    assert actual['questionnaire']['questions'][1]['when'] == {'parts': ['handles', '?']}
    assert actual['questionnaire']['questions'][1]['options'][0]['when'] == {'parts': ['handles']}
    del actual['questionnaire']['questions'][1]['when']
    del actual['questionnaire']['questions'][1]['options'][0]['when']
    assert actual == before
    assert plan(result['configuration'], {'questions': []})['changes'] == []


def test_plan_is_repeat_safe_and_refuses_removed_dependency_choices():
    original = {'questionnaire': {'questions': [
        {'id': 'parts', 'options': [{'id': 'handles'}]},
        {'id': 'finish', 'options': []}]}}
    definition = {'questions': [{'id': 'finish', 'when': {'parts': ['handles']}}]}
    result = plan(original, definition)
    again = plan(result['configuration'], definition)
    assert again['changes'] == []
    assert again['configuration_sha256'] == result['configuration_sha256']
    original['questionnaire']['questions'][0]['options'] = []
    with pytest.raises(ValueError, match='Reconcile'):
        plan(original, definition)
