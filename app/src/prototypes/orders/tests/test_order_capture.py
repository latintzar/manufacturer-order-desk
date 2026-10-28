"""Saved request needs are bounded customer facts, independent of quoted prices."""
import copy

import customer_details
import pytest
from platform_source import order_projection
from store import CompanyStore

pytest_plugins = ['test_order_api']


def needs():
    return {'schema': 'rocoto.orders.capture.v1', 'entry_path': 'questionnaire', 'language': 'en',
        'questionnaire': {'title': 'Door needs', 'project': 'Twelve replacement doors', 'questions': [
            {'id': 'parts', 'label': 'Parts required', 'status': 'answered', 'answers': [{'id': 'lock', 'label': 'Lock'}]},
            {'id': 'hand', 'label': 'Door hand', 'status': 'unknown', 'answers': [{'id': '?', 'label': 'I am not sure'}]},
            {'id': 'size', 'label': 'Dimensions', 'status': 'unanswered', 'answers': []}]},
        'proposal': {'title': 'Lock proposal', 'summary': 'Confirm existing dimensions.',
                     'selected': [{'code': 'A', 'quantity': 12, 'reason': 'Customer selected lock'}]}}


def test_checkout_persists_needs_and_native_projection_without_changing_price(order_api):
    from test_order_api import order, request
    payload = order()
    payload['customer']['capture'] = needs()
    status, saved = request(order_api, 'orders', payload, key='captured-needs-order-001')
    assert status == 201, saved
    database = CompanyStore(order_api[1])
    try:
        stored = database.read_order(saved['id'])
        assert stored['customer']['capture'] == needs()
        projected = order_projection(database, database.one('SELECT * FROM orders WHERE id=?', (saved['id'],)))
        assert projected['customer_id'] == stored['customer_id']
        assert projected['request_context'] == needs()
        assert projected['is_demo'] is False
        assert projected['quote'] == saved['quote']
    finally:
        database.close()


@pytest.mark.parametrize('mutation', [
    lambda value: value.update(entry_path='catalogue'),
    lambda value: value['questionnaire']['questions'][0].update(label='x' * 401),
    lambda value: value['questionnaire']['questions'][1].update(status='answered'),
    lambda value: value['questionnaire']['questions'][2].update(status='unknown'),
    lambda value: value['proposal']['selected'][0].update(quantity=True),
    lambda value: value['proposal'].update(price=0),
    lambda value: value['questionnaire'].update(questions=value['questionnaire']['questions'] * 20),
])
def test_capture_rejects_ambiguous_states_oversize_and_commercial_fields(mutation):
    value = copy.deepcopy(needs())
    mutation(value)
    with pytest.raises(ValueError):
        customer_details.capture(value)


def test_public_customer_cannot_mark_real_request_as_demo():
    with pytest.raises(ValueError):
        customer_details.validate({'name': 'Customer', 'email': 'customer@example.test', 'is_demo': True}, {})


def test_specification_file_must_match_claimed_order_attachment():
    value = {'name': 'Customer', 'email': 'customer@example.test', 'capture': {
        'schema': 'rocoto.orders.capture.v1', 'entry_path': 'specification', 'language': 'en',
        'specification': {'text': '12 locks', 'lines': [], 'file_id': 'a' * 32}}}
    with pytest.raises(ValueError):
        customer_details.validate(value, {})
    value['specification_file'] = 'a' * 32
    assert customer_details.validate(value, {})['capture']['specification']['file_id'] == 'a' * 32


def test_long_cyrillic_specification_capture_fits_bounded_order_transport(order_api):
    from test_order_api import order, request
    payload = order()
    text = 'Брава за училищни врати. ' * 700
    payload['customer'].update(specification=text, capture={
        'schema': 'rocoto.orders.capture.v1', 'entry_path': 'specification', 'language': 'bg',
        'specification': {'text': text, 'lines': [{'source': 'Брава A', 'quantity': 3,
                                                'selected_code': 'A', 'status': 'exact'}]}})
    status, saved = request(order_api, 'orders', payload, key='capture-long-specification')
    assert status == 201, saved
