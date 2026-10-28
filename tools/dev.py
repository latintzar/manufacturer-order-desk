#!/usr/bin/env python3
"""Run the actual order service and native workspace with an isolated authored sample."""
from pathlib import Path
import argparse,json,os,signal,stat,subprocess,sys,tempfile,time,urllib.request
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parents[1]
def private_json(path):
 s=path.lstat()
 if not stat.S_ISREG(s.st_mode) or s.st_uid!=os.getuid() or s.st_nlink!=1 or s.st_mode&0o077:raise ValueError('Use an owner-only local state file.')
 return json.loads(path.read_text())
def environment(state=None,guest=False,public_origin=''):
 env={k:v for k,v in os.environ.items() if k in {'PATH','LANG','LC_ALL','TMPDIR','SSL_CERT_FILE','SSL_CERT_DIR'}}
 env.update(PYTHONUNBUFFERED='1',PYTHONDONTWRITEBYTECODE='1',ROCOTO_VERTICAL='manufacturer',ROCOTO_BROWSE_SESSIONS='true' if guest else 'false',ROCOTO_AUTO_BROWSE='true' if guest else 'false',ROCOTO_READ_ONLY='true' if guest else 'false')
 if guest:env['ROCOTO_SESSION_COOKIE']='manufacturer_session'
 if public_origin:env['ROCOTO_PUBLIC_ORIGIN']=public_origin
 if state is not None:
  home=Path(state)/'home';home.mkdir(mode=0o700,parents=True,exist_ok=True);home.chmod(0o700)
  env.update(HOME=str(home),XDG_CONFIG_HOME=str(home/'.config'),XDG_CACHE_HOME=str(home/'.cache'),XDG_DATA_HOME=str(home/'.local/share'))
 return env

def main():
 os.umask(0o077)
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--state',type=Path,default=ROOT/'.local/first-result');p.add_argument('--workspace-port',type=int,default=18580);p.add_argument('--orders-port',type=int,default=18581);p.add_argument('--base-path',default='',help='Application mount, such as /apps/manufacturer-order-desk/');p.add_argument('--guest',action='store_true',help='Enter through the native read-only visitor membership');p.add_argument('--public-origin',default='',help='Exact recipient HTTPS origin');p.add_argument('--internal',choices=['orders','workspace'],help=argparse.SUPPRESS);a=p.parse_args()
 sys.path.insert(0,str(ROOT/'harness/mechanics'));from web_mount import base_path
 try:a.base_path=base_path(a.base_path)
 except ValueError as error:p.error(str(error))
 if a.public_origin:
  u=urlsplit(a.public_origin)
  if u.scheme!='https' or not u.hostname or u.username or u.password or u.path not in {'','/'} or u.query or u.fragment:p.error('Use the exact recipient HTTPS origin.')
  a.public_origin=a.public_origin.rstrip('/')
 if a.orders_port==a.workspace_port or not all(1024<=n<=65535 for n in [a.orders_port,a.workspace_port]):p.error('Choose two different unprivileged local ports.')
 state=a.state.expanduser().absolute()
 if state.is_symlink():raise ValueError('Choose an owned local state directory.')
 # The home is created only after the seed, whose empty-directory contract remains unchanged.
 if a.internal:
  receipt=private_json(state/'receipt.json');keys=private_json(state/'local-credentials.json');own_env=environment(state,a.guest,a.public_origin);own_env['MANUFACTURER_ORDERS_ORIGIN']=f'http://127.0.0.1:{a.orders_port}';os.environ.clear();os.environ.update(own_env)
  import offline;offline.install()
  def stop(*_):raise KeyboardInterrupt
  signal.signal(signal.SIGTERM,stop)
  try:
   if a.internal=='orders':
    sys.path.insert(0,str(ROOT/'app/src/prototypes/orders'));import serve,configurator_versions
    bridge=configurator_versions.Bridge(Path(receipt['orders_state']),token=keys['orders_token'],company=receipt['company'],scope=keys['company_scope'])
    httpd=serve.server(Path(receipt['public']),a.orders_port,Path(receipt['orders_state']),bridge=bridge)
    try:httpd.serve_forever()
    except KeyboardInterrupt:pass
    finally:httpd.server_close()
   else:
    os.environ['ROCOTO_MANUFACTURER_ORDERS_TOKEN']=keys['orders_token'];sys.path.insert(0,str(ROOT/'harness'));import layout;layout.install('manufacturer');import server,uvicorn
    from web_mount import MountedApp
    app=MountedApp(server.create_app(Path(receipt['workspace'])),prefix=a.base_path,orders_origin=own_env['MANUFACTURER_ORDERS_ORIGIN'],company=receipt['company'],read_only=a.guest,public_origin=a.public_origin)
    try:uvicorn.run(app,host='127.0.0.1',port=a.workspace_port,access_log=False)
    except KeyboardInterrupt:pass
  finally:(state/('network-'+a.internal+'.json')).write_text(json.dumps(offline.counts(),indent=2)+'\n')
  return
 own_env=environment(guest=a.guest,public_origin=a.public_origin);os.environ.clear();os.environ.update(own_env)
 import offline;offline.install()
 from sample_build import build
 with tempfile.TemporaryDirectory(prefix='manufacturer-bootstrap-') as bootstrap:
  os.environ.update(HOME=bootstrap,XDG_CONFIG_HOME=bootstrap+'/.config',XDG_CACHE_HOME=bootstrap+'/.cache',XDG_DATA_HOME=bootstrap+'/.local/share')
  receipt=build(state)
 own_env=environment(state,a.guest,a.public_origin);os.environ.clear();os.environ.update(own_env)
 logs=state/'logs';logs.mkdir(mode=0o700,exist_ok=True);children=[];handles=[]
 try:
  for kind in ['orders','workspace']:
   log=(logs/(kind+'.log')).open('ab');handles.append(log)
   command=[sys.executable,str(Path(__file__).resolve()),'--internal',kind,'--state',str(state),'--workspace-port',str(a.workspace_port),'--orders-port',str(a.orders_port),'--base-path',a.base_path]
   if a.guest:command.append('--guest')
   if a.public_origin:command.extend(['--public-origin',a.public_origin])
   children.append(subprocess.Popen(command,env=own_env,stdout=log,stderr=log))
   port=a.orders_port if kind=='orders' else a.workspace_port;path='/'+receipt['company']+'/' if kind=='orders' else a.base_path+'/'
   for _ in range(200):
    if children[-1].poll() is not None:raise RuntimeError(f'Check the private {kind} log in {logs}.')
    try:
     with urllib.request.urlopen(f'http://127.0.0.1:{port}'+path,timeout=1):break
    except OSError:time.sleep(.1)
   else:raise RuntimeError(f'Check the private {kind} log in {logs}.')
  print(f'Workspace: http://127.0.0.1:{a.workspace_port}{a.base_path}/'+('' if a.guest else '?operator=1'),flush=True)
  print(f'Configurator: http://127.0.0.1:{a.workspace_port}{a.base_path}/orders/{receipt["company"]}/#order',flush=True)
  print(f'Owner sign-in code file: {receipt["code_file"]}',flush=True)
  print('Sample data is saved in '+str(state),flush=True)
  def stop(*_):raise KeyboardInterrupt
  signal.signal(signal.SIGTERM,stop)
  while all(c.poll() is None for c in children):time.sleep(.25)
 except KeyboardInterrupt:pass
 finally:
  for c in children:
   if c.poll() is None:c.terminate()
  for c in children:
   try:c.wait(timeout=15)
   except subprocess.TimeoutExpired:c.kill();c.wait()
  for h in handles:h.close()
  (state/'network-parent.json').write_text(json.dumps(offline.counts(),indent=2)+'\n')
if __name__=='__main__':main()
