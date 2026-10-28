/* A company-owned, specification-first catalogue. Filtering and article numbers use the full catalogue. */
(function () {
'use strict';
const list = value => Array.isArray(value) ? value : value == null ? [] : [value];
const pairSize = row => {const a=row.a||{},keys=a.A!=null&&a.B!=null?['A','B']:['backset','centres'],parts=keys.map(key=>list(a[key])[0]);return parts.every(value=>value!==''&&value!=null&&Number.isFinite(Number(value))&&Number(value)>0)?[parts.map(Number).join('/')]:[]};
const numericFacets=new Set(['backset','centres','A','B','length','width','height','diameter','thickness','plate']);
const facetValue=(key,value)=>numericFacets.has(key)&&value!==''&&Number.isFinite(Number(value))?String(Number(value)):String(value);
const values = (row, key) => key === '_size' ? pairSize(row) : key === 'form' ? [row.cat.form] : key === 'model' ? [row.cat.code, ...list(row.a?.model)] : list(row.a?.[key]).map(value=>facetValue(key,value));
const matches = (row, filters) => Object.entries(filters || {}).every(([key, allowed]) => values(row, key).some(value => list(allowed).some(wanted => facetValue(key,wanted) === facetValue(key,value))));
const searchable = value => typeof value === 'string' || typeof value === 'number' ? String(value) : value && typeof value === 'object' ? Object.values(value).map(searchable).join(' ') : '';
const normalized = value => String(value).normalize('NFKC').toLocaleLowerCase().trim();
const searchIndex = new WeakMap();
const searches = (row, query) => {
  if(!query.trim())return true;
  let text=searchIndex.get(row);
  if(text===undefined){text=normalized([row.c,row.name,row.n,row.cat.bg,row.cat.en,row.s,row.se,row.a].map(searchable).join(' '));searchIndex.set(row,text)}
  return normalized(query).split(/\s+/).every(term=>text.includes(term));
};
// The same explicit dependency rule used by ask.js and the server questionnaire.
const whenOk = (when, answers) => !when || Object.entries(when).every(([key, allowed]) => list(answers[key]).some(value => list(allowed).includes(value)));
function ui(env) {
  const {K, S, cfg, esc, ic} = env, def = cfg.picker;
  const A = {entry:'', generation:0, pending:null, screen:'start', family:'', filters:{}, query:'', text:'', file:null, busy:'', error:'', spec:[], chosen:{}, quantities:{}, answers:{}, section:'', proposal:null, clarify:null, clarification:{}, after:null, added:'', demoOrder:null, allocationReview:null, readingId:'', allocationConfirmed:false};
  // A reviewed matrix stays attached to its basket while the user browses other paths.
  let allocationCapture=S.capture?.specification?.reading_id&&S.capture.specification.allocations_confirmed===true?JSON.parse(JSON.stringify(S.capture)):null;
  const tx = value => typeof value === 'string' ? value : value?.[K.L.lang] || value?.bg || value?.en || '';
  const words = {
    en:{start:'Do you have a specification to upload or paste?',startSub:'Upload your list, or choose the hardware for your project.',yes:'Yes, I have one',yesSub:'A file or a list of products',no:'No',noSub:'Choose products for your door',choose:'How would you like to choose?',know:'I know what I’m looking for',knowSub:'Browse products and dimensions',help:'Help me choose',helpSub:'Tell us about the door and the project',spec:'Your specification',paste:'Paste your product list',upload:'Drop a specification here',file:'Choose a file',types:'PDF, Word, Excel or an image · up to 15 MB',read:'Read specification',reading:'Reading your specification…',uploading:'Uploading your file…',families:'Product catalogue',articles:'articles',filter:'Filter by name or article number',clear:'Clear filters',results:'Articles',add:'Add',added:'Added to your order',quantity:'Quantity',sku:'Article',all:'Add confirmed articles',chooseArticle:'Choose an article',exact:'Confirmed',unknown:'For the team to confirm',review:'Check each line and choose the matching article.',back:'Back',proposal:'Prepare my proposal',preparing:'Preparing your proposal…',unsure:'I’m not sure',helpTitle:'Your door and project',helpIntro:'Answer in any order. Share the details you know.',summary:'Your proposal',edit:'Change answers',addProposal:'Add selected articles',request:'Add as a request',retry:'Try again',empty:'Choose another combination to see articles.',specEmpty:'Paste your specification or choose a file.',error:'Please try again. Your choices are saved.',chooseShape:'Which shape do you need?',confirm:'Continue',project:'Project details',projectPlaceholder:'Number of doors, replacement parts, building type…',more:'Show more articles',specLine:'Your line',selection:'Matching article',optional:'Optional',remove:'Remove file',catalogue:'All products',reference:'Quote reference',quantityError:'Enter a whole quantity from 1 to 9,999.',sourceReview:'The team will confirm the remaining dimensions.',requestNeeds:'Send project details',select:'Select',chooseDetails:'Choose details',matching:'matching articles',allMatching:'See all matching articles',capacity:'Your order can contain up to 100 product lines.',sellingQuantity:'Check the quantity against the product’s pack size.'},
    bg:{start:'Имате ли спецификация?',startSub:'Качете списъка си или изберете обкова за вашия проект.',yes:'Да, имам',yesSub:'Файл или списък с продукти',no:'Не',noSub:'Изберете продукти за вратата',choose:'Как искате да изберете?',know:'Знам какво търся',knowSub:'Продукти и размери от каталога',help:'Помогнете ми да избера',helpSub:'Разкажете за вратата и проекта',spec:'Вашата спецификация',paste:'Поставете списъка с продукти',upload:'Пуснете спецификацията тук',file:'Изберете файл',types:'PDF, Word, Excel или изображение · до 15 MB',read:'Прочети спецификацията',reading:'Прочитане на спецификацията…',uploading:'Качване на файла…',families:'Каталог с продукти',articles:'артикула',filter:'Име или каталожен номер',clear:'Изчисти филтрите',results:'Артикули',add:'Добави',added:'Добавено в поръчката',quantity:'Брой',sku:'Артикул',all:'Добави потвърдените',chooseArticle:'Изберете артикул',exact:'Потвърден',unknown:'За уточняване с екипа',review:'Проверете всеки ред и изберете артикул.',back:'Назад',proposal:'Подготви предложение',preparing:'Подготвяне на предложението…',unsure:'Не знам',helpTitle:'Вашата врата и проект',helpIntro:'Отговорете в удобен ред с детайлите, които знаете.',summary:'Вашето предложение',edit:'Промени отговорите',addProposal:'Добави избраните артикули',request:'Добави като запитване',retry:'Опитай отново',empty:'Изберете друга комбинация, за да видите артикули.',specEmpty:'Поставете спецификацията или изберете файл.',error:'Опитайте отново. Изборът ви е запазен.',chooseShape:'Каква форма ви трябва?',confirm:'Продължи',project:'Детайли за проекта',projectPlaceholder:'Брой врати, резервни части, вид сграда…',more:'Покажи още артикули',specLine:'Вашият ред',selection:'Артикул',optional:'По желание',remove:'Премахни файла',catalogue:'Всички продукти',reference:'Номер за запитване',quantityError:'Въведете цяло количество от 1 до 9 999.',sourceReview:'Екипът ще уточни останалите размери.',requestNeeds:'Изпрати детайлите за проекта',select:'Избери',chooseDetails:'Уточни детайлите',matching:'артикула',allMatching:'Всички артикули',capacity:'Поръчката може да съдържа до 100 продуктови реда.',sellingQuantity:'Проверете количеството спрямо размера на опаковката.'}
  };
  const t = key => words[K.L.lang === 'en' ? 'en' : 'bg'][key] || key;
  let cachedCategories=null,cachedRows=[],cachedFamilies=new Map();
  const allRows=()=>{if(cachedCategories!==K.C.cats){cachedCategories=K.C.cats;cachedRows=K.C.cats.flatMap(cat=>cat.items);cachedFamilies=new Map()}return cachedRows};
  const family = () => def.families.find(f => f.id === A.family);
  const familyRows=f=>{const rows=allRows();if(!cachedFamilies.has(f))cachedFamilies.set(f,rows.filter(row=>matches(row,f?.match||{})));return cachedFamilies.get(f)};
  const title = row => tx(row.name || row.n || row.cat) || row.c;
  const searchHtml = () => '<label class="search pick-search">'+ic('search',18)+'<input type="search" data-pick-query value="'+esc(A.query)+'" placeholder="'+esc(t('filter'))+'" aria-label="'+esc(t('filter'))+'"></label>';
  const resultsHtml = (found, draw = articleRow) => '<div class="pick-results">'+(found.length?found.slice(0,A.limit||60).map(row=>draw(row)).join(''):'<p class="pick-empty">'+t('empty')+'</p>')+'</div>'+(found.length>(A.limit||60)?button('more',esc(t('more'))):'');
  const picture = row => row ? env.pic(row) : '';
  const drawing = (id, fallback = 'package') => cfg.drawings?.[id] || '<span class="pick-symbol">'+ic(fallback,44,1.2)+'</span>';
  const button = (action, label, cls = 'pick-button', extra = '') => '<button type="button" class="'+cls+'" data-pick="'+action+'" '+extra+'>'+label+'</button>';
  const heading = (title, sub = '') => '<div class="pick-heading"><h1>'+esc(title)+'</h1>'+(sub ? '<p>'+esc(sub)+'</p>' : '')+'</div>';
  const pair = cards => '<div class="pick-pair">'+cards.map(([action,label,sub,draw,icon]) => button(action,'<span class="pick-card-art">'+drawing(draw,icon)+'</span><strong>'+esc(label)+'</strong><small>'+esc(sub)+'</small><span class="pick-card-arrow">'+ic('arrow-right',20)+'</span>','pick-card')).join('')+'</div>';
  function startHtml() { return '<div class="pick-entry">'+heading(tx(cfg.headline)||t('start'),tx(cfg.description)||t('startSub'))+pair([['spec',t('yes'),t('yesSub'),'specification','file-text'],['choose',t('no'),t('noSub'),'door-interior','door-open']])+'</div>'; }
  function chooseHtml() { return '<div class="pick-entry">'+heading(t('choose'))+pair([['families',t('know'),t('knowSub'),'catalogue','search'],['help',t('help'),t('helpSub'),'door-interior','door-open']])+'</div>'; }
  function specHtml() { return heading(t('spec'))+'<label class="pick-drop" id="pick-drop"><span>'+ic('upload',28)+'</span><b>'+esc(A.file?.name || t('upload'))+'</b><span class="pick-file-label">'+t('file')+'</span><small>'+t('types')+'</small><input type="file" data-pick-file accept=".pdf,.docx,.xlsx,.csv,.txt,.png,.jpg,.jpeg,.webp" '+(A.busy?'disabled':'')+'></label>'+(A.file?button('remove-file',esc(t('remove')),'lnk'):'')+'<label class="pick-label">'+t('paste')+'<textarea data-pick-text maxlength="24000" placeholder="24 × брава 50/72, секретна\n24 × дръжка АТИНА, сатин">'+esc(A.text)+'</textarea></label>'; }
  function specCustomerHtml() {
    if(!A.demoOrder)return '';
    const c=S.co||{},bg=K.L.lang==='bg',warehouses=A.demoOrder.warehouses||[];
    const field=(key,label)=>'<label>'+label+'<input type="text" data-pick-order-field="'+key+'" value="'+esc(c[key]||'')+'" maxlength="'+(key==='poNumber'?80:200)+'"></label>';
    return '<section class="pick-customer-review" aria-labelledby="pick-customer-title"><div class="pick-customer-identity"><span class="pick-customer-avatar">P</span><div><small>'+(bg?'Демо заявка':'Demo order')+'</small><h2 id="pick-customer-title">'+esc(c.company||'Практикер')+'</h2></div>'+ic('file-text',22)+'</div><div class="pick-customer-fields">'+field('coName',bg?'Фирма за фактура':'Invoice company')+field('poNumber',bg?'Номер на поръчка (PO)':'Purchase order (PO)')+field('eik',bg?'ЕИК':'Company registration')+'<label>'+(bg?'Склад за изпълнение':'Fulfilment warehouse')+'<select data-pick-warehouse>'+warehouses.map(w=>'<option value="'+esc(w.id)+'" '+(c.warehouseId===w.id?'selected':'')+'>'+esc(w.name)+' · '+esc(w.erpCode||w.erp_code||'')+'</option>').join('')+'</select></label></div><p class="pick-invoice-address">'+ic('map-pin',15)+' '+esc([c.bline1,c.bcity,c.bzip].filter(Boolean).join(', '))+'</p><label class="pick-customer-confirm"><input type="checkbox" data-pick-customer-confirm '+(c.warehouseConfirmed==='yes'?'checked':'')+'><span>'+(bg?'Потвърждавам фирмата, данните за фактура и склада.':'I confirm the company, invoice details and warehouse.')+'</span></label></section>';
  }
  function allocationReady() {
    return !A.allocationReview || (!A.allocationReview.issues?.length && A.allocationConfirmed && A.spec.every((line,n)=>A.chosen[n] && A.quantities['spec:'+n]===line.qty));
  }
  function allocationIssue(issue) {
    const labels={identify_columns:'Уточнете колоната с артикулните номера.',identify_quantity_columns:'Уточнете колоните с количества и обекти.',duplicate_destination:'Разграничете повторените обекти.',whole_quantity:'Въведете цяло количество.',quantity_limit:'Разделете количеството на по-малки поръчки.',formula_quantity:'Потвърдете изчислените количества в Excel.',formula_value_required:'Запазете изчислените стойности в Excel.',unmapped_cell:'Проверете стойността в тази колона.',article_required:'Попълнете артикулния номер.',destination_total_mismatch:'Проверете общото количество за обекта.',invalid_total:'Поправете общото количество.',line_total_mismatch:'Сборът по обекти се различава от общото количество.',check_line_quantity:'Проверете количеството на реда.',total_value_required:'Попълнете общото количество.',document_total_mismatch:'Проверете общия сбор на документа.',article_rows_required:'Добавете редовете с артикули.',image_layout_review:'Качете оригиналния Excel файл за разпределението по обекти.',document_table_review:'Качете таблицата в Excel, за да проверите колоните.',document_text_review:'Качете Excel, CSV или документ с четим текст.'};
    if(typeof issue==='string')return issue;
    return (K.L.lang==='bg'?(labels[issue.code]||'Проверете отбелязаната клетка.'):issue.message||String(issue.code||'Check the source cell').replaceAll('_',' '))+(issue.source_cell?' · '+issue.source_cell:'');
  }
  function allocationsHtml() {
    const review=A.allocationReview;if(!review)return '';
    const bg=K.L.lang==='bg',destinations=review.destinations||[],allocations=review.allocations||[];
    return '<section class="pick-allocation-review"><div class="pick-results-heading"><h2>'+ (bg?'Разпределение по обекти':'Delivery destinations')+'</h2><span>'+destinations.length+' '+(bg?'обекта':'destinations')+'</span></div><div class="pick-allocation-scroll" tabindex="0"><table><thead><tr><th>'+(bg?'Артикул':'Article')+'</th>'+destinations.map(d=>'<th title="'+esc(d.source_cell||'')+'">'+esc(d.label||d.id)+'</th>').join('')+'<th>'+(bg?'Общо':'Total')+'</th></tr></thead><tbody>'+A.spec.map((line,n)=>'<tr><th>'+esc(A.chosen[n]||allocations.find(a=>a.line===n)?.sku||line.source)+'</th>'+destinations.map(d=>{const q=allocations.filter(a=>a.line===n&&a.destination_id===d.id).reduce((sum,a)=>sum+a.quantity,0);return '<td>'+(q||'—')+'</td>'}).join('')+'<td><strong>'+line.qty+'</strong></td></tr>').join('')+'</tbody></table></div>'+ (review.issues?.length?'<div class="pick-allocation-issues" role="status"><strong>'+(bg?'Проверете оригиналния документ':'Check the original document')+'</strong><ul>'+review.issues.slice(0,12).map(issue=>'<li>'+esc(allocationIssue(issue))+'</li>').join('')+'</ul></div>':'<label class="pick-customer-confirm"><input type="checkbox" data-pick-allocation-confirm '+(A.allocationConfirmed?'checked':'')+'><span>'+(bg?'Потвърждавам обектите и количествата от документа.':'I confirm the destinations and quantities from the document.')+'</span></label>')+'</section>';
  }
  function specResultsHtml() {
    return specCustomerHtml()+heading(t('spec'),t('review'))+allocationsHtml()+'<div class="pick-spec-table"><div class="pick-spec-head"><span>'+t('specLine')+'</span><span>'+t('selection')+'</span><span>'+t('quantity')+'</span></div>'+A.spec.map((line,n) => {
      const codes=(line.matches||[]).filter(c=>K.C.items[c]), selected=A.chosen[n], row=K.C.items[selected];
      const select='<select data-pick-match="'+n+'" aria-label="'+esc(t('chooseArticle'))+'"><option value="">'+t('chooseArticle')+'</option>'+codes.map(c=>'<option value="'+esc(c)+'" '+(String(selected)===String(c)?'selected':'')+'>'+esc([title(K.C.items[c]),plainSpec(K.C.items[c]),c].filter(Boolean).join(' · '))+'</option>').join('')+'</select>';
      return '<div class="pick-spec-row"><p>'+esc(line.source)+'</p><div>'+(codes.length?select:'<span class="pick-review">'+t('unknown')+'</span>')+(row?'<small class="pick-confirmed">'+ic('check',14)+' '+t('exact')+' · '+esc(row.c)+'</small>':'')+'</div><input type="number" min="1" max="9999" step="1" data-pick-qty="spec:'+n+'" '+(A.allocationReview?'readonly':'')+' value="'+(A.quantities['spec:'+n]??line.qty??1)+'" aria-label="'+esc(t('quantity'))+'"></div>';
    }).join('')+'</div>'+(!A.allocationReview&&A.spec.some(l=>!l.matches?.length)?button('request-spec',esc(t('request')),'lnk'):'');
  }
  function familiesHtml() {
    if(A.query.trim()){const found=allRows().filter(row=>searches(row,A.query));return heading(t('families'))+searchHtml()+'<div class="pick-results-heading"><h2>'+t('results')+' <span>'+found.length+'</span></h2>'+button('clear',esc(t('clear')),'lnk')+'</div>'+resultsHtml(found)}
    return heading(t('families'))+searchHtml()+'<div class="pick-families">'+def.families.map(f => {
      const rows=familyRows(f), cover=K.C.byCode[f.photo]?.items[0] || rows[0];
      return button('family','<span class="pick-family-photo">'+picture(cover)+'</span><b>'+esc(tx(f.title))+'</b><small>'+rows.length+' '+t('articles')+'</small>','pick-family','data-family="'+esc(f.id)+'"');
    }).join('')+'</div>';
  }
  function plainSpec(row) {
    const source=K.L.lang==='en'?(row.se||row.s):row.s;
    if(typeof source==='string'&&source.trim()&&normalized(source)!==normalized(title(row)))return source;
    return (def.families.find(f=>matches(row,f.match||{}))?.facets||[]).filter(f=>f.key!=='model').flatMap(f=>f.options.filter(o=>values(row,f.key).some(v=>String(v)===String(o.value))).map(o=>tx(o.label))).filter(Boolean).join(' · ');
  }
  function modelTitle(row) {
    const facet=def.families.find(f=>matches(row,f.match||{}))?.facets?.find(f=>f.key==='model');
    return tx(facet?.options.find(o=>String(o.value)===String(row.cat.code))?.label)||tx(row.cat);
  }
  function articleRow(row, why = '', slot = '', choice = null) {
    const model=modelTitle(row),details=plainSpec(row),description=[details,why&&normalized(why)!==normalized(details)&&normalized(why)!==normalized(title(row))?why:''].filter(Boolean).join(' · ');
    const qty=A.quantities[slot || row.c] ?? (choice!==null?A.proposal?.choices?.[choice]?.qty:slot.startsWith('proposal:')?A.proposal?.lines?.[+slot.split(':')[1]]?.qty:1) ?? 1;
    const index=!slot&&choice===null?S.basket.findIndex(line=>String(line.code)===String(row.c)&&line.rows?.length===1&&!line.sheet&&(line.why||'')===note()):-1;
    const line=S.basket[index],bg=K.L.lang==='bg';
    const controls=line?'<div class="pick-cart-controls">'+button('cart-remove',ic('trash-2',17),'pick-cart-remove','data-line="'+index+'" aria-label="'+(bg?'Премахни':'Remove')+' '+esc(row.c)+'"')+button('cart-step',ic('minus',17),'pick-cart-step','data-line="'+index+'" data-delta="-1" aria-label="'+(bg?'Намали броя':'Decrease quantity')+'" '+(line.rows[0].n<=1?'disabled':''))+'<input class="pick-cart-quantity" type="number" min="1" max="999" step="1" value="'+line.rows[0].n+'" data-pick-cart-qty="'+index+'" aria-label="'+esc(t('quantity'))+'">'+button('cart-step',ic('plus',17),'pick-cart-step','data-line="'+index+'" data-delta="1" aria-label="'+(bg?'Увеличи броя':'Increase quantity')+'" '+(line.rows[0].n>=999?'disabled':''))+'</div>':(slot?'<input type="number" min="1" max="9999" step="1" value="'+qty+'" data-pick-qty="'+esc(slot)+'" aria-label="'+esc(t('quantity'))+'">':'')+button(choice===null?'add':'select-choice','<span>'+t(choice===null?'add':'select')+'</span>','pick-add','aria-label="'+esc(t(choice===null?'add':'select')+' '+title(row)+' · '+row.c)+'" data-code="'+esc(row.c)+'" data-slot="'+esc(slot)+'"'+(choice===null?'':' data-choice="'+choice+'"'));
    return '<div class="pick-article"><button type="button" class="pick-article-photo" data-pick="inspect" data-code="'+esc(row.c)+'" aria-label="'+esc(title(row))+'">'+picture(row)+'</button><div class="pick-article-text">'+(model&&normalized(model)!==normalized(title(row))?'<strong class="pick-article-model">'+esc(model)+'</strong>':'')+'<button type="button" data-pick="inspect" data-code="'+esc(row.c)+'"><b>'+esc(title(row))+'</b></button><small>'+esc(description)+'</small><code>'+esc((row.a?.article_status==='request'?t('reference')+' · ':'')+row.c)+'</code></div><div class="pick-article-actions">'+controls+'</div></div>';
  }
  function cartQuantity(index,value) {
    const line=S.basket[index],row=line&&K.C.items[line.code];
    if(!row||line.rows?.length!==1)return;
    if(value!==line.rows[0].n&&holdAllocationChange())return;
    if(!Number.isInteger(value)||value<1||value>999){A.error=t('quantityError');env.render();return}
    const n=env.quantity?env.quantity(row,value):value;
    if(n!==value){A.error=t('sellingQuantity');env.render();return}
    line.rows[0].n=n;A.error='';remember();env.render();
  }
  function facetsHtml() {
    const f=family(),rows=familyRows(f),searched=rows.filter(row=>searches(row,A.query)),found=searched.filter(row=>matches(row,A.filters));
    const priority=key=>({model:0,material:1,body:1,latch:1,finish:2,colour:2,_size:3,backset:4,width:4,centres:5,plate:5,A:4,B:5,length:6}[key]??7);
    const sizes=[...new Set(rows.flatMap(pairSize))].sort((a,b)=>a.localeCompare(b,undefined,{numeric:true}));
    const extra=[{key:'plate',title:{bg:'Ширина на планката · мм',en:'Forend width · mm'}},{key:'width',title:{bg:'Ширина · мм',en:'Width · mm'}},{key:'hand',title:{bg:'Посока',en:'Handing'},labels:{L:{bg:'Лява',en:'Left'},R:{bg:'Дясна',en:'Right'}}},{key:'latch',title:{bg:'Материал на езика',en:'Latch material'},labels:{alloy:{bg:'Цинкова сплав',en:'Zinc alloy'},ceramic:{bg:'Металокерамика',en:'Sintered metal'}}}].filter(facet=>!f.facets.some(f=>f.key===facet.key)).map(facet=>({...facet,options:[...new Set(rows.flatMap(row=>values(row,facet.key)))].filter(value=>value&&(!numericFacets.has(facet.key)||Number(value)>0)).sort((a,b)=>a.localeCompare(b,undefined,{numeric:true})).map(value=>({value,label:facet.labels?.[value]||value}))})).filter(facet=>facet.options.length);
    const facets=[...f.facets,...extra,...(sizes.length?[{key:'_size',title:{bg:'Размер · мм',en:'Size · mm'},options:sizes.map(value=>({value,label:value}))}]:[])].map(facet=>{const seen=new Set();return {...facet,options:facet.options.filter(option=>{const key=facetValue(facet.key,option.value);if(seen.has(key))return false;seen.add(key);return true}).map(option=>({...option,value:facetValue(facet.key,option.value)}))}}).sort((a,b)=>priority(a.key)-priority(b.key));
    const active=Object.entries(A.filters).map(([key,value])=>{const facet=facets.find(f=>f.key===key),option=facet?.options.find(o=>String(o.value)===String(value));return button('filter',esc(tx(option?.label)||String(value))+' '+ic('x',14),'pick-option','data-key="'+esc(key)+'" data-value="'+esc(value)+'" aria-label="'+esc(tx(facet?.title)+': '+tx(option?.label)+' — '+t('clear'))+'"')}).join('');
    const root=env.root(),previous=root.querySelector('.pick-filter-panel'),expanded=previous?previous.open:(root.querySelector('.main')?.clientWidth||0)>=840;
    const counted=facets.map(facet=>{
      const rest={...A.filters};delete rest[facet.key];const counts=new Map();
      for(const row of searched)if(matches(row,rest))for(const value of new Set(values(row,facet.key).map(String)))counts.set(value,(counts.get(value)||0)+1);
      return {...facet,counts};
    });
    const nextFacet=counted.find(facet=>A.filters[facet.key]==null&&(facet.options.some(option=>{const n=facet.counts.get(String(option.value))||0;return n>0&&n<found.length})||['colour','finish','latch','hand','material','body'].includes(facet.key)&&facet.options.filter(option=>(facet.counts.get(String(option.value))||0)>0).length>1))?.key;
    const filters=counted.map(facet=>{
      const chosen=facet.options.find(option=>String(option.value)===String(A.filters[facet.key]));
      return '<details class="pick-facet" '+(facet.key===nextFacet?'open':'')+'><summary class="pick-facet-label"><h2>'+esc(tx(facet.title))+'</h2>'+(chosen?'<span class="pick-facet-selected">'+esc(tx(chosen.label))+'</span>':'')+ic('chevron-down',14)+'</summary>'+(facet.help?button('info',ic('info',15),'ib','data-help="'+esc(facet.help)+'" aria-label="'+esc(tx(facet.title))+'"'):'')+'<div class="pick-options '+(facet.kind==='pict'?'pictures':'')+(facet.kind==='model'?' models':'')+'">'+facet.options.map(option=>{
        const count=facet.counts.get(String(option.value))||0,on=String(A.filters[facet.key])===String(option.value),cover=facet.kind==='model'?(K.C.byCode[option.value]?.items[0]||rows.find(row=>matches(row,{[facet.key]:option.value}))):null;
        const art=option.drawing?'<span class="pick-option-art">'+drawing(option.drawing)+'</span>':cover?'<span class="pick-option-art">'+picture(cover)+'</span>':option.swatch&&/^#[\da-f]{3,8}$/i.test(option.swatch)?'<i class="pick-swatch" style="background:'+option.swatch+'"></i>':'';
        return button('filter',art+'<span>'+esc(tx(option.label))+'</span><small>'+count+'</small>','pick-option','data-key="'+esc(facet.key)+'" data-value="'+esc(option.value)+'" aria-pressed="'+on+'" '+(!count&&!on?'disabled':''));
      }).join('')+'</div></details>';
    }).join('');
    const filtersLabel=K.L.lang==='bg'?'Филтри':'Filters';
    return '<div class="pick-catalogue"><div class="pick-catalogue-toolbar">'+heading(tx(f.title))+searchHtml()+(active?'<div class="pick-active-filters">'+active+button('clear',esc(t('clear')),'lnk')+'</div>':'')+'</div><div class="pick-catalogue-layout"><details class="pick-filter-panel" '+(expanded?'open':'')+'><summary><span>'+filtersLabel+(Object.keys(A.filters).length?' <small>'+Object.keys(A.filters).length+'</small>':'')+'</span>'+ic('chevron-down',16)+'</summary><div class="pick-facets">'+filters+'</div></details><section class="pick-catalogue-results" aria-label="'+esc(t('results'))+'"><div class="pick-results-heading"><h2>'+t('results')+' <span>'+found.length+'</span></h2></div>'+resultsHtml(found)+'</section></div></div>';
  }
  function guideQuestions() { return (cfg.questionnaire?.questions||[]).filter(q=>whenOk(q.when,A.answers)); }
  function guideOptions(question) { return (question.options||[]).filter(option=>whenOk(option.when,A.answers)); }
  function pruneAnswers() {
    const questions=cfg.questionnaire?.questions||[];
    // Dependencies can cascade even when the company lists sections in another order.
    for(let pass=0;pass<=questions.length;pass++){
      let changed=false;
      for(const question of questions){
        if(!Object.hasOwn(A.answers,question.id))continue;
        const before=list(A.answers[question.id]),options=guideOptions(question);
        let kept=whenOk(question.when,A.answers)?before.filter(id=>id==='?'?question.unsure:options.some(option=>option.id===id)):[];
        if(kept.includes('?'))kept=['?'];else if(question.kind!=='multiple')kept=kept.slice(0,1);
        if(JSON.stringify(before)!==JSON.stringify(kept)||!kept.length){if(kept.length)A.answers[question.id]=kept;else delete A.answers[question.id];changed=true}
      }
      if(!changed)break;
    }
    if(A.section&&!guideQuestions().some(q=>q.id===A.section))A.section='';
  }
  function helpHtml() {
    pruneAnswers();const qs=guideQuestions();
    return heading(t('helpTitle'),t('helpIntro'))+'<div class="pick-sections">'+qs.map(q=>{
      const chosen=list(A.answers[q.id]),done=chosen.length,open=A.section===q.id,options=guideOptions(q);
      return '<section class="pick-question"><button type="button" class="pick-question-heading" data-pick="section" data-section="'+esc(q.id)+'" aria-expanded="'+open+'"><span>'+esc(tx(q.title))+'</span><small>'+(done?chosen[0]==='?'?t('unsure'):chosen.map(id=>tx(q.options.find(o=>o.id===id)?.label)).join(', '):'')+'</small>'+ic(done?'check':'chevron-down',18)+'</button>'+(open?'<div class="pick-question-body"><div class="pick-answers '+(options.length===2?'two':'')+'">'+options.map(o=>button('answer','<span class="pick-answer-art">'+(o.picture?'<img src="'+esc((cfg.root||cfg.base.replace(/\/rocoto\/$/,''))+o.picture)+'" alt="">':drawing(o.drawing||o.draw,q.id==='hand'?'door-open':'settings'))+'</span><span>'+esc(tx(o.label))+'</span>','pick-answer','data-question="'+esc(q.id)+'" data-answer="'+esc(o.id)+'" aria-pressed="'+chosen.includes(o.id)+'"')).join('')+'</div>'+(q.unsure?button('answer',esc(t('unsure')),'pick-unsure','data-question="'+esc(q.id)+'" data-answer="?" aria-pressed="'+(chosen[0]==='?')+'"'):'')+'</div>':'')+'</section>';
    }).join('')+'</div><label class="pick-label">'+t('project')+'<textarea data-pick-project maxlength="2000" placeholder="'+esc(t('projectPlaceholder'))+'">'+esc(A.answers.project||'')+'</textarea></label>';
  }
  function proposalHtml() {
    const proposal=A.proposal||{},questions=cfg.questionnaire?.questions||[];
    const lines=(proposal.lines||[]).map((line,n)=>K.C.items[line.c]?'<div class="pick-proposal-line"><label class="pick-include"><input type="checkbox" data-pick-include="'+n+'" '+(line.included!==false?'checked':'')+' aria-label="'+esc(t('add')+' '+title(K.C.items[line.c]))+'"></label>'+articleRow(K.C.items[line.c],tx(line.why),'proposal:'+n)+'</div>':'').join('');
    const choices=(proposal.choices||[]).map((choice,n)=>{
      if(choice.selected)return '';
      const questionsHtml=(choice.unresolved||[]).map(id=>questions.find(q=>q.id===id)).filter(Boolean).map(q=>button('proposal-question',esc(tx(q.title))+' '+ic('arrow-right',16),'pick-option','data-section="'+esc(q.id)+'"')).join('');
      return '<section class="pick-choice-group"><div class="pick-results-heading"><h2>'+esc(tx(choice.title))+'</h2><span>'+choice.count+' '+t('matching')+'</span></div>'+(choice.source_unconfirmed?'<p class="pick-review">'+t('sourceReview')+'</p>':'')+(questionsHtml?'<div class="pick-active-filters">'+questionsHtml+'</div>':'')+'<div class="pick-results">'+(choice.matches||[]).filter(c=>K.C.items[c]).map(c=>articleRow(K.C.items[c],'','choice:'+n+':'+c,n)).join('')+'</div>'+(choice.count>(choice.matches||[]).length?button('choice-catalogue',esc(t('allMatching')),'lnk','data-choice="'+n+'"'):'')+'</section>';
    }).join('');
    return heading(tx(proposal.title)||t('summary'),tx(proposal.text))+'<div class="pick-proposal">'+lines+choices+'</div><div class="pick-proposal-actions">'+button('help',esc(t('edit')),'lnk')+button('request-proposal',esc(t('requestNeeds')),'lnk')+'</div>';
  }
  function choiceHtml(){
    const n=A.activeChoice,choice=A.proposal?.choices?.[n];if(!choice)return proposalHtml();
    const found=(choice.matching_codes||choice.matches||[]).map(code=>K.C.items[code]).filter(row=>row&&searches(row,A.query));
    return heading(tx(choice.title),found.length+' '+t('matching'))+searchHtml()+resultsHtml(found,row=>articleRow(row,'','choice:'+n+':'+row.c,n));
  }
  function clarificationHtml() {
    if(!A.clarify)return '';
    const c=A.clarify;
    return '<div class="pick-modal-shade"><section class="pick-clarify" role="dialog" aria-modal="true" aria-labelledby="pick-clarify-title"><button type="button" class="ib pick-modal-close" data-pick="clarify-close" aria-label="'+esc(t('back'))+'">'+ic('x',18)+'</button><h2 id="pick-clarify-title">'+esc(tx(c.title)||t('chooseShape'))+'</h2><div class="pick-pair">'+c.options.map(o=>button('clarify','<span class="pick-card-art">'+drawing(o.drawing)+'</span><strong>'+esc(tx(o.label))+'</strong>','pick-card','data-value="'+esc(o.value)+'"')).join('')+'</div></section></div>';
  }
  function render() {
    const root=env.root();let modal=root.querySelector('#pick-clarifications');if(!modal){modal=document.createElement('div');modal.id='pick-clarifications';modal.style.display='contents';root.querySelector('#sheet').appendChild(modal)}modal.innerHTML=clarificationHtml();if(A.clarify)modal.querySelector('[data-pick="clarify"]')?.focus({preventScroll:true});let el=root.querySelector('#pick');
    if(!el){el=document.createElement('div');el.id='pick';el.className='co picker';el.hidden=true;root.querySelector('.main').appendChild(el);el.addEventListener('input',input);el.addEventListener('change',change);['dragover','dragleave','drop'].forEach(type=>el.addEventListener(type,drag));}
    root.querySelector('#sheet').classList.add('has-picker');el.hidden=S.view!=='pick';if(el.hidden)return;
    const paneScope=A.screen+'|'+A.family,samePane=A.renderedPane===paneScope;
    const scrolls=['.pick-scroll','.pick-filter-panel','.pick-catalogue-results'].map(selector=>[selector,samePane?(el.querySelector(selector)?.scrollTop||0):0]);
    const focus=root.activeElement,inside=!!focus&&!!el.contains?.(focus),at=inside?focus.selectionStart:null;
    const identity=inside?{tag:focus.tagName,css:focus.className,data:{...focus.dataset},section:focus.closest?.('.pick-question')?.querySelector('[data-section]')?.dataset.section}:null;
    A.renderedPane=paneScope;
    const screen={start:startHtml,choose:chooseHtml,spec:specHtml,'spec-result':specResultsHtml,families:familiesHtml,facets:facetsHtml,help:helpHtml,proposal:proposalHtml,choice:choiceHtml}[A.screen]||startHtml;
    let action='',label='';if(A.screen==='spec'){action='read';label=t('read')}if(A.screen==='spec-result'){action='add-spec';label=t('all')}if(A.screen==='help'){action='propose';label=t('proposal')}if(A.screen==='proposal'){const selected=(A.proposal?.lines||[]).some(line=>line.included!==false&&K.C.items[line.c]);action=selected?'add-proposal':'help';label=t(selected?'addProposal':'chooseDetails')}
    el.innerHTML='<div class="co-scroll pick-scroll">'+screen()+(A.error?'<p class="pick-error" role="alert">'+esc(A.error)+'</p>':'')+'</div>'+(action?'<div class="i-bar pick-bar"><span role="status">'+esc(A.busy?t(A.busy):A.added?t('added'):'')+'</span>'+button(action,esc(A.busy?t(A.busy):label)+ic('arrow-right',18),'act',(A.busy||action==='add-spec'&&(!allocationReady()||A.demoOrder&&S.co?.warehouseConfirmed!=='yes'))?'disabled':'')+'</div>':'');
    for(const [selector,top] of scrolls){const pane=el.querySelector(selector);if(pane)pane.scrollTop=top}
    root.querySelector('#back').hidden=A.screen==='start';root.querySelector('#logo').hidden=false;root.querySelector('#langs').hidden=false;
    if(A.clarify)modal.querySelector('[data-pick="clarify"]')?.focus({preventScroll:true});
    if(identity&&!A.clarify){
      let next=[...el.querySelectorAll('button,input,textarea,select')].find(node=>node.tagName===identity.tag&&node.className===identity.css&&Object.entries(identity.data).every(([key,value])=>node.dataset[key]===value));
      if(!next&&identity.section){
        const parent=(cfg.questionnaire?.questions||[]).find(q=>q.id===identity.section),ids=[identity.section,...Object.keys(parent?.when||{})];
        next=[...el.querySelectorAll('[data-pick="section"]')].find(node=>ids.includes(node.dataset.section));
      }
      next?.focus({preventScroll:true});if(at!=null&&next?.setSelectionRange)try{next.setSelectionRange(at,at)}catch(e){}
    }
  }
  function withBasket(value){const kept=JSON.parse(JSON.stringify(value));if(kept.proposal)kept.proposal.selected=kept.proposal.selected.filter(line=>S.basket.some(item=>String(item.code)===String(line.code)));return kept}
  function retainedAllocation() {
    if(allocationCapture&&S.basket.some(item=>allocationCapture.specification.lines.some(line=>line.selected_code&&String(item.code)===String(line.selected_code))))return allocationCapture;
    allocationCapture=null;return null;
  }
  function holdAllocationChange() {
    if(!retainedAllocation())return false;
    A.error=K.L.lang==='bg'?'Завършете поръчката по спецификацията или премахнете артикулите ѝ, за да започнете друга.':'Complete this specification order, or remove its articles to start another.';
    render();return true;
  }
  function context() {
    const retained=retainedAllocation();if(retained)return withBasket(retained);
    pruneAnswers();
    if(!A.entry)return withBasket(S.capture||{schema:'rocoto.orders.capture.v1',entry_path:'catalogue',language:K.L.lang});
    const value={schema:'rocoto.orders.capture.v1',entry_path:A.entry,language:K.L.lang};
    if(A.entry==='questionnaire'){
      value.questionnaire={title:tx(cfg.questionnaire?.title)||t('helpTitle'),project:A.answers.project||'',questions:(cfg.questionnaire?.questions||[]).map(q=>{
        const given=list(A.answers[q.id]),unknown=given.includes('?');
        return {id:q.id,label:tx(q.title),status:unknown?'unknown':given.length?'answered':'unanswered',answers:given.map(id=>({id,label:id==='?'?t('unsure'):tx(q.options.find(o=>o.id===id)?.label)}))};
      })};
      if(A.proposal)value.proposal={title:tx(A.proposal.title),summary:tx(A.proposal.text),selected:(A.proposal.lines||[]).flatMap((line,n)=>line.included!==false&&S.basket.some(item=>String(item.code)===String(line.c))?[{code:String(line.c),quantity:A.quantities['proposal:'+n]||line.qty||1,reason:tx(line.why)}]:[])};
    }
    if(A.entry==='specification')value.specification={text:A.text.trim(),...(A.file?{file_id:A.file.id}:{}),lines:A.spec.map((line,n)=>({source:line.source,quantity:A.quantities['spec:'+n]||line.qty||1,selected_code:String(A.chosen[n]||''),status:line.status}))};
    if(value.specification&&A.allocationReview)Object.assign(value.specification,{reading_id:A.readingId,allocations_confirmed:A.allocationConfirmed,review:A.allocationReview});
    if(A.demoOrder)value.demo_order={...A.demoOrder,customer:{...A.demoOrder.customer,...S.co}};
    return withBasket(value);
  }
  function remember(){S.capture=context();S.demoOrder=S.capture.demo_order||null;env.save()}
  function restoreCapture(value){
    const saved=JSON.parse(JSON.stringify(value));
    if(saved.demo_order){A.demoOrder=saved.demo_order;S.demoOrder=saved.demo_order;S.co={...S.co,...saved.demo_order.customer};S.inv='company'}
    if(saved.questionnaire){A.answers=Object.fromEntries(saved.questionnaire.questions.filter(q=>q.answers.length).map(q=>[q.id,q.answers.map(a=>a.id)]));A.answers.project=saved.questionnaire.project}
    if(saved.proposal){A.proposal={title:saved.proposal.title,text:saved.proposal.summary,lines:saved.proposal.selected.map(line=>({c:line.code,qty:line.quantity,why:line.reason}))}}
    if(saved.specification){A.allocationReview=saved.specification.review||null;A.readingId=saved.specification.reading_id||'';A.allocationConfirmed=saved.specification.allocations_confirmed===true;A.text=saved.specification.text;A.file=saved.specification.file_id?{id:saved.specification.file_id}:null;A.spec=saved.specification.lines.map(line=>({source:line.source,qty:line.quantity,status:line.status,matches:line.selected_code?[line.selected_code]:[]}));saved.specification.lines.forEach((line,n)=>{A.chosen[n]=line.selected_code;A.quantities['spec:'+n]=line.quantity})}
  }
  function enter(path){
    if(!path)return;
    const prior=A.entry||S.capture?.entry_path,retained=retainedAllocation();
    if(prior!==path){
      A.demoOrder=null;S.demoOrder=null;A.allocationReview=null;A.readingId='';A.allocationConfirmed=false;A.generation++;A.pending=null;A.busy='';A.answers={};A.proposal=null;A.section='';A.text='';A.file=null;A.spec=[];A.chosen={};A.quantities={};A.clarification={};A.clarify=null;A.after=null;S.capture=null;
    }
    if(path==='specification'&&retained)restoreCapture(retained);
    else if(!A.entry&&S.capture)restoreCapture(S.capture);
    A.entry=path;remember();
  }
  function go(screen) { enter(({help:'questionnaire',proposal:'questionnaire',spec:'specification','spec-result':'specification',families:'catalogue',facets:'catalogue'})[screen]);A.screen=screen;A.error='';S.view='pick';S.bask=false;if(screen==='help'&&!A.section)A.section=cfg.questionnaire?.questions[0]?.id||'';env.render();env.root().querySelector('.pick-scroll').scrollTop=0; }

  function back(){const parent={choose:'start',spec:'start','spec-result':'spec',families:'choose',facets:'families',help:'choose',proposal:'help',choice:'proposal'};if(A.clarify){A.clarify=null;A.after=null;render();restoreFocus();return}go(parent[A.screen]||'start')}
  async function call(path,payload) {
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),90000);
    try{const response=await fetch(cfg.base+'api/'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),signal:controller.signal}),result=await response.json();if(!response.ok||!result.ok)throw new Error(result.message||t('error'));return result}finally{clearTimeout(timer)}
  }
  async function upload(file) {
    if(A.busy)return;if(!file?.size||file.size>15*1024*1024){A.error=t('types');return render()}
    const generation=A.generation;let uploaded=false;A.demoOrder=null;S.demoOrder=null;A.allocationReview=null;A.readingId='';A.allocationConfirmed=false;if(S.co)S.co.warehouseConfirmed='';A.pending=generation;A.busy='uploading';A.error='';render();const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),45000);
    try{const response=await fetch(cfg.base+'api/uploads',{method:'POST',headers:{'Content-Type':file.type||'application/octet-stream','X-File-Name':encodeURIComponent(file.name),'Idempotency-Key':crypto.randomUUID()},body:file,signal:controller.signal}),result=await response.json();if(!response.ok||!result.ok)throw new Error(result.message||t('error'));if(generation!==A.generation)return;A.file=result.upload;A.file.name||=file.name;A.text='';uploaded=true}catch(error){if(generation===A.generation)A.error=error.name==='AbortError'?t('error'):error.message}finally{clearTimeout(timer);if(generation===A.pending){A.pending=null;A.busy='';remember();render();if(uploaded&&cfg.preview&&cfg.checkout?.demoUploadScenario==='praktiker')read()}}
  }
  async function read() {
    if(A.busy)return;if(!A.text.trim()&&!A.file){A.error=t('specEmpty');return render()}
    const generation=A.generation;A.pending=generation;A.busy='reading';A.error='';render();try{const result=await call('spec',A.text.trim()?{text:A.text.trim()}:{upload:A.file.id});if(generation!==A.generation)return;A.allocationReview=result.review||null;A.readingId=result.reading_id||'';A.allocationConfirmed=false;A.demoOrder=result.demo_order||null;S.demoOrder=A.demoOrder;if(A.demoOrder){S.co={...S.co,...A.demoOrder.customer,warehouseConfirmed:''};S.inv='company';S.billOther=true}A.spec=result.lines||[];A.chosen={};A.spec.forEach((line,n)=>{if(line.status==='exact'&&line.matches?.length===1&&K.C.items[line.matches[0]])A.chosen[n]=line.matches[0];A.quantities['spec:'+n]=line.qty||1});A.screen='spec-result'}catch(error){if(generation===A.generation)A.error=error.name==='AbortError'?t('error'):error.message}finally{if(generation===A.pending){A.pending=null;A.busy='';remember();env.render()}}
  }
  async function propose() {
    if(A.busy)return;const generation=A.generation;A.pending=generation;A.busy='preparing';A.error='';render();try{const result=await call('propose',{answers:A.answers});if(generation!==A.generation)return;A.proposal=result;(A.proposal.lines||[]).forEach((line,n)=>A.quantities['proposal:'+n]=line.qty||1);A.screen='proposal'}catch(error){if(generation===A.generation)A.error=error.name==='AbortError'?t('error'):error.message}finally{if(generation===A.pending){A.pending=null;A.busy='';remember();env.render()}}
  }
  function catalogueNote(){
    if(A.entry!=='catalogue')return [];
    const labels={_size:{bg:'Размер',en:'Size'},plate:{bg:'Ширина на планката',en:'Forend width'},width:{bg:'Ширина',en:'Width'},latch:{bg:'Материал на езика',en:'Latch material'},hand:{bg:'Посока',en:'Handing'}};
    const extra={L:{bg:'Лява',en:'Left'},R:{bg:'Дясна',en:'Right'},alloy:{bg:'Цинкова сплав',en:'Zinc alloy'},ceramic:{bg:'Металокерамика',en:'Sintered metal'}};
    return Object.entries(A.filters).sort(([a],[b])=>a==='model'?-1:b==='model'?1:a.localeCompare(b)).map(([key,value])=>{const facet=family()?.facets.find(f=>f.key===key),option=facet?.options.find(o=>facetValue(key,o.value)===facetValue(key,value));return tx(facet?.title||labels[key]||key)+': '+tx(option?.label||extra[value]||String(value))});
  }
  function note() {return (A.entry==='questionnaire'?cfg.questionnaire?.questions||[]:[]).filter(q=>A.answers[q.id]).map(q=>tx(q.title)+': '+list(A.answers[q.id]).map(id=>id==='?'?t('unsure'):tx(q.options.find(o=>o.id===id)?.label)).join(', ')).concat(catalogueNote(),Object.values(A.clarification),A.answers.project||'').filter(Boolean).join('; ').slice(0,900)}
  function addMany(lines,allocation=false) {
    if(holdAllocationChange())return false;
    const basket=JSON.parse(JSON.stringify(S.basket));
    for(const {code,qty=1,why=''} of lines){
      const row=K.C.items[code];if(!row)continue;
      if(!Number.isInteger(qty)||qty<1||qty>9999){A.error=t('quantityError');render();return false}
      const reason=[why,note()].filter(Boolean).join('; ').slice(0,900);
      let remaining=qty;
      const existing=basket.find(line=>String(line.code)===String(code)&&line.why===reason&&line.rows?.length===1&&line.rows[0].n<999);
      if(existing){const take=Math.min(999-existing.rows[0].n,remaining),total=existing.rows[0].n+take;if(!env.quantity||env.quantity(row,total)===total){existing.rows[0].n=total;remaining-=take}}
      while(remaining>0){
        const amount=env.quantity?env.quantity(row,Math.min(999,remaining)):Math.min(999,remaining);
        if(amount<1||amount>remaining){A.error=t('sellingQuantity');render();return false}
        basket.push({code:row.c,rows:[{x:1000,n:amount}],sheet:null,angle:false,why:reason});remaining-=amount;
      }
      if(basket.length>100){A.error=t('capacity');render();return false}
    }
    S.basket=basket;A.error='';A.added=String(lines.at(-1)?.code||'');if(allocation)allocationCapture=context();remember();return true;
  }
  function add(code,qty=1,why=''){return addMany([{code,qty,why}])}
  function confirmItems(codes,after){
    const rows=codes.map(code=>K.C.items[code]).filter(Boolean);
    const next=()=>{for(const row of rows)if(clarifyFor({...row.a,form:row.cat.form},next))return;after?.()};
    next();
  }
  function clarifyFor(filters,after) {
    const q=(def.clarify||[]).find((c,n)=>c.enabled!==false&&!A.clarification[n]&&Object.entries(c.when||{}).every(([key,allowed])=>list(filters[key]).some(value=>list(allowed).some(v=>String(v)===String(value)))));
    if(!q)return false;A.dialogTrigger=env.root().activeElement;A.clarify=q;A.after=after||null;render();return true;
  }
  function revealNextFacet() {
    const panel=env.root().querySelector('.pick-filter-panel');
    if(!panel?.open)return;
    const next=panel.querySelector('.pick-facet[open]'),label=next?.querySelector('.pick-facet-label');
    if(!label)return;
    const bounds=panel.getBoundingClientRect(),header=panel.querySelector(':scope > summary')?.getBoundingClientRect().height||0;
    const target=label.getBoundingClientRect(),first=next.querySelector('.pick-option:not(:disabled)')?.getBoundingClientRect();
    if(target.top<bounds.top+header||target.bottom>bounds.bottom||(first&&first.bottom>bounds.bottom))
      panel.scrollTop=Math.max(0,panel.scrollTop+target.top-bounds.top-header-8);
  }
  function click(event) {
    const el=event.target.closest('button');if(!el)return false;
    if(el.id==='launch'&&!S.open){env.open();return true}
    if(el.dataset.act==='back'&&S.view==='pick'){back();return true}
    const d=el.dataset;if(!d.pick)return false;
    if(el.disabled)return true;
    const action=d.pick;
    if(['start','choose','spec','families','help'].includes(action))go(action);
    else if(action==='family'){A.family=d.family;A.filters={};A.query='';A.limit=60;go('facets');clarifyFor(family().match)}
    else if(action==='filter'){if(String(A.filters[d.key])===d.value)delete A.filters[d.key];else A.filters[d.key]=d.value;A.limit=60;render();revealNextFacet();clarifyFor(A.filters)}
    else if(action==='clear'){A.filters={};A.query='';A.limit=60;render()}
    else if(action==='results')env.root().querySelector('.pick-results-heading')?.scrollIntoView({block:'start',behavior:'smooth'});
    else if(action==='more'){A.limit=(A.limit||60)+60;render()}
    else if(action==='inspect')env.showItem(d.code);
    else if(action==='add'){confirmItems([d.code],()=>{add(d.code,A.quantities[d.slot||d.code]??1);env.render()})}
    else if(action==='cart-step'){const line=S.basket[+d.line];if(line)cartQuantity(+d.line,line.rows[0].n+Number(d.delta))}
    else if(action==='cart-remove'){S.basket.splice(+d.line,1);A.error='';remember();env.render()}
    else if(action==='read')read();
    else if(action==='remove-file'){A.file=null;A.demoOrder=null;S.demoOrder=null;A.allocationReview=null;A.readingId='';A.allocationConfirmed=false;remember();render()}
    else if(action==='section'){if(guideQuestions().some(q=>q.id===d.section)){A.section=A.section===d.section?'':d.section;render()}}
    else if(action==='answer'){
      const q=guideQuestions().find(q=>q.id===d.question);if(!q||!(d.answer==='?'?q.unsure:guideOptions(q).some(o=>o.id===d.answer)))return true;
      A.generation++;A.proposal=null;const old=list(A.answers[q.id]);A.answers[q.id]=d.answer==='?'?['?']:q.kind==='multiple'?(old.includes(d.answer)?old.filter(v=>v!==d.answer):old.filter(v=>v!=='?').concat(d.answer)):[d.answer];pruneAnswers();remember();render();const option=q.options.find(o=>o.id===d.answer);if(option?.match)clarifyFor(option.match)
    }
    else if(action==='propose')propose();
    else if(action==='proposal-question'){A.section=d.section;go('help')}
    else if(action==='select-choice'){
      const choice=A.proposal.choices[+d.choice];if(!choice||!(choice.matching_codes||choice.matches||[]).includes(d.code))return true;
      const slot='choice:'+d.choice+':'+d.code,qty=A.quantities[slot]??choice.qty??1;
      if(!Number.isInteger(qty)||qty<1||qty>9999){A.error=t('quantityError');render();return true}
      confirmItems([d.code],()=>{choice.selected=d.code;A.proposal.lines||=[];const n=A.proposal.lines.length;A.proposal.lines.push({c:d.code,qty,why:choice.title,part:choice.part,included:true});A.quantities['proposal:'+n]=qty;A.proposal.ready=A.proposal.choices.every(c=>c.selected);A.screen='proposal';remember();render()})
    }
    else if(action==='choice-catalogue'){A.activeChoice=+d.choice;A.query='';A.limit=60;A.screen='choice';env.render();env.root().querySelector('.pick-scroll').scrollTop=0}
    else if(action==='request-proposal'){if(holdAllocationChange())return true;if(S.basket.length>=100){A.error=t('capacity');render();return true}const text=[t('helpTitle'),note()].filter(Boolean).join('\n');S.basket.push({custom:text});A.added='request';remember();env.render()}
    else if(action==='add-spec'){if(!allocationReady()||A.demoOrder&&S.co?.warehouseConfirmed!=='yes')return true;const lines=Object.entries(A.chosen).filter(([,code])=>code).map(([n,code])=>({code,qty:A.quantities['spec:'+n]??1,why:A.spec[n].source}));if(A.allocationReview&&S.basket.length){const expected={},actual={};for(const line of lines)expected[line.code]=(expected[line.code]||0)+line.qty;for(const line of S.basket)actual[line.code||'custom']=(actual[line.code||'custom']||0)+(line.rows||[]).reduce((sum,row)=>sum+row.n,0);if(Object.keys(expected).length===Object.keys(actual).length&&Object.entries(expected).every(([code,qty])=>actual[code]===qty)){A.added='matrix';allocationCapture=context();remember();env.render();return true}A.error=K.L.lang==='bg'?'За тази спецификация започнете с празна поръчка.':'Start with an empty order for this specification.';render();return true}confirmItems(lines.map(line=>line.code),()=>{addMany(lines,!!A.allocationReview);env.render()})}
    else if(action==='request-spec'){if(holdAllocationChange())return true;const text=A.spec.filter(line=>!line.matches?.length).map(line=>line.qty+' × '+line.source).join('\n').slice(0,4000);if(text&&S.basket.length<100){S.basket.push({custom:text,...(A.file?{file:A.file}:{})});remember();A.added='request';env.render()}}
    else if(action==='add-proposal'){const lines=(A.proposal.lines||[]).flatMap((line,n)=>line.included!==false?[{code:line.c,qty:A.quantities['proposal:'+n]??line.qty??1,why:tx(line.why)}]:[]);confirmItems(lines.map(line=>line.code),()=>{addMany(lines);env.render()})}
    else if(action==='clarify'){const q=A.clarify,index=def.clarify.indexOf(q),option=q.options.find(o=>String(o.value)===d.value);if(index>=0)A.clarification[index]=tx(q.title)+': '+tx(option?.label);A.clarify=null;const after=A.after;A.after=null;after?.();render();if(!A.clarify)restoreFocus()}
    else if(action==='clarify-close'){A.clarify=null;A.after=null;render();restoreFocus()}
    else if(action==='info'){const help=def.help?.[d.help];if(help){A.dialogTrigger=env.root().activeElement;A.clarify={title:help.title,options:[{value:'close',label:help.text,drawing:help.drawing}]};render()}}
    return true;
  }
  function restoreFocus(){
    const trigger=A.dialogTrigger;A.dialogTrigger=null;
    if(trigger?.isConnected){trigger.focus({preventScroll:true});return}
    const buttons=[...env.root().querySelectorAll('button')];
    const replacement=trigger?.dataset&&buttons.find(button=>Object.entries(trigger.dataset).every(([key,value])=>button.dataset[key]===value));
    (replacement||env.root().querySelector('#back'))?.focus({preventScroll:true});
  }
  function key(event){
    if(A.clarify&&event.key==='Tab'){
      const focusable=[...env.root().querySelectorAll('.pick-clarify button:not([disabled]),.pick-clarify [tabindex="0"]')];
      const first=focusable[0],last=focusable.at(-1),active=env.root().activeElement;
      if(event.shiftKey&&(active===first||!focusable.includes(active))){event.preventDefault();last?.focus()}
      else if(!event.shiftKey&&(active===last||!focusable.includes(active))){event.preventDefault();first?.focus()}
      return true;
    }
    if(event.key==='Escape'&&(A.clarify||S.view==='pick'&&A.screen!=='start')){event.preventDefault();back();return true}
    return false;
  }
  function input(event) {const el=event.target,d=el.dataset;if(d.pickOrderField!=null){S.co||={};S.co[d.pickOrderField]=el.value;S.co.warehouseConfirmed='';const check=env.root().querySelector('[data-pick-customer-confirm]');if(check)check.checked=false;const add=env.root().querySelector('[data-pick="add-spec"]');if(add)add.disabled=true}if(d.pickText!=null){A.allocationReview=null;A.readingId='';A.allocationConfirmed=false;A.text=el.value;A.spec=[];A.chosen={};A.generation++}if(d.pickProject!=null){A.answers.project=el.value;A.proposal=null;A.generation++}if(d.pickQuery!=null){A.query=el.value;A.limit=60;render()}if(d.pickQty!=null){const n=Number(el.value);A.quantities[d.pickQty]=n}remember()}
  function change(event){const el=event.target,d=el.dataset;if(d.pickAllocationConfirm!=null){A.allocationConfirmed=el.checked;render()}if(d.pickCustomerConfirm!=null){S.co.warehouseConfirmed=el.checked?'yes':'';render()}if(d.pickWarehouse!=null){const w=A.demoOrder?.warehouses?.find(w=>w.id===el.value);if(w){Object.assign(S.co,{warehouseId:w.id,warehouseName:w.name,warehouseErpCode:w.erpCode||w.erp_code||'',warehouseConfirmed:''});render()}}if(d.pickCartQty!=null)cartQuantity(+d.pickCartQty,Number(el.value));if(d.pickFile!=null&&el.files?.[0])upload(el.files[0]);if(d.pickMatch!=null){A.chosen[d.pickMatch]=el.value;A.allocationConfirmed=false;render()}if(d.pickInclude!=null){A.proposal.lines[+d.pickInclude].included=el.checked;render()}remember()}
  function drag(event){const drop=event.target.closest('#pick-drop');if(!drop)return;event.preventDefault();drop.classList.toggle('over',event.type==='dragover');if(event.type==='drop'&&event.dataTransfer?.files?.[0])upload(event.dataTransfer.files[0])}
  function stamp(customer){delete customer.questionnaire;delete customer.specification;delete customer.specification_file;customer.capture=context();delete customer.capture.demo_order;if(customer.capture.specification){const spec=customer.capture.specification;delete spec.review;if(spec.text)customer.specification=spec.text;if(spec.file_id)customer.specification_file=spec.file_id}return customer}
  return {render,click,confirmItems,note,key,start:()=>go('start'),resume:()=>go(A.screen==='start'?'families':A.screen),stamp,reset:()=>{allocationCapture=null;A.entry='';S.capture=null;A.demoOrder=null;S.demoOrder=null;A.allocationReview=null;A.readingId='';A.allocationConfirmed=false;A.generation++;A.pending=null;A.busy='';A.answers={};A.proposal=null;A.text='';A.file=null;A.spec=[];A.chosen={};A.quantities={};A.clarification={};A.screen='start'},state:A};
}
window.RocotoPick={ui,matches,values,searches};
})();
