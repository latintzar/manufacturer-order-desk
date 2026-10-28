#!/usr/bin/env python3
"""Generate a private customer instance package. Creates files; starts no services."""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import shutil
from urllib.parse import urlsplit


def private(path,value):
    descriptor=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(descriptor,'w') as stream:stream.write(value)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--project',required=True)
    parser.add_argument('--company-id',required=True)
    parser.add_argument('--environment',default='demo')
    parser.add_argument('--public-origin',required=True)
    parser.add_argument('--callback-url',required=True)
    parser.add_argument('--operator-email',required=True)
    parser.add_argument('--email',default='')
    parser.add_argument('--port',type=int,default=3110)
    parser.add_argument('--headless-local',action='store_true',help='Use private loopback HTTP for the headless API; public-origin remains metadata.')
    args=parser.parse_args()
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{2,60}',args.project):parser.error('Use a unique lowercase Compose project name.')
    for key in ('public_origin','callback_url'):
        value=getattr(args,key);url=urlsplit(value)
        if url.scheme!='https' or not url.hostname or url.username or url.password or url.query or url.fragment or any(c in value for c in '\r\n'):
            parser.error('Use an owned HTTPS origin and callback URL.')
    if urlsplit(args.public_origin).path:parser.error('Use an origin without a path.')
    if not 1024<=args.port<=65535:parser.error('Choose a nonprivileged local port.')
    for email in (args.operator_email,args.email):
        if email and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):parser.error('Use a complete company email address.')
    args.out.mkdir(mode=0o700,parents=True,exist_ok=False)
    (args.out/'operator').mkdir(mode=0o700)
    source=Path(__file__).resolve().parent
    shutil.copyfile(source/'compose.yaml',args.out/'compose.yaml')
    shutil.copyfile(source/'bootstrap.rb',args.out/'operator'/'bootstrap.rb')
    env={
        'CHATWOOT_PROJECT':args.project,'CHATWOOT_PORT':str(args.port),'FRONTEND_URL':args.public_origin,
        'FORCE_SSL':'false' if args.headless_local else 'true','SECRET_KEY_BASE':secrets.token_hex(64),'POSTGRES_PASSWORD':secrets.token_hex(32),
        'REDIS_PASSWORD':secrets.token_hex(32),'MAILER_SENDER_EMAIL':args.operator_email,
        'ACTIVE_RECORD_ENCRYPTION_PRIMARY_KEY':secrets.token_hex(32),
        'ACTIVE_RECORD_ENCRYPTION_DETERMINISTIC_KEY':secrets.token_hex(32),
        'ACTIVE_RECORD_ENCRYPTION_KEY_DERIVATION_SALT':secrets.token_hex(32),
    }
    private(args.out/'.env',''.join(k+'='+v+'\n' for k,v in env.items()))
    bootstrap={'company_id':args.company_id,'environment_id':args.environment,'name':args.project,
        'operator_email':args.operator_email,'operator_password':secrets.token_urlsafe(36),
        'callback_url':args.callback_url,'email':args.email,'origin':('http://127.0.0.1:'+str(args.port)) if args.headless_local else args.public_origin}
    private(args.out/'operator'/'bootstrap-input.json',json.dumps(bootstrap,indent=2)+'\n')
    print('Private instance package created: '+str(args.out.resolve()))


if __name__=='__main__':main()
