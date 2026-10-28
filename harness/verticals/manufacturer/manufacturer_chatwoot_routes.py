"""Private configuration, native admission and signature-first Chatwoot ingress.

The browser receives normalized history and readiness only. Chatwoot credentials
and mailbox credentials stay in server-owned mode-0600 configuration files.
"""
from dataclasses import fields
from pathlib import Path
import re
import threading
import time

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from manufacturer_chatwoot import ChatwootConfig, ChatwootHeld, ManufacturerChatwoot, MAX_BODY, verify_webhook
from registered_oauth import read_private_configuration

ENVIRONMENT = re.compile(r'[a-z0-9][a-z0-9-]{0,63}')
HOOK_PREFIX = '/hooks/manufacturer-chatwoot/'
SECRET_FIELDS = {'schema_version','company_id','environment_id','account_id','api_token','webhook_secret'}
CONFIG_FIELDS = {f.name for f in fields(ChatwootConfig)} - {'api_token','webhook_secret'}


def configuration_for(root,environment,company_id=None):
    root=Path(root);path=root/'manufacturer-chatwoot.json'
    if not path.exists() and not path.is_symlink():return None
    try:
        value=read_private_configuration(path,max_bytes=32768)
        identity=read_private_configuration(root/'.workspace-identity.json',max_bytes=32768)
        expected=identity.get('company_scope')
        if (not isinstance(value,dict) or set(value)!=CONFIG_FIELDS|{'schema_version','credentials_path'}
            or value.get('schema_version')!=1 or value.get('company_id')!=expected or not expected
            or company_id is not None and company_id!=expected or value.get('environment_id')!=environment):
            raise ValueError()
        location=value['credentials_path']
        if not isinstance(location,str) or not Path(location).is_absolute():raise ValueError()
        secret=read_private_configuration(Path(location),max_bytes=32768)
        if (not isinstance(secret,dict) or set(secret)!=SECRET_FIELDS or
            any(secret[k]!=value[k] for k in ('schema_version','company_id','environment_id','account_id'))):raise ValueError()
        return ChatwootConfig(**{k:value[k] for k in CONFIG_FIELDS},api_token=secret['api_token'],webhook_secret=secret['webhook_secret'])
    except (OSError,ValueError,TypeError,KeyError):
        raise ChatwootHeld('Review the private company communication configuration.') from None


class _ConfiguredChatwoot:
    """Re-read private commissioning before each operation, including revocation."""
    def __init__(self,selected,extension):
        self.selected,self.extension=selected,extension
        self._cached=None
        self._lock=threading.Lock()

    def _adapter(self):
        environment=self.selected.get('environment_id')
        if not isinstance(environment,str) or not ENVIRONMENT.fullmatch(environment):
            raise ChatwootHeld('Use the native company communication context.')
        company=self.extension.company_id
        config=configuration_for(self.selected['state'],environment,company)
        config=config or ChatwootConfig(company_id=company,environment_id=environment)
        with self._lock:
            if self._cached is None or self._cached.config!=config:
                self._cached=ManufacturerChatwoot(self.selected['state'],company_id=company,environment_id=environment,config=config)
            return self._cached

    def __getattr__(self,name):
        if name.startswith('_'):raise AttributeError(name)
        return getattr(self._adapter(),name)


def install_chatwoot(host,selected,extension):
    """Attach the lazy adapter. This starts no worker and sends no message."""
    if not hasattr(extension,'chatwoot'):extension.chatwoot=_ConfiguredChatwoot(selected,extension)
    return extension.chatwoot


def _existing_configuration(host,environment):
    if not ENVIRONMENT.fullmatch(environment):raise ChatwootHeld('Use the company communication route.')
    with host.access.connect() as db:
        if not db.execute('SELECT 1 FROM environments WHERE id=?',(environment,)).fetchone():
            raise ChatwootHeld('Use the company communication route.')
    root=Path(host.state) if environment=='demo' else Path(host.state)/'environments'/environment
    if root.is_symlink() or not root.is_dir():raise ChatwootHeld('Use the company communication route.')
    config=configuration_for(root,environment)
    if config is None or config.commissioned_until<=time.time():raise ChatwootHeld('Complete the communication connection.')
    return config


def register_chatwoot(app,host,*,context,invoke):
    previous_public=host.options.get('public_request',lambda request:False)
    previous_limit=host.options.get('request_body_limit',lambda request:None)
    host.options['public_request']=lambda request:bool(request.method=='POST' and
        re.fullmatch(re.escape(HOOK_PREFIX)+ENVIRONMENT.pattern,request.url.path)) or previous_public(request)
    host.options['request_body_limit']=lambda request:MAX_BODY if request.url.path.startswith(HOOK_PREFIX) else previous_limit(request)
    buckets={};lock=threading.Lock()

    @app.get('/api/manufacturer/communication/status')
    async def status(request:Request):
        actor,extension=context(request)
        invoke(extension.member,actor)
        install_chatwoot(host,extension.selected,extension)
        return JSONResponse(await run_in_threadpool(invoke,extension.chatwoot.status),headers={'Cache-Control':'private, no-store'})

    @app.post(HOOK_PREFIX+'{environment}')
    async def webhook(environment:str,request:Request):
        raw=bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw)>MAX_BODY:raise HTTPException(413,'Use a communication event up to 256 KB.')
        try:
            config=await run_in_threadpool(_existing_configuration,host,environment)
            value=verify_webhook(bytes(raw),dict(request.headers),config.webhook_secret,now=time.time())
            if ((value.get('account') or {}).get('id')!=config.account_id or
                (value.get('inbox') or {}).get('id') not in (config.email_inbox_id,config.service_inbox_id)):
                raise ChatwootHeld('Verify the event company.')
        except (ValueError,OSError,TypeError):
            raise HTTPException(403,'Verify the company communication signature.') from None
        with lock:
            minute=int(time.time()//60)
            for old in list(buckets):
                if old[1]<minute:del buckets[old]
            key=(environment,minute)
            if buckets.get(key,0)>=120:raise HTTPException(429,'Retry the communication receipt shortly.')
            buckets[key]=buckets.get(key,0)+1
        # Signature, existing environment and exact account/inbox precede workspace recovery.
        selected=host.workspace(environment);extension=selected['vertical']
        if extension.company_id!=config.company_id:raise HTTPException(403,'Verify the event company.')
        install_chatwoot(host,selected,extension)
        result=await run_in_threadpool(invoke,extension.chatwoot.receive_webhook,bytes(raw),dict(request.headers))
        return JSONResponse(result,headers={'Cache-Control':'private, no-store'})
