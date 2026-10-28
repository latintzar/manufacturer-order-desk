"""Real conversation-store pagination and event metadata through the HTTP boundary."""
from types import SimpleNamespace
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest
from manufacturer_conversations import ManufacturerConversations
from manufacturer_conversation_routes import register_conversations
from manufacturer_store import Missing


@pytest.fixture
def boundary(tmp_path):
    store = ManufacturerConversations(tmp_path, 'company-fixture')
    source = {'id':'order-1','customer_id':'buyer','display_number':'#1042','status':'requested',
              'lines':[{'code':'101037','name':'Handle','quantity':2,'unit':'pc'}]}
    profile = {'id':'buyer','display_name':'Buyer Company',
               'contacts':[{'name':'Иван Петров','email':'buyer@example.test'}]}
    members = [{'id':'peter','display_name':'Питър'}, {'id':'client','display_name':'Мария Иванова'}]
    class Extension:
        conversations = store
        company_id = 'company-fixture'
        selected = {'state':tmp_path,'environment_id':'demo',
                    'business_scope':SimpleNamespace(members=lambda:members)}
        def member(self, actor):
            return {'role':'owner' if actor == 'peter' else 'operator'}
        def authorized(self, actor):
            return actor in {'peter','client'}
        def customer(self, actor, customer_id):
            if customer_id != 'buyer':
                raise HTTPException(404)
            return {'customer':profile}
        def _customer_snapshot(self, actor):
            return [{**profile,'orders':[source]}],None,None
    extension = Extension()
    def invoke(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Missing as exc:
            raise HTTPException(404, str(exc))
    app = FastAPI()
    register_conversations(app, context=lambda request,*args:('client',extension),
                           body=lambda request:request.json(), invoke=invoke)
    store.ensure_service(actor='peter',current=lambda:True)
    store.ensure_customer('buyer',contacts=profile['contacts'],actor='peter',current=lambda:True)
    store.record_source_order('buyer',source,actor='peter',current=lambda:True)
    with TestClient(app) as client:
        yield client,store,source


def pages(client, path):
    latest = client.get(path).json()
    result = latest['messages']
    while latest['has_more']:
        latest = client.get(path,params={'before':latest['next_before']}).json()
        result = latest['messages'] + result
    return result


def test_service_history_over_fifty_retains_every_message_and_exact_authors(boundary):
    client,store,_ = boundary
    for index in range(63):
        store.send_service_message(text=f'Message {index}',actor='peter' if index%2 else 'client',
            side='provider' if index%2 else 'client',idempotency_key=f'service-{index}',current=lambda:True)
    latest = client.get('/api/manufacturer/service-conversation').json()
    assert len(latest['messages']) == 50 and latest['has_more']
    all_messages = pages(client,'/api/manufacturer/service-conversation')
    assert [m['text'] for m in all_messages] == [f'Message {i}' for i in range(63)]
    assert len({m['id'] for m in all_messages}) == 63
    assert all_messages[0]['author_name'] == 'Мария Иванова'
    assert all_messages[1]['author_name'] == 'Питър'
    assert all_messages[0]['direction'] == 'outbound'
    assert all_messages[1]['direction'] == 'inbound'
    for invalid in ['0','-1','not-a-cursor','9223372036854775808']:
        assert client.get('/api/manufacturer/service-conversation',params={'before':invalid}).status_code == 422


def test_customer_history_resolves_proposal_confirmation_and_system_metadata(boundary):
    client,store,source = boundary
    result = store.propose_request('buyer','order-1',proposal=source,recipient='buyer@example.test',
        expected_revision=0,actor='peter',idempotency_key='proposal-1',current=lambda:True)
    store.confirm_proposal('buyer','order-1',version_id=result['proposal']['id'],customer_actor='portal-link',
        evidence={'method':'review_link','contact':'buyer@example.test'},current=lambda:True)
    incoming = store.record_customer_message('buyer',text='Thank you',sender='buyer@example.test',provider='fixture',
        provider_event_id='incoming-1',provenance={'signature_verified':True},current=lambda:True)
    store.record_email_intent('buyer',message_id=incoming['id'],intent='confirmation',confidence=.9,
        ambiguous=False,evidence={'source':'fixture'},actor='peter',idempotency_key='intent-1',current=lambda:True)
    for index in range(55):
        store.send_message('buyer',text=f'Customer note {index}',recipient='buyer@example.test',actor='client',
            idempotency_key=f'note-{index}',current=lambda:True)
    latest = client.get('/api/manufacturer/conversations/buyer').json()
    assert len(latest['messages']) == 50 and latest['has_more'] and latest['delivery_ready'] is False
    messages = pages(client,'/api/manufacturer/conversations/buyer')
    assert len(messages) == 60 and len({m['id'] for m in messages}) == 60
    proposal = next(m for m in messages if m['kind']=='proposal')
    confirmation = next(m for m in messages if m['kind']=='customer_confirmation')
    classification = next(m for m in messages if m['kind']=='email_intent')
    assert proposal['order_number'] == '#1042' and proposal['version'] == 1
    assert proposal['author_name'] == 'Питър' and proposal['delivery']['status'] == 'pending'
    assert confirmation['order_number'] == '#1042' and confirmation['version'] == 1
    assert confirmation['author_name'] == 'Иван Петров'
    assert classification['author_name'] == 'Система' and classification['data']['authority'] == 'suggestion'
    assert messages[-1]['author_name'] == 'Мария Иванова'
    assert client.post('/api/manufacturer/conversations/buyer/messages',json={'text':'Not sent','idempotency_key':'held-message'}).status_code == 503
    assert client.get('/api/manufacturer/conversations/buyer',params={'order_id':'foreign'}).status_code == 404
    assert client.get('/api/manufacturer/conversations/foreign',params={'before':latest['next_before']}).status_code == 404
