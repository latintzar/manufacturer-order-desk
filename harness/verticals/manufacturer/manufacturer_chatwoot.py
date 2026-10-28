"""Company-bound headless Chatwoot CE application API (v4.18.0).

Chatwoot owns communication history. This adapter stores numeric bindings,
operation hashes and bounded webhook receipts; business review records stay in
ManufacturerConversations. Human actions and deterministic notifications call
this adapter from authenticated host code. It is never registered as an AI tool.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import time
from urllib.parse import urlsplit

import httpx

from manufacturer_conversations import _email

MAX_BODY = 256 * 1024
MAX_RECEIPTS = 20000
MAX_OPERATIONS = 100000


class ChatwootHeld(ValueError):
    """A sanitized setup, scope, receipt or admission error."""


def _require(condition, message='Review the company communication connection.'):
    if not condition:
        raise ChatwootHeld(message)


def _text(value, maximum=8000, *, empty=False):
    _require(isinstance(value, str) and len(value) <= maximum and (empty or bool(value.strip()))
             and not any(ord(c) < 32 and c not in '\n\r\t' for c in value))
    return value.strip()


def _id(value):
    _require(type(value) is int and 0 < value <= 9223372036854775807)
    return value


def _key(value):
    _require(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:@-]{0,199}', value))
    return value


def _json(value):
    try:
        result=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
        _require(len(result.encode()) <= MAX_BODY)
        return result
    except (ValueError,TypeError,RecursionError):
        raise ChatwootHeld('Use a bounded communication document.') from None


def _hash(value):
    return hashlib.sha256(value.encode() if isinstance(value,str) else value).hexdigest()


def _origin(value):
    _require(isinstance(value,str) and len(value) <= 2048)
    try:
        url=urlsplit(value)
        _require(url.hostname and not url.username and not url.password and not url.query and not url.fragment
                 and url.path == '' and (url.scheme=='https' or
                     url.scheme=='http' and url.hostname in ('127.0.0.1','localhost','::1')))
        _require(url.port is None or 1 <= url.port <= 65535)
    except ValueError:
        raise ChatwootHeld('Use the commissioned communication origin.') from None
    return value


@dataclass(frozen=True)
class ChatwootConfig:
    company_id: str
    environment_id: str
    origin: str = ''
    account_id: int = 0
    api_token: str = ''
    webhook_secret: str = ''
    service_inbox_id: int = 0
    email_inbox_id: int = 0
    commissioned_until: float = 0
    evidence_id: str = ''
    email_enabled: bool = False
    email_evidence_id: str = ''
    sender_email: str = ''
    daily_send_limit: int = 20

    def missing(self, now):
        missing=[]
        for name,valid in (
            ('api_origin',bool(self.origin)),('account',type(self.account_id) is int and self.account_id>0),
            ('api_token',isinstance(self.api_token,str) and 16 <= len(self.api_token) <= 1024),
            ('webhook_secret',isinstance(self.webhook_secret,str) and 24 <= len(self.webhook_secret) <= 1024),
            ('commissioning_evidence',bool(self.evidence_id)),
            ('commissioning_expiry',type(self.commissioned_until) in (int,float) and now < self.commissioned_until < 4102444800),
            ('service_inbox',type(self.service_inbox_id) is int and self.service_inbox_id>0),
            ('email_inbox',type(self.email_inbox_id) is int and self.email_inbox_id>0),
            ('email_roundtrip',bool(self.email_evidence_id)),('sender_email',bool(self.sender_email)),
            ('email_enabled',self.email_enabled is True),
            ('daily_send_limit',type(self.daily_send_limit) is int and 1 <= self.daily_send_limit <= 200),
        ):
            if not valid:missing.append(name)
        if self.origin:_origin(self.origin)
        if self.sender_email:_email(self.sender_email)
        if self.email_inbox_id and self.service_inbox_id:
            _require(self.email_inbox_id != self.service_inbox_id)
        return missing


def verify_webhook(raw, headers, secret, *, now):
    """Verify the pinned CE release's HMAC(timestamp + '.' + exact body)."""
    _require(isinstance(raw,bytes) and 0<len(raw)<=MAX_BODY)
    _require(isinstance(secret,str) and 24<=len(secret)<=1024)
    headers={str(k).lower():v for k,v in headers.items()}
    timestamp=headers.get('x-chatwoot-timestamp','')
    signature=headers.get('x-chatwoot-signature','')
    _require(isinstance(timestamp,str) and re.fullmatch(r'[0-9]{1,12}',timestamp)
             and abs(now-int(timestamp))<=300,'Use a current signed communication event.')
    _require(isinstance(signature,str) and re.fullmatch(r'sha256=[a-f0-9]{64}',signature))
    expected='sha256='+hmac.new(secret.encode(),timestamp.encode()+b'.'+raw,hashlib.sha256).hexdigest()
    _require(hmac.compare_digest(signature,expected),'Verify the communication event signature.')
    try:
        value=json.loads(raw)
        _require(isinstance(value,dict))
        _json(value)
        return value
    except (ValueError,TypeError,RecursionError):
        raise ChatwootHeld('Use a complete signed communication event.') from None


class ChatwootHTTP:
    """Fixed account/origin, server token, bounded responses and zero redirects."""
    def __init__(self, config, *, client=None):
        self.config=config
        self.origin=_origin(config.origin)
        self.account_id=_id(config.account_id)
        _require(isinstance(config.api_token,str) and 16<=len(config.api_token)<=1024
                 and not any(ord(c)<33 for c in config.api_token))
        self._client=client

    def request(self, method, path, *, payload=None, params=None):
        _require(method in ('GET','POST','PATCH') and isinstance(path,str)
                 and re.fullmatch(r'/[a-z0-9_/]+',path) and '..' not in path)
        if payload is not None:_json(payload)
        client=self._client or httpx.Client(timeout=10,follow_redirects=False,trust_env=False)
        try:
            with client.stream(method,f'{self.origin}/api/v1/accounts/{self.account_id}{path}',
                    headers={'api_access_token':self.config.api_token,'Accept':'application/json'},
                    json=payload,params=params,timeout=10,follow_redirects=False) as response:
                body=bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    _require(len(body)<=MAX_BODY,'Review the communication response size.')
                _require(200<=response.status_code<300,'Review the communication provider receipt.')
                value=json.loads(body)
                _require(isinstance(value,(dict,list)))
                return value
        except (httpx.HTTPError,ValueError,RecursionError):
            raise ChatwootHeld('Review the communication provider receipt.') from None
        finally:
            if self._client is None:client.close()

    def create_api_inbox(self, name):
        """Operator commissioning only; API inbox has no email channel."""
        return self.request('POST','/inboxes',payload={'name':_text(name,120),'lock_to_single_conversation':True,
            'greeting_enabled':False,'enable_auto_assignment':False,'channel':{'type':'api','hmac_mandatory':True}})

    def create_email_inbox(self, name, email):
        """Create a disabled email inbox; credential commissioning is a separate step."""
        return self.request('POST','/inboxes',payload={'name':_text(name,120),'greeting_enabled':False,
            'enable_auto_assignment':False,'channel':{'type':'email','email':_email(email),
                'imap_enabled':False,'smtp_enabled':False}})

    def configure_email_inbox(self, inbox_id, *, email, imap, smtp, current):
        """Private operator path. Both mailbox transports require verified TLS."""
        _require(callable(current) and current() is True)
        _require(set(imap)=={'address','port','login','password'}
                 and set(smtp)=={'address','port','login','password','domain','ssl_tls'})
        channel={'email':_email(email),'imap_enabled':True,'imap_enable_ssl':True,
            'imap_authentication':'plain','smtp_enabled':True,'smtp_authentication':'login',
            'smtp_enable_ssl_tls':smtp['ssl_tls'],'smtp_enable_starttls_auto':not smtp['ssl_tls'],
            'smtp_openssl_verify_mode':'peer'}
        _require(type(smtp['ssl_tls']) is bool)
        for transport,settings in [('imap',imap),('smtp',smtp)]:
            _require(type(settings['port']) is int and 1<=settings['port']<=65535)
            for field in ('address','port','login','password'):
                channel[transport+'_'+field]=settings[field] if field=='port' else _text(settings[field],1024)
        channel['smtp_domain']=_text(smtp['domain'],253)
        _require(current() is True)
        # The API response can contain credentials: only return non-secret evidence.
        value=self.request('PATCH',f'/inboxes/{_id(inbox_id)}',payload={'channel':channel})
        return {'id':_id(value.get('id')),'channel_type':value.get('channel_type'),
                'imap_enabled':value.get('imap_enabled') is True,'smtp_enabled':value.get('smtp_enabled') is True}

    def create_webhook(self, callback_url):
        parsed=urlsplit(callback_url)
        _require(parsed.scheme=='https' and parsed.hostname and not parsed.username and not parsed.password
                 and not parsed.query and not parsed.fragment)
        # Return only to private commissioning code: payload.webhook.secret belongs in a mode-0600 file.
        return self.request('POST','/webhooks',payload={'webhook':{'name':'Rocoto communication receipts',
            'url':callback_url,'subscriptions':['message_created','message_updated']}})


class _Plain(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.parts=[];self.hidden=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style','head'):self.hidden+=1
        elif not self.hidden and tag in ('p','div','br','li'):self.parts.append('\n')
    def handle_endtag(self,tag):
        if tag in ('script','style','head'):self.hidden=max(0,self.hidden-1)
    def handle_data(self,data):
        if not self.hidden:self.parts.append(data)


def _plain(value):
    _require(isinstance(value,str) and len(value.encode())<=MAX_BODY)
    parser=_Plain();parser.feed(value)
    text=''.join(parser.parts).strip()
    return ''.join(c for c in text if ord(c)>=32 or c in '\n\r\t')[:8000]


class ManufacturerChatwoot:
    def __init__(self,state,*,company_id,environment_id,config=None,client=None,clock=time.time):
        self.company_id,self.environment_id=_key(company_id),_key(environment_id)
        self.config=config or ChatwootConfig(company_id=company_id,environment_id=environment_id)
        _require(self.config.company_id==company_id and self.config.environment_id==environment_id)
        self.clock,self.client=clock,client
        if self.config.origin:_origin(self.config.origin)
        if client is not None:
            _require(client.config==self.config)
        root=Path(state);root.mkdir(parents=True,exist_ok=True)
        self.path=root/'manufacturer-chatwoot.sqlite'
        _require(not self.path.is_symlink())
        try:
            descriptor=os.open(self.path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600);os.close(descriptor)
        except FileExistsError:pass
        info=self.path.stat()
        _require(stat.S_ISREG(info.st_mode) and info.st_uid==os.geteuid() and not info.st_mode&0o077)
        with self._db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS scope (singleton INTEGER PRIMARY KEY,company TEXT,environment TEXT,origin TEXT,account INTEGER)')
            row=db.execute('SELECT * FROM scope WHERE singleton=1').fetchone()
            identity=(company_id,environment_id,self.config.origin,self.config.account_id)
            if row:
                _require((row['company'],row['environment'])==identity[:2])
                _require(not row['origin'] or (row['origin'],row['account'])==identity[2:])
                if not row['origin'] and self.config.origin:
                    db.execute('UPDATE scope SET origin=?,account=? WHERE singleton=1',identity[2:])
            else:db.execute('INSERT INTO scope VALUES(1,?,?,?,?)',identity)
            db.execute('''CREATE TABLE IF NOT EXISTS bindings (customer TEXT,channel TEXT,inbox INTEGER,
                contact INTEGER,conversation INTEGER,recipient TEXT,PRIMARY KEY(customer,channel),UNIQUE(inbox,conversation))''')
            db.execute('''CREATE TABLE IF NOT EXISTS operations (operation TEXT PRIMARY KEY,customer TEXT,channel TEXT,
                conversation INTEGER,request_hash TEXT,actor TEXT,side TEXT,status TEXT,message INTEGER,created REAL)''')
            db.execute('CREATE UNIQUE INDEX IF NOT EXISTS operation_message ON operations(message) WHERE message IS NOT NULL')
            db.execute('''CREATE TABLE IF NOT EXISTS webhooks (hash TEXT PRIMARY KEY,event TEXT,message INTEGER,
                conversation INTEGER,inbox INTEGER,result TEXT,created REAL)''')

    @contextmanager
    def _db(self):
        db=sqlite3.connect(self.path,timeout=15);db.row_factory=sqlite3.Row
        try:
            db.execute('BEGIN IMMEDIATE');yield db;db.commit()
        except BaseException:db.rollback();raise
        finally:db.close()

    def status(self):
        missing=self.config.missing(self.clock())
        common={'api_origin','account','api_token','webhook_secret','commissioning_evidence','commissioning_expiry'}
        base=not common.intersection(missing)
        return {'provider':'chatwoot','state':'configured' if base else 'setup','connected':False,
            'selected':bool(self.config.origin),
            'service_ready':base and 'service_inbox' not in missing,
            'email_ready':base and not set(missing).intersection({'email_inbox','email_roundtrip','sender_email','email_enabled','daily_send_limit'}),
            'missing':missing,'evidence_id':self.config.evidence_id or None,
            'email_evidence_id':self.config.email_evidence_id or None}

    def _admit(self,channel,current,*,sending=False):
        _require(channel in ('email','service') and callable(current) and current() is True,
                 'Continue with current company communication access.')
        status=self.status()
        _require(status['service_ready'] if channel=='service' else status['state']=='configured')
        if channel=='email':
            _id(self.config.email_inbox_id)
            if sending:_require(status['email_ready'],'Complete the company email round trip.')
        return self.client or ChatwootHTTP(self.config)

    def _inbox(self,channel):
        return _id(self.config.email_inbox_id if channel=='email' else self.config.service_inbox_id)

    def _binding(self,customer,channel):
        with self._db() as db:
            row=db.execute('SELECT * FROM bindings WHERE customer=? AND channel=?',(_key(customer),channel)).fetchone()
        _require(row is not None,'Open a connected company conversation.')
        return dict(row)

    def _verify_thread(self,client,binding):
        value=client.request('GET',f"/conversations/{binding['conversation']}")
        _require(value.get('id')==binding['conversation'] and value.get('inbox_id')==binding['inbox'])
        if value.get('account_id') is not None:_require(value['account_id']==self.config.account_id)
        contact=(value.get('meta') or {}).get('sender') or {}
        _require(contact.get('id')==binding['contact'])
        if binding['channel']=='email':_require(_email(contact.get('email'))==binding['recipient'],
            'Review the current customer email before sending.')
        return value

    def ensure_thread(self,customer,*,channel,name,recipient='',current):
        """Host supplies a source-validated contact. Creates no messages or emails."""
        client=self._admit(channel,current);customer=_key(customer);name=_text(name,120)
        recipient=_email(recipient) if channel=='email' else ''
        inbox=self._inbox(channel)
        # Lock the bounded sequence across processes; remote ambiguity never repeats a message send.
        with self._db() as db:
            existing=db.execute('SELECT * FROM bindings WHERE customer=? AND channel=?',(customer,channel)).fetchone()
            if existing:
                _require(existing['recipient']==recipient and existing['inbox']==inbox)
                binding=dict(existing)
                if channel == 'email':
                    threads=client.request('GET',f"/contacts/{binding['contact']}/conversations").get('payload',[])
                    _require(isinstance(threads,list) and len(threads)<=100)
                    matching=[thread for thread in threads if thread.get('inbox_id')==inbox]
                    if matching:
                        binding['conversation']=max(_id(thread.get('id')) for thread in matching)
                self._verify_thread(client,binding);_require(current() is True)
                db.execute('UPDATE bindings SET conversation=? WHERE customer=? AND channel=?',
                    (binding['conversation'],customer,channel))
                return binding
            inbox_value=client.request('GET',f'/inboxes/{inbox}')
            _require(inbox_value.get('id')==inbox and inbox_value.get('channel_type')==('Channel::Email' if channel=='email' else 'Channel::Api'))
            identifier='rocoto-'+_hash(_json([self.company_id,channel,customer]))[:40]
            contacts=client.request('GET','/contacts/search',params={'q':recipient or identifier})
            items=contacts.get('payload',[])
            _require(isinstance(items,list) and len(items)<=100)
            matches=[c for c in items if isinstance(c,dict) and
                (str(c.get('email','')).lower()==recipient if recipient else c.get('identifier')==identifier)]
            _require(len(matches)<=1,'Review the customer contact binding.')
            if matches:contact=matches[0]
            else:
                _require(current() is True)
                payload={'inbox_id':inbox,'identifier':identifier,'name':name}
                if recipient:payload['email']=recipient
                created=client.request('POST','/contacts',payload=payload)
                contact=(created.get('payload') or {}).get('contact') or {}
            contact_id=_id(contact.get('id'))
            if recipient:_require(str(contact.get('email','')).lower()==recipient)
            conversations=client.request('GET',f'/contacts/{contact_id}/conversations').get('payload',[])
            _require(isinstance(conversations,list) and len(conversations)<=100)
            matches=[v for v in conversations if v.get('inbox_id')==inbox]
            # Existing mail threads preserve Chatwoot's reply headers. The newest is selected once.
            if matches:conversation=max(matches,key=lambda v:_id(v.get('id')))
            else:
                _require(current() is True)
                conversation=client.request('POST','/conversations',payload={'inbox_id':inbox,'contact_id':contact_id,
                    'status':'open','additional_attributes':{'rocoto_company':self.company_id,'rocoto_customer':customer}})
            binding=dict(customer=customer,channel=channel,inbox=inbox,contact=contact_id,
                         conversation=_id(conversation.get('id')),recipient=recipient)
            self._verify_thread(client,binding);_require(current() is True)
            try:db.execute('INSERT INTO bindings VALUES(:customer,:channel,:inbox,:contact,:conversation,:recipient)',binding)
            except sqlite3.IntegrityError:raise ChatwootHeld('Review the existing customer conversation binding.') from None
            return binding

    def _messages(self,client,binding,before=None):
        params={}
        if before is not None:params['before']=_id(before)
        value=client.request('GET',f"/conversations/{binding['conversation']}/messages",params=params)
        items=value.get('payload',[])
        _require(isinstance(items,list) and len(items)<=100)
        for item in items:
            _require(isinstance(item,dict) and item.get('conversation_id')==binding['conversation']
                     and item.get('inbox_id')==binding['inbox'])
        return items

    def history(self,customer,*,channel,current,before=None):
        client=self._admit(channel,current);binding=self._binding(customer,channel)
        self._verify_thread(client,binding)
        threads=[binding]
        truncated=False
        if channel=='email':
            values=client.request('GET',f"/contacts/{binding['contact']}/conversations").get('payload',[])
            _require(isinstance(values,list) and len(values)<=100)
            values=sorted((v for v in values if v.get('inbox_id')==binding['inbox']),key=lambda v:_id(v.get('id')),reverse=True)
            truncated=len(values)>10
            threads=[dict(binding,conversation=_id(value['id'])) for value in values[:10]] or [binding]
        gathered=[];provider_has_more=False
        for thread in threads:
            self._verify_thread(client,thread)
            page=self._messages(client,thread,before)
            gathered.extend(page);provider_has_more=provider_has_more or len(page)>=20
        gathered=sorted({item['id']:item for item in gathered}.values(),key=lambda item:_id(item['id']))
        has_more=provider_has_more or len(gathered)>40
        items=gathered[-40:]
        result=[]
        with self._db() as db:
            for item in items:
                if item.get('private') is not False or item.get('message_type') not in (0,1,'incoming','outgoing'):continue
                identifier=_id(item.get('id'))
                operation=db.execute('SELECT actor,side FROM operations WHERE message=?',(identifier,)).fetchone()
                incoming=item.get('message_type') in (0,'incoming')
                sender=item.get('sender') or {}
                author=operation['actor'] if operation else ('contact-'+str(binding['contact']) if incoming else 'chatwoot-user-'+str(sender.get('id','unknown')))
                created=item.get('created_at')
                _require(type(created) in (int,float) and 0<created<4102444800)
                result.append({'id':'chatwoot-'+str(identifier),'sequence':identifier,'kind':'message','text':_plain(item.get('content') or ''),
                    'author_id':author,'author_type':('customer' if channel=='email' else 'client') if incoming else 'provider',
                    'author_name':_text(sender.get('name') or ('Клиент' if incoming else 'Екип'),200),
                    'direction':'inbound' if incoming else 'outbound',
                    'created_at':datetime.fromtimestamp(created,timezone.utc).isoformat(),
                    'data':{'provider':'chatwoot','provider_message_id':identifier,'provider_status':item.get('status','accepted')},
                    'delivery':{'status':self._delivery_status(item),'provider':'chatwoot','provider_message_id':identifier}})
        _require(current() is True)
        return {'id':'chatwoot-conversation-'+str(binding['conversation']),'messages':result,
            'next_before':min((m['id'] for m in items),default=None),'has_more':has_more,'provider':'chatwoot','coverage':{'threads':len(threads),'truncated':truncated},
            'delivery_ready':self.status()['email_ready'] if channel=='email' else True}

    @staticmethod
    def _delivery_status(message):
        # Chatwoot's default `sent` marks its queued job, not recipient delivery.
        return message.get('status') if message.get('status') in ('delivered','read','failed') else 'accepted'

    def _receipt(self,row):
        return {'provider':'chatwoot','status':row['status'],'provider_message_id':row['message'],
                'operation_id':row['operation'],'evidence_id':'chatwoot-operation-'+row['operation']}

    def send(self,customer,*,channel,text,idempotency_key,actor,current,side='outgoing',send_admission=None):
        client=self._admit(channel,current,sending=True);text=_text(text);actor=_key(actor)
        _require(side in ('incoming','outgoing') and (channel=='service' or side=='outgoing'))
        binding=self._binding(customer,channel);self._verify_thread(client,binding)
        context={'company_id':self.company_id,'environment_id':self.environment_id,'customer_id':customer,
            'recipient':binding['recipient'],'actor':actor,'channel':channel}
        if channel=='email':
            _require(callable(send_admission) and send_admission(context) is True,'Continue with the current company email allowance.')
            inbox=client.request('GET',f"/inboxes/{binding['inbox']}")
            _require(inbox.get('smtp_enabled') is True and inbox.get('imap_enabled') is True
                     and inbox.get('email')==self.config.sender_email,'Verify the commissioned mailbox transports.')
        operation=_hash(_json([self.company_id,customer,channel,_key(idempotency_key)]))
        payload={'content':text,'message_type':side,'private':False,'content_type':'text',
                 'content_attributes':{'rocoto_operation':operation}}
        if channel=='email':payload['to_emails']=binding['recipient']
        request_hash=_hash(_json([payload,actor,binding]))
        with self._db() as db:
            row=db.execute('SELECT * FROM operations WHERE operation=?',(operation,)).fetchone()
            if row:
                _require(row['request_hash']==request_hash,'Keep the original message for this send operation.')
                if row['status']!='uncertain':return self._receipt(row)
            else:
                _require(db.execute('SELECT count(*) FROM operations').fetchone()[0]<MAX_OPERATIONS,'Archive completed communication receipts before continuing.')
                if channel=='email':
                    start=int(self.clock()//86400)*86400
                    count=db.execute("SELECT count(*) FROM operations WHERE channel='email' AND created>=?",(start,)).fetchone()[0]
                    _require(count<self.config.daily_send_limit,'Continue with the next company email allowance.')
                _require(current() is True)
                # Durable before wire. A crash or timeout preserves uncertainty and never repeats POST.
                db.execute('INSERT INTO operations VALUES(?,?,?,?,?,?,?,?,?,?)',
                    (operation,customer,channel,binding['conversation'],request_hash,actor,side,'uncertain',None,self.clock()))
        if row:
            # Bounded reconciliation from canonical history; absence remains uncertain.
            message=next((m for m in self._messages(client,binding) if
                (m.get('content_attributes') or {}).get('rocoto_operation')==operation and m.get('private') is False
                and m.get('message_type') in ((1,'outgoing') if side=='outgoing' else (0,'incoming'))),None)
            if message is None:return self._receipt(row)
        else:
            _require(current() is True)
            if channel=='email':_require(send_admission(context) is True)
            try:message=client.request('POST',f"/conversations/{binding['conversation']}/messages",payload=payload)
            except ChatwootHeld:
                with self._db() as db:return self._receipt(db.execute('SELECT * FROM operations WHERE operation=?',(operation,)).fetchone())
        _require(message.get('conversation_id')==binding['conversation'] and message.get('inbox_id')==binding['inbox'])
        with self._db() as db:
            db.execute('UPDATE operations SET status=?,message=? WHERE operation=?',
                (self._delivery_status(message),_id(message.get('id')),operation))
            return self._receipt(db.execute('SELECT * FROM operations WHERE operation=?',(operation,)).fetchone())

    def send_notification(self,customer,*,event,order_number,review_url,idempotency_key,actor,current,send_admission):
        """Approved deterministic templates. The caller derives event from committed business state."""
        _require(event in ('request_received','review_ready','request_confirmed'))
        number=_text(order_number,100)
        parsed=urlsplit(review_url)
        _require(parsed.scheme=='https' and parsed.hostname and not parsed.username and not parsed.password)
        _text(review_url,2048)
        templates={'request_received':'Получихме поръчка {number}. Можете да я прегледате: {url}',
            'review_ready':'Предложението за поръчка {number} е готово за преглед: {url}',
            'request_confirmed':'Потвърдихте поръчка {number}. Подробностите са тук: {url}'}
        return self.send(customer,channel='email',text=templates[event].format(number=number,url=review_url),
            idempotency_key=idempotency_key,actor=actor,current=current,send_admission=send_admission)

    def receive_webhook(self,raw,headers):
        value=verify_webhook(raw,headers,self.config.webhook_secret,now=self.clock())
        _require(self.status()['state']=='configured')
        _require((value.get('account') or {}).get('id')==self.config.account_id)
        inbox=_id((value.get('inbox') or {}).get('id'))
        _require(inbox in (self.config.email_inbox_id,self.config.service_inbox_id))
        event=value.get('event');_require(event in ('message_created','message_updated'))
        message=_id(value.get('id'));conversation=value.get('conversation') or {}
        conversation_id=_id(conversation.get('id'))
        _require(conversation.get('inbox_id')==inbox)
        # Delivery header is not signed by Chatwoot. Exact payload hash is the dedupe key.
        digest=_hash(raw)
        with self._db() as db:
            old=db.execute('SELECT result FROM webhooks WHERE hash=?',(digest,)).fetchone()
            if old:return json.loads(old['result'])
            db.execute('DELETE FROM webhooks WHERE created<?',(self.clock()-30*86400,))
            _require(db.execute('SELECT count(*) FROM webhooks').fetchone()[0]<MAX_RECEIPTS,'Review the communication receipt capacity.')
            binding=db.execute('SELECT customer,channel FROM bindings WHERE conversation=? AND inbox=?',(conversation_id,inbox)).fetchone()
            # A new email thread may use an already source-validated contact. The signed
            # sender ID can associate evidence; canonical reads still validate each thread.
            sender=(value.get('sender') or {})
            if binding is None and value.get('message_type')=='incoming' and type(sender.get('id')) is int:
                matches=db.execute('SELECT customer,channel FROM bindings WHERE contact=? AND inbox=?',
                    (sender['id'],inbox)).fetchall()
                if len(matches)==1:binding=matches[0]
            # Unbound mail is reviewed through the source-validated contact binding step.
            result={'status':'received' if binding else 'review','provider':'chatwoot','event':event,
                'provider_message_id':message,'provider_conversation_id':conversation_id,
                'customer_id':binding['customer'] if binding else None,'authority':'evidence'}
            db.execute('INSERT INTO webhooks VALUES(?,?,?,?,?,?,?)',
                (digest,event,message,conversation_id,inbox,_json(result),self.clock()))
            return result
