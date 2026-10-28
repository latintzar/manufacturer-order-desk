#!/usr/bin/env python3
"""Run the actual order service and native workspace with an isolated authored sample."""
from pathlib import Path
import argparse,json,os,signal,stat,subprocess,sys,time,urllib.request
ROOT=Path(__file__).resolve().parents[1]
def private_json(path):
 s=path.lstat()
 if not stat.S_ISREG(s.st_mode) or s.st_uid!=os.getuid() or s.st_nlink!=1 or s.st_mode&0o077:raise ValueError('Use an owner-only local state file.')
 return json.loads(path.read_text())
def environment():
 return {k:v for k,v in os.environ.items() if k in {'PATH','LANG','LC_ALL','TMPDIR','SSL_CERT_FILE','SSL_CERT_DIR'}}|{'PYTHONUNBUFFERED':'1','ROCOTO_VERTICAL':'manufacturer','ROCOTO_BROWSE_SESSIONS':'false'}
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--state',type=Path,default=ROOT/'.local/first-result');p.add_argument('--workspace-port',type=int,default=18580);p.add_argument('--orders-port',type=int,default=18581);p.add_argument('--internal',choices=['orders','workspace'],help=argparse.SUPPRESS);a=p.parse_args()
 if a.orders_port==a.workspace_port or not all(1024<=n<=65535 for n in [a.orders_port,a.workspace_port]):p.error('Choose two different unprivileged local ports.')
 state=a.state.expanduser().absolute()
 if state.is_symlink():raise ValueError('Choose an owned local state directory.')
 if a.internal:
  receipt=private_json(state/'receipt.json');keys=private_json(state/'local-credentials.json');own_env=environment();own_env['MANUFACTURER_ORDERS_ORIGIN']=f'http://127.0.0.1:{a.orders_port}';os.environ.clear();os.environ.update(own_env)
  import offline;offline.install()
  try:
   if a.internal=='orders':
    sys.path.insert(0,str(ROOT/'app/src/prototypes/orders'));import serve,configurator_versions
    bridge=configurator_versions.Bridge(Path(receipt['orders_state']),token=keys['orders_token'],company=receipt['company'],scope=keys['company_scope'])
    httpd=serve.server(Path(receipt['public']),a.orders_port,Path(receipt['orders_state']),bridge=bridge)
    def stop(*_):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,stop)
    try:httpd.serve_forever()
    except KeyboardInterrupt:pass
    finally:httpd.server_close()
   else:
    os.environ['ROCOTO_MANUFACTURER_ORDERS_TOKEN']=keys['orders_token'];sys.path.insert(0,str(ROOT/'harness'));import layout;layout.install('manufacturer');import server,uvicorn
    uvicorn.run(server.create_app(Path(receipt['workspace'])),host='127.0.0.1',port=a.workspace_port,access_log=False)
  finally:(state/('network-'+a.internal+'.json')).write_text(json.dumps(offline.counts(),indent=2)+'\n')
  return
 # All inherited provider/state settings are excluded from sample construction and child runtimes.
 own_env=environment();os.environ.clear();os.environ.update(own_env)
 import offline;offline.install()
 from sample_build import build
 receipt=build(state)
 logs=state/'logs';logs.mkdir(mode=0o700,exist_ok=True);children=[];handles=[]
 try:
  for kind in ['orders','workspace']:
   log=(logs/(kind+'.log')).open('ab');handles.append(log)
   children.append(subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--internal',kind,'--state',str(state),'--workspace-port',str(a.workspace_port),'--orders-port',str(a.orders_port)],env=own_env,stdout=log,stderr=log))
   port=a.orders_port if kind=='orders' else a.workspace_port
   for _ in range(200):
    if children[-1].poll() is not None:raise RuntimeError(f'Check the private {kind} log in {logs}.')
    try:
     with urllib.request.urlopen(f'http://127.0.0.1:{port}/'+(receipt['company']+'/' if kind=='orders' else ''),timeout=1):break
    except OSError:time.sleep(.1)
   else:raise RuntimeError(f'Check the private {kind} log in {logs}.')
  print(f'Workspace editor: http://127.0.0.1:{a.workspace_port}/?operator=1',flush=True)
  print(f'Configurator: http://127.0.0.1:{a.orders_port}/{receipt["company"]}/#order',flush=True)
  print(f'Sign-in code file: {receipt["code_file"]}',flush=True)
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
