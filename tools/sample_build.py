"""Create an owned sample manufacturer using the real Orders store and widget bundle."""
from pathlib import Path
import json,os,sys,shutil,secrets

ROOT=Path(__file__).resolve().parents[1]
ORDERS=ROOT/'app/src/prototypes/orders'
SLUG='sample-hardware'

def build(state):
 state=Path(state).absolute();state.mkdir(parents=True,exist_ok=True,mode=0o700)
 marker=state/'.manufacturer-first-result'
 if marker.exists():
  receipt=json.loads((state/'receipt.json').read_text())
  # Reopening retained sample data gives the local owner a fresh one-use code.
  sys.path.insert(0,str(ROOT/'harness'));import layout;layout.install('manufacturer')
  from access import AccessStore
  code=AccessStore(Path(receipt['workspace'])).issue('demo',owner=True,principal_id='sample-owner')
  code_file=Path(receipt['code_file']);code_file.write_text(code+'\n');code_file.chmod(0o600)
  return receipt
 if any(state.iterdir()):raise ValueError('Use an empty owned first-result directory.')
 marker.write_text('Authored local sample. No external accounts or customer records.\n');marker.chmod(0o600)
 cache=state/'cache';os.environ['ROCOTO_ORDERS_CACHE']=str(cache)
 sys.path.insert(0,str(ORDERS))
 from store import CompanyStore
 from quote import quote
 from pipeline import bundle
 config={
  'slug':SLUG,'name':{'en':'Sample Hardware'},'source':'https://sample-hardware.example.test/',
  'priceList':{'url':'https://sample-hardware.example.test/catalogue','path':'catalogue'},
  'currency':'EUR','vat':.2,'languages':['en'],'defaultLanguage':'en','home':{'en':'index.html'},
  'accent':'#a34e2e','logo':'/rocoto/sample/lever.webp','orderPrefix':'SH','delivery':0,'hours':{'1':[540,1020,960],'2':[540,1020,960],'3':[540,1020,960],'4':[540,1020,960],'5':[540,1020,960]},
  'shop':{'backlog':0},'strings':{'en':{'pickup':'Collect from the workshop','pickSub':'Sample Hardware','pickAddr':'Example workshop','delFee':'Delivery on confirmation','search':'Search {n} articles','sizes':'{n} articles','addSize':'Add an article','basketEmpty':'Your selected articles appear here.','tryQ':['lever','latch','cylinder'],'noRes':'Search by part name or article code.','preview':'made by atelier neyra','launch':'Order door hardware','empty':'Add an article to start your order.','customD':'Describe the parts and quantities you need.','customPh':'For example: six satin lever sets for interior doors.','contactSub':'Your request is saved for the sales team.','submitNote':'The sales team reviews your request.','donePrev':'Your request is saved for review.','doneLive':'Your request is saved for review.','doneCopy':'Your request is saved.','doneNext':'Open the workspace to review it.','estNote':'Delivery is confirmed during review.','byMail':'Confirmed during review','st2s':'The team reviews availability and price.'}},
  'headline':'Order door hardware','description':'Choose products and send your requirements.','button_label':'Start order',
  'checkout':{'companyRequired':True,'agentEditing':False,'customerResearch':False,'warehouses':[{'id':'workshop','name':'Main workshop','erpCode':'DEMO'}]},
  'questionnaire':{'id':'sample-hardware','title':{'en':'Choose door hardware'},'questions':[
   {'id':'family','kind':'single','title':{'en':'Which part do you need?'},'unsure':True,'options':[
    {'id':'levers','label':{'en':'Lever sets'},'match':{'family':['lever']}},
    {'id':'latches','label':{'en':'Latches'},'match':{'family':['latch']}},
    {'id':'cylinders','label':{'en':'Cylinders'},'match':{'family':['cylinder']}}]},
   {'id':'finish','kind':'single','title':{'en':'Which finish?'},'unsure':True,'options':[
    {'id':'satin','label':{'en':'Satin'},'match':{'finish':['satin']}},
    {'id':'black','label':{'en':'Black'},'match':{'finish':['black']}}]}]},
  'theme':{},'texts':{},'assets':[]}
 catalogue={'company':config['name'],'source':config['source'],'asOf':'2026-10-28','currency':'EUR','vat':.2,'forms':[{'id':'door','en':'Door hardware','bg':'Door hardware'}],'metals':[{'id':'hardware','en':'Hardware','bg':'Hardware'}],'services':[],'cats':[]}
 for family,title,prefix,price in [('lever','Lever sets','LV',24),('latch','Latches','LT',16),('cylinder','Cylinders','CY',0)]:
  items=[]
  for index,finish in enumerate(['satin','black'],1):
   items.append({'c':f'SH-{prefix}-{index:02}','s':f'{dict(lever='Lever set',latch='Latch',cylinder='Cylinder')[family]} · {finish}','se':f'{dict(lever='Lever set',latch='Latch',cylinder='Cylinder')[family]} · {finish}','u':'pc','p':price,'q':family=='cylinder','r':{'k':'whole'},'minimum':1,'step':1,'pack':1,'a':{'family':family,'finish':finish,'size':'standard'},'img':f'/{SLUG}/rocoto/sample/{family}.webp'})
  catalogue['cats'].append({'code':prefix,'en':title,'bg':title,'metal':'hardware','form':'door','shape':'special','mat':'hardware','img':f'/{SLUG}/rocoto/sample/{family}.webp','a':{'family':family},'items':items})
 orders_state=state/'orders';database=orders_state/'companies'/SLUG/'company.db';database.parent.mkdir(parents=True)
 store=CompanyStore(database);store.ingest_catalog(catalogue,config,actor='sample-author',evidence='Authored sample fixture, 2026-10-28')
 created=[]
 for i,(company,codes) in enumerate([('Example Joinery',[('SH-LV-01',6),('SH-LT-01',6)]),('Example Facilities',[('SH-CY-02',12)])],1):
  requested=[{'code':code,'rows':[{'x':0,'n':qty}]} for code,qty in codes];priced=quote(catalogue,requested);priced['quote']['fulfilment']='pickup'
  customer={'name':f'Sample buyer {i}','company':company,'email':f'buyer{i}@example.test','language':'en','is_demo':True,'warehouseId':'workshop','warehouseName':'Main workshop','warehouseErpCode':'DEMO','warehouseConfirmed':True,'project':('Interior doors' if i==1 else 'Maintenance stock')}
  result=store.submit_order(customer,priced['lines'],priced['quote'],f'authored-sample-order-{i:02}',actor='sample-author',evidence='Authored sample fixture, 2026-10-28');created.append(result['id'])
 store.close()
 public=state/'public';folder=public/SLUG/'rocoto';folder.mkdir(parents=True)
 bundle.three();shutil.copyfile(bundle.three(),folder/'three.min.js');shutil.copyfile(ROOT/'app/public/inter.woff2',folder/'inter.woff2')
 (folder/'sample').mkdir();
 for image in (ROOT/'fixtures/sample-hardware/images').glob('*.webp'):shutil.copyfile(image,folder/'sample'/image.name)
 (folder/'g').mkdir();(folder/'g/index.json').write_text('{"sets":{},"items":{},"variantTypes":[]}\n')
 (folder/'catalog.json').write_text(json.dumps(catalogue,ensure_ascii=False));(folder/'configuration.json').write_text(json.dumps(config,ensure_ascii=False))
 (folder/'site.json').write_text(json.dumps({'slug':SLUG,'name':config['name'],'source':config['source'],'languages':['en'],'geo':{}}))
 (folder/'configurator.js').write_text(bundle.bundle(config));(folder/'embed.html').write_text('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Order door hardware</title><script src="configurator.js" defer></script>')
 (public/SLUG/'index.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Sample Hardware</title><style>body{margin:0;padding:48px;font:16px system-ui;background:#f4efe7;color:#29271f}h1{font-size:48px;letter-spacing:-2px}a{color:inherit}footer{margin-top:64px;font-size:12px}</style><h1>Door hardware</h1><p>Sample Hardware</p><a href="#order">Open the configurator</a><footer><a href="https://atelierneyra.com">made by atelier neyra</a></footer><script src="rocoto/configurator.js" defer></script></html>')
 workspace=state/'workspace';workspace.mkdir()
 sys.path.insert(0,str(ROOT/'harness'));import layout;layout.install('manufacturer')
 from workspace_identity import workspace_scope
 from access import AccessStore
 scope=workspace_scope(workspace)
 key=secrets.token_urlsafe(32)
 binding={'company_id':scope,'company_slug':SLUG,'transport':'orders-api'}
 (workspace/'manufacturer-source.json').write_text(json.dumps(binding));(workspace/'manufacturer-source.json').chmod(0o600)
 credentials={'orders_token':key,'company_scope':scope};(state/'local-credentials.json').write_text(json.dumps(credentials));(state/'local-credentials.json').chmod(0o600)
 access=AccessStore(workspace);code=access.issue('demo',owner=True,principal_id='sample-owner');code_file=state/'owner-code.txt';code_file.write_text(code+'\n');code_file.chmod(0o600)
 receipt={'synthetic':True,'company':SLUG,'catalogue_types':3,'articles':6,'sample_orders':len(created),'state':str(state),'public':str(public),'orders_state':str(orders_state),'workspace':str(workspace),'code_file':str(code_file),'external_provider_configuration':'held by the local first-result launcher'}
 (state/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');(state/'receipt.json').chmod(0o600)
 return receipt

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--state',type=Path,required=True);a=p.parse_args();print(json.dumps(build(a.state)))
