/* Rocoto order widget UI. The flow is a delivery-app menu: search or scroll the menu, open a product, set its
   options, add to basket; the basket stays on the right. One shadow root keeps the host site's styles out and ours in.
   Needs RocotoCore, RocotoPricing and RocotoGeom; product pictures are path-traced stills made at build time. Menu, sticky section tabs, item page and basket panel follow the
   Sancho storefront (ShopExperience, ProductRow, ItemDetail, BasketPanel). */
(function(){
'use strict';
const K=window.RocotoCore,P=window.RocotoPricing,t=K.t,C=K.C,X=K.X;
const CFG=Object.assign({base:'/rocoto/',logo:'',accent:'var(--accent)',key:'rocoto-basket-v1',preview:true,delivery:null},window.RocotoConfig||{});
const ICON=__ICONS__,CSS=__CSS__;
const ic=(n,s,w)=>'<svg class="i" width="'+(s||18)+'" height="'+(s||18)+'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="'+(w||1.75)+'" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+ICON[n]+'</svg>';
const U={
 en:{go:'Start order',yourBasket:'Your basket',empty:'Add a size to start your order.',goCheckout:'Go to checkout',viewBasket:'View basket',
  segPick:'Pickup',segDel:'Delivery',pickAddr:'',delSub:'By our truck to your address',
  range:'{n} sizes · {a} to {b}',one:'{n} sizes · {a}',fromW:'from',perM:'/m',perSheet:'/sheet',each:'each',results:'Results for “{q}”',
  examples:'Show examples',exNote:'Photo from {v}.',fit:'Best fit',truth:'Actual size',calib:'Calibrate',calText:'Hold a bank card to the screen and drag until the outline matches it.',calDone:'Done',back:'Back to the menu',
  cutType:'Cut',straight:'Straight cut',angleCut:'Angle cut',perCut:'{v} per cut',perCutU:'per cut',details:'Price details',ofVat:'of which VAT 20%',short:'Add',
  soldLen:'Sold in {v} m',soldAny:'Sold by the centimetre',soldStrip:'Sold as {w} mm strips of any length',soldHalf:'Sold as half or whole sheets',soldWhole:'Sold whole',
  upTo:'up to {v} mm',fixed:'Length set to {v} mm, the longest piece we sell.',surBar:'Part-length surcharge',surSheet:'Strip surcharge, 20%',pcs:'{n} × {v}',
  sections:'Menu sections',clear:'Clear search',menu:'Menu',delFee:'Delivery',
  est:'Ready {when}',estDel:'Delivery {when}',estNote:'Estimated. {c} confirms the time by e-mail.',byMail:'Time confirmed by e-mail',delAt:'Address at checkout',sumL:'Summary',listNote:'Published catalogue prices',detailsL:'Details',each2:'{v} mm each',
  estShort:'estimated ready {when}',thisM:'this morning',thisA:'this afternoon',tomM:'tomorrow morning',tomA:'tomorrow afternoon',dayM:'{d} morning',dayA:'{d} afternoon',
  contactSub:'Your order and every update arrive at this address, with the {c} sales team in copy.',optional:'optional',
  submit:'Submit order',submitNote:'{c} confirms your date by email, then sends your invoice.',needEmail:'Enter your e-mail to receive the order.',needPhone:'Enter a phone number for the sales team.',
  doneT:'Your order is submitted',doneLive:'A copy is on its way to {e}, with the {c} sales team in copy.',donePrev:'This preview ends here. Live, a copy goes to {e} with the {c} sales team in copy.',
  st1:'Submitted',st1s:'Order {n}',st2:'Accepted by {c}',st2s:'Your confirmed date and invoice arrive by email.',st3p:'Ready to collect',st3d:'On its way to you',st3s:'Estimated {when}.',
  again:'New order',backSite:'Back to the site',orderNo:'Order {n}',
  qEmail:'Your e-mail',qReceive:'Pickup or delivery',qAddress:'Delivery address',addrPh:'Street, number, town',qInvoice:'Invoice',invP:'A name on the invoice',invC:'Company name, EIK and VAT number',
  prev:'Back',qPhone:'Phone for the sales team',phoneSub:'{c} calls about this order.',next:'Continue',needName:'Enter the name for the invoice.',needCo:'Enter the company name and its EIK.',needAddr:'Choose the delivery address.',change:'Change',
  doneCopy:'A copy of your order is on its way to {e}.',doneNext:'You get an e-mail as soon as our team confirms the order.',listL:'Price list',listV:'of {v}',
  line1:'Address',line2:'Floor, entrance, a note for the driver',bline2:'Address, second line',zip:'Postcode',invName:'Name on the invoice',addCo:'Invoice for a company',coAddr:'Company address',billSame:'Company address: the delivery address.',billOther:'Use another address',infoL:'Information',
  perKg:'/kg',kgU:'kg',onConf:'On confirmation',askT:'Price on confirmation',askSub:'{c} confirms the price and the ready time by e-mail.',stdL:'Standard',
  customT:'Custom request',customD:'Another size, grade or processing: describe it and {c} confirms the price and the ready time.',customPh:'For example: 12 plates 300 × 200 × 8, S355, with four 14 mm holes each',customHead:'Your request',needText:'Describe what you need.',
  incl:'incl. VAT',excl:'excl. VAT',prices:'Prices',totalEx:'Total excl. VAT',totalIn:'Total incl. VAT',found:'{n} results',crumbs:['Basket','Details','Submitted'],shortSub:'Submit',lines1:'1 line',linesN:'{n} lines',
  estL:'Estimated ready',estDL:'Estimated delivery',soldL:'Sold in',weightL:'Weight',codeL:'Code',kgm:'kg/m',kgs:'kg',
  vStrip:'Strips {w} mm wide',vHalf:'Half or whole sheets',vWhole:'Whole pieces',vAny:'Any length'},
 bg:{go:'Започни поръчка',yourBasket:'Вашата количка',empty:'Добавете размер, за да започнете поръчката.',goCheckout:'Към поръчка',viewBasket:'Виж количката',
  segPick:'Вземане',segDel:'Доставка',pickAddr:'',delSub:'С наш камион до вашия адрес',
  range:'{n} размера · {a} до {b}',one:'{n} размер · {a}',fromW:'от',perM:'/м',perSheet:'/лист',each:'/бр.',results:'Резултати за „{q}”',
  examples:'Покажи примери',exNote:'Снимка от {v}.',fit:'Близък план',truth:'Реален размер',calib:'Калибрирай',calText:'Допрете банкова карта до екрана и плъзнете, докато контурът съвпадне с нея.',calDone:'Готово',back:'Към менюто',
  cutType:'Рязане',straight:'Право рязане',angleCut:'Рязане под ъгъл',perCut:'{v} на срез',perCutU:'на срез',details:'Разбивка на цената',ofVat:'в т.ч. ДДС 20%',short:'Добави',
  soldLen:'Продава се на {v} м',soldAny:'Продава се на сантиметър',soldStrip:'Продава се на ленти с ширина {w} мм и произволна дължина',soldHalf:'Продава се на половин или цял лист',soldWhole:'Продава се цяло',
  upTo:'до {v} мм',fixed:'Дължината е {v} мм. Това е най-дългото парче, което предлагаме.',surBar:'Надценка за част от дължина',surSheet:'Надценка за лента, 20%',pcs:'{n} × {v}',
  sections:'Раздели на менюто',clear:'Изчисти търсенето',menu:'Меню',delFee:'Доставка',
  est:'Готовност: {when}',estDel:'Доставка: {when}',estNote:'Ориентировъчно. {c} потвърждава срока по имейл.',byMail:'Срокът се потвърждава по имейл',delAt:'Адресът се въвежда при поръчката',sumL:'Обобщение',listNote:'Цени от сайта; потвърждават се с поръчката',detailsL:'Данни за продукта',each2:'по {v} мм',
  estShort:'очаквана готовност {when}',thisM:'тази сутрин',thisA:'днес следобед',tomM:'утре сутринта',tomA:'утре следобед',dayM:'{d} сутринта',dayA:'{d} следобед',
  contactSub:'Поръчката и всяка промяна по нея пристигат на този имейл, с копие до търговския екип на {c}.',optional:'по желание',
  submit:'Изпрати поръчката',submitNote:'{c} потвърждава срока по имейл, след което изпраща фактурата.',needEmail:'Въведете имейл, за да получите копие от поръчката.',needPhone:'Въведете телефон за търговския екип.',
  doneT:'Поръчката е изпратена',doneLive:'Копие пътува към {e}, с копие до търговския екип на {c}.',donePrev:'Тази демонстрация приключва тук. В реалната версия копие отива на {e} и до търговския екип на {c}.',
  st1:'Изпратена',st1s:'Поръчка {n}',st2:'Приета от {c}',st2s:'Ще получите потвърдения срок и фактурата по имейл.',st3p:'Готова за вземане',st3d:'На път към вас',st3s:'Очаква се {when}.',
  again:'Нова поръчка',backSite:'Обратно към сайта',orderNo:'Поръчка {n}',
  qEmail:'Вашият имейл',qReceive:'Вземане или доставка',qAddress:'Адрес за доставка',addrPh:'Улица, номер, населено място',qInvoice:'Фактура',invP:'Име върху фактурата',invC:'Име на фирмата, ЕИК и ДДС номер',
  prev:'Назад',qPhone:'Телефон за връзка',phoneSub:'{c} звъни за тази поръчка.',next:'Продължи',needName:'Въведете име за фактурата.',needCo:'Въведете името на фирмата и ЕИК.',needAddr:'Изберете адрес за доставка.',change:'Промени',
  doneCopy:'Копие от поръчката пътува към {e}.',doneNext:'Ще получите имейл веднага щом екипът ни потвърди поръчката.',listL:'Ценова листа',listV:'от {v}',
  line1:'Адрес',line2:'Етаж, вход, бележка за шофьора',bline2:'Адрес, втори ред',zip:'Пощенски код',invName:'Име за фактурата',addCo:'Фактура за фирма',coAddr:'Адрес на фирмата',billSame:'Адрес на фирмата: адресът за доставка.',billOther:'Друг адрес',infoL:'Информация',
  perKg:'/кг',kgU:'кг',onConf:'При потвърждение',askT:'Цена при потвърждение',askSub:'{c} потвърждава цената и срока по имейл.',stdL:'Стандарт',
  customT:'Заявка по поръчка',customD:'Друг размер, марка или обработка: опишете изискването и {c} потвърждава цената и срока.',customPh:'Например: 12 планки 300 × 200 × 8, S355, с по четири отвора 14 мм',customHead:'Вашата заявка',needText:'Опишете какво ви трябва.',
  incl:'с ДДС',excl:'без ДДС',prices:'Цени',totalEx:'Общо без ДДС',totalIn:'Общо с ДДС',found:'{n} резултата',crumbs:['Количка','Данни','Изпратена'],shortSub:'Изпрати',lines1:'1 ред',linesN:'{n} реда',
  estL:'Очаквана готовност',estDL:'Очаквана доставка',soldL:'Продава се на',weightL:'Тегло',codeL:'Номер',kgm:'кг/м',kgs:'кг',
  vStrip:'Ленти {w} мм',vHalf:'Половин или цял лист',vWhole:'Цели парчета',vAny:'Произволна дължина'}};
Object.assign(U.en,{estPrice:'Estimate · incl. VAT',readyWaiting:'Ready time with your order',estimating:'Estimating ready time',retry:'Try again',saveError:'Your basket is saved. Please try submitting again.',saving:'Saving request…',savedT:'Your order request is saved',savedCopy:'Your request is awaiting company confirmation.',savedNext:'The team confirms your date, then sends your invoice.',claim:'Claim this order page',claimTitle:'Company access',claimSub:'Enter your company email address to request access to the catalogue and orders.',claimSubmit:'Request access',claimSaved:'Your access request is saved',claimNext:'Company ownership is verified before access is granted.',claimEmail:'Company email',claimNeed:'Enter your name and company email address.',minimum:'Minimum quantity',quantityStep:'Quantity step',pack:'Pack size',quantityHint:'Purchase at least {min} units, in multiples of {step}.',quoteError:'Check the order quantities and try again.',contactSaved:'Your contact details stay with your order request.',again:'New Order',pricedItems:'Priced items',lineLimit:'An order can contain up to 100 lines.',customLimit:'Describe the request in up to 4,000 characters.',designFile:'Design file',dropFile:'Drop your design file here',chooseFile:'or choose a file',fileTypes:'PDF, image, DXF, DWG, STEP, STL or OBJ · up to 15 MB',uploadingFile:'Uploading {name}…',fileReady:'Ready for the workshop',removeFile:'Remove file',fileError:'Choose the design file again.',designOnly:'Design file: {name}',customNotes:'Notes for the workshop'});
Object.assign(U.en,{language:'Language',bulgarian:'Bulgarian',english:'English'});
Object.assign(U.bg,{estPrice:'Ориентировъчно · с ДДС',readyWaiting:'Очакван срок при поръчка',estimating:'Изчисляване на срока',retry:'Опитай отново',saveError:'Количката е запазена. Опитайте да изпратите отново.',saving:'Запазване на заявката…',savedT:'Заявката за поръчка е запазена',savedCopy:'Вашата заявка очаква потвърждение от компанията.',savedNext:'Екипът потвърждава срока, след което изпраща фактурата.',claim:'Поемете тази страница за поръчки',claimTitle:'Достъп за компанията',claimSub:'Въведете служебния си имейл за достъп до каталога и поръчките.',claimSubmit:'Заяви достъп',claimSaved:'Заявката за достъп е запазена',claimNext:'Собствеността на компанията се проверява преди предоставяне на достъп.',claimEmail:'Служебен имейл',claimNeed:'Въведете име и служебен имейл.',minimum:'Минимално количество',quantityStep:'Стъпка на количеството',pack:'Брой в опаковка',quantityHint:'Закупете поне {min} единици, в количество, кратно на {step}.',quoteError:'Проверете количествата и опитайте отново.',contactSaved:'Контактните данни се пазят със заявката за поръчка.',pricedItems:'Артикули с цена',lineLimit:'Една поръчка може да съдържа до 100 реда.',customLimit:'Опишете заявката с до 4000 знака.',listNote:'Публикувани цени от каталога',designFile:'Файл с проект',dropFile:'Пуснете файла с проекта тук',chooseFile:'или изберете файл',fileTypes:'PDF, изображение, DXF, DWG, STEP, STL или OBJ · до 15 MB',uploadingFile:'Качване на {name}…',fileReady:'Файлът е готов за работилницата.',removeFile:'Премахни файла',fileError:'Изберете файла с проекта отново.',designOnly:'Файл с проект: {name}',customNotes:'Бележки за работилницата',language:'Език',bulgarian:'Български',english:'English'});
const u=(k,v)=>{let s=(K.OVR[K.L.lang]||{})[k];if(s==null)s=(U[K.L.lang]||U.en)[k];if(v)Object.keys(v).forEach(x=>{s=s.replace('{'+x+'}',v[x])});return s};
const clamp=(n,a,b)=>Math.min(b,Math.max(a,n));
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const still=()=>matchMedia('(prefers-reduced-motion:reduce)').matches;

const S={slide:0,recvOpen:false,codeOpen:false,custom:'',customFile:null,uploading:false,uploadName:'',vat:true,step:0,geo:'',sugg:[],aq:'',open:false,view:'menu',bask:false,tab:0,q:'',item:null,rows:[{x:1000,n:1}],sheet:{a:1000,b:500,n:1},angle:false,peek:null,editing:-1,basket:[],capture:null,
  fulfil:'pickup',inv:'person',co:{},bad:'',done:null,scale:'fit',ex:false,pd:false,yaw:.75,pitch:.4,touch:-1e9,drag:null,cell:0};
let root,host,POST={},GEN={},SUPPLY={items:{}},spy=null,spyLock=0;
const REMOTE={signature:'',result:null,error:'',pending:false,timer:null,controller:null,sequence:0};
const WRITE={pending:false,fingerprint:'',key:'',error:'',claim:{name:'',email:'',pending:false,key:'',fingerprint:'',error:'',saved:null}};
const UPLOAD={fingerprint:'',key:''};
const LZ=window.RocotoLaser,LZC={},LZ3={el:null,handle:null,id:''};   /* laser: the checks this visit has read, and the one 3D stage */
const $=s=>root.querySelector(s);
const save=()=>{try{localStorage.setItem(CFG.key,JSON.stringify(S.basket));localStorage.setItem(CFG.key+'-vat',S.vat?'1':'0');if(S.basket.length&&S.capture)localStorage.setItem(CFG.key+'-capture',JSON.stringify(S.capture));else localStorage.removeItem(CFG.key+'-capture')}catch(e){}};
const load=()=>{try{S.basket=(JSON.parse(localStorage.getItem(CFG.key)||'[]')||[]).map(l=>l&&l.laser?{laser:l.laser,view:lzClean(l.view)}:l).filter(l=>l&&(l.custom||(l.laser?laserOn()&&!!l.view&&l.laser.quantity>=1:C.items[l.code])));S.capture=S.basket.length?JSON.parse(localStorage.getItem(CFG.key+'-capture')||'null'):null;const demo=S.capture?.demo_order;if(demo?.customer&&typeof demo.customer==='object'&&!Array.isArray(demo.customer)){S.demoOrder=demo;S.co={...S.co,...demo.customer};S.inv='company';S.billOther=true}S.vat=true}catch(e){S.basket=[];S.capture=null}try{const raw=sessionStorage.getItem(CFG.key+'-language-draft');if(raw){const draft=JSON.parse(raw);S.co=draft.co||{};S.fulfil=draft.fulfil||S.fulfil;S.inv=draft.inv||S.inv;S.billOther=!!draft.billOther;sessionStorage.removeItem(CFG.key+'-language-draft')}}catch(e){}};

function languageHtml(){
 const langs=[CFG.lang||'bg',...Object.keys(CFG.langs||{})].filter((lang,index,all)=>all.indexOf(lang)===index);
 if(langs.length<2)return'';
 const label=lang=>lang==='bg'?u('bulgarian'):lang==='en'?u('english'):lang.toUpperCase();
 return '<div class="langs" id="langs" role="group" aria-label="'+u('language')+'">'+langs.map(lang=>'<button type="button" data-language="'+esc(lang)+'" aria-label="'+esc(label(lang))+'" aria-pressed="'+(K.L.lang===lang)+'">'+esc(lang.toUpperCase())+'</button>').join('')+'</div>';
}
function switchLanguage(lang){
 const path=lang===(CFG.lang||'bg')?'/':(CFG.langs||{})[lang];if(!path||lang===K.L.lang)return;
 save();try{sessionStorage.setItem(CFG.key+'-language-draft',JSON.stringify({co:S.co,fulfil:S.fulfil,inv:S.inv,billOther:!!S.billOther}))}catch(e){}
 const rootPath=(CFG.root||'').replace(/\/$/,'');location.assign(rootPath+path+'#order');
}

/* Server state owns submitted prices and ready windows. A changed basket invalidates its quote. */
const basketSignature=()=>JSON.stringify(S.basket);
/* what the server reads of a line: a laser line is its check, material, thickness and quantity */
const wire=lines=>lines.map(l=>l.laser?{laser:l.laser}:l);
const currentQuote=()=>REMOTE.signature===basketSignature()?REMOTE.result:null;
const requestKey=()=>globalThis.crypto?.randomUUID?.()||('request_'+Date.now().toString(36)+'_'+Math.random().toString(36).slice(2));
async function api(path,payload,key,signal){
 const control=new AbortController(),timer=setTimeout(()=>control.abort(),15000);
 if(signal)signal.addEventListener('abort',()=>control.abort(),{once:true});
 try{const response=await fetch(CFG.base+'api/'+path,{method:'POST',headers:{'Content-Type':'application/json',...(key?{'Idempotency-Key':key}:{})},body:JSON.stringify(payload),signal:control.signal});
  const result=await response.json();if(!response.ok||!result.ok)throw new Error(result.message||u('saveError'));return result;
 }catch(error){if(error.name==='AbortError'||error.name==='TypeError')throw new Error(u(path==='quote'?'quoteError':'saveError'));throw error}finally{clearTimeout(timer)}
}
async function uploadFile(file){
 if(!file||S.uploading)return;
 const lz=S.view==='laser'&&S.lz;
 if(lz&&(!file.size||file.size>4*1024*1024||!/\.(dxf|svg)$/i.test(file.name))){lz.bad=/\.(dxf|svg)$/i.test(file.name)?'lzR_size':'lzR_format';return renderAll()}
 if(!file.size||file.size>15*1024*1024){S.bad='fileError';return renderAll()}
 const fingerprint=[file.name,file.size,file.lastModified||0].join('|');
 if(UPLOAD.fingerprint!==fingerprint){UPLOAD.fingerprint=fingerprint;UPLOAD.key=requestKey()}
 S.uploading=true;S.uploadName=file.name;S.bad='';if(lz){lz.bad='';lz.name=file.name}renderAll();
 const control=new AbortController(),timer=setTimeout(()=>control.abort(),45000);
 try{
  const response=await fetch(CFG.base+'api/uploads',{method:'POST',headers:{'Content-Type':file.type||'application/octet-stream','X-File-Name':encodeURIComponent(file.name),'Idempotency-Key':UPLOAD.key},body:file,signal:control.signal});
  const result=await response.json();if(!response.ok||!result.ok)throw new Error(result.message||u('fileError'));
  if(lz){const before=lz.file;lz.file=result.upload;lz.bad='';if(before&&before.id!==lz.file.id&&!uploadReferenced(before.id))discardUpload(before).catch(()=>{})}
  else{const previous=S.customFile;S.customFile=result.upload;S.bad='';
  if(previous&&previous.id!==S.customFile.id&&!uploadReferenced(previous.id))discardUpload(previous).catch(()=>{})}
 }catch(error){if(lz)lz.bad='lzR_upload';else S.bad='fileError'}
 finally{clearTimeout(timer);S.uploading=false;S.uploadName='';if(lz&&S.lz===lz&&lz.file&&!lz.bad)laserCheck();else renderAll()}
}
const uploadReferenced=id=>S.basket.some(line=>line.upload_id===id||line.view?.upload?.id===id||line.view?.fixed?.id===id);
async function discardUpload(file){
 if(!file?.id||!file.discard_token)return false;
 const response=await fetch(CFG.base+'api/uploads/'+file.id,{method:'DELETE',headers:{'Upload-Capability':file.discard_token}});
 const result=await response.json();if(!response.ok||!result.ok)throw new Error(result.message||u('fileError'));return true;
}
async function removeCustomFile(){
 const file=S.customFile;if(!file||S.uploading)return;
 if(uploadReferenced(file.id)){S.customFile=null;S.bad='';UPLOAD.fingerprint='';UPLOAD.key='';return renderAll()}
 S.uploading=true;S.bad='';renderAll();
 try{await discardUpload(file);if(S.customFile?.id===file.id)S.customFile=null;UPLOAD.fingerprint='';UPLOAD.key=''}
 catch(error){S.bad='fileError'}
 finally{S.uploading=false;renderAll()}
}
function readyWindow(ready){
 if(!ready?.earliest||!ready?.latest)return '';
 const fmt=new Intl.DateTimeFormat(K.L.lang==='bg'?'bg-BG':'en-GB',{day:'numeric',month:'short',timeZone:ready.timezone||'Europe/Sofia'}),a=fmt.format(new Date(ready.earliest)),b=fmt.format(new Date(ready.latest));return a===b?a:a+' – '+b;
}
function readyLabel(){if(S.basket.some(l=>l.custom||l.laser||(!l.custom&&C.items[l.code]?.q)))return u('byMail');const result=currentQuote(),window=result&&readyWindow(result.ready);return window?u('est',{when:window}):REMOTE.pending?u('estimating'):u('readyWaiting')}
function scheduleQuote(force=false){
 const signature=basketSignature();if(!force&&signature===REMOTE.signature)return;
 REMOTE.signature=signature;REMOTE.result=null;REMOTE.error='';REMOTE.sequence++;const sequence=REMOTE.sequence;
 clearTimeout(REMOTE.timer);REMOTE.controller?.abort();REMOTE.pending=!!S.basket.length;
 if(!S.basket.length)return;
 const lines=wire(JSON.parse(signature));REMOTE.timer=setTimeout(async()=>{
  const controller=new AbortController();REMOTE.controller=controller;
  try{const result=await api('quote',{lines},null,controller.signal);if(sequence!==REMOTE.sequence||signature!==basketSignature())return;REMOTE.result=result;REMOTE.error='';}
  catch(error){if(sequence!==REMOTE.sequence||controller.signal.aborted)return;REMOTE.error=error.message||u('quoteError');}
  finally{if(sequence===REMOTE.sequence){REMOTE.pending=false;if(root){renderBasket();$('#launch').innerHTML=launchHtml();if(S.view==='co'){$('#cbar').innerHTML=cbarHtml();paintSum();const r=$('#f-receive');if(r)r.innerHTML=CO.receive()}}}}
 },250);
}
const selling=i=>SUPPLY.items?.[i.c]?.selling||{minimum:1,step:1,pack:1,status:'assumed'};
function increment(i){const rule=selling(i),a=Math.max(1,Math.round(rule.step||1)),b=Math.max(1,Math.round(rule.pack||1));const gcd=(x,y)=>y?gcd(y,x%y):x;return a*b/gcd(a,b)}
function quantity(i,value,direction){
 if(mode(i)!=='piece')return clamp(value,1,999);
 const step=increment(i),minimum=Math.ceil((selling(i).minimum||1)/step)*step;
 return clamp(Math.max(minimum,(direction<0?Math.floor(value/step):Math.ceil(value/step))*step),minimum,Math.floor(999/step)*step);
}
function quantityRule(i,p){
 if(!p.ok)return p;const rule=selling(i),n=(i.stockBasis==='metre'||i.u==='m')&&p.bought?p.bought/1000:p.units?.length?p.units.reduce((v,u)=>v+u.count,0):p.n||1,step=increment(i);
 return n<(rule.minimum||1)||Math.abs(n/step-Math.round(n/step))>1e-7?{...p,ok:false,why:'quantity',minimum:rule.minimum,step}:p;
}
/* ---------- turnaround: working days from, to. One component, `.ta`, in the basket, on a product and on a menu row ---------- */
Object.assign(U.en,{taL:'Turnaround',taDay:'1 day',taDays:'{n} days',taRange:'{a}–{b} days',taConf:'On confirmation',taNote:'Estimated, confirmed by e-mail',taNote0:'The time arrives by e-mail'});
Object.assign(U.bg,{taL:'Срок',taDay:'1 ден',taDays:'{n} дни',taRange:'{a}–{b} дни',taConf:'По потвърждение',taNote:'Ориентировъчно, потвърждава се по имейл',taNote0:'Срокът идва по имейл'});
const taDays=v=>Array.isArray(v)&&v.length===2&&v.every(n=>Number.isInteger(n)&&n>=1&&n<=60)&&v[0]<=v[1]?[v[0],v[1]]:null;
/* the slower end decides the colour: 1 day gold, 2 days green, 3 to 5 days blue; longer or unknown stays neutral */
const taTier=d=>!d?0:d[1]<=1?1:d[1]<=2?2:d[1]<=5?3:0;
const taText=d=>!taTier(d)?u('taConf'):d[0]===d[1]?(d[0]===1?u('taDay'):u('taDays',{n:d[0]})):u('taRange',{a:d[0],b:d[1]});
/* the item's own lead from the supply answer when the server gives one, else the company setting for this kind of line */
const taOf=(kind,code)=>(code&&taDays(SUPPLY.items?.[code]?.turnaround?.days))||taDays((CFG.turnaround||{})[kind]);
function taLine(l){if(l.custom||l.laser)return taOf('custom');const p=linePlan(l);return taOf(p.ok&&p.cuts>0?'cut':'stock',l.code)}
function taBasket(lines){let slow=null;for(const l of lines){const d=taLine(l);if(!taTier(d))return null;if(!slow||d[1]>slow[1]||(d[1]===slow[1]&&d[0]>slow[0]))slow=d}return slow}
function taItem(){const p=curPlan();return taOf(p.ok&&p.cuts>0?'cut':'stock',shown().c)}
/* size '' is the basket's block, 'm' sits by a product's name, 's' is the mark on a row and in the price bar */
/* a company with no turnaround setting keeps one statement, the basket's block: its rows, products and price bars carry no mark */
const taHtml=(d,size,word,side)=>size&&!taTier(d)&&!CFG.turnaround?'':'<span class="ta'+(size?' '+size:'')+'" data-t="'+taTier(d)+'" aria-label="'+u('taL')+': '+esc(word||taText(d))+'">'+(size==='s'?ic('clock',13,2):'')+'<b>'+esc(word||taText(d))+'</b>'+(size==='s'?'':'<small>'+u(taTier(d)?'taNote':'taNote0')+'</small>')+(side?'<em>'+esc(side)+'</em>':'')+'</span>';

/* ---------- laser cutting: a drawing is checked, shown in its material, priced, and added as one line ---------- */
Object.assign(U.en,{lzT:'Laser cutting',lzRow:'Upload a DXF or SVG drawing and see the price at once.',lzTag:'Instant quote',
  lzFileT:'Your drawing',lzFileSub:'Upload a DXF or SVG. We check the drawing and show the price at once.',lzDrop:'Drop your drawing here',lzTypes:'DXF or SVG · up to 4 MB',lzChecking:'Checking {name}…',
  lzCheckT:'Drawing check',lzSize:'Size',lzCut:'Cut length',lzPierce:'Pierces',lzFound:'Findings',lzClean:'The drawing is ready to cut.',
  lzOpen1:'1 open contour',lzOpenN:'{n} open contours',lzDup1:'1 duplicate line',lzDupN:'{n} duplicate lines',lzSmall1:'1 narrow feature',lzSmallN:'{n} narrow features',lzJunc1:'1 junction',lzJuncN:'{n} junctions',
  lzOk:'Corrected',lzReview:'For review',lzFixed:'We corrected the drawing. Cutting follows the corrected file.',lzUse:'Use the corrected file',lzGet:'Download it',
  lzMatT:'Material and thickness',lzMat:'Material',lzThick:'Thickness, mm',lzSumT:'Summary',lzFile:'File',lzQty:'Quantity',lzEst:'Estimate · incl. VAT',lzEstShort:'estimated price',lzPiece:'/pc',lzPriceL:'Price',
  lzCost1:'Material',lzCost2:'Cutting and piercing',lzCost3:'Setup',lzMin:'Minimum order',lzAsCustom:'Send it as a custom request',
  lzR_format:'Choose a DXF or SVG drawing.',lzR_size:'Choose a drawing up to 4 MB.',lzR_entities:'This drawing is very detailed. Send it as a custom request.',lzR_points:'This drawing is very detailed. Send it as a custom request.',
  lzR_time:'The workshop reads this drawing by hand. Send it as a custom request.',lzR_empty:'Draw the cut lines as lines, arcs, circles or polylines.',lzR_busy:'Please try again in a minute.',lzR_rate:'Please try again in a minute.',
  lzR_upload:'Choose the drawing again.',lzR_storage:'Choose the drawing again.',lzR_off:'Laser cutting is being prepared. Send the drawing as a custom request.'});
Object.assign(U.bg,{lzT:'Лазерно рязане',lzRow:'Качете чертеж в DXF или SVG и вижте цената веднага.',lzTag:'Моментална оферта',
  lzFileT:'Вашият чертеж',lzFileSub:'Качете DXF или SVG. Проверяваме чертежа и показваме цената веднага.',lzDrop:'Пуснете чертежа тук',lzTypes:'DXF или SVG · до 4 MB',lzChecking:'Проверка на {name}…',
  lzCheckT:'Проверка на чертежа',lzSize:'Размер',lzCut:'Рязане',lzPierce:'Пробиви',lzFound:'Констатации',lzClean:'Чертежът е готов за рязане.',
  lzOpen1:'1 отворен контур',lzOpenN:'{n} отворени контура',lzDup1:'1 дублирана линия',lzDupN:'{n} дублирани линии',lzSmall1:'1 тесен елемент',lzSmallN:'{n} тесни елемента',lzJunc1:'1 възел',lzJuncN:'{n} възела',
  lzOk:'Коригирано',lzReview:'За преглед',lzFixed:'Коригирахме чертежа. Рязането е по коригирания файл.',lzUse:'Използвай коригирания файл',lzGet:'Изтегли го',
  lzMatT:'Материал и дебелина',lzMat:'Материал',lzThick:'Дебелина, мм',lzSumT:'Обобщение',lzFile:'Файл',lzQty:'Количество',lzEst:'Ориентировъчно · с ДДС',lzEstShort:'ориентировъчна цена',lzPiece:'/бр.',lzPriceL:'Цена',
  lzCost1:'Материал',lzCost2:'Рязане и пробиви',lzCost3:'Настройка',lzMin:'Минимална поръчка',lzAsCustom:'Изпрати като заявка по поръчка',
  lzR_format:'Изберете чертеж във формат DXF или SVG.',lzR_size:'Изберете чертеж до 4 MB.',lzR_entities:'Чертежът е много подробен. Изпратете го като заявка по поръчка.',lzR_points:'Чертежът е много подробен. Изпратете го като заявка по поръчка.',
  lzR_time:'Работилницата разчита този чертеж ръчно. Изпратете го като заявка по поръчка.',lzR_empty:'Начертайте линиите за рязане като линии, дъги, окръжности или полилинии.',lzR_busy:'Опитайте отново след минута.',lzR_rate:'Опитайте отново след минута.',
  lzR_upload:'Изберете чертежа отново.',lzR_storage:'Изберете чертежа отново.',lzR_off:'Лазерното рязане се подготвя. Изпратете чертежа като заявка по поръчка.'});
const LZR=['format','size','entities','points','time','empty','busy','rate','upload','storage','off'];
const laserOn=()=>!!CFG.laser&&!!LZ&&!!window.RocotoLaserQuote;
const lzValid=c=>!!(c&&typeof c.id==='string'&&c.bounds?.w>0&&c.bounds?.h>0&&c.cut&&Array.isArray(c.contours)&&Array.isArray(c.materials)&&c.materials.length&&c.materials.every(m=>m&&typeof m.id==='string'&&Array.isArray(m.thicknesses)&&m.thicknesses.length)&&c.tariff?.rates);
const lzMat=(c,id)=>c.materials.find(m=>m.id===id)||c.materials[0];
const lzNear=(m,v)=>m.thicknesses.includes(v)?v:m.thicknesses.reduce((a,b)=>Math.abs(b-v)<Math.abs(a-v)?b:a);
/* the estimate, by the formula the server prices the line with (laser_quote.mjs) */
const lzQuote=(c,id,thickness,n)=>window.RocotoLaserQuote.quote(c,lzMat(c,id),c.tariff,thickness,n);
function lzTotal(l){const c=LZC[l.laser.id],q=c&&lzQuote(c,l.laser.material,l.laser.thickness,l.laser.quantity);return q&&q.ok?q.gross:(l.view?.gross||0)}
const lzNow=()=>lzQuote(S.lz.check,S.lz.material,S.lz.thickness,S.lz.n);
const lzDim=b=>K.num(b.w,b.w<100?1:0)+X+K.num(b.h,b.h<100?1:0)+' '+t('mm');
const lzLen=mm=>mm>=1000?K.num(mm/1000,2)+' '+M():K.num(mm)+' '+t('mm');
const lzColor=v=>/^#[0-9a-fA-F]{6}$/.test(v||'')?v:'#8a8d91';
/* what an order line keeps to draw itself: names, outline and estimate; the server reads only `laser` */
function lzView(z,q){
  const c=z.check,m=lzMat(c,z.material);
  return{name:c.name,w:c.bounds.w,h:c.bounds.h,d:LZ.outline(c),color:lzColor(m.look?.color),bg:m.bg||'',en:m.en||'',gross:q.gross,thumb:(LZ3.handle&&LZ3.id===c.id&&LZ3.handle.snapshot(128))||'',
    upload:z.file?{id:z.file.id,discard_token:z.file.discard_token}:null,fixed:c.fixed?.discard_token?{id:c.fixed.upload,discard_token:c.fixed.discard_token}:null};
}
function lzClean(v){
  if(!v||!(v.w>0)||!(v.h>0)||typeof v.d!=='string'||!/^[MLZ0-9 .-]*$/.test(v.d))return null;
  return{...v,name:String(v.name||''),color:lzColor(v.color),thumb:/^data:image\/(jpeg|png|webp);base64,[A-Za-z0-9+/=]+$/.test(v.thumb||'')?v.thumb:''};
}
const lzDiscard=v=>[v?.upload,v?.fixed].forEach(f=>{if(f?.id&&!uploadReferenced(f.id))discardUpload(f).catch(()=>{})});
/* a stored line's check, asked for again so its picture and quantity keep working after a reload */
function lzWarm(){
  S.basket.forEach(l=>{const id=l.laser?.id;if(!id||id in LZC||!/^[a-f0-9]{32}$/.test(id))return;LZC[id]=null;
    fetch(CFG.base+'api/laser/'+id).then(r=>r.json()).then(c=>{if(c&&c.ok&&lzValid(c)){LZC[id]=c;if(root)renderBasket()}else delete LZC[id]}).catch(()=>{delete LZC[id]})});
}
async function laserCheck(){
 const z=S.lz;if(!z||!z.file)return;z.busy='check';z.bad='';renderAll();
 const control=new AbortController(),timer=setTimeout(()=>control.abort(),25000);
 try{const response=await fetch(CFG.base+'api/laser',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({upload:z.file.id}),signal:control.signal});
  const result=await response.json();if(S.lz!==z)return;
  if(!result.ok||!lzValid(result))z.bad='lzR_'+(LZR.includes(result.reason)?result.reason:'upload');
  else{LZC[result.id]=result;z.check=result;const m=lzMat(result,result.default?.material);z.material=m.id;z.thickness=lzNear(m,result.default?.thickness??m.thicknesses[0]);z.step='check'}
 }catch(error){if(S.lz===z)z.bad='lzR_busy'}
 finally{clearTimeout(timer);if(S.lz===z){z.busy='';renderAll();const sc=$('#coscroll');if(sc)sc.scrollTop=0}}
}
const lzHead=(title,meta,right)=>'<div class="ihead"><div><h1>'+title+'</h1>'+(meta?'<p class="meta">'+esc(meta)+'</p>':'')+'</div>'+(right||'')+'</div>';
const lzRate=q=>'<div class="ih-r"><div class="rate">'+K.eur(q.gross/q.quantity)+'<em>'+u('lzPiece')+'</em></div>'+taHtml(taOf('custom'),'m')+'</div>';
function lzFound(c){
  const kinds=[['open_contour','lzOpen'],['duplicate','lzDup'],['small_feature','lzSmall'],['junction','lzJunc']],rows=[];
  kinds.forEach(([kind,key])=>[true,false].forEach(fixed=>{const n=(c.issues||[]).filter(i=>i.kind===kind&&!!i.fixed===fixed).length;
    if(n)rows.push('<div><span>'+(n===1?u(key+'1'):u(key+'N',{n:n}))+'</span><b class="'+(fixed?'ok':'rev')+'">'+ic(fixed?'check':'info',15,2)+u(fixed?'lzOk':'lzReview')+'</b></div>')}));
  if(!rows.length)return '<p class="say lz-clean">'+ic('check',15,2)+u('lzClean')+'</p>';
  return '<section class="grp"><div class="g-h"><h3>'+u('lzFound')+'</h3></div><div class="dl marks">'+rows.join('')+'</div>'+
    (c.fixed?'<p class="snote">'+u('lzFixed')+'</p>'+(c.fixed.path?'<div class="more"><a class="btn" href="'+esc(CFG.base+c.fixed.path)+'" download="'+esc(c.fixed.name||'')+'">'+ic('download',16)+u('lzGet')+'</a></div>':''):'')+'</section>';
}
function lzOptsHtml(){
  const z=S.lz,c=z.check,m=lzMat(c,z.material);
  const grp=(title,body)=>'<section class="grp"><div class="g-h"><h3>'+title+'</h3></div>'+body+'</section>';
  return grp(u('lzMat'),'<div class="opts" role="radiogroup" aria-label="'+u('lzMat')+'">'+c.materials.map(x=>{const q=lzQuote(c,x.id,lzNear(x,z.thickness),z.n),a=x.thicknesses[0],b=x.thicknesses[x.thicknesses.length-1];
      return '<button class="opt" type="button" role="radio" data-lz-mat="'+esc(x.id)+'" aria-checked="'+(x.id===m.id)+'"><i class="rd"></i><span class="oi"><i class="sw" style="background-color:'+lzColor(x.look?.color)+'"></i></span><span><b>'+esc(K.name(x))+'</b><small>'+K.dimStr(a)+'–'+K.dimStr(b)+' '+t('mm')+'</small></span><em>'+(q.ok?K.eur(q.gross):'')+'</em></button>'}).join('')+'</div>')+
    grp(u('lzThick'),'<div class="szs" style="--w:56px">'+m.thicknesses.map(v=>'<button class="sz" type="button" data-lz-th="'+v+'" aria-pressed="'+(v===z.thickness)+'">'+K.dimStr(v)+'</button>').join('')+'</div>')+
    grp(u('lzQty'),'<div class="row"><span class="step"><button type="button" data-lz-d="-1" aria-label="−">'+ic('minus',16)+'</button><input type="text" inputmode="numeric" autocomplete="off" value="'+z.n+'" data-lz-n aria-label="'+u('lzQty')+'"><button type="button" data-lz-d="1" aria-label="+">'+ic('plus',16)+'</button></span></div>');
}
function laserHtml(){
  const z=S.lz,c=z.check,prog='<div class="prog"><i style="width:'+({file:25,check:50,material:75,summary:100})[z.step]+'%"></i></div>';
  if(z.step==='file'||!c){
    const busy=S.uploading?u('uploadingFile',{name:S.uploadName||z.name}):z.busy?u('lzChecking',{name:z.name}):'';
    return prog+'<div class="q"><h1>'+u('lzFileT')+'</h1><p class="q-sub">'+u('lzFileSub')+'</p><label class="file-drop'+(busy?' busy':'')+'" id="file-drop">'+ic('file-text',28,1.4)+'<span><b>'+esc(busy||u('lzDrop'))+'</b><small>'+u('chooseFile')+'</small><em>'+u('lzTypes')+'</em></span><input id="design-file" data-upload type="file" accept=".dxf,.svg"'+(busy?' disabled':'')+'></label>'+
      (z.bad?'<p class="hint err" role="alert">'+esc(u(z.bad))+'</p>'+(z.file?'<div class="more"><button class="btn" type="button" data-act="lz-custom">'+u('lzAsCustom')+ic('arrow-right',16)+'</button></div>':''):'')+'</div>';
  }
  if(z.step==='check')return prog+'<div class="lzp"><div class="hero lz-hero">'+LZ.drawing(c)+'</div>'+lzHead(u('lzCheckT'),c.name)+
    '<div class="figs"><div><b>'+lzDim(c.bounds)+'</b><span>'+u('lzSize')+'</span></div><div><b>'+lzLen(c.cut.length_mm)+'</b><span>'+u('lzCut')+'</span></div><div><b>'+K.num(c.cut.pierces)+'</b><span>'+u('lzPierce')+'</span></div></div>'+lzFound(c)+'</div>';
  if(z.step==='material')return prog+'<div class="lzp"><div class="hero lz-hero s3" id="lz3d"></div><div id="lz-head"></div><div id="lz-opts"></div></div>';
  const q=lzNow(),m=lzMat(c,z.material),row=(k,v)=>'<div><span>'+k+'</span><b>'+esc(v)+'</b></div>',sum=(k,v)=>'<div><span>'+k+'</span><b>'+K.eur(v)+'</b></div>';
  return prog+'<div class="lzp"><div class="hero lz-hero s3 mini" id="lz3d"></div>'+lzHead(u('lzSumT'),'',lzRate(q))+
    '<section class="grp"><div class="dl">'+row(u('lzFile'),c.name)+row(u('lzMat'),K.name(m)+' · '+K.dimStr(z.thickness)+' '+t('mm'))+row(u('lzQty'),K.num(z.n))+row(u('lzSize'),lzDim(c.bounds))+'</div></section>'+
    '<section class="grp"><div class="g-h"><h3>'+u('lzPriceL')+'</h3><small>'+u('lzEstShort')+'</small></div><div class="sums">'+(q.minimum?sum(u('lzMin'),q.net):sum(u('lzCost1'),q.material)+sum(u('lzCost2'),Math.round((q.cutting+q.piercing)*100)/100)+sum(u('lzCost3'),q.setup))+sum(t('vat'),q.vat)+
      '<div class="sum-t"><span>'+u('totalIn')+'</span><b>'+K.eur(q.gross)+'</b></div></div></section></div>';
}
function lzBarHtml(){
  const z=S.lz,q=lzNow(),last=z.step==='summary',full=z.editing<0&&S.basket.length>=100;
  const label=last?(z.editing>=0?t('update'):t('add')):z.step==='check'&&z.check.fixed?u('lzUse'):u('next'),short=last?u('short'):u('next');
  return '<div class="tot"><span class="t1"><b id="num">'+(q.ok?K.eur(q.gross):'—')+'</b></span><small>'+u('lzEst')+'</small></div>'+taHtml(taOf('custom'),'s')+
    '<button class="act" type="button" data-act="'+(last?'lz-add':'lz-next')+'"'+(q.ok&&!(last&&full)?'':' disabled')+'><span class="lg">'+label+'</span><span class="sh">'+short+'</span>'+ic('arrow-right',18)+'</button>';
}
/* one 3D stage for the visit to this drawing: made once, moved between the material and summary screens, let go on leaving */
function lzDrop(){if(LZ3.handle)LZ3.handle.dispose();LZ3.handle=null;LZ3.el=null;LZ3.id=''}
function lzStage(){
  const z=S.view==='laser'&&S.lz;if(!z||!z.check)return lzDrop();
  if(LZ3.handle&&LZ3.id!==z.check.id)lzDrop();
  const slot=z.step==='material'||z.step==='summary'?$('#lz3d'):null;if(!slot||!slot.appendChild)return;
  const m=lzMat(z.check,z.material);
  if(!LZ3.handle){LZ3.el=document.createElement('div');LZ3.el.className='s3-box';LZ3.id=z.check.id;slot.appendChild(LZ3.el);LZ3.handle=LZ.mount(LZ3.el,z.check,{base:CFG.base,material:m,thickness:z.thickness,still:still()})}
  else{if(LZ3.el.parentNode!==slot)slot.appendChild(LZ3.el);LZ3.handle.set(m,z.thickness)}
}
function lzPaint(keepOpts){
  const z=S.lz,cb=$('#cbar');if(!z)return;
  if(z.check&&z.step==='material'){const q=lzNow(),h=$('#lz-head'),o=$('#lz-opts');if(h)h.innerHTML=lzHead(u('lzMatT'),z.check.name+' · '+lzDim(z.check.bounds),q.ok?lzRate(q):'');if(o&&!keepOpts)o.innerHTML=lzOptsHtml()}
  if(cb){cb.hidden=z.step==='file'||!z.check;if(!cb.hidden)cb.innerHTML=lzBarHtml()}
  lzStage();
}
function lzOpen(){S.lz={step:'file',file:null,check:null,material:'',thickness:0,n:1,busy:'',bad:'',name:'',editing:-1};S.view='laser';S.bask=false;S.editing=-1;renderAll()}
function lzLeave(){const z=S.lz;S.lz=null;if(z?.file&&z.editing<0)lzDiscard({upload:z.file,fixed:z.check?.fixed?.discard_token?{id:z.check.fixed.upload,discard_token:z.check.fixed.discard_token}:null});showMenu()}
function lzBack(){
  const z=S.lz;if(!z||z.step==='file'||z.busy||S.uploading||(z.editing>=0&&z.step==='material'))return lzLeave();
  if(z.step==='check'){lzDiscard({upload:z.file,fixed:z.check?.fixed?.discard_token?{id:z.check.fixed.upload,discard_token:z.check.fixed.discard_token}:null});z.file=null;z.check=null;z.step='file';UPLOAD.fingerprint='';UPLOAD.key=''}
  else z.step=z.step==='summary'?'material':'check';
  renderAll();const sc=$('#coscroll');if(sc)sc.scrollTop=0;
}
function lzNext(){const z=S.lz;if(!z||!z.check)return;z.step=z.step==='check'?'material':'summary';renderAll();const sc=$('#coscroll');if(sc)sc.scrollTop=0}
function lzAdd(){
  const z=S.lz,q=z&&z.check&&lzNow();if(!q||!q.ok)return;
  if(z.editing<0&&S.basket.length>=100)return;
  const line={laser:{id:z.check.id,material:z.material,thickness:z.thickness,quantity:z.n},view:lzView(z,q)};
  if(z.editing>=0&&S.basket[z.editing]){S.basket[z.editing]=line;S.fresh=z.editing}else{S.basket.push(line);S.fresh=S.basket.length-1}
  S.lz=null;save();showMenu();setTimeout(()=>{S.fresh=-1},600);
}
/* a drawing the check hands back goes on as today's custom request, with its file */
function lzToCustom(){const z=S.lz;S.lz=null;S.customFile=z?.file||null;S.custom='';S.editing=-1;S.bad='';S.view='custom';renderAll()}
function dropLine(n){const gone=S.basket.splice(n,1)[0];save();if(gone?.file&&!uploadReferenced(gone.file.id))discardUpload(gone.file).catch(()=>{});if(gone?.laser)lzDiscard(gone.view);if(!S.basket.length&&S.view==='co')S.view='menu'}

/* ---------- recurring work: asked at checkout when the company's setting says so ---------- */
Object.assign(U.en,{recT:'Order frequency',recQ:'Is this a recurring order?',recOnce:'One-off',recOnceSub:'A single order',recYes:'Recurring',recYesSub:'The same parts on a schedule',recWeekly:'Weekly',recMonthly:'Monthly',recQuarterly:'Quarterly',recSchedule:'By schedule',recNote:'Quantity or schedule'});
Object.assign(U.bg,{recT:'Честота на поръчката',recQ:'Това повтаряща се поръчка ли е?',recOnce:'Еднократна',recOnceSub:'Една поръчка',recYes:'Повтаряща се',recYesSub:'Същите детайли по график',recWeekly:'Седмично',recMonthly:'Месечно',recQuarterly:'На тримесечие',recSchedule:'По график',recNote:'Количество или график'});
const REC=[['weekly','recWeekly'],['monthly','recMonthly'],['quarterly','recQuarterly'],['schedule','recSchedule']];
const recAsk=()=>!!CFG.checkout?.recurring?.ask;
/* the customer fields an order carries: a code for each choice, and the same answer as a sentence in both languages */
function recFields(){
  const on=S.co.recurring==='recurring',f=on?(REC.find(x=>x[0]===S.co.recurringFrequency)||REC[1]):null,note=on?String(S.co.recurringNote||'').trim():'';
  const say=lang=>{const w=U[lang];return on?[w.recYes,w[f[1]],note].filter(Boolean).join(' · '):w.recOnce};
  return{recurring:on?'recurring':'one-off',...(on?{recurringFrequency:f[0],...(note?{recurringNote:note}:{})}:{}),recurringBg:say('bg'),recurringEn:say('en')};
}

/* ---------- catalogue helpers ---------- */
const isSheet=i=>i.cat.shape==='sheet'||i.cat.shape==='chequer';
/* sheet: pieces cut from a sheet; bar: a cut list from stock lengths; piece: a count of pieces, sheets or kilograms */
const mode=i=>P.lineMode(i);
const ask=i=>!!i.q;   /* the company settles this item's price when it confirms the order */
const maxLen=i=>i.r.k==='len'&&i.r.l.length?Math.max.apply(null,i.r.l)*1000:i.r.max?i.r.max*1000:i.L>1?i.L*1000:100000;
const cn=c=>K.L.lang==='en'?c.en:c.bg;
const metalOf=c=>K.name(C.metals.find(m=>m.id===c.metal));
const FORMS=()=>C.forms.filter(f=>C.cats.some(c=>c.form===f.id));
/* the rate a customer compares: per metre for bars, per sheet for sheets, each for pieces */
const rate=i=>ask(i)?(i.rate?[i.rate[0],{m:'perM',kg:'perKg',sheet:'perSheet',pc:'each'}[i.rate[1]]||'each']:[0,'']):mode(i)==='sheet'||i.u==='sheet'?[i.p,'perSheet']:i.u==='kg'?[i.p,'perKg']:mode(i)==='bar'?[i.p/(i.u==='m'?1:i.L),'perM']:[i.p,'each'];
function catFrom(c){const first=c.items.find(i=>!ask(i))||c.items[0],un=rate(first)[1];let best=null;c.items.forEach(i=>{const r=rate(i);if(!ask(i)&&r[1]===un&&r[0]>0&&(best==null||r[0]<best))best=r[0]});return[best||0,un]}
function catRange(c){
  const lv=K.levels(c),n=c.items.length,mm=c.items[0].d&&!/^(ipe|hea|heb|upn)$/.test(c.shape)?' '+t('mm'):'';
  if(lv.length<2||!c.items[0].d)return n===1?(K.L.lang==='en'?'1 size':'1 размер'):t('sizes',{n:n});
  const nb=x=>String(x).replace(/ /g,'\u00a0');
  return u('range',{n:n,a:nb(lv[0].key),b:nb(lv[lv.length-1].key+mm)});
}
const pr=n=>K.eur(n);
const vatW=()=>u('incl');
const price=(v,un,from)=>v>0?'<span class="pr">'+(from?'<i>'+u('fromW')+'</i> ':'')+K.eur(v,3)+'<em>'+u(un)+'</em></span>':'<span class="pr"><i>'+u('askT')+'</i></span>';
function nearest(cat,prev){
  if(!prev||!prev.d)return null;let best=null,bd=1e9;
  cat.items.forEach(i=>{if(!i.d||i.d.length!==prev.d.length)return;let q=0;i.d.forEach((v,k)=>{q+=Math.abs(v-prev.d[k])*(k===i.d.length-1?3:1)});if(q<bd){bd=q;best=i}});
  return best;
}
function setItem(code){if(C.items[code])S.item=code}
/* Preserve the customer's entry, including incomplete input, until it validates. */
const entered=v=>/^\d+(?:[.,]\d+)?$/.test(v.trim())?Number(v.trim().replace(',','.')):v;
function planOf(i,rows,sheet,angle){return quantityRule(i,P.quoteLine(i,{rows,sheet,angle}))}
const shown=()=>C.items[S.peek||S.item];
const curPlan=()=>planOf(C.items[S.item],S.rows,S.sheet,S.angle);
const linePlan=l=>l.custom?{ok:true,ask:1,total:0,cuts:0}:l.laser?{ok:true,est:1,total:lzTotal(l),cuts:0}:planOf(C.items[l.code],l.rows||[{x:0,n:1}],l.sheet||{},l.angle);
const lineAsk=l=>!!l.custom||(!l.laser&&(ask(C.items[l.code])||!!linePlan(l).pending));
const lineTotal=l=>{const p=linePlan(l);return p.ok?p.total:0};
const basketTotal=()=>currentQuote()?.quote.gross??S.basket.reduce((a,l)=>a+lineTotal(l),0);
const company=()=>K.name(C.data.company);
/* The date displayed by the source website; it is not a verified price revision. */
function asOf(){const m=/^(\d{1,2})[\/.](\d{1,2})[\/.](\d{4})$/.exec(C.data.asOf||'');if(!m)return C.data.asOf||'';const d=new Date(+m[3],+m[2]-1,+m[1]);return K.L.lang==='bg'?('0'+m[1]).slice(-2)+'.'+('0'+m[2]).slice(-2)+'.'+m[3]:d.toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric'})}
const cap=x=>x.charAt(0).toUpperCase()+x.slice(1);
const M=()=>K.L.lang==='en'?'m':'\u043c';
function soldVal(i){
  const r=i.r;
  if(r.lengths&&i.d)return r.lengths.map(l=>K.num(i.d[1])+X+K.num(l)).join(' · ')+' '+t('mm');
  if(isSheet(i)&&i.d)return r.k==='strip'?u('vStrip',{w:K.num(i.d[1])}):r.k==='half'?u('vHalf'):u('vWhole');
  if(r.k==='any')return u('vAny');
  if(r.k==='len'&&r.l.length)return r.l.map(K.dimStr).join(' · ')+' '+M();
  return u('vWhole');
}

const singular=s=>s.replace(/\b(tubes|bars|pipes|angles|sheets|plates|beams|profiles)\b/,m=>m.slice(0,-1));
const BEAM={ipe:1,hea:1,heb:1},BEAMBG='Двойно Т-профил ',UBG='П-профил ';
function titleOf(i){
  const sh=i.cat.shape,en=K.L.lang==='en';
  if(BEAM[sh])return en?K.label(i)+' beam':BEAMBG+K.label(i);
  if(sh==='upn')return en?K.label(i)+' channel':UBG+K.label(i);
  let name=en?singular(i.cat.en):i.cat.product?.bg||i.cat.bg;
  if(sh==='sq_tube'&&i.d&&i.d[0]!==i.d[1])name=en?name.replace(/square/i,'rectangular'):'Правоъгълна тръба';
  if(sh==='angle'&&i.d&&i.d[0]!==i.d[1])name=en?name.replace(/equal/i,'Unequal'):'Неравностранен винкел';
  return name+(i.d?' '+K.label(i).replace(/ /g,'\u00a0'):': '+K.k1(i));
}
function soldIn(i){
  const r=i.r;
  if(r.lengths&&i.d)return soldVal(i);
  if(isSheet(i)&&i.d)return r.k==='strip'?u('soldStrip',{w:K.num(i.d[1])}):r.k==='half'?u('soldHalf'):u('soldWhole');
  if(r.k==='any')return u('soldAny');
  if(r.k==='len'&&r.l.length)return u('soldLen',{v:r.l.map(K.dimStr).join(' · ')});
  return u('soldWhole');
}
function buyText(i,p){
  if(!p.ok)return'';
  if(p.piece)return u('pcs',{n:p.n,v:i.d?K.label(i):K.k1(i)});
  if(mode(i)==='sheet')return p.units.map(un=>un.len===i.d[2]?t('wholeSheet',{n:un.count,w:K.num(un.w),l:K.num(un.len)}):un.len===i.d[2]/2?t('halfSheet',{n:un.count}):t('strip',{n:un.count,w:K.num(un.w),l:K.num(un.len)})).join(' + ');
  if(i.r.k==='any')return p.units.map(x=>t('piece',{n:x.count,l:K.num(x.len)})).join(' + ');
  const g={};p.units.forEach(x=>{g[x.len]=(g[x.len]||0)+x.count});
  return Object.keys(g).sort((a,b)=>b-a).map(l=>t('bar',{n:g[l],l:K.dimStr(l/1000)})).join(' + ');
}
const qtyText=(i,n)=>i.u==='kg'?K.num(n)+' '+u('kgU'):t('lines',{n:n});
const cutText=l=>l.custom?l.custom:l.sheet?l.sheet.n+X+K.num(l.sheet.a)+X+K.num(l.sheet.b)+' '+t('mm'):mode(C.items[l.code])==='piece'&&!(ask(C.items[l.code])&&C.items[l.code].L)?qtyText(C.items[l.code],l.rows[0].n):l.rows.map(r=>r.n+X+K.num(r.x)+' '+t('mm')).join(' · ');
const cutsText=n=>n===1?t('cut1'):t('cuts',{n:n});
function drawSvg(g){
  const A='fill="rgba(38,39,34,.07)" fill-rule="evenodd" stroke="#262722" stroke-width="1.6" stroke-linejoin="round"',D='stroke="rgba(38,39,34,.44)" stroke-width="1.2" fill="none"',f=K.dimStr;
  const hd=(a,b,y,v)=>'<path d="M'+a+' '+y+'H'+b+'M'+a+' '+(y-4)+'v8M'+b+' '+(y-4)+'v8" '+D+'/><text x="'+((a+b)/2)+'" y="'+(y+15)+'" text-anchor="middle">'+v+'</text>';
  const vd=(x,a,b,v)=>'<path d="M'+x+' '+a+'V'+b+'M'+(x-4)+' '+a+'h8M'+(x-4)+' '+b+'h8" '+D+'/><text x="'+(x+8)+'" y="'+((a+b)/2+4)+'">'+v+'</text>';
  const ld=(x1,y1,x2,y2,v)=>'<path d="M'+x1+' '+y1+'L'+x2+' '+y2+'" '+D+'/><text x="'+(x2+4)+'" y="'+(y2+4)+'">'+v+'</text>';
  let h;
  switch(g.k){
    case'flat':h='<rect x="24" y="30" width="86" height="20" rx="2" '+A+'/>'+hd(24,110,64,f(g.w))+vd(122,30,50,f(g.t));break;
    case'round':h='<circle cx="66" cy="42" r="32" '+A+'/>'+hd(34,98,84,'Ø '+f(g.d));break;
    case'square':h='<rect x="34" y="8" width="64" height="64" rx="3" '+A+'/>'+hd(34,98,84,f(g.a));break;
    case'hex':h='<path d="M48 10h36l18 31-18 31H48L30 41z" '+A+'/>'+vd(114,10,72,f(g.s));break;
    case'box':h=g.a===g.b?'<path d="M41 8h50a7 7 0 017 7v50a7 7 0 01-7 7H41a7 7 0 01-7-7V15a7 7 0 017-7zM46 17h40a3 3 0 013 3v40a3 3 0 01-3 3H46a3 3 0 01-3-3V20a3 3 0 013-3z" '+A+'/>'+hd(34,98,84,f(g.a))+ld(94,26,112,18,f(g.t))
      :'<path d="M26 16h78a6 6 0 016 6v40a6 6 0 01-6 6H26a6 6 0 01-6-6V22a6 6 0 016-6zM30 24h70a2 2 0 012 2v32a2 2 0 01-2 2H30a2 2 0 01-2-2V26a2 2 0 012-2z" '+A+'/>'+hd(20,110,80,f(g.a))+vd(122,16,68,f(g.b))+'<text x="36" y="46">'+f(g.t)+'</text>';break;
    case'tube':h='<path d="M66 10a32 32 0 100 64 32 32 0 000-64zM66 19a23 23 0 110 46 23 23 0 010-46z" '+A+'/>'+hd(34,98,84,'Ø '+f(g.d))+ld(92,24,112,16,f(g.t));break;
    case'angle':h='<path d="M34 8h11v53h53v11H34z" '+A+'/>'+hd(34,98,84,f(g.a))+(g.b!==g.a?vd(20,8,72,''):'')+ld(45,26,62,20,f(g.t))+(g.b!==g.a?'<text x="2" y="44">'+f(g.b)+'</text>':'');break;
    case'tee':h='<path d="M30 12h72v10H71v50H61V22H30z" '+A+'/>'+hd(30,102,86,f(g.a))+vd(114,12,72,f(g.b));break;
    case'u':h='<path d="M40 10h50v9H51v46h39v9H40z" '+A+'/>'+hd(40,90,88,f(g.b))+vd(102,10,74,f(g.h));break;
    case'i':h='<path d="M36 10h60v9H71v46h25v9H36v-9h25V19H36z" '+A+'/>'+hd(36,96,88,f(g.b))+vd(108,10,74,f(g.h));break;
    default:h='<rect x="10" y="36" width="94" height="10" rx="1.5" '+A+'/>'+vd(114,36,46,f(g.t));
  }
  return '<svg viewBox="0 0 172 104" aria-hidden="true">'+h+'</svg>';
}

/* ---------- pictures: three-shot sets mapped to each item's verified material variant ---------- */
const poster=c=>POST[c.code]?CFG.base+'t/'+POST[c.code]:'';
const pic=i=>{const src=slidesOf(i.cat,i)[0];return src?'<img src="'+esc(src)+'" alt="" loading="lazy">':ic('box',28)};
const catPic=c=>pic(K.mid(c));
const pump=()=>{};
const setOf=(c,i)=>{const key=i&&(GEN.items||{})[i.c];return key?(GEN.sets||{})[key]||null:(GEN.variantTypes||[]).includes(c.code)?null:(GEN.sets||{})[c.code]||null};
const slidesOf=(c,i)=>{const g=setOf(c,i);return g&&g.length?g.map(f=>CFG.base+'g/'+f):(GEN.variantTypes||[]).includes(c.code)?[]:poster(c)?[poster(c)]:c.img?[c.img]:[]};
let slideTouched=0,slideHover=false;
function slideTo(n,automatic=false){
  if(!automatic)slideTouched=Date.now();
  const el=$('#slides'),k=el.children.length;if(!k)return;S.slide=(n+k)%k;
  el.style.transform='translateX(-'+S.slide*100+'%)';
  root.querySelectorAll('#dots button').forEach((b,x)=>b.setAttribute('aria-current',x===S.slide));
}

/* ---------- menu ---------- */
function catRow(c){
  const r=catFrom(c);
  return '<button class="it" type="button" data-cat="'+c.code+'"><span class="tx"><b>'+esc(cn(c))+'</b><small>'+esc(metalOf(c))+' · '+esc(catRange(c))+'</small><span class="pr-l">'+price(r[0],r[1],true)+taHtml(taOf('stock'),'s')+'</span></span><span class="th">'+catPic(c)+'<span class="plus">'+ic('plus',18)+'</span></span></button>';
}
function itemRow(i,len){
  const r=rate(i);
  return '<button class="it" type="button" data-item="'+i.c+'"'+(len?' data-len="'+len+'"':'')+'><span class="tx"><b>'+esc(titleOf(i))+(len?' · '+K.num(len)+' '+t('mm'):'')+'</b><small>'+esc(metalOf(i.cat))+' · '+esc(soldIn(i))+'</small><span class="pr-l">'+price(r[0],r[1])+taHtml(taOf(len?'cut':'stock',i.c),'s')+'</span></span><span class="th">'+pic(i,176)+'<span class="plus">'+ic('plus',18)+'</span></span></button>';
}
function menuHtml(){
  return (ASK?ASK.banner():'')+ /* questionnaire hook */
    FORMS().map((f,n)=>'<section class="sec" data-sec="'+n+'"><h2>'+esc(K.name(f))+'</h2><div class="rows">'+C.cats.filter(c=>c.form===f.id).map(catRow).join('')+'</div></section>').join('')+
    '<section class="sec" data-sec="'+FORMS().length+'"><h2>'+u(laserOn()?'lzT':'customT')+'</h2><div class="rows">'+(laserOn()?laserRow():'')+customRow()+'</div></section><footer class="claim-entry"><button type="button" class="lnk" data-act="claim">'+u('claim')+'</button></footer>';
}
const customText=()=>K.name(C.data.custom)||u('customD',{c:company()});
const laserRow=()=>'<button class="it" type="button" data-act="laser"><span class="tx"><b>'+u('lzT')+'</b><small>'+u('lzRow')+'</small><span class="pr-l"><span class="pr"><i>'+u('lzTag')+'</i></span>'+taHtml(taOf('custom'),'s')+'</span></span><span class="th ico">'+ic('zap',28,1.25)+'<span class="plus">'+ic('plus',18)+'</span></span></button>';
const customRow=()=>'<button class="it" type="button" data-act="custom"><span class="tx"><b>'+u('customT')+'</b><small>'+esc(customText())+'</small><span class="pr-l"><span class="pr"><i>'+u('askT')+'</i></span>'+taHtml(taOf('custom'),'s')+'</span></span><span class="th ico">'+ic('pencil',28,1.25)+'<span class="plus">'+ic('plus',18)+'</span></span></button>';
function tabsHtml(){return '<span class="ink" id="ink"></span>'+FORMS().map((f,n)=>'<button class="tab" type="button" role="tab" data-tab="'+n+'" aria-current="'+(n===S.tab)+'">'+esc(K.name(f))+'</button>').join('')+'<button class="tab" type="button" role="tab" data-tab="'+FORMS().length+'" aria-current="'+(S.tab===FORMS().length)+'">'+u(laserOn()?'lzT':'customT')+'</button>'}
function resultsHtml(){
  const res=K.search(S.q,40);
  if(!res||!res.length)return '<p class="none">'+t('noRes')+'</p><div class="try">'+t('tryQ').map(x=>'<button class="cb" type="button" data-try="'+esc(x)+'">'+esc(x)+'</button>').join('')+'</div><div class="rows" style="margin-top:16px">'+(laserOn()?laserRow():'')+customRow()+'</div>';
  return '<p class="res-n">'+u('found',{n:res.length})+'</p><div class="rows">'+res.map(r=>r.item?itemRow(r.item,r.len):catRow(r.cat)).join('')+'</div>';
}
function renderMenu(){
  const q=!!S.q;
  $('#tabs').hidden=q;$('#secs').hidden=q;$('#res').hidden=!q;$('#clr').hidden=!q;
  if(q){$('#res').innerHTML=resultsHtml();$('#menu').scrollTop=0}else ink();
  pump();
}
/* the sliding mark under the current section */
function ink(){const tabs=$('#tabs'),b=tabs.querySelector('[aria-current="true"]'),i=$('#ink');if(b&&i&&b.offsetWidth){i.style.width=b.offsetWidth+'px';i.style.transform='translateX('+b.offsetLeft+'px)'}}
function setTab(n){
  if(n===S.tab)return;S.tab=n;
  const tabs=$('#tabs');tabs.querySelectorAll('.tab').forEach((b,k)=>b.setAttribute('aria-current',k===n));
  const b=tabs.querySelector('[data-tab="'+n+'"]');if(b)tabs.scrollTo({left:b.offsetLeft-(tabs.clientWidth-b.offsetWidth)/2,behavior:still()?'auto':'smooth'});
  ink();
}
function jump(n,instant){
  const m=$('#menu'),sec=m.querySelector('[data-sec="'+n+'"]');if(!sec)return;
  spyLock=performance.now()+700;setTab(n);
  m.scrollTo({top:sec.offsetTop-$('#bar').offsetHeight+6,behavior:instant||still()?'auto':'smooth'});
}
function watch(){
  if(spy||!('IntersectionObserver' in window))return;
  const m=$('#menu');
  spy=new IntersectionObserver(es=>{if(performance.now()<spyLock)return;es.forEach(e=>{if(e.isIntersecting)setTab(+e.target.dataset.sec)})},{root:m,rootMargin:'-'+($('#bar').offsetHeight+8)+'px 0px -70% 0px',threshold:0});
  m.querySelectorAll('.sec').forEach(s=>spy.observe(s));
}

Object.assign(U.bg,{resumeSlideshow:'Пусни слайдшоуто'});
Object.assign(U.en,{productInfo:'Product information',closeInfo:'Close product information',previousPhoto:'Previous photo',nextPhoto:'Next photo',pauseSlideshow:'Pause slideshow',resumeSlideshow:'Play slideshow',specifications:'Specifications',ordering:'Ordering and cutting',dimensions:'Dimensions',stockLength:'Stock length',cutPrice:'Cutting',selectedProduct:'Selected product',productCode:'Product code'});
Object.assign(U.bg,{productInfo:'Информация за продукта',closeInfo:'Затвори информацията',previousPhoto:'Предишна снимка',nextPhoto:'Следваща снимка',pauseSlideshow:'Пауза на слайдшоуто',specifications:'Характеристики',ordering:'Поръчка и рязане',dimensions:'Размери',stockLength:'Дължина на пръта',cutPrice:'Рязане',selectedProduct:'Избран продукт',productCode:'Код на продукта'});
function sourceHref(path){
  try{const base=new URL(C.data.source),url=new URL(path||base.href,base);return ['https:','http:'].includes(url.protocol)&&url.origin===base.origin?url.href:''}catch(e){return''}
}
function sourceLink(label,href){return href?'<a href="'+esc(href)+'" target="_blank" rel="noopener noreferrer">'+esc(label)+'</a>':esc(label)}
Object.assign(U.en,{sources:'Sources',productPage:'Manufacturer product page',publishedCatalogue:'Published catalogue',cataloguePrice:'Catalogue price',aboutProduct:'About this product'});
Object.assign(U.bg,{sources:'Източници',productPage:'Продуктова страница на производителя',publishedCatalogue:'Публикувана ценова листа',cataloguePrice:'Каталожна цена',aboutProduct:'За продукта'});
function showProductInfo(){
  const i=C.items[S.item],c=i.cat,rule=selling(i),url=c.url&&(c.url[K.L.lang]||c.url.bg||c.url.en),source=url?sourceHref(url):sourceHref(C.data.source);
  const row=(label,value,href)=>value?'<div><dt>'+esc(label)+'</dt><dd>'+sourceLink(value,href)+'</dd></div>':'';
  const details=row(u('productCode'),i.c,source)+row(t('metal'),metalOf(c))+row(u('stdL'),c.std&&K.name(c.std),source)+row(u('dimensions'),i.d?i.d.map(K.dimStr).join(' × ')+' '+t('mm'):K.label(i))+row(u('stockLength'),i.L?K.dimStr(i.L)+' '+M():'')+row(u('weightL'),wOf(i));
  const r=rate(i),cataloguePrice=ask(i)?u('askT'):(r[0]>0?K.eur(r[0],3)+' '+u(r[1]):'');
  const ordering=row(u('cataloguePrice'),cataloguePrice)+row(u('soldL'),soldVal(i))+row(u('cutPrice'),i.cut>0?pr(i.cut)+' '+u('perCutU'):'')+row(u('minimum'),rule.minimum>1?K.num(rule.minimum):'')+row(u('quantityStep'),rule.step>1?K.num(rule.step):'')+row(u('pack'),rule.pack>1?K.num(rule.pack):'');
  const about=[c.info&&K.name(c.info),c.note&&K.name(c.note)].filter(Boolean);
  const references=(url?'<p>'+sourceLink(u('productPage'),source)+'</p>':'')+'<p>'+sourceLink(u('publishedCatalogue'),sourceHref(C.data.source))+'</p>';
  const dialog=$('#product-info');
  dialog.innerHTML='<header class="pi-header"><span>'+u('productInfo')+'</span><button class="ib" type="button" data-act="info-close" aria-label="'+u('closeInfo')+'">'+ic('x',24)+'</button></header><main class="pi-body"><div class="pi-heading"><p class="pi-code">'+sourceLink(i.c,source)+'</p><h1 id="pi-title">'+esc(titleOf(i))+'</h1><p class="pi-material">'+esc(metalOf(c))+'</p></div><section><h2>'+u('specifications')+'</h2><dl>'+details+'</dl></section><section><h2>'+u('ordering')+'</h2><dl>'+ordering+'</dl></section>'+(about.length?'<section><h2>'+u('aboutProduct')+'</h2>'+about.map(text=>'<p class="pi-copy">'+esc(text)+'</p>').join('')+'</section>':'')+'<section class="pi-sources"><h2>'+u('sources')+'</h2>'+references+'</section></main>';
  dialog.showModal();dialog.querySelector('[data-act="info-close"]').focus();
}

/* ---------- item: options of one product ---------- */
function headHtml(){
  const i=shown(),r=rate(i),c=i.cat;
  return '<div><h1>'+esc(titleOf(i))+'</h1><p class="meta">'+esc([metalOf(c),c.std&&K.name(c.std)].filter(Boolean).join(' · '))+'</p></div>'+
    '<div class="ih-r"><div class="rate">'+(r[0]>0?K.eur(r[0],3)+'<em>'+u(r[1])+'</em>':'<em class="ask">'+u('askT')+'</em>')+'</div>'+taHtml(taItem(),'m')+'</div>';
}
const wOf=y=>y.w>0&&!y.validation?(y.L?K.num(y.w/y.L,2)+' '+u('kgm'):K.num(y.w,1)+' '+u('kgs')):'';
function detailsHtml(i){
  const c=i.cat,rule=selling(i),row=(k,v)=>v?'<div><span>'+k+'</span><b>'+esc(v)+'</b></div>':'';
  return '<section class="grp"><div class="g-h"><h3>'+u('detailsL')+'</h3></div><div class="dl">'+row(t('metal'),metalOf(c))+row(u('stdL'),c.std&&K.name(c.std))+row(u('soldL'),soldVal(i))+row(u('weightL'),wOf(i))+row(u('codeL'),i.c)+(rule.minimum>1?row(u('minimum'),K.num(rule.minimum)):'')+(rule.step>1?row(u('quantityStep'),K.num(rule.step)):'')+(rule.pack>1?row(u('pack'),K.num(rule.pack)):'')+'</div>'+
    [c.info&&K.name(c.info),c.note&&K.name(c.note)].filter(Boolean).map(x=>'<p class="snote">'+esc(x)+'</p>').join('')+'</section>';
}
function planHtml(){
  const i=C.items[S.item],p=curPlan(),m=mode(i);
  const note=S.note?'<p class="say amb">'+S.note+'</p>':'';
  if(!p.ok){
    const why=p.why==='quantity'?(p.minimum?u('quantityHint',{min:p.minimum,step:p.step}):(K.L.lang==='en'?'Enter a whole quantity from 1 to 999 per row, up to 3,000 pieces.':'Въведете цяло количество от 1 до 999 на ред, до 3000 броя.')):p.why==='angle'?(K.L.lang==='en'?'Enter an angle from 30° to 150°.':'Въведете ъгъл от 30° до 150°.'):p.why==='long'?t('tooLong',{v:K.num(p.max)}):p.why==='big'?t('tooBig',{w:K.num(p.max[0]),l:K.num(p.max[1])}):p.why==='nocut'?t('wholeOnly',{v:p.lens.map(x=>K.dimStr(x/1000)+' m').join(', ')}):t('enterLen');
    return '<p class="say err">'+why+'</p>';
  }
  let h=note;
  if(m==='bar'&&i.r.k!=='any'){
    h+=p.units.slice(0,6).map(x=>{const used=x.cut.reduce((a,b)=>a+b,0),rest=x.len-used;return '<div class="bar"><span class="nw">'+(x.count>1?x.count+X:'')+K.dimStr(x.len/1000)+' '+(K.L.lang==='en'?'m':'м')+'</span><div>'+x.cut.map(c=>'<i style="--w:'+c+'"></i>').join('')+(rest>P.KERF?'<u style="--w:'+rest+'"></u>':'')+'</div></div>'}).join('');
  }
  if(m!=='piece'){
    const off=m==='sheet'?0:Math.round(p.offcut-(p.cuts?p.cuts*P.KERF:0));
    h+='<p class="say">'+t('youBuy')+' '+buyText(i,p)+'. '+(m==='sheet'?'':off>P.KERF?(p.units.length>1||p.units[0].count>1?t('offcuts',{v:K.num(Math.max(0,off))}):t('offcut',{v:K.num(Math.max(0,off))})):p.cuts?t('exact'):t('noCuts'))+'</p>';
  }
  const limited=P.rules.partLength?.limits?.[i.L];
  if(m==='bar'&&limited&&p.units?.some(x=>limited[x.len/1000]))h+='<p class="snote">'+(K.L.lang==='en'?'One '+Object.keys(limited).join(' or ')+' m piece per order line; further pieces use whole bars.':'Едно парче '+Object.keys(limited).join(' или ')+' м на ред; следващите парчета са от цели пръти.')+'</p>';
  if(p.pending)h+='<p class="snote">'+esc(u('submitNote',{c:company()}))+'</p>';
  return h;
}
const cellW=a=>Math.max(72,Math.min(220,Math.max.apply(null,a.map(x=>String(x).length))*8+26));
function optsHtml(){
  const i=C.items[S.item],cat=i.cat,m=mode(i),H=K.HEAD[cat.shape]||K.HEAD.special;
  const grp=(title,right,body)=>'<section class="grp"><div class="g-h"><h3>'+title+'</h3>'+(right?'<small>'+right+'</small>':'')+'</div>'+body+'</section>';
  const lv=K.levels(cat),gi=lv.findIndex(g=>g.items.indexOf(i)>=0),g=lv[gi],unit=i.d?', '+t('mm'):'';
  let h='';
  /* first choice: the outer size, as cells with nothing around them */
  if(lv.length>1)h+=grp(t(H[0])+unit,'','<div class="szs" style="--w:'+cellW(lv.map(x=>x.key))+'px">'+lv.map((x,n)=>'<button class="sz" type="button" data-g="'+n+'" aria-pressed="'+(n===gi)+'">'+esc(x.key)+'</button>').join('')+'</div>');
  /* second choice: the variants of that size, each with what it changes: weight and price */
  if(g.items.length>1)h+=grp(lv.length>1?t(H[1])+(H[1]!=='grade'&&H[1]!=='format'?unit:''):t(H[0])+unit,'','<div class="vars" role="radiogroup">'+g.items.map(y=>{const r=rate(y);
    return '<button class="var" type="button" role="radio" data-size="'+y.c+'" aria-checked="'+(y===i)+'"><i></i><b>'+esc(((lv.length>1?K.k2(y):K.label(y))||K.label(y))+(g.items.filter(z=>K.k2(z)===K.k2(y)).length>1?' · '+K.dimStr(y.L)+' '+M()+(g.items.filter(z=>K.k2(z)===K.k2(y)&&z.L===y.L).length>1?' · '+y.c:''):''))+'</b><span>'+wOf(y)+'</span><em>'+(r[0]>0?K.eur(r[0],3)+'<small>'+u(r[1])+'</small>':u('onConf'))+'</em></button>'}).join('')+'</div>');
  const stepper=(val,attr)=>'<span class="step"><button type="button" '+attr+' data-d="-1" aria-label="−">'+ic('minus',16)+'</button><input type="text" inputmode="numeric" autocomplete="off" value="'+esc(val)+'" '+attr+' data-f="n" aria-label="'+t('qty')+'"><button type="button" '+attr+' data-d="1" aria-label="+">'+ic('plus',16)+'</button></span>';
  if(m==='bar'){
    h+=grp(t('cut'),soldVal(i),'<div class="cl">'+S.rows.map((r,n)=>'<div class="row"><label class="field"><input type="text" inputmode="numeric" autocomplete="off" value="'+esc(r.x)+'" data-row="'+n+'" data-f="x" aria-label="'+t('len')+'"><span>'+t('mm')+'</span></label><span class="times">×</span>'+stepper(r.n,'data-row="'+n+'"')+(S.rows.length>1?'<button class="xb" type="button" data-del="'+n+'" aria-label="'+t('remove')+'">'+ic('x',16)+'</button>':'')+'</div>').join('')+'</div>'+
      '<div class="more"><button class="cb" type="button" data-act="addrow"'+(S.rows.length>=100?' disabled':'')+'>'+ic('plus',14)+t('addLen')+'</button>'+(i.r.k==='len'?i.r.l.map(l=>'<button class="cb" type="button" data-full="'+Math.round(l*1000)+'">'+t('fullBar',{l:K.dimStr(l)})+'</button>').join(''):'')+'</div><div class="plan" id="plan">'+planHtml()+'</div>');
    if(i.cut>0&&!ask(i)){
      const ch=(v,name,amt)=>'<button class="var" type="button" role="radio" data-angle="'+v+'" aria-checked="'+(!!S.angle===!!v)+'"><i></i><b>'+name+'</b><span></span><em>'+pr(amt)+'<small> '+u('perCutU')+'</small></em></button>';
      h+=grp(u('cutType'),'','<div class="vars" role="radiogroup">'+ch(0,u('straight'),i.cut)+ch(1,u('angleCut'),i.cut*(P.rules.angleCutFactor||1))+'</div>'+(S.angle?'<div class="grid2 angle-options"><label class="fl"><input type="number" min="30" max="150" value="'+esc(S.angle.degrees??90)+'" data-angle-degrees><span>'+(K.L.lang==='en'?'Angle, degrees':'Ъгъл, градуси')+'</span></label><label class="fl"><select data-angle-ends><option value="1"'+(S.angle.ends===2?'':' selected')+'>'+(K.L.lang==='en'?'One end':'Един край')+'</option><option value="2"'+(S.angle.ends===2?' selected':'')+'>'+(K.L.lang==='en'?'Both ends':'Двата края')+'</option></select></label></div>':''));
    }
  }else if(m==='sheet'){
    h+=grp(t('sheetCut'),u('upTo',{v:K.num(i.d[2])+X+K.num(i.d[1])}),'<div class="row"><label class="field"><input type="text" inputmode="numeric" autocomplete="off" value="'+esc(S.sheet.a)+'" data-sf="a" aria-label="'+t('len')+'"><span>'+t('mm')+'</span></label><span class="times">×</span><label class="field"><input type="text" inputmode="numeric" autocomplete="off" value="'+esc(S.sheet.b)+'" data-sf="b" aria-label="'+t('wid')+'"><span>'+t('mm')+'</span></label><span class="times">×</span>'+stepper(S.sheet.n,'data-sf="n"')+'</div>'+
      '<div class="more">'+[[i.d[2],i.d[1]],[i.d[2]/2,i.d[1]],[1000,500],[500,500]].filter((p,n,a)=>a.findIndex(q=>q[0]===p[0]&&q[1]===p[1])===n).map(p=>'<button class="cb" type="button" data-pc="'+p[0]+'x'+p[1]+'">'+K.num(p[0])+X+K.num(p[1])+'</button>').join('')+'</div><div class="plan" id="plan">'+planHtml()+'</div>');
  }else h+=grp(i.u==='kg'?u('weightL')+', '+u('kgU'):t('qty'),'','<div class="row">'+stepper(S.rows[0].n,'data-row="0"')+'</div><div class="plan" id="plan">'+planHtml()+'</div>');
  if(ask(i))h+='<p class="snote">'+esc(u('askSub',{c:company()}))+'</p>';
  return h+detailsHtml(i);
}
function barHtml(){
  const i=C.items[S.item],p=curPlan(),lab=S.editing>=0?t('update'):t('add');
  const full=S.editing<0&&S.basket.length>=100;
  if(p.ok&&p.ask)return '<div class="tot"><span class="t1"><b class="word">'+u('onConf')+'</b></span><small>'+u('askT')+'</small></div>'+taHtml(taItem(),'s')+'<button class="act" type="button" data-act="add"'+(full?' disabled':'')+'><span class="lg">'+lab+'</span><span class="sh">'+u('short')+'</span>'+ic('arrow-right',18)+'</button>';
  return '<button class="tot" type="button" data-act="pd" aria-expanded="'+(S.pd&&p.ok)+'"'+(p.ok?'':' disabled')+'><span class="t1"><b id="num">'+(p.ok?pr(p.total):'—')+'</b>'+(p.ok?ic('chevron-down',16):'')+'</span><small>'+(p.ok?(p.pending?u('estPrice'):vatW()):'')+'</small></button>'+taHtml(taItem(),'s')+
    '<button class="act" type="button" data-act="add"'+(p.ok&&!full?'':' disabled')+'><span class="lg">'+lab+'</span><span class="sh">'+u('short')+'</span>'+ic('arrow-right',18)+'</button>';
}
function pdHtml(){
  const i=C.items[S.item],p=curPlan(),sheet=mode(i)==='sheet';if(!p.ok)return'';
  return '<div class="sums"><div><span>'+esc(buyText(i,p))+(p.kg>0?' · '+t('kg',{v:K.num(p.kg,1)}):'')+'</span><b>'+pr(p.base)+'</b></div>'+
    (p.sur>.004?'<div><span>'+u(sheet?'surSheet':'surBar')+'</span><b>'+pr(p.sur)+'</b></div>':'')+
    (p.cuts&&p.cutCost>0?'<div><span>'+(p.angle?u('angleCut'):t('cutting'))+' · '+(sheet&&p.cuts===1?(K.L.lang==='en'?'1 severing cut, double rate (2 × ':'1 разделителен срез, двойна цена (2 × ')+pr(i.cut)+')':cutsText(p.cuts)+' × '+pr(p.cutCost/p.cuts))+'</span><b>'+pr(p.cutCost)+'</b></div>':'')+
    '<div class="sum-t"><span>'+u('totalIn')+'</span><b>'+pr(p.total)+'</b></div>'+
    '<div><span>'+u('ofVat')+'</span><b>'+K.eur(p.total-p.total/(1+C.data.vat))+'</b></div></div>';
}
function renderLive(){ /* everything that follows the numbers, leaving the inputs alone */
  const i=shown(),was=$('#num')&&$('#num').textContent;
  $('#ihead').innerHTML=headHtml();$('#ibar').innerHTML=barHtml();
  const nu=$('#num');if(was&&nu&&nu.textContent!==was)nu.classList.add('tick');
  const pd=$('#pd');pd.hidden=!S.pd;if(S.pd)pd.innerHTML=pdHtml();
  const dw=$('#draw');dw.hidden=!i.d;if(i.d)dw.innerHTML=drawSvg(window.RocotoGeom.geomOf(i.cat.shape,i.d));
  const sl=slidesOf(i.cat,i),hero=$('#hero'),key=i.c+'|'+sl.join('|');
  hero.classList.toggle('schematic',!sl.length&&!!i.d);hero.hidden=!sl.length&&!i.d;
  if(hero.dataset.k!==key){
    hero.dataset.k=key;S.slide=0;hero.classList.toggle('gen',!!setOf(i.cat,i));hero.style.background=setOf(i.cat,i)&&GEN.bg?GEN.bg:'';
    $('#slides').innerHTML=sl.map((x,n)=>'<img src="'+x+'" alt=""'+(n?' loading="lazy"':'')+' draggable="false">').join('');
    $('#dots').innerHTML=sl.length>1?sl.map((x,n)=>'<button type="button" data-slide="'+n+'" aria-label="'+(n+1)+' / '+sl.length+'"></button>').join(''):'';
    $('#prev').hidden=$('#nxt').hidden=$('#slideshow').hidden=sl.length<2;slideTo(0);
  }
}
function renderItem(){$('#iopts').innerHTML=optsHtml();renderLive()}

/* ---------- basket: the right 3/8 ---------- */
function lineHtml(l,n,ro){
  const ctl=(single,q,fixed)=>ro?'':'<div class="l-ctl">'+(single?'<span class="stp"><button type="button" data-ld="-1" data-n="'+n+'" aria-label="'+(q<=1?t('remove'):'−')+'">'+ic(q<=1?'trash-2':'minus',14)+'</button><span>'+q+'</span><button type="button" data-ld="1" data-n="'+n+'" aria-label="+">'+ic('plus',14)+'</button></span>':'')+(fixed?'':'<button class="lnk" type="button" data-edit="'+n+'">'+t('edit')+'</button>')+(single?'':'<button class="lnk" type="button" data-rm="'+n+'">'+t('remove')+'</button>')+'</div>';
  const cls='line'+(!ro&&n===S.fresh?' arrived':'');
  if(l.custom)return '<div class="'+cls+'"><span class="lt ico">'+ic(l.file?'file-text':'pencil',18)+'</span><div><b>'+u('customT')+'</b><small class="clamp">'+esc(l.custom)+'</small>'+(l.file?'<small class="file-line">'+esc(l.file.name)+'</small>':'')+taHtml(taLine(l),'s')+ctl(false,0)+'</div><div class="amt soft">'+u('quoteItem')+'</div></div>';
  if(l.laser){const v=l.view,q=l.laser.quantity,quoted=S.view!=='done'&&currentQuote()?.lines?.[n]?.gross;
    return '<div class="'+cls+'"><span class="lt lz">'+(v.thumb?'<img src="'+v.thumb+'" alt="">':LZ.picture(v))+'<i>'+q+'</i></span><div><b>'+u('lzT')+'</b><small>'+esc(v.name)+'</small><small>'+esc(K.name(v)+' · '+K.dimStr(l.laser.thickness)+' '+t('mm'))+'</small>'+taHtml(taLine(l),'s')+ctl(true,q,!LZC[l.laser.id])+
      '</div><div class="amt">'+pr(typeof quoted==='number'?quoted:lzTotal(l))+'<small>'+u('lzEstShort')+'</small></div></div>'}
  const i=C.items[l.code],p=(S.view!=='done'&&currentQuote()?.lines?.[n]?.plan)||linePlan(l),single=!!l.sheet||l.rows.length===1,q=l.sheet?l.sheet.n:l.rows[0].n,pc=mode(i)==='piece'&&!(ask(i)&&i.L);
  const sub=l.sheet?K.num(l.sheet.a)+X+K.num(l.sheet.b)+' '+t('mm'):pc?'':single?u('each2',{v:K.num(l.rows[0].x)}):l.rows.map(r=>r.n+X+K.num(r.x)+' '+t('mm')).join(' · ');
  return '<div class="'+cls+'"><span class="lt">'+pic(i)+(single?'<i>'+q+(i.u==='kg'?' '+u('kgU'):'')+'</i>':'')+'</span><div><b>'+esc(titleOf(i))+'</b>'+(sub||l.angle?'<small>'+esc(sub)+(l.angle?(sub?' · ':'')+u('angleCut')+' '+(l.angle.degrees||90)+'° · '+(l.angle.ends===2?(K.L.lang==='en'?'both ends':'двата края'):(K.L.lang==='en'?'one end':'един край')):'')+'</small>':'')+
    (p.ok&&!p.ask&&mode(i)==='bar'&&i.r.k!=='any'?'<small>'+t('youBuy')+' '+esc(buyText(i,p))+'</small>':'')+taHtml(taLine(l),'s')+ctl(single,q)+
    '</div><div class="amt'+(p.ask?' soft':'')+'">'+(p.ask?u('quoteItem'):pr(p.ok?p.total:0))+'</div></div>';
}
function basketHtml(){
  const done=S.view==='done'&&S.done,co=S.view==='co',ro=co||!!done,lines=done?S.done.lines:S.basket,has=lines.length>0;
  const quoted=!done&&currentQuote(),tot=quoted?quoted.quote.gross:lines.reduce((a,l)=>a+lineTotal(l),0),del=(done?S.done.fulfil:S.fulfil)==='delivery',ship=0,all=tot,ex=quoted?quoted.quote.net:all/(1+C.data.vat);
  const anyAsk=lines.some(lineAsk);
  const chosen=!!done||co,delv=del&&chosen;
  /* the order's turnaround stays at the top of the panel: the slowest line decides; a date the server has quoted sits beside it */
  const days=has?taBasket(lines):null,when=!done&&!delv&&!lines.some(l=>l.custom||l.laser)&&readyWindow(currentQuote()?.ready);
  return '<div class="b-top"><div class="b-head"><h2>'+(co?u('orderSum'):u('yourBasket'))+'</h2><button class="ib" type="button" data-act="bask-close" aria-label="'+t('close')+'">'+ic('x',18)+'</button></div>'+
    (has&&(days||when)?taHtml(days,'',!taTier(days)&&when?u('est',{when:when}):'',taTier(days)&&when?when:''):'')+
    (chosen?'<div class="b-info"><div class="i-row">'+ic(del?'truck':'map-pin',18)+'<span><b>'+u(del?'segDel':'segPick')+'</b><small>'+esc(del?((S.hasd&&addrLine('d'))||u('delAt')):u('pickAddr'))+'</small></span></div></div>':'')+'</div>'+
    '<div class="b-lines">'+(has?'<h3>'+t('summary')+'</h3>'+lines.map((l,n)=>lineHtml(l,n,ro)).join(''):'<div class="empty">'+ic('shopping-basket',22,1.5)+'<p>'+u('empty')+'</p></div>')+
      (ro?'':'<div class="tiles">'+(laserOn()?'<button type="button" data-act="laser">'+ic('zap',18)+'<span>'+u('lzT')+'</span></button>':'')+'<button type="button" data-act="custom">'+ic('pencil',18)+'<span>'+u('customT')+'</span></button></div>')+
      '</div>'+
    '<div class="b-foot">'+(has&&(!anyAsk||all>0)?'<h3>'+u('sumL')+'</h3><div class="sums"><div><span>'+t('subtotal')+'</span><b>'+K.eur(ex)+'</b></div><div><span>'+t('vat')+'</span><b>'+K.eur(all-ex)+'</b></div>'+(delv?'<div><span>'+t('delivery')+'</span><b>'+u('quoteDelivery')+'</b></div>':'')+
        '<div class="sum-t"><span>'+(anyAsk?u('pricedItems'):t('total'))+'</span><b id="btot">'+pr(all)+'</b></div></div>'+(C.data.asOf?'<p class="fine">'+esc(u('listNote',{v:asOf()}))+'</p>':''):has&&!co?'<p class="say">'+u('quoteTotal')+'</p>':'')+
      (REMOTE.error?'<p class="hint err" role="alert">'+esc(REMOTE.error)+' <button type="button" class="lnk" data-act="retry-quote">'+u('retry')+'</button></p>':'')+(ro?'':'<button class="act" type="button" data-act="checkout"'+(has?'':' disabled')+'>'+u('goCheckout')+ic('arrow-right',18)+'</button>')+'</div>';
}
function renderBasket(){
  scheduleQuote();
  const was=$('#btot')&&$('#btot').textContent;
  $('#basket').innerHTML=basketHtml();
  const bt=$('#btot');if(was&&bt&&bt.textContent!==was)bt.classList.add('tick');
  const n=S.basket.length,mc=$('#mcart');mc.hidden=!(n&&(S.view==='menu'||S.view==='pick'));
  if(n)mc.innerHTML='<span><i class="cnt'+(S.fresh>=0?' pop':'')+'">'+n+'</i>'+u('viewBasket')+'<b>'+(S.basket.some(lineAsk)?u('onConf'):pr(basketTotal()))+'</b></span>';
  pump();
}

/* ---------- freeform work: retained as an unpriced request until the company specifies it ---------- */
function customHtml(){
  const error=S.bad?'<p class="hint err" role="alert">'+esc(u(S.bad))+'</p>':'';
  const file=S.customFile,upload=S.uploading;
  const drop=file?'':'<label class="file-drop" id="file-drop">'+ic('file-text',28,1.4)+'<span><b>'+esc(upload?u('uploadingFile',{name:S.uploadName||u('designFile')}):u('dropFile'))+'</b><small>'+u('chooseFile')+'</small><em>'+u('fileTypes')+'</em></span><input id="design-file" data-upload type="file" accept=".pdf,.png,.jpg,.jpeg,.webp,.dxf,.dwg,.step,.stp,.stl,.obj"'+(upload?' disabled':'')+'></label>';
  const attached=file?'<div class="file-card">'+ic('file-text',22,1.5)+'<span><b>'+esc(file.name)+'</b><small>'+Math.max(1,Math.ceil(file.size/1024))+' KB · '+u('fileReady')+'</small></span><button type="button" class="ib" data-act="remove-file" aria-label="'+u('removeFile')+'"'+(upload?' disabled':'')+'>'+ic('x',17)+'</button></div>':'';
  return '<div class="q"><h1>'+u('customHead')+'</h1><p class="q-sub">'+esc(customText())+'</p>'+
    drop+attached+'<label class="fl area custom-notes"><textarea class="tall" data-custom maxlength="4000" placeholder="'+esc(u('customPh'))+'" aria-label="'+u('customNotes')+'">'+esc(S.custom)+'</textarea></label>'+error+'</div>';
}
function addCustom(){
  const description=String(S.custom||'').trim();
  if(S.uploading)return;
  if(!description&&!S.customFile){S.bad='needText';return renderAll()}
  if(description.length>4000){S.bad='customLimit';return renderAll()}
  if(S.editing<0&&S.basket.length>=100){S.bad='lineLimit';return renderAll()}
  const previous=S.editing>=0&&S.basket[S.editing]?.file,customFileNow=S.customFile;
  const line={custom:description||u('designOnly',{name:S.customFile.name}),...(S.customFile?{upload_id:S.customFile.id,file:S.customFile}:{})};
  if(S.editing>=0&&S.basket[S.editing]){S.basket[S.editing]=line;S.fresh=S.editing}else{S.basket.push(line);S.fresh=S.basket.length-1}
  S.custom='';S.customFile=null;S.bad='';save();showMenu();setTimeout(()=>{S.fresh=-1},600);
  if(previous&&previous.id!==customFileNow?.id&&!uploadReferenced(previous.id))discardUpload(previous).catch(()=>{});
}

/* ---------- checkout: the customer submits an order request; the company accepts it by e-mail ---------- */
Object.assign(U.en,{quoteItem:'To quote',quoteTotal:'Quote by email',requestLine:'1 item',requestLines:'{n} items',quoteDelivery:'Price with your quote',requestSubmit:'Request a quote',requestNote:'{c} will email you the price and delivery date for approval.',contactName:'Contact name',needName:'Enter your contact name.'});
Object.assign(U.bg,{quoteItem:'За оферта',quoteTotal:'Оферта по имейл',requestLine:'1 позиция',requestLines:'{n} позиции',quoteDelivery:'Цена с офертата',requestSubmit:'Изпрати запитване',requestNote:'{c} ще изпрати цена и срок по имейл за вашето одобрение.',contactName:'Лице за контакт',needName:'Въведете име за контакт.'});
const AC={company:'organization',website:'url',email:'email',phone:'tel',name:'name',line1:'address-line1',line2:'address-line2',zip:'postal-code',city:'address-level2',coName:'organization',bline1:'billing address-line1',bline2:'billing address-line2',bzip:'billing postal-code',bcity:'billing address-level2'};
/* ---------- checkout: one page, in the order a shop's checkout runs: contact, receiving, address, invoice, notes ---------- */
Object.assign(U.en,{secContact:'Contact',addrL:'Address',aptL:'Apartment, floor, entrance',editOrder:'Edit order',orderSum:'Order summary',useHere:'Use my location',phoneDel:'Phone for the delivery',coSame:'Company address is the delivery address',hereLabel:'My location',needCoAddr:'Enter the company address.',needAddr:'Enter the delivery address.'});
Object.assign(U.bg,{secContact:'Контакт',addrL:'Адрес',aptL:'Апартамент, етаж, вход',editOrder:'Промени поръчката',orderSum:'Обобщение на поръчката',useHere:'Използвай моето местоположение',phoneDel:'Телефон за доставката',coSame:'Адресът на фирмата е адресът за доставка',hereLabel:'Моето местоположение',needCoAddr:'Въведете адреса на фирмата.',needAddr:'Въведете адрес за доставка.'});
Object.assign(U.bg,{poNumber:'Номер на поръчка (PO) · по избор',warehouse:'Склад за изпълнение',warehouseChoose:'Изберете склад',warehouseConfirm:'Потвърждавам склада за тази поръчка',needWarehouse:'Изберете склад и потвърдете получаването.'});
Object.assign(U.en,{poNumber:'Purchase order (PO) · optional',warehouse:'Fulfilment warehouse',warehouseChoose:'Choose a warehouse',warehouseConfirm:'I confirm the warehouse for this order',needWarehouse:'Choose and confirm the fulfilment warehouse.'});
const checkoutWarehouses=()=>S.demoOrder?.warehouses||S.capture?.demo_order?.warehouses||CFG.checkout?.warehouses||[];
const warehouseText=value=>typeof value==='string'?value:value?.[K.L.lang]||value?.bg||value?.en||'';
S.errs={};
const errP=k=>S.errs[k]?'<p class="ferr" id="co-error-'+k+'" role="alert">'+esc(u(S.errs[k]))+'</p>':'';
function clearErr(k,el){
  if(!S.errs[k])return;delete S.errs[k];
  const l=(el||root.querySelector('[data-co="'+k+'"]'))?.closest('.fl');if(!l)return;
  l.classList.remove('bad');const input=l.querySelector('input');input?.removeAttribute('aria-invalid');input?.removeAttribute('aria-describedby');const e=l.parentNode.querySelector('.ferr');if(e)e.remove();
}
/* one field: a floating label, an icon at its right end where it helps, its own message under it */
const fld=(k,lab,type,cls,icon)=>'<div class="f'+(cls?' '+cls:'')+'"><label class="fl'+(icon?' has-acc':'')+(S.errs[k]?' bad':'')+'"><input type="'+(type||'text')+'" data-co="'+k+'" value="'+esc(S.co[k]||'')+'" placeholder=" " autocomplete="'+(AC[k]||'off')+'"'+(['name','email','phone','company','coName','eik'].includes(k)?' aria-required="true"':'')+(S.errs[k]?' aria-invalid="true" aria-describedby="co-error-'+k+'"':'')+(type==='email'?' inputmode="email" autocapitalize="off" spellcheck="false"':type==='tel'?' inputmode="tel"':'')+'><span>'+lab+'</span>'+(icon?'<i class="acc">'+ic(icon,18)+'</i>':'')+'</label>'+errP(k)+'</div>';
/* the map is Google's own embed: with a browser key from config, or the keyless embed address. One frame for the whole visit:
   made once, warmed as the checkout opens, moved by its address alone, kept through every repaint of the form around it */
const MAP={el:null,src:''};
const mapSrc=(q,z)=>{const e=encodeURIComponent(q);return CFG.mapsKey?'https://www.google.com/maps/embed/v1/place?key='+CFG.mapsKey+'&q='+e+'&zoom='+z+'&language='+K.L.lang:'https://maps.google.com/maps?q='+e+'&z='+z+'&hl='+K.L.lang+'&output=embed'};
function mapAt(){const c=S.co;if(c.lat!=null&&c.lat!=='')return[c.lat+','+c.lng,16];if(S.hasd&&addrLine('d'))return[addrLine('d'),16];if(S.near)return[S.near.lat+','+S.near.lng,14];return[CFG.mapHome||'Bulgaria',7]}
function mapSync(){
  const box=$('#comap');if(!box)return;
  const on=S.view==='co'&&S.fulfil==='delivery';box.classList.toggle('on',on);
  if(!on&&!(S.view==='co'&&S.mapWarm))return;
  const a=mapAt(),src=mapSrc(a[0],a[1]);
  if(!MAP.el){MAP.el=document.createElement('iframe');MAP.el.className='map';MAP.el.title=t('address');MAP.el.setAttribute('referrerpolicy','no-referrer-when-downgrade');MAP.el.addEventListener('load',()=>{const b=$('#comap');if(b)b.classList.add('ready')})}
  if(MAP.el.parentNode!==box){box.appendChild(MAP.el);MAP.src=''}
  if(MAP.src!==src){MAP.src=src;box.classList.remove('ready');MAP.el.src=src}
}
/* the customer's own position, asked once they choose delivery: it centres the map and brings nearby streets first */
function locate(then){
  if(S.near){if(then)then(S.near);return}
  if(!navigator.geolocation||(S.nearAsked&&!then))return;S.nearAsked=true;
  navigator.geolocation.getCurrentPosition(p=>{S.near={lat:+p.coords.latitude.toFixed(5),lng:+p.coords.longitude.toFixed(5)};if(then)then(S.near);else if(S.view==='co')mapSync()},()=>{const b=root.querySelector('[data-act="here"]');if(b)b.classList.remove('busy')},{enableHighAccuracy:!!then,timeout:8000,maximumAge:then?0:600000});
}
const suggHtml=()=>(S.sugg||[]).map((x,n)=>'<button type="button" data-sugg="'+n+'">'+ic('map-pin',16)+'<span><b>'+esc(x.main)+'</b><small>'+esc(x.secondary||'')+'</small></span></button>').join('');
const ADDR={d:['line1','line2','zip','city'],b:['bline1','bline2','bzip','bcity']};
const addrLine=w=>{const k=ADDR[w],c=S.co;return[c[k[0]],c[k[1]],[c[k[2]],c[k[3]]].filter(Boolean).join(' ')].filter(Boolean).join(', ')};
/* a chosen suggestion or the customer's position fills the street line, the postcode and the town in place */
function addrApply(w,o){
  const k=ADDR[w];S.co[k[0]]=o.line1||'';if(o.zip!=null)S.co[k[2]]=o.zip;if(o.city!=null)S.co[k[3]]=o.city;S['has'+w]=!!S.co[k[0]];
  if(w==='d'){S.co.lat=o.lat!=null?o.lat:null;S.co.lng=o.lng!=null?o.lng:null;S.co.address=addrLine('d')}
  S.geoFor=w;S.aq=S.co[k[0]];const el=$('#aq'+w);if(el){el.value=S.aq;clearErr(k[0],el)}
  [k[2],k[3]].forEach(f=>{const i=root.querySelector('[data-co="'+f+'"]');if(i)i.value=S.co[f]||''});
  if(w==='d')mapSync();renderBasket();
}
function useHere(){
  const b=root.querySelector('[data-act="here"]');if(b)b.classList.add('busy');
  locate(n=>{
    const done=o=>{const x=root.querySelector('[data-act="here"]');if(x)x.classList.remove('busy');S.sugg=[];paintSugg();addrApply('d',o)};
    geoGet('api/here?lat='+n.lat+'&lng='+n.lng+'&lang='+K.L.lang).then(d=>done(d&&d.ok?{line1:d.line1,zip:d.zip||'',city:d.city||'',lat:n.lat,lng:n.lng}:{line1:u('hereLabel')+' ('+n.lat.toFixed(5)+', '+n.lng.toFixed(5)+')',lat:n.lat,lng:n.lng}))
      .catch(()=>done({line1:u('hereLabel')+' ('+n.lat.toFixed(5)+', '+n.lng.toFixed(5)+')',lat:n.lat,lng:n.lng}));
  });
}
/* the address: one line with suggestions and the position button at its right end, then apartment, postcode and town */
function addrHtml(w){
  const k=ADDR[w],here=w==='d'&&!!navigator.geolocation;
  return '<div class="addr-box"><label class="fl has-acc'+(S.errs[k[0]]?' bad':'')+'"><input type="text" data-addr="'+w+'" id="aq'+w+'" role="combobox" aria-autocomplete="list" autocomplete="'+(w==='b'?'billing ':'')+'address-line1" autocorrect="off" spellcheck="false" enterkeyhint="next" value="'+esc(S.co[k[0]]||'')+'" placeholder=" "><span>'+u('addrL')+'</span>'+
    (here?'<button type="button" class="acc" data-act="here" aria-label="'+u('useHere')+'" title="'+u('useHere')+'">'+ic('locate-fixed',18)+'</button>':'<i class="acc">'+ic('search',18)+'</i>')+'</label><div class="sugg" id="sugg'+w+'">'+(S.geoFor===w?suggHtml():'')+'</div>'+errP(k[0])+'</div>'+
    '<div class="grid2 a-rest">'+fld(k[1],u('aptL')+' · '+u('optional'),'text','wide')+fld(k[2],u('zip'))+fld(k[3],t('city'))+'</div>';
}
Object.assign(U.en,{secCompany:'Your company and project',companyName:'Company name',website:'Website · optional',trade:'Type of work · optional',project:'Project · optional',projectPh:'Your project, building type, or how you will use these products',needCompany:'Enter your company name.'});
Object.assign(U.bg,{secCompany:'Вашата фирма и проект',companyName:'Име на фирмата',website:'Уебсайт · по желание',trade:'Дейност · по желание',project:'Проект · по желание',projectPh:'Вашият проект, вид сграда или за какво ще използвате продуктите',needCompany:'Въведете името на фирмата.'});
if(CFG.checkout?.customerResearch===false){U.bg.secCompany='Вашата фирма';U.en.secCompany='Your company'}
const CO={
  company:()=>'<div class="grid2">'+fld('company',u('companyName'),'text','wide','building-2')+(CFG.checkout?.customerResearch===false?'':fld('website',u('website'),'text')+fld('trade',u('trade'),'text'))+'</div>'+(CFG.checkout?.customerResearch===false?'':'<label class="pick-label">'+u('project')+'<textarea data-co="project" maxlength="2000" placeholder="'+esc(u('projectPh'))+'">'+esc(S.co.project||'')+'</textarea></label>'),
  contact:()=>'<div class="grid2">'+fld('name',u('contactName'),'text','wide','user')+fld('email',t('email'),'email','','mail')+fld('phone',t('phone'),'tel','','phone')+'</div>',
  receive:()=>{const o=(v,icon,name,sub,right)=>'<button class="opt" type="button" role="radio" data-fulfil="'+v+'" aria-checked="'+(S.fulfil===v)+'"><i class="rd"></i><span class="oi">'+ic(icon,20)+'</span><span><b>'+name+'</b><small>'+esc(sub)+'</small></span><em>'+right+'</em></button>';
    return '<div class="opts" role="radiogroup" aria-label="'+u('qReceive')+'">'+o('pickup','store',t('pick'),t('pickSub'),t('free'))+o('delivery','truck',t('deliver'),t('deliverSub'),u('quoteDelivery'))+'</div>'},
  addr:()=>S.fulfil==='delivery'?'<h3 class="sub3">'+u('qAddress')+'</h3>'+addrHtml('d'):'',
  invoice:()=>{const co=S.inv==='company',same=S.fulfil==='delivery'&&!S.billOther;
    const chk=(on,attr,label)=>'<button type="button" class="chk" role="checkbox" aria-checked="'+on+'" '+attr+'><i>'+ic('check',14,2.5)+'</i><span>'+label+'</span></button>';
    return chk(co,'data-inv="'+(co?'person':'company')+'"',u('addCo'))+
      (co?'<div class="grid2 co-f">'+fld('coName',t('coName'),'text','wide','building-2')+fld('eik',t('eik'))+fld('vatNo',t('vatNo'))+fld('mol',t('mol'),'text','wide')+'</div>'+
        (S.fulfil==='delivery'?chk(!S.billOther,'data-act="bill-toggle"',u('coSame')):'')+(same?'':'<h3 class="sub3">'+u('coAddr')+'</h3>'+addrHtml('b')):'')},
  recurring:()=>{const on=S.co.recurring==='recurring',f=S.co.recurringFrequency||'monthly';
    const o=(v,icon,name,sub)=>'<button class="opt" type="button" role="radio" data-rec="'+v+'" aria-checked="'+((v==='recurring')===on)+'"><i class="rd"></i><span class="oi">'+ic(icon,20)+'</span><span><b>'+name+'</b><small>'+sub+'</small></span></button>';
    return '<div class="opts" role="radiogroup" aria-label="'+u('recQ')+'">'+o('one-off','package',u('recOnce'),u('recOnceSub'))+o('recurring','repeat',u('recYes'),u('recYesSub'))+'</div>'+
      (on?'<div class="szs rec-f" style="--w:148px">'+REC.map(x=>'<button class="sz" type="button" data-recf="'+x[0]+'" aria-pressed="'+(x[0]===f)+'">'+u(x[1])+'</button>').join('')+'</div><div class="grid2 co-f">'+fld('recurringNote',u('recNote')+' · '+u('optional'),'text','wide')+'</div>':'')},
  reference:()=>fld('poNumber',u('poNumber'),'text'),
  warehouse:()=>{const options=checkoutWarehouses();if(!options.length)return '';const selected=options.find(w=>w.id===S.co.warehouseId);return '<div class="warehouse-field"><label class="pick-label">'+u('warehouse')+'<select data-warehouse aria-label="'+u('warehouse')+'"><option value="">'+u('warehouseChoose')+'</option>'+options.map(w=>'<option value="'+esc(w.id)+'"'+(w.id===S.co.warehouseId?' selected':'')+'>'+esc(warehouseText(w.name))+'</option>').join('')+'</select></label>'+(selected?'<p class="hint">'+esc([warehouseText(selected.address),selected.erpCode].filter(Boolean).join(' · '))+'</p>':'')+'<label class="warehouse-confirm"><input type="checkbox" data-warehouse-confirm'+(S.co.warehouseConfirmed==='yes'?' checked':'')+'><span>'+u('warehouseConfirm')+'</span></label>'+errP('warehouseId')+'</div>'},
  notes:()=>'<label class="fl area"><textarea data-co="notes" placeholder="'+t('notesPh')+'" aria-label="'+t('notes')+'">'+esc(S.co.notes||'')+'</textarea></label>',
  foot:()=>(WRITE.error?'<p class="ferr" role="alert">'+esc(WRITE.error)+'</p>':'')+'<p class="snote">'+esc(u(S.basket.some(lineAsk)?'requestNote':'submitNote',{c:company()}))+'</p>'
};
function coHtml(){
  return '<div class="cof"><button type="button" class="osum" id="osum" data-act="sum-toggle"></button><div class="osum-b" id="osumb" hidden></div>'+
    '<section class="sec"><h2>'+u('secContact')+'</h2><div id="f-contact"></div></section>'+
    '<section class="sec"><h2>'+u('secCompany')+'</h2><div id="f-company"></div><div id="f-reference"></div></section>'+
    (checkoutWarehouses().length?'<section class="sec"><div id="f-warehouse"></div></section>':'')+
    '<section class="sec"><h2>'+u('qReceive')+'</h2><div id="f-receive"></div><div id="f-addr"></div><div class="mapbox" id="comap"></div></section>'+
    '<section class="sec"><h2>'+u('qInvoice')+'</h2><div id="f-invoice"></div></section>'+
    (recAsk()?'<section class="sec"><h2>'+u('recT')+'</h2><div id="f-recurring"></div></section>':'')+
    '<section class="sec"><h2>'+t('notes')+'<small>'+u('optional')+'</small></h2><div id="f-notes"></div></section>'+
    '<div id="f-foot"></div></div>';
}
/* the order summary a phone shows above the form: closed it states the total, open it lists the lines */
function paintSum(){
  const b=$('#osum');if(!b)return;const all=basketTotal(),anyAsk=S.basket.some(lineAsk);
  b.setAttribute('aria-expanded',!!S.sumOpen);b.innerHTML='<span>'+ic('shopping-basket',18)+u('orderSum')+ic('chevron-down',16)+'</span><b>'+(anyAsk&&!all?u('quoteTotal'):pr(all))+'</b>';
  const body=$('#osumb');body.hidden=!S.sumOpen;if(S.sumOpen)body.innerHTML=S.basket.map((l,n)=>lineHtml(l,n,true)).join('');
}
function paintCo(which){(which||Object.keys(CO)).forEach(k=>{const el=$('#f-'+k);if(el)el.innerHTML=CO[k]()});paintSum();mapSync()}
function cbarHtml(){
  const all=basketTotal(),anyAsk=S.basket.some(lineAsk);
  const amount=anyAsk&&!all?'<b class="word">'+u(S.basket.length===1?'requestLine':'requestLines',{n:S.basket.length})+'</b>':'<b>'+pr(all)+'</b>';
  return '<div class="tot"><span class="t1">'+amount+'</span><small>'+(anyAsk?(all?u('pricedItems'):u('quoteTotal')):vatW())+'</small></div>'+
    '<button class="act" type="button" data-act="next"'+(WRITE.pending?' disabled':'')+'><span class="lg">'+u(WRITE.pending?'saving':anyAsk?'requestSubmit':'submit')+'</span><span class="sh">'+u(WRITE.pending?'saving':anyAsk?'requestSubmit':'shortSub')+'</span>'+ic('arrow-right',18)+'</button>';
}
function validate(){
  const v=k=>(S.co[k]||'').trim(),e={};
  if(!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v('email')))e.email='needEmail';
  if(v('company').length<2)e.company='needCompany';
  if(checkoutWarehouses().length&&(!checkoutWarehouses().some(w=>w.id===v('warehouseId'))||v('warehouseConfirmed')!=='yes'))e.warehouseId='needWarehouse';
  if(v('phone').replace(/\D/g,'').length<6)e.phone='needPhone';
  if(S.fulfil==='delivery'){if(v('line1').length<3)e.line1='needAddr';S.co.address=addrLine('d')}
  if(v('name').length<2)e.name='needName';
  if(S.inv==='company'){if(v('coName').length<2)e.coName='needCo';if(v('eik').replace(/\D/g,'').length<9)e.eik='needCo';if(!(S.fulfil==='delivery'&&!S.billOther)&&v('bline1').length<3)e.bline1='needCoAddr'}
  return e;
}
/* the one button: every field is checked together, the first one that needs the customer comes into view with its message */
function next(){
  S.errs=validate();
  const k=['name','email','phone','company','warehouseId','line1','coName','eik','bline1'].find(x=>S.errs[x]);
  if(!k)return submit();
  paintCo();const el=root.querySelector(k==='warehouseId'?'[data-warehouse]':k==='line1'?'#aqd':k==='bline1'?'#aqb':'[data-co="'+k+'"]');
  if(el){el.scrollIntoView({block:'center'});try{el.focus({preventScroll:true})}catch(e){}}
}
/* address search: a debounced, cached, capped caller; it stands down to plain fields when the service says so or fails twice */
const GEO={n:0,cache:{},ctl:null,timer:0,sid:Math.random().toString(36).slice(2)+Date.now().toString(36)};
const geoGet=(path,sig)=>{const c=new AbortController(),tm=setTimeout(()=>c.abort(),2500);if(sig)sig.addEventListener('abort',()=>c.abort());return fetch(CFG.base+path,{signal:c.signal}).then(r=>r.json()).finally(()=>clearTimeout(tm))};
function paintSugg(){const w=S.geoFor||'d',el=$('#sugg'+w);if(el)el.innerHTML=suggHtml();const i=$('#aq'+w);if(i)i.setAttribute('aria-expanded',!!(S.sugg||[]).length)}
function geoSearch(q,w){
  clearTimeout(GEO.timer);q=q.trim();S.geoFor=w;
  if(q.length<3||S.geo==='off'){S.sugg=[];return paintSugg()}
  if(GEO.cache[q]){S.sugg=GEO.cache[q];return paintSugg()}
  GEO.timer=setTimeout(()=>{
    if(GEO.n>=60){S.geo='off';return}GEO.n++;
    if(GEO.ctl)GEO.ctl.abort();GEO.ctl=new AbortController();
    geoGet('api/places?q='+encodeURIComponent(q)+'&session='+GEO.sid+'&lang='+K.L.lang+(S.near?'&near='+S.near.lat+','+S.near.lng:''),GEO.ctl.signal).then(d=>{
      if(!d||!d.ok){S.geo='off';S.sugg=[];return paintSugg()}
      GEO.cache[q]=d.items||[];if((S.aq||'').trim()===q){S.sugg=GEO.cache[q];paintSugg()}
    }).catch(e=>{if(GEO.ctl&&GEO.ctl.signal.aborted)return;S.geo='off';S.sugg=[];paintSugg()});
  },140);
}
function geoPick(x){
  const w=S.geoFor||'d',k=ADDR[w],town=(x.secondary||'').split(',')[0].trim();
  S.sugg=[];paintSugg();addrApply(w,{line1:x.main,city:town});
  {const el=root.querySelector('[data-co="'+k[1]+'"]');if(el&&matchMedia('(min-width:901px)').matches)el.focus()}
  geoGet('api/place?id='+encodeURIComponent(x.id)+'&session='+GEO.sid+'&lang='+K.L.lang).then(d=>{
    GEO.sid=Math.random().toString(36).slice(2)+Date.now().toString(36);
    if(d&&d.ok&&S.co[k[0]]===x.main)addrApply(w,{line1:d.line1||x.main,zip:d.zip||'',city:d.city||town,lat:d.lat,lng:d.lng});
  }).catch(()=>{});
}
async function submit(){
 if(WRITE.pending)return;
 const customer=Object.fromEntries(Object.entries(S.co).filter(([k,v])=>v!=null&&!/^recurring/.test(k)).map(([k,v])=>[k,String(v)]));
 customer.language=K.L.lang;customer.kind='company';if(recAsk())Object.assign(customer,recFields());
 if(ASK)ASK.stamp(customer,S.basket);if(PICK)PICK.stamp(customer); /* questionnaire hook */
 const kept=JSON.parse(JSON.stringify(S.basket)),payload={lines:wire(kept),customer,fulfilment:S.fulfil},fingerprint=JSON.stringify(payload);
 if(WRITE.fingerprint!==fingerprint){let previous;try{previous=JSON.parse(sessionStorage.getItem(CFG.key+'-request')||'null')}catch(e){}WRITE.fingerprint=fingerprint;WRITE.key=previous?.fingerprint===fingerprint?previous.key:requestKey();try{sessionStorage.setItem(CFG.key+'-request',JSON.stringify({fingerprint,key:WRITE.key}))}catch(e){}}
 WRITE.pending=true;WRITE.error='';renderAll();
 try{const result=await api('orders',payload,WRITE.key);
  S.done={no:result.id,email:customer.email,lines:kept,total:result.quote.gross,fulfil:S.fulfil,ready:result.ready,quote:result.quote};
  if(basketSignature()===JSON.stringify(kept)){S.basket=[];S.capture=null;PICK?.reset()}save();S.view='done';S.bask=false;WRITE.fingerprint='';WRITE.key='';try{sessionStorage.removeItem(CFG.key+'-request')}catch(e){}
 }catch(error){WRITE.error=error.message||u('saveError');}
 finally{WRITE.pending=false;renderAll();if(S.view==='done')$('#coscroll').scrollTop=0}
}
function claimHtml(){
 const c=WRITE.claim;if(c.saved)return '<div class="done"><h1>'+u('claimSaved')+'</h1><p class="lead">'+u('claimNext')+'</p><button type="button" class="btn" data-act="claim-back">'+u('menu')+'</button></div>';
 const field=(key,label,type)=>'<label class="fl"><input type="'+type+'" data-claim-field="'+key+'" value="'+esc(c[key])+'" placeholder=" " autocomplete="'+key+'"><span>'+label+'</span></label>';
 return '<div class="q"><h1>'+u('claimTitle')+'</h1><p class="q-sub">'+u('claimSub')+'</p>'+field('name',t('name'),'text')+field('email',u('claimEmail'),'email')+(c.error?'<p class="hint err" role="alert">'+esc(c.error)+'</p>':'')+'</div>';
}
async function submitClaim(){
 const c=WRITE.claim;if(c.pending)return;
 if(c.name.trim().length<2||!/^\S+@\S+\.\S+$/.test(c.email.trim())){c.error=u('claimNeed');return renderAll()}
 const payload={name:c.name.trim(),email:c.email.trim()},fingerprint=JSON.stringify(payload);
 if(c.fingerprint!==fingerprint){c.fingerprint=fingerprint;c.key=requestKey()}
 c.pending=true;c.error='';renderAll();
 try{c.saved=await api('claims',payload,c.key)}catch(error){c.error=error.message||u('saveError')}
 finally{c.pending=false;renderAll()}
}

/* the confirmation: a letter drops into its envelope, the flap closes, the seal lands */
const MAIL='<svg class="mail" viewBox="0 0 240 190" aria-hidden="true"><ellipse class="m-sh" cx="120" cy="178" rx="78" ry="6"/>'+
  '<g class="m-env"><rect class="m-back" x="36" y="58" width="168" height="106" rx="6"/>'+
  '<g class="m-hide"><g class="m-paper"><rect x="56" y="72" width="128" height="84" rx="4"/><rect class="m-mark" x="68" y="84" width="24" height="8" rx="2"/><path d="M68 106h104M68 118h104M68 130h64"/></g></g>'+
  '<path class="m-front" d="M36 64l84 58 84-58v94a6 6 0 0 1-6 6H42a6 6 0 0 1-6-6z"/><path class="m-flap" d="M37 61l83 57 83-57z"/>'+
  '<g class="m-seal"><rect x="105" y="103" width="30" height="30" rx="6"/><path d="M113 118l5 5 9-10"/></g></g>'+
  '<path class="m-lines" d="M6 92h18M0 112h24M8 132h16"/></svg>';
function doneHtml(){
  const d=S.done;
  const pending=!!d.quote?.confirmation,amount=pending?(d.total>0?' · '+u('pricedItems')+' '+K.eur(d.total):' · '+u('onConf')):(d.total>0?' · '+K.eur(d.total):'');
  return '<div class="done">'+MAIL+'<h1>'+u('savedT')+'</h1><p class="lead">'+esc(u('savedCopy',{n:d.no}))+'</p><p class="lead">'+esc(u('savedNext'))+'</p><p class="receipt">'+u('orderNo',{n:d.no})+amount+'</p>'+
    '<div class="row2"><button class="act" type="button" data-act="again">'+u('again')+ic('arrow-right',18)+'</button></div></div>';
}

/* ---------- shell ---------- */
function launchHtml(){
  const n=S.basket.length;
  return '<span class="l-t"><b>'+t('launch')+'</b><small>'+readyLabel()+'</small></span><span class="go">'+(n?t('basket')+'<i>'+n+'</i>':u('go')+ic('arrow-right',18))+'</span>';
}
function renderAll(){
  $('#launch').innerHTML=launchHtml();
  const sh=$('#sheet');if(!S.open){sh.hidden=true;$('#scrim').hidden=true;return}
  sh.hidden=false;$('#scrim').hidden=false;sh.classList.toggle('bask',!!S.bask);sh.classList.toggle('solo',S.view==='done'||S.view==='claim');
  $('#menu').setAttribute('aria-hidden',S.view!=='menu');
  if(S.view==='laser'&&!S.lz)S.view='menu';
  const form=S.view==='co'||S.view==='done'||S.view==='custom'||S.view==='claim'||S.view==='laser';
  $('#item').hidden=S.view!=='item';$('#co').hidden=!form;
  if(S.view==='item')renderItem();
  if(form){const z=S.lz,key=S.view==='laser'?'laser|'+z.step+'|'+z.busy+'|'+z.bad+'|'+S.uploading+'|'+S.uploadName+'|'+(z.check?.id||'')+'|'+z.editing+'|'+(z.step==='summary'?z.material+'|'+z.thickness+'|'+z.n:''):S.view==='claim'?'claim|'+WRITE.claim.pending+'|'+WRITE.claim.error+'|'+(WRITE.claim.saved?.id||''):S.view==='done'?'done':S.view==='custom'?'custom|'+S.editing+'|'+S.custom+'|'+S.bad+'|'+S.uploading+'|'+S.uploadName+'|'+(S.customFile?.id||''):'co|'+K.L.lang;const cs=$('#costep');if(cs.dataset.k!==key){cs.dataset.k=key;cs.innerHTML=S.view==='laser'?laserHtml():S.view==='claim'?claimHtml():S.view==='done'?doneHtml():S.view==='custom'?customHtml():coHtml();if(S.view==='co')paintCo()}if(S.view==='co'){const f=$('#f-foot');if(f)f.innerHTML=CO.foot()}const cb=$('#cbar');cb.hidden=S.view==='done'||(S.view==='claim'&&!!WRITE.claim.saved);if(S.view==='claim')cb.innerHTML='<button class="act" type="button" data-act="claim-submit"'+(WRITE.claim.pending?' disabled':'')+'>'+u(WRITE.claim.pending?'saving':'claimSubmit')+ic('arrow-right',18)+'</button>';if(S.view==='co')cb.innerHTML=cbarHtml();if(S.view==='custom')cb.innerHTML='<div class="tot"><span class="t1"><b class="word">'+u('onConf')+'</b></span><small>'+u('askT')+'</small></div><button class="act" type="button" data-act="add-custom"'+(S.uploading||S.editing<0&&S.basket.length>=100?' disabled':'')+'><span class="lg">'+(S.editing>=0?t('update'):t('add'))+'</span><span class="sh">'+u('short')+'</span>'+ic('arrow-right',18)+'</button>';if(S.view==='laser')lzPaint()}
  if(S.view!=='laser')lzDrop();
  $('#back').hidden=S.view==='menu'||S.view==='done';$('#logo').hidden=S.view==='item'||S.view==='co'||S.view==='custom'||S.view==='claim'||S.view==='laser';
  const langs=$('#langs');if(langs)langs.hidden=S.view!=='menu';
  $('#crumbs').hidden=true;{const bk=$('#back'),co=S.view==='co';bk.setAttribute('aria-label',u(co?'editOrder':'menu'));bk.classList.toggle('wide',co);bk.innerHTML=ic('chevron-left',24)+(co?'<span>'+u('editOrder')+'</span>':'')}
  if(S.view==='co'){if(S.fulfil==='delivery')locate();if(!S.mapWarm)setTimeout(()=>{S.mapWarm=true;mapSync()},400)}
  mapSync();renderBasket();watch();if(S.view==='menu')ink();
  if(ASK)ASK.render();if(PICK)PICK.render(); /* questionnaire hook */
}
function showItem(code,len,keep){
  const i=C.items[code];if(!i)return;
  if(!keep){S.rows=[{x:1000,n:1}];S.sheet={a:1000,b:500,n:1};S.angle=false;S.editing=-1}
  if(!keep&&mode(i)==='bar'&&i.r.k==='len'&&i.r.l.length)S.rows=[{x:Math.round((i.r.l.indexOf(i.L)>=0?i.L:Math.max.apply(null,i.r.l))*1000),n:1}];
  setItem(code);
  if(!keep&&mode(i)==='sheet')S.sheet={a:Math.min(1000,i.d[2]),b:Math.min(500,i.d[1]),n:1};
  if(!keep&&mode(i)==='piece')S.rows[0].n=quantity(i,1);
  if(len&&mode(i)==='bar')S.rows=[{x:len,n:1}]
  S.view='item';S.peek=null;S.pd=false;S.ex='';S.note='';S.bask=false;S.drawn='';S.scale='fit';
  renderAll();$('#iscroll').scrollTop=0;$('#stage').classList.remove('mini');
}
function showMenu(){if(PICK){S.lz=null;S.peek=null;S.pd=false;S.editing=-1;S.done=null;S.bad='';return PICK.resume()}S.lz=null;S.view='menu';S.peek=null;S.pd=false;S.editing=-1;S.done=null;S.bad='';renderAll()}
function leaveCustom(){
  const file=S.customFile;if(file&&!uploadReferenced(file.id))discardUpload(file).catch(()=>{});
  S.customFile=null;S.custom='';showMenu();
}
function open(code,len){
  if(!C.ready)return;
  const first=!S.open;S.open=true;S.bask=false;if(PICK&&first&&!code&&S.view==='menu')S.view='pick';
  document.documentElement.style.overflow='hidden';
  if(code&&C.items[code])showItem(code,len);else{if(S.view==='item'&&!S.item)S.view='menu';renderAll()}
  if(first){
    const row=document.querySelector((CFG.table||'#products-table')+' tbody tr td'),pc=row&&C.items[row.textContent.trim()];
    if(pc&&!code){const n=FORMS().findIndex(f=>f.id===pc.cat.form);if(n>0)jump(n,true)}
  }
  if(location.hash!=='#order')try{history.replaceState(null,'','#order')}catch(e){}
}
function close(){S.open=false;S.bask=false;document.documentElement.style.overflow='';renderAll();try{history.replaceState(null,'',location.pathname+location.search)}catch(e){}if(window.parent!==window&&new URLSearchParams(location.search).get('rocoto_embed')==='1')window.parent.postMessage({type:'rocoto:close'},'*')}
if(window.parent!==window&&/(?:[?&])rocoto_embed=1(?:&|$)/.test(location.search||''))window.addEventListener('message',event=>{if(event.source!==window.parent)return;if(event.data?.type==='rocoto:open')open();else if(event.data?.type==='rocoto:hide')close()});

function addLine(){
  const i=C.items[S.item],m=mode(i),p=curPlan();if(!p.ok)return;
  if(S.editing<0&&S.basket.length>=100)return;
  const line={code:i.c,rows:m==='sheet'?null:S.rows.map(r=>({x:r.x,n:r.n})),sheet:m==='sheet'?{a:S.sheet.a,b:S.sheet.b,n:S.sheet.n}:null,angle:m==='bar'&&S.angle?Object.assign({},S.angle):false,...(S.editing>=0&&S.basket[S.editing]?{why:S.basket[S.editing].why||''}:PICK?{why:PICK.note()}: {})};
  if(S.editing>=0&&S.basket[S.editing]){S.basket[S.editing]=line;S.fresh=S.editing}else{S.basket.push(line);S.fresh=S.basket.length-1}
  save();showMenu();
  const el=root.querySelector('.line.arrived');if(el&&el.scrollIntoView)try{$('#basket .b-lines').scrollTop=el.offsetTop}catch(e){}
  setTimeout(()=>{S.fresh=-1},600);
}
function setQuery(v,keepFocus){
  S.q=v.trim();renderMenu();if(!keepFocus){const q=$('#q');q.value=v;q.focus()}
}

/* questionnaire hook */ /* the company's guided questions (ask.js), handed what they need from this page */
const ASK=window.RocotoAsk&&CFG.questionnaire&&!CFG.picker?window.RocotoAsk.ui({cfg:CFG,K:K,S:S,ic:ic,esc:esc,u:u,pic:i=>pic(i),root:()=>root,open:()=>open(),render:()=>renderAll(),showMenu:()=>showMenu(),save:()=>save(),still:still,narrow:()=>matchMedia('(max-width:900px)').matches}):null;

/* picker hook: shares the real basket, product detail and checkout. */
const PICK=window.RocotoPick&&CFG.picker?window.RocotoPick.ui({cfg:CFG,K,S,ic,esc,pic:i=>pic(i),root:()=>root,open:()=>open(),render:()=>renderAll(),showItem:code=>showItem(code),save:()=>save(),quantity:(i,n)=>quantity(i,n)}):null;

/* ---------- events ---------- */
function onClick(e){
  if(PICK&&PICK.click(e))return;if(ASK&&ASK.click(e))return; /* questionnaire hook */
  const el=e.target.closest('button');
  if(S.pd&&!(el&&el.dataset.act==='pd')&&!e.target.closest('#pd')){S.pd=false;if(S.view==='item')renderLive()}
  if(!el)return;const d=el.dataset;
  if(el.id==='launch')return open();
  if(d.language)return switchLanguage(d.language);
  if(d.tab!=null)return jump(+d.tab);
  if(d.try!=null)return setQuery(d.try);
  if(d.cat){const c=C.byCode[d.cat];return showItem(K.mid(c).c)}
  if(d.item)return showItem(d.item,+d.len||0);
  if(d.g!=null){const cur=C.items[S.item],g=K.levels(cur.cat)[+d.g],k=K.k2(cur);setItem((g.items.find(y=>K.k2(y)===k)||nearest({items:g.items},cur)||g.items[0]).c);S.peek=null;return renderItem()}
  if(d.size){setItem(d.size);S.peek=null;return renderItem()}
  if(d.full){S.rows[S.rows.length-1].x=+d.full;return renderItem()}
  if(d.pc){const p=d.pc.split('x').map(Number);S.sheet.a=p[0];S.sheet.b=p[1];return renderItem()}
  if(d.del!=null){S.rows.splice(+d.del,1);return renderItem()}
  if(d.d){const k=+d.d;if(d.sf){S.sheet.n=clamp((Number(S.sheet.n)||0)+k,1,999)}else{const r=S.rows[+d.row],item=C.items[S.item];r.n=quantity(item,(Number(r.n)||0)+k*(mode(item)==='piece'?increment(item):1),k)}return renderItem()}
  if(d.angle!=null){S.angle=d.angle==='1'?{degrees:90,ends:1}:false;return renderItem()}
  if(d.ld&&S.basket[+d.n]?.laser){const l=S.basket[+d.n],q=l.laser.quantity+(+d.ld);if(q<1)dropLine(+d.n);else{l.laser.quantity=Math.min(999,q);l.view.gross=lzTotal(l);save()}return renderAll()}
  if(d.lzMat){const z=S.lz,m=lzMat(z.check,d.lzMat);z.material=m.id;z.thickness=lzNear(m,z.thickness);return lzPaint()}
  if(d.lzTh){S.lz.thickness=Number(d.lzTh);return lzPaint()}
  if(d.lzD){S.lz.n=clamp((Number(S.lz.n)||1)+(+d.lzD),1,999);return lzPaint()}
  if(d.rec){S.co.recurring=d.rec;if(d.rec==='recurring'&&!S.co.recurringFrequency)S.co.recurringFrequency='monthly';return paintCo(['recurring'])}
  if(d.recf){S.co.recurringFrequency=d.recf;return paintCo(['recurring'])}
  if(d.ld){const l=S.basket[+d.n],k=+d.ld,o=l.sheet||l.rows[0];if(k<0&&o.n<=(mode(C.items[l.code])==='piece'?selling(C.items[l.code]).minimum||1:1))S.basket.splice(+d.n,1);else o.n=quantity(C.items[l.code],o.n+k*(mode(C.items[l.code])==='piece'?increment(C.items[l.code]):1),k);save();if(!S.basket.length&&S.view==='co')S.view='menu';return renderAll()}
  if(d.edit!=null){const l=S.basket[+d.edit];if(l.laser){const c=LZC[l.laser.id];if(!c)return;S.lz={step:'material',file:l.view.upload,check:c,material:l.laser.material,thickness:l.laser.thickness,n:l.laser.quantity,busy:'',bad:'',name:c.name,editing:+d.edit};S.view='laser';S.bask=false;return renderAll()}if(l.custom){S.custom=l.custom;S.customFile=l.file||null;S.editing=+d.edit;S.view='custom';S.bask=false;S.bad='';renderAll();const ta=root.querySelector('[data-custom]');if(ta)ta.focus();return}if(l.rows)S.rows=l.rows.map(r=>({x:r.x,n:r.n}));if(l.sheet)S.sheet=Object.assign({},l.sheet);S.angle=l.angle?Object.assign({degrees:90,ends:1},typeof l.angle==='object'?l.angle:{}):false;S.editing=+d.edit;return showItem(l.code,0,true)}
  if(d.rm!=null){dropLine(+d.rm);return renderAll()}
  if(d.slide!=null)return slideTo(+d.slide);
  if(d.sugg!=null){const x=(S.sugg||[])[+d.sugg];return x?geoPick(x):0}
  if(d.fulfil){S.fulfil=d.fulfil;if(S.view!=='co')return renderAll();paintCo(['contact','receive','addr','invoice']);renderBasket();$('#cbar').innerHTML=cbarHtml();if(d.fulfil==='delivery'){locate();const a=$('#aqd');if(a&&!a.value&&matchMedia('(min-width:901px)').matches)a.focus()}return}
  if(d.inv){S.inv=d.inv;if(d.inv==='company'&&!S.co.coName)S.co.coName=S.co.company||'';paintCo(['invoice']);if(d.inv==='company'){const a=root.querySelector('[data-co="coName"]');if(a)a.focus()}return}
  switch(d.act){
    case'here':return useHere();
    case'claim':S.view='claim';S.bask=false;WRITE.claim.error='';renderAll();return;
    case'claim-submit':return submitClaim();
    case'claim-back':return showMenu();
    case'retry-quote':scheduleQuote(true);return renderBasket();
    case'close':return close();
    case'back':return S.view==='laser'?lzBack():S.view==='custom'?leaveCustom():showMenu();
    case'laser':return lzOpen();
    case'lz-next':return lzNext();
    case'lz-add':return lzAdd();
    case'lz-custom':return lzToCustom();
    case'next':return next();

    case'clr':$('#q').value='';return setQuery('');
    case'pd':S.pd=!S.pd;return renderLive();
    case'addrow':if(S.rows.length>=100)return;S.rows.push({x:S.rows[S.rows.length-1].x,n:1});renderItem();{const a=root.querySelectorAll('[data-f="x"]');const x=a[a.length-1];x.focus();x.select()}return;
    case'add':return PICK?PICK.confirmItems([S.item],addLine):addLine();
    case'bask-open':S.bask=true;return renderAll();
    case'bask-close':S.bask=false;return renderAll();
    case'checkout':if(!S.basket.length)return;S.view='co';S.bask=false;S.bad='';S.errs={};S.sumOpen=false;renderAll();$('#coscroll').scrollTop=0;{const a=root.querySelector('[data-co="name"]');if(a&&!a.value&&matchMedia('(min-width:901px)').matches)try{a.focus({preventScroll:true})}catch(e){}}return;
    case'again':return showMenu();
    case'product-info':return showProductInfo();
    case'info-close':$('#product-info').close();$('#photo-info').focus();return;
    case'slideshow':S.slidePaused=!S.slidePaused;$('#slideshow').setAttribute('aria-pressed',!!S.slidePaused);$('#slideshow').setAttribute('aria-label',u(S.slidePaused?'resumeSlideshow':'pauseSlideshow'));$('#slideshow').innerHTML=ic(S.slidePaused?'play':'pause',16);return;
    case'prev':return slideTo(S.slide-1);
    case'nxt':return slideTo(S.slide+1);
    case'code':S.codeOpen=!S.codeOpen;renderBasket();{const el=root.querySelector('#basket [data-co="code"]');if(el)el.focus()}return;
    case'bill-toggle':S.billOther=!S.billOther;paintCo(['invoice']);if(S.billOther){const el=$('#aqb');if(el)el.focus()}return;
    case'sum-toggle':S.sumOpen=!S.sumOpen;return paintSum();
    case'custom':S.view='custom';S.custom='';S.customFile=null;S.editing=-1;S.bad='';S.bask=false;renderAll();{const ta=root.querySelector('[data-custom]');if(ta)ta.focus()}return;
    case'remove-file':return removeCustomFile();
    case'add-custom':return addCustom();
  }
}
function onInput(e){
  const el=e.target,d=el.dataset;
  if(el.id==='q')return setQuery(el.value,true);
  if(d.addr){const w=d.addr,k=ADDR[w];S.aq=el.value;S.geoFor=w;S.co[k[0]]=el.value;S['has'+w]=el.value.trim().length>=3;if(w==='d'){S.co.lat=null;S.co.lng=null}clearErr(k[0],el);return geoSearch(el.value,w)}
  if(d.custom!=null){S.custom=el.value;if(S.bad){S.bad='';const error=root.querySelector('#coscroll [role="alert"]');if(error)error.remove()}return}
  if(d.claimField){WRITE.claim[d.claimField]=el.value;return}
  if(d.lzN!=null){const n=Number(el.value.trim());if(Number.isInteger(n)&&n>=1&&n<=999){S.lz.n=n;lzPaint(true)}return}
  if(d.co){S.co[d.co]=el.value;clearErr(d.co,el);return}
  if(d.angleDegrees!=null){S.angle.degrees=entered(el.value);$('#plan').innerHTML=planHtml();return renderLive()}
  if(d.angleEnds!=null){S.angle.ends=Number(el.value)===2?2:1;return renderLive()}
  S.note='';
  if(d.f&&d.row!=null){S.rows[+d.row][d.f]=entered(el.value)}
  else if(d.sf){S.sheet[d.sf]=entered(el.value)}
  else return;
  $('#plan').innerHTML=planHtml();renderLive();
}
function onChange(e){
  if(e.target.matches?.('[data-warehouse]')){const selected=checkoutWarehouses().find(w=>w.id===e.target.value);Object.assign(S.co,{warehouseId:selected?.id||'',warehouseName:warehouseText(selected?.name),warehouseErpCode:selected?.erpCode||'',warehouseConfirmed:''});paintCo(['warehouse']);return}
  if(e.target.matches?.('[data-warehouse-confirm]')){S.co.warehouseConfirmed=e.target.checked?'yes':'';if(e.target.checked){delete S.errs.warehouseId;root.querySelector('#co-error-warehouseId')?.remove()}return}
  if(e.target.dataset?.upload!=null&&e.target.files?.[0])uploadFile(e.target.files[0]);
}
function onFileDrag(e){
  const drop=e.target.closest?.('#file-drop');if(!drop)return;
  e.preventDefault();
  if(e.type==='dragover')drop.classList.add('over');
  else if(e.type==='dragleave'&&!drop.contains(e.relatedTarget))drop.classList.remove('over');
  else if(e.type==='drop'){drop.classList.remove('over');if(e.dataTransfer?.files?.[0])uploadFile(e.dataTransfer.files[0])}
}
function onOver(e){
  if(S.view!=='item'||!e.target.closest)return;
  const el=e.target.closest('[data-g],[data-size]');let code=null;
  if(el&&el.closest('#iopts')){
    const d=el.dataset,cur=C.items[S.item];
    if(d.size)code=d.size;
    else{const g=K.levels(cur.cat)[+d.g],k=K.k2(cur);code=(g.items.find(y=>K.k2(y)===k)||g.items[0]).c}
    if(code===S.item)code=null;
    if(code&&mode(C.items[code])!==mode(cur))code=null;
  }
  if(code!==S.peek){S.peek=code;renderLive()}
}
function onKey(e){
  if(!S.open)return;
  if(PICK&&PICK.key(e))return;if(ASK&&ASK.key(e))return; /* questionnaire hook */
  if($('#product-info').open){if(e.key==='Escape'){e.preventDefault();$('#product-info').close();$('#photo-info').focus()}return}
  const q=$('#q'),ae=root.activeElement;
  if(e.key==='Escape'){
    if(S.pd){S.pd=false;renderLive()}else if(S.bask){S.bask=false;renderAll()}else if(S.view==='laser')lzLeave();else if(S.view==='custom')leaveCustom();else if(S.view!=='menu')showMenu();else if(S.q){q.value='';setQuery('')}else close();
    return;
  }
  if(ae===q&&e.key==='Enter'){e.preventDefault();const f=$('#res .it');if(f)f.click();return}
  if(S.view==='menu'&&(ae===q||(ae&&ae.classList&&ae.classList.contains('it')))&&(e.key==='ArrowDown'||e.key==='ArrowUp')){
    const a=[].slice.call(root.querySelectorAll(S.q?'#res .it':'#secs .it')),n=a.indexOf(ae),k=e.key==='ArrowDown'?n+1:n-1;
    e.preventDefault();if(k<0)q.focus();else if(a[k]){a[k].focus();a[k].scrollIntoView({block:'nearest'})}return;
  }
  if(ae&&ae.dataset&&ae.dataset.f==='x'&&(e.key==='ArrowUp'||e.key==='ArrowDown')){e.preventDefault();const r=S.rows[+ae.dataset.row],st=e.shiftKey?100:10;r.x=Math.max(10,(r.x||0)+(e.key==='ArrowUp'?st:-st));ae.value=r.x;$('#plan').innerHTML=planHtml();renderLive();return}
  if(ae&&ae.dataset&&ae.dataset.f==='x'&&e.key==='Enter'){e.preventDefault();const el=root.querySelector('[data-act="addrow"]');if(el)el.click();return}
  if(S.view==='item'&&(e.key==='ArrowLeft'||e.key==='ArrowRight')&&!(ae&&/INPUT|TEXTAREA/.test(ae.tagName)))return slideTo(S.slide+(e.key==='ArrowRight'?1:-1));
  if(e.key==='/'&&!(ae&&/INPUT|TEXTAREA/.test(ae.tagName))){e.preventDefault();q.focus()}
  if(e.key==='Enter'&&ae&&ae.tagName==='INPUT'&&ae!==q){
    const fields=[].slice.call(root.querySelectorAll('#coscroll input[data-co],#coscroll input[data-addr]')),at=fields.indexOf(ae),on=()=>{if(at>=0&&at<fields.length-1)fields[at+1].focus();else next()};
    if(ae.dataset.co){e.preventDefault();on()}
    else if(ae.dataset.addr){e.preventDefault();S.geoFor=ae.dataset.addr;const f=(S.sugg||[])[0];if(f)geoPick(f);else on()}
    else ae.blur();
  }
}

/* ---------- host page hooks ---------- */
/* the label on the company's colour: white where ink would read worse (WCAG contrast against each) */
function onAccent(){
  const m=/^#([0-9a-f]{6})$/i.exec(CFG.accent||'');if(!m)return'';
  const v=parseInt(m[1],16),lin=c=>{c/=255;return c<=.03928?c/12.92:Math.pow((c+.055)/1.055,2.4)},L=.2126*lin(v>>16)+.7152*lin(v>>8&255)+.0722*lin(v&255),inkL=.0116;
  return 1.05/(L+.05)>(L+.05)/(inkL+.05)?'#fff':'';
}
function hookTable(){
  const tb=document.querySelector(CFG.table||'#products-table');if(!tb||tb.dataset.rocoto)return;tb.dataset.rocoto='1';
  const head=tb.querySelector('thead tr');if(head){const td=document.createElement('td');td.textContent=t('order');head.appendChild(td)}
  tb.querySelectorAll('tbody tr').forEach(tr=>{
    const code=(tr.cells[0]&&tr.cells[0].textContent||'').trim(),td=document.createElement('td');td.style.textAlign='center';
    if(C.items[code]){const b=document.createElement('button');b.type='button';b.textContent='+';b.setAttribute('aria-label',t('order')+' '+code);
      b.style.cssText='width:26px;height:26px;border:0;border-radius:50%;background:'+CFG.accent+';color:'+(onAccent()||'#262722')+';font:700 17px/26px Arial,sans-serif;cursor:pointer;padding:0';
      b.addEventListener('click',()=>open(code));td.appendChild(b)}
    tr.appendChild(td);
  });
}
function mount(){
  host=document.createElement('div');host.id='rocoto-configurator';document.body.appendChild(host);
  root=host.attachShadow({mode:'open'});
  if(window.FontFace&&!Array.from(document.fonts).some(face=>face.family.replaceAll('"','')==='Rocoto Inter')){const face=new FontFace('Rocoto Inter','url('+CFG.base+'inter.woff2)',{weight:'400',style:'normal'});document.fonts.add(face);face.load().catch(()=>{})}
  const ph=esc(t('search',{n:K.num(C.n)}));
  root.innerHTML='<style>'+CSS+'</style><div class="r" style="--accent:'+CFG.accent+(onAccent()?';--on-accent:'+onAccent():'')+'">'+
    '<button class="launch" id="launch" type="button"></button>'+
    '<div class="scrim" id="scrim" hidden></div>'+
    '<div class="sheet" id="sheet" role="dialog" aria-modal="true" aria-label="'+t('launch')+'" hidden>'+
      '<header class="head"><button class="bk" id="back" type="button" data-act="back" aria-label="'+u('menu')+'" hidden>'+ic('chevron-left',24)+'</button><img class="logo" id="logo" src="'+(CFG.logos?.[K.L.lang]||CFG.logo)+'" alt="'+esc(K.name(C.data.company))+'"><div class="crumbs" id="crumbs" hidden></div>'+languageHtml()+
        '<button class="ib x" type="button" data-act="close" aria-label="'+t('close')+'">'+ic('x',18)+'</button></header>'+
      '<div class="body"><div class="main">'+
        '<div class="menu" id="menu"><div class="m-bar" id="bar"><label class="search">'+ic('search',18)+'<input id="q" type="search" autocomplete="off" spellcheck="false" enterkeyhint="search" placeholder="'+ph+'" aria-label="'+ph+'"><button class="ib" id="clr" type="button" data-act="clr" aria-label="'+u('clear')+'" hidden>'+ic('x',16)+'</button></label>'+
          '<nav class="tabs" id="tabs" role="tablist" aria-label="'+u('sections')+'">'+tabsHtml()+'</nav></div><div id="secs">'+menuHtml()+'</div><div id="res" hidden></div></div>'+
        '<div class="item" id="item" hidden><div class="i-scroll" id="iscroll"><div class="stage" id="stage"><div class="hero" id="hero"><div class="slides" id="slides"></div><button class="nav prev" id="prev" type="button" data-act="prev" aria-label="'+u('previousPhoto')+'" hidden>'+ic('chevron-left',28)+'</button><button class="nav nxt" id="nxt" type="button" data-act="nxt" aria-label="'+u('nextPhoto')+'" hidden>'+ic('chevron-right',28)+'</button><div class="dots" id="dots"></div><button class="photo-info" id="photo-info" type="button" data-act="product-info" aria-label="'+u('productInfo')+'">'+ic('info',22)+'</button><button class="slideshow" id="slideshow" type="button" data-act="slideshow" aria-label="'+u('pauseSlideshow')+'" aria-pressed="false">'+ic('pause',16)+'</button><div class="draw" id="draw"></div></div></div>'+
          '<div class="ihead" id="ihead"></div><div id="iopts"></div></div>'+
          '<div class="i-bar"><div class="pd" id="pd" hidden></div><div id="ibar" style="display:contents"></div></div></div>'+
        '<div class="co" id="co" hidden><div class="co-scroll" id="coscroll"><div id="costep"></div></div><div class="i-bar" id="cbar"></div></div>'+
        '<button class="mcart" id="mcart" type="button" data-act="bask-open" hidden></button>'+
      '</div><div class="side"><aside class="basket" id="basket" aria-label="'+u('yourBasket')+'"></aside></div></div>'+
    '</div><dialog class="product-info" id="product-info" aria-labelledby="pi-title"></dialog></div>';
  root.addEventListener('click',onClick);
  root.addEventListener('input',onInput);
  root.addEventListener('change',onChange);
  ['dragover','dragleave','drop'].forEach(name=>root.addEventListener(name,onFileDrag));
  root.addEventListener('error',e=>{if(e.target.tagName==='IMG'){e.target.hidden=true;e.target.closest('.th')?.classList.add('missing')}},true);
  root.addEventListener('mouseover',onOver);
  $('#iopts').addEventListener('mouseleave',()=>{if(S.peek){S.peek=null;renderLive()}});
  $('#scrim').addEventListener('click',close);
  root.addEventListener('focusin',e=>{const d=e.target.dataset||{};if((d.f||d.sf)&&e.target.select)e.target.select()});
  let hold=0;root.addEventListener('pointerdown',e=>{const b=e.target.closest&&e.target.closest('[data-d]');if(!b)return;const key=b.dataset.row!=null?'[data-row="'+b.dataset.row+'"][data-d="'+b.dataset.d+'"]':'[data-sf][data-d="'+b.dataset.d+'"]';clearInterval(hold);let n=0;hold=setInterval(()=>{if(++n>4){const el=root.querySelector(key);if(el)el.click()}},70)});
  ['pointerup','pointercancel','pointerleave'].forEach(x=>root.addEventListener(x,()=>clearInterval(hold),true));
  $('#iscroll').addEventListener('scroll',()=>{const sc=$('#iscroll'),st=$('#stage'),mini=st.classList.contains('mini');if(!mini&&sc.scrollTop>70)st.classList.add('mini');else if(mini&&sc.scrollTop<8)st.classList.remove('mini')},{passive:true});
  document.addEventListener('keydown',onKey);
  { /* swipe the pictures; arrows work too */
    const he=$('#hero');let sx=null;
    he.addEventListener('pointerenter',e=>{if(e.pointerType==='mouse')slideHover=true});
    he.addEventListener('pointerleave',()=>{slideHover=false});
    setInterval(()=>{if(S.open&&S.view==='item'&&!S.bask&&!S.slidePaused&&!slideHover&&!$('#product-info').open&&!still()&&document.visibilityState==='visible'&&Date.now()-slideTouched>=6000)slideTo(S.slide+1,true)},6500);
    he.addEventListener('pointerdown',e=>{sx=e.clientX});
    he.addEventListener('pointerup',e=>{if(sx==null)return;const dx=e.clientX-sx;sx=null;if(Math.abs(dx)>36)slideTo(S.slide+(dx<0?1:-1))});
    he.addEventListener('pointercancel',()=>{sx=null});
  }
  renderAll();hookTable();
  /* the 3D library comes down while the visitor reads the page, so the first product opens with its model ready */
  if(location.hash==='#order')open();
}
function boot(){
  const j=url=>fetch(url,{signal:AbortSignal.timeout(8000)}).then(r=>r.ok?r.json():Promise.reject());
  Promise.all([j(CFG.base+'catalog.json'),CFG.posters?j(CFG.base+'t/index.json').catch(()=>({})):{},j(CFG.base+'g/index.json').catch(()=>({})),j(CFG.base+'api/supply').catch(()=>({items:{}}))]).then(a=>{K.index(a[0]);POST=a[1]||{};GEN=a[2]||{};SUPPLY=a[3]||{items:{}};load();lzWarm();mount();setInterval(()=>{if(S.open&&document.visibilityState!=='hidden'&&S.basket.length)scheduleQuote(true)},60000);setInterval(()=>{if(S.open&&document.visibilityState!=='hidden')j(CFG.base+'api/supply').then(v=>{SUPPLY=v}).catch(()=>{})},300000)}).catch(()=>{});
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
window.RocotoConfigurator={open:open,close:close,state:S};
})();
