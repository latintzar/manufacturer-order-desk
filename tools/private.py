"""Recipient-owned private settings; credential values stay outside source and stdout."""
from pathlib import Path
import json,os,stat,tempfile
SCHEMA='manufacturer.private-credentials.v1'
DEFAULT=Path.home()/'.config/manufacturer-order-desk'
ALLOWED={'ROCOTO_OPENAI_API_KEY','ROCOTO_MANUFACTURER_ORDERS_TOKEN','ROCOTO_ORDERS_CONFIGURATOR_TOKEN'}
def directory(path):
 p=Path(path).expanduser().absolute()
 if p.is_symlink():raise ValueError('Use an owned private configuration directory.')
 p.mkdir(parents=True,exist_ok=True,mode=0o700);s=p.stat()
 if s.st_uid!=os.getuid() or not stat.S_ISDIR(s.st_mode):raise ValueError('Use an owned private configuration directory.')
 p.chmod(0o700);return p
def read(path):
 p=directory(path)/'credentials.json'
 if p.is_symlink():raise ValueError('Use an owner-only regular credentials file.')
 if not p.exists():return {}
 s=p.lstat()
 if not stat.S_ISREG(s.st_mode) or s.st_uid!=os.getuid() or s.st_nlink!=1 or s.st_mode&0o077 or s.st_size>65536:raise ValueError('Use the owner-only credentials file.')
 j=json.loads(p.read_text());values=j.get('values',{})
 if j.get('schema')!=SCHEMA or not isinstance(values,dict) or set(values)-ALLOWED or any(not isinstance(v,str) for v in values.values()):raise ValueError('Use the manufacturer credential schema.')
 return values
def write(path,values):
 p=directory(path);target=p/'credentials.json'
 if target.exists():read(p)
 fd,temp=tempfile.mkstemp(prefix='.credentials-',dir=p)
 try:
  os.fchmod(fd,0o600)
  with os.fdopen(fd,'w') as f:json.dump({'schema':SCHEMA,'values':values},f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
  os.replace(temp,target)
 finally:
  if Path(temp).exists():Path(temp).unlink()
 return target
