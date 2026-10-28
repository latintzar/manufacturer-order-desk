#!/usr/bin/env python3
"""Serve one recipient-owned process with explicit state and private credentials."""
from pathlib import Path
import argparse,json,os,sys
import private
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--role',choices=['orders','workspace'],required=True);p.add_argument('--state',type=Path,required=True);p.add_argument('--port',type=int,required=True);p.add_argument('--keys-directory',type=Path,default=private.DEFAULT);p.add_argument('--orders-origin',required=True);p.add_argument('--public-origin');p.add_argument('--public-directory',type=Path);p.add_argument('--company');p.add_argument('--company-scope');p.add_argument('--enable-managed-agents',action='store_true');a=p.parse_args()
 if not a.state.is_absolute() or a.state.is_symlink() or not 1024<=a.port<=65535:p.error('Choose an absolute owned state path and an unprivileged local port.')
 a.state.mkdir(parents=True,exist_ok=True,mode=0o700)
 if a.state.stat().st_uid!=os.getuid():raise ValueError('Use recipient-owned runtime state.')
 values=private.read(a.keys_directory);env={k:v for k,v in os.environ.items() if k in {'PATH','LANG','LC_ALL','TMPDIR','SSL_CERT_FILE','SSL_CERT_DIR'}};env.update(MANUFACTURER_ORDERS_ORIGIN=a.orders_origin,ROCOTO_VERTICAL='manufacturer',ROCOTO_BROWSE_SESSIONS='false');os.environ.clear();os.environ.update(env)
 if a.role=='workspace':
  for k in ['ROCOTO_MANUFACTURER_ORDERS_TOKEN','ROCOTO_OPENAI_API_KEY']:
   if k in values:os.environ[k]=values[k]
  if a.public_origin:os.environ['ROCOTO_PUBLIC_ORIGIN']=a.public_origin
  if a.enable_managed_agents:os.environ['ROCOTO_AGENT_AUTH_MODE']='openai_api'
  sys.path.insert(0,str(ROOT/'harness'));import layout;layout.install('manufacturer');import server,uvicorn
  uvicorn.run(server.create_app(a.state),host='127.0.0.1',port=a.port,access_log=False)
 else:
  if not a.public_directory or not a.public_directory.is_dir() or not a.company or not a.company_scope:p.error('The Orders role needs its built public directory, company slug and workspace scope.')
  sys.path.insert(0,str(ROOT/'app/src/prototypes/orders'));import serve as order_server,configurator_versions
  bridge=configurator_versions.Bridge(a.state,token=values.get('ROCOTO_ORDERS_CONFIGURATOR_TOKEN',''),company=a.company,scope=a.company_scope)
  httpd=order_server.server(a.public_directory,a.port,a.state,bridge=bridge)
  try:httpd.serve_forever()
  except KeyboardInterrupt:pass
  finally:httpd.server_close()
if __name__=='__main__':main()
