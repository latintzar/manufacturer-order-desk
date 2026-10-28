#!/usr/bin/env python3
"""Bind one recipient workspace to its own Orders service."""
from pathlib import Path
import argparse,json,os,sys
import private
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workspace-state',type=Path,required=True);p.add_argument('--company',required=True);p.add_argument('--keys-directory',type=Path,default=private.DEFAULT);a=p.parse_args()
 state=a.workspace_state
 if not state.is_absolute() or state.is_symlink():p.error('Choose an absolute owned workspace state directory.')
 state.mkdir(parents=True,exist_ok=True,mode=0o700)
 if state.stat().st_uid!=os.getuid():raise ValueError('Use recipient-owned state.')
 import re
 if not re.fullmatch(r'[a-z][a-z0-9-]{1,40}',a.company):p.error('Choose the company slug used by its Orders database.')
 keys=private.read(a.keys_directory)
 if len(keys.get('ROCOTO_MANUFACTURER_ORDERS_TOKEN',''))<32:raise ValueError('Generate the private Orders token first with configure.py.')
 sys.path.insert(0,str(ROOT/'harness'));import layout;layout.install('manufacturer');from workspace_identity import workspace_scope
 scope=workspace_scope(state);target=state/'manufacturer-source.json'
 if target.exists() and (target.is_symlink() or target.stat().st_uid!=os.getuid() or target.stat().st_nlink!=1):raise ValueError('Use an owned source binding.')
 value={'company_id':scope,'company_slug':a.company,'transport':'orders-api'}
 fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'w') as f:json.dump(value,f,indent=2);f.write('\n')
 target.chmod(0o600);print(json.dumps({'company':a.company,'company_scope':scope,'binding_file':str(target)}))
if __name__=='__main__':main()
