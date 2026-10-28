#!/usr/bin/env python3
"""Save recipient keys through hidden terminal input."""
import argparse,getpass,secrets
from pathlib import Path
import private

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,default=private.DEFAULT);g=p.add_mutually_exclusive_group(required=True);g.add_argument('--openai',action='store_true');g.add_argument('--generate-orders-token',action='store_true');a=p.parse_args();values=private.read(a.directory)
 if a.openai:
  key=getpass.getpass('Your OpenAI project key: ').strip()
  if len(key)<16 or len(key)>16384 or any(c.isspace() for c in key):raise ValueError('Enter the complete project key.')
  values['ROCOTO_OPENAI_API_KEY']=key
 else:
  key=secrets.token_urlsafe(32);values['ROCOTO_MANUFACTURER_ORDERS_TOKEN']=key;values['ROCOTO_ORDERS_CONFIGURATOR_TOKEN']=key
 path=private.write(a.directory,values);print('Saved owner-only settings: '+str(path))
if __name__=='__main__':main()
