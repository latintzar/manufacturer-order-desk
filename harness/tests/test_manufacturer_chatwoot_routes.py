"""Signed Chatwoot ingress verifies scope before any workspace initialization."""
from contextlib import contextmanager
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3
import sys
import time
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'verticals/manufacturer'))
from manufacturer_chatwoot import ChatwootHTTP, ChatwootHeld
from manufacturer_chatwoot_routes import configuration_for,install_chatwoot,register_chatwoot
from test_manufacturer_chatwoot import cfg,event,signed


@pytest.fixture
def boundary(tmp_path,monkeypatch):
    @contextmanager
    def connect():
        with sqlite3.connect(tmp_path/'access.sqlite') as db:yield db
    with connect() as db:db.execute('CREATE TABLE environments (id TEXT)');db.execute("INSERT INTO environments VALUES('demo')")
    calls=[]
    extension=SimpleNamespace(company_id='company-a',member=lambda actor: actor=='peter')
    selected={'state':tmp_path,'environment_id':'demo','vertical':extension}
    extension.selected=selected
    app=FastAPI()
    def workspace(environment):calls.append(environment);return selected
    host=SimpleNamespace(state=tmp_path,access=SimpleNamespace(connect=connect),options={},workspace=workspace)
    install_chatwoot(host,selected,extension)
    def context(request):
        if request.headers.get('x-actor')!='peter':raise HTTPException(403)
        return 'peter',extension
    def invoke(function,*args,**kwargs):
        try:return function(*args,**kwargs)
        except ValueError:raise HTTPException(403)
    register_chatwoot(app,host,context=context,invoke=invoke)
    def external_trap(*a,**kw):pytest.fail('Webhook/status performed provider I/O')
    monkeypatch.setattr(ChatwootHTTP,'request',external_trap)
    return tmp_path,host,extension,TestClient(app),calls


def commission(root):
    data=asdict(cfg(commissioned_until=time.time()+86400));data['schema_version']=1
    secret={k:data.pop(k) for k in ('api_token','webhook_secret')}
    secret.update({k:data[k] for k in ('company_id','environment_id','account_id','schema_version')})
    for path,value in [(root/'chatwoot-secret.json',secret),(root/'.workspace-identity.json',{'company_scope':'company-a'})]:
        path.write_text(json.dumps(value));path.chmod(0o600)
    data['credentials_path']=str(root/'chatwoot-secret.json')
    path=root/'manufacturer-chatwoot.json';path.write_text(json.dumps(data));path.chmod(0o600)
    return path


def test_missing_setup_is_explicit_and_webhook_opens_no_workspace(boundary):
    root,host,extension,client,calls=boundary
    result=client.get('/api/manufacturer/communication/status',headers={'x-actor':'peter'}).json()
    assert result['state']=='setup' and not result['email_ready'] and not result['connected']
    assert client.post('/hooks/manufacturer-chatwoot/demo',content=b'{}').status_code==403
    assert calls==[]


def test_signature_scope_and_bounded_body_precede_workspace_lookup(boundary):
    root,host,extension,client,calls=boundary;commission(root)
    raw,headers=signed(event(),now=int(time.time()))
    assert client.post('/hooks/manufacturer-chatwoot/demo',content=raw,headers={**headers,'X-Chatwoot-Signature':'wrong'}).status_code==403
    other,hdr=signed(event(account={'id':4}),now=int(time.time()))
    assert client.post('/hooks/manufacturer-chatwoot/demo',content=other,headers=hdr).status_code==403
    assert client.post('/hooks/manufacturer-chatwoot/missing',content=raw,headers=headers).status_code==403
    assert client.post('/hooks/manufacturer-chatwoot/demo',content=b'x'*(256*1024+1)).status_code==413
    assert calls==[]
    result=client.post('/hooks/manufacturer-chatwoot/demo',content=raw,headers=headers)
    assert result.status_code==200 and result.json()['status']=='review'
    assert calls==['demo']


def test_private_configuration_and_runtime_revocation(boundary):
    root,host,extension,client,calls=boundary;path=commission(root)
    assert extension.chatwoot.status()['service_ready']
    value=json.loads(path.read_text());value['commissioned_until']=0;path.write_text(json.dumps(value))
    assert not extension.chatwoot.status()['service_ready']
    path.chmod(0o644)
    with pytest.raises(ValueError):configuration_for(root,'demo','company-a')


@pytest.fixture
def cutover(tmp_path):
    from manufacturer_conversations import ManufacturerConversations
    from manufacturer_conversation_routes import register_conversations
    from test_manufacturer_conversations import order
    class Adapter:
        def __init__(self):self.sent=[];self.email=False;self.selected=True
        def status(self):return dict(selected=self.selected,service_ready=True,email_ready=self.email,missing=[])
        def ensure_thread(self,*a,**kw):assert kw['current']()
        def history(self,*a,**kw):return dict(messages=[dict(id='chatwoot-1',sequence=1,kind='message',text='Chatwoot history',created_at='2027-01-15T08:00:00+00:00',author_id='peter',author_type='provider',data={})],has_more=False,next_before=None)
        def send(self,*a,**kw):
            assert kw['current']()
            if kw.get('send_admission'):assert kw['send_admission']({'recipient':'buyer@example.test'})
            self.sent.append((a,kw));return {'provider':'chatwoot','status':'accepted'}
    class Extension:
        def __init__(self):
            self.company_id='company-a';self.chatwoot=Adapter();self.conversations=ManufacturerConversations(tmp_path,'company-a')
            self.selected={'state':tmp_path,'environment_id':'demo','business_scope':SimpleNamespace(members=lambda:[{'id':'peter','display_name':'Peter'}])}
            self.original=order();self.profile={'id':'buyer','display_name':'Buyer','contacts':[{'email':'buyer@example.test'}],'is_demo':False}
        def member(self,actor,**kw):
            if actor!='peter':raise ValueError()
            return {'role':'owner'}
        def authorized(self,actor):return actor=='peter'
        def customer(self,actor,customer):self.member(actor);assert customer=='buyer';return {'customer':self.profile}
        def _customer_snapshot(self,actor):return ([dict(self.profile,orders=[self.original])],None,None)
    extension=Extension();app=FastAPI()
    def context(request,writable=False):
        actor=request.headers.get('x-actor','peter')
        try:extension.member(actor)
        except ValueError:raise HTTPException(403)
        return actor,extension
    async def body(request):return await request.json()
    def invoke(fn,*args,**kwargs):
        try:return fn(*args,**kwargs)
        except ValueError:raise HTTPException(403)
    register_conversations(app,context=context,body=body,invoke=invoke)
    return extension,TestClient(app)


def test_service_routes_cutover_preserves_single_authoritative_history(cutover):
    extension,client=cutover
    data=client.get('/api/manufacturer/service-conversation').json()
    assert data['messages'][0]['text']=='Chatwoot history' and data['archive']['provider']=='native'
    assert client.post('/api/manufacturer/service-conversation/messages',json={'text':'Hello','idempotency_key':'one'}).status_code==200
    assert len(extension.chatwoot.sent)==1
    assert extension.conversations.service_conversation()['messages']==[]
    assert client.get('/api/manufacturer/service-conversation/archive').json()['archive'] is True


def test_customer_routes_keep_order_events_and_hold_uncommissioned_email(cutover):
    extension,client=cutover
    data=client.get('/api/manufacturer/conversations/buyer').json()
    assert {m['kind'] for m in data['messages']}=={'order_submitted','message'}
    assert data['delivery_ready'] is False
    payload={'text':'Customer reply','idempotency_key':'one','order_id':'order-1'}
    assert client.post('/api/manufacturer/conversations/buyer/messages',json=payload).status_code==503
    assert extension.chatwoot.sent==[]
    extension.chatwoot.email=True
    assert client.post('/api/manufacturer/conversations/buyer/messages',json=payload).status_code==200
    assert len(extension.chatwoot.sent)==1
    assert all(m['kind']!='human_message' for m in extension.conversations.conversation('buyer')['messages'])


def test_demo_origin_survives_profile_changes_and_blocks_delivery(cutover):
    extension,client=cutover;extension.chatwoot.email=True
    extension.original['is_demo']=True
    assert client.get('/api/manufacturer/conversations/buyer').json()['delivery_ready'] is False
    extension.original['is_demo']=False
    assert client.get('/api/manufacturer/conversations/buyer').json()['delivery_ready'] is False
    assert client.post('/api/manufacturer/conversations/buyer/messages',json={'text':'Hello','idempotency_key':'one'}).status_code==503
    assert extension.chatwoot.sent==[]


def test_unselected_service_retains_existing_native_path(cutover):
    extension,client=cutover;extension.chatwoot.selected=False
    assert client.post('/api/manufacturer/service-conversation/messages',json={'text':'Hello','idempotency_key':'one'}).status_code==200
    assert extension.conversations.service_conversation()['messages'][0]['text']=='Hello'
    assert extension.chatwoot.sent==[]


@pytest.mark.parametrize('environment',[None,'other'])
def test_commissioned_adapter_requires_the_explicit_native_environment(boundary,environment):
    root,host,extension,client,calls=boundary;commission(root)
    if environment is None:extension.selected.pop('environment_id')
    else:extension.selected['environment_id']=environment
    with pytest.raises(ChatwootHeld):extension.chatwoot.status()
    assert calls==[]
    assert not (root/'manufacturer-chatwoot.sqlite').exists()
