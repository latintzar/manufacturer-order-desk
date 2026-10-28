/* Human conversations: service with the company team and a customer's complete correspondence. */
(() => {
  'use strict';
  let workspaceHost=null;
  const node=(tag,cls='',text)=>{const e=document.createElement(tag);e.className=cls;if(text!==undefined)e.textContent=text;return e;};
  const icon=name=>{const s=document.createElementNS('http://www.w3.org/2000/svg','svg');s.setAttribute('class','icon');s.setAttribute('aria-hidden','true');const u=document.createElementNS(s.namespaceURI,'use');u.setAttribute('href','#i-'+name);s.append(u);return s;};
  const button=(label,symbol,action)=>{const b=node('button','mh-icon');b.type='button';b.title=label;b.setAttribute('aria-label',label);b.append(icon(symbol));b.addEventListener('click',action);return b;};
  async function api(path,payload){let r;try{r=await fetch('/api/manufacturer/'+path,{cache:'no-store',...(payload?{method:'POST',headers:{'Content-Type':'application/json','X-Rocoto-Page':'1'},body:JSON.stringify(payload)}:{})});}catch{throw Error('Check your connection and try again.');}let value={};try{value=await r.json();}catch{}if(!r.ok)throw Error(r.status===409?'A newer version is available. Review it before sending.':r.status===503?(path.startsWith('conversations/')?'Set up email delivery to send this review.':'Reconnecting. Try again.'):r.status===403?'Sign in to the workspace.':'Try again.');return value;}
  function conversationView(root,{customerId=null,orderId=null,onClose,onExpand,identity='',isCurrent=()=>true}){
    let disposed=false,visible=true,loading=false,ready=false,epoch=0,timer,signature='',data=null,pending=null,olderLoading=false,nextBefore=null,cursorReady=false;
    const messagesById=new Map();
    const current=()=>!disposed&&isCurrent();
    const path=customerId?'conversations/'+encodeURIComponent(customerId):'service-conversation';
    const draftKey=identity?'manufacturer-human-draft:'+identity+':'+(customerId||'service'):null;
    const shell=node('section','mh-conversation'),header=node('header','mh-header'),avatar=node('span','mh-avatar',customerId?'C':'T'),heading=node('div','mh-heading'),title=node('h2','',customerId?'Customer conversation':'Team'),subtitle=node('p','',customerId?'Messages and orders':'Your team'),actions=node('div','mh-header-actions');
    heading.append(title,subtitle);header.append(avatar,heading,actions);if(onExpand){const expand=button('Expand','fullscreen',()=>{const expanded=onExpand();expand.setAttribute('aria-expanded',String(expanded));expand.title=expanded?'Collapse':'Expand';expand.setAttribute('aria-label',expand.title);});expand.classList.add('mh-expand');expand.setAttribute('aria-expanded','false');actions.append(expand);}if(onClose)actions.append(button('Close','close',onClose));
    const history=node('div','mh-history');history.setAttribute('role','log');history.setAttribute('aria-label','Conversation history');history.tabIndex=0;history.setAttribute('aria-busy','true');for(let i=0;i<3;i++){const placeholder=node('div','mh-history-skeleton');placeholder.setAttribute('aria-hidden','true');history.append(placeholder);}
    const form=node('form','mh-compose'),to=node('div','mh-recipient'),text=node('textarea'),footer=node('div','mh-compose-footer'),channel=node('span','mh-channel',customerId?'Email':'Team message'),send=button('Send','send',()=>{}),notice=node('p','mh-notice');
    text.placeholder=customerId?'Write to the customer…':'Write to your team…';text.setAttribute('aria-label','Message');text.maxLength=12000;text.rows=3;send.type='submit';send.disabled=true;notice.hidden=true;notice.setAttribute('role','status');
    try{if(draftKey){text.value=sessionStorage.getItem(draftKey)||'';pending=JSON.parse(sessionStorage.getItem(draftKey+':submission')||'null');}}catch{}
    footer.append(channel,send);form.append(to,text,footer);shell.append(header,history,notice,form);root.replaceChildren(shell); window.RocotoManufacturerFooter?.(shell);
    function keepDraft(){try{if(draftKey){if(text.value)sessionStorage.setItem(draftKey,text.value);else sessionStorage.removeItem(draftKey);}}catch{}send.disabled=!current()||!ready||!text.value.trim()||loading||Boolean(customerId&&data?.delivery_ready!==true);}
    function resizeText(){text.style.height='auto';text.style.height=Math.min(160,text.scrollHeight)+'px';}
    text.addEventListener('input',()=>{keepDraft();resizeText();});
    text.addEventListener('keydown',event=>{if(event.key==='Enter'&&(event.metaKey||event.ctrlKey)){event.preventDefault();form.requestSubmit();}});
    function metadata(message){
      const meta=node('div','mh-message-meta');
      meta.append(node('span','',message.author_name||(message.author_type==='system'?'System':'Team')));
      if(message.created_at){const d=new Date(typeof message.created_at==='number'?message.created_at*1000:message.created_at);if(Number.isFinite(d.valueOf())){const time=node('time','',new Intl.DateTimeFormat('en-GB',{hour:'2-digit',minute:'2-digit',day:'numeric',month:'short'}).format(d));time.dateTime=d.toISOString();meta.append(time);}}
      const status=message.delivery?.status||message.delivery_state||message.delivery?.state||message.delivery_status;
      const label=({pending:'Prepared',sending:'Sending',sent:'Sent',delivered:'Delivered',failed:'Ready to resend',uncertain:'Checking delivery'})[status];
      if(label)meta.append(node('span','mh-delivery',label));return meta;
    }
    function eventNode(message){
      const order=message.order||message.payload?.order||{},details=message.data||{},related=message.order_id||details.order_id||order.id;
      const labels={order:'Order received',order_card:'Order received',order_submitted:'Order received',order_updated:'Order updated',proposal:'Review version',customer_confirmation:'Customer confirmed',customer_change_requested:'Change requested'};
      let row;
      if(labels[message.kind]&&related){
        row=node('article','mh-order-event'+(message.kind==='customer_confirmation'?' mh-confirmed':''));
        const card=node('a','mh-order-card');card.href='?view=orders&order='+encodeURIComponent(related);card.dataset.manufacturerRoute='orders';
        if(orderId&&related===orderId)card.setAttribute('aria-current','true');
        const heading=node('strong','mh-order-title',message.order_number||order.display_number||order.number||'Order');
        const version=message.version||details.version;if(version)heading.append(node('small','mh-order-version','Version '+version));
        card.append(icon('package'),heading,node('span','mh-order-summary',labels[message.kind]),icon('chevron'));
        row.append(card);
        if(message.text)row.append(node('p','mh-event-note',message.text));
        row.append(metadata(message));
      }else if(['system','review','email_intent'].includes(message.kind)){
        row=node('article','mh-system');let label=message.text||message.body||message.summary;
        if(message.kind==='email_intent'){
          const topic=({question:'question',change_request:'change',confirmation:'confirmation',cancellation:'cancellation',other:'other',unknown:'clarification'})[details.intent]||'clarification';
          label=(details.ambiguous?'Topic to review: ':'Suggested topic: ')+topic;
        }
        row.append(node('p','',label||'Conversation event'),metadata(message));
      }else{
        row=node('article','mh-message '+(message.direction==='inbound'?'mh-incoming':'mh-outgoing'));
        row.append(node('div','mh-bubble',message.text||message.body||'Conversation event'),metadata(message));
      }
      row.dataset.messageId=message.id;return row;
    }
    const older=node('button','mh-older','Earlier messages');older.type='button';older.hidden=true;
    function render(value,{prepend=false,latest=false}={}){
      const first=!ready;ready=true;
      if(latest||!data)data=value;
      if(!cursorReady||prepend){nextBefore=value.has_more?value.next_before:null;cursorReady=true;}
      for(const message of value.messages||[]){if(!prepend||!messagesById.has(message.id))messagesById.set(message.id,message);}
      title.textContent=data.customer?.display_name||data.customer?.company||data.title||(customerId?'Customer':'Team');avatar.textContent=title.textContent.slice(0,1).toLocaleUpperCase();
      if(customerId){const recipients=data.contacts||data.customer?.contacts||[];to.textContent=recipients.find(c=>c.email)?.email||'Customer email';to.hidden=false;if(data.delivery_ready===false){channel.textContent='Email · setup';notice.textContent='Email setup is in progress. Your draft stays saved here.';notice.hidden=false;}}
      else to.hidden=true;
      const messages=[...messagesById.values()].sort((a,b)=>a.sequence-b.sequence),next=JSON.stringify([messages,nextBefore]);
      older.disabled=olderLoading;older.textContent=olderLoading?'Loading…':'Earlier messages';
      if(next===signature){keepDraft();return;}signature=next;
      const pinned=history.scrollHeight-history.scrollTop-history.clientHeight<90,oldTop=history.scrollTop;
      const top=history.getBoundingClientRect().top,anchor=[...history.querySelectorAll('[data-message-id]')].find(el=>el.getBoundingClientRect().bottom>top);
      const anchorId=anchor?.dataset.messageId,anchorTop=anchor?.getBoundingClientRect().top,fragment=document.createDocumentFragment();
      older.hidden=!nextBefore;fragment.append(older);for(const message of messages)fragment.append(eventNode(message));
      if(!messages.length){const empty=node('div','mh-empty');empty.append(icon('chat'),node('h3','',customerId?'Customer conversation':'Team chat'),node('p','',customerId?'Orders and messages appear here.':'Send changes, prices and questions here.'));fragment.append(empty);}
      const olderFocused=document.activeElement===older;
      history.setAttribute('aria-busy','false');history.replaceChildren(fragment);
      if(first||pinned&&!prepend)history.scrollTop=history.scrollHeight;
      else{const target=anchorId&&[...history.querySelectorAll('[data-message-id]')].find(el=>el.dataset.messageId===anchorId);history.scrollTop=target?oldTop+target.getBoundingClientRect().top-anchorTop:oldTop;}
      if(olderFocused){if(older.hidden)history.focus({preventScroll:true});else older.focus({preventScroll:true});}keepDraft();
    }
    function historyPath(before){const query=new URLSearchParams();if(orderId)query.set('order_id',orderId);if(before)query.set('before',before);return path+(query.size?'?'+query:'');}
    async function load(){
      if(!current()||!visible||document.hidden)return;const version=++epoch;
      try{
        const value=await api(historyPath());if(!current()||version!==epoch)return;
        const previousLatest=Math.max(0,...[...messagesById.values()].map(m=>m.sequence));
        let page=value;
        // Bridge a burst larger than one page so polling cannot leave a hidden gap.
        while(previousLatest&&page.has_more&&page.messages?.length&&page.messages[0].sequence>previousLatest){
          page=await api(historyPath(page.next_before));if(!current()||version!==epoch)return;
          for(const message of page.messages||[])if(!messagesById.has(message.id))messagesById.set(message.id,message);
        }
        render(value,{latest:true});
      }catch(error){if(current()&&version===epoch){notice.textContent=error.message;notice.hidden=false;history.setAttribute('aria-busy','false');if(!ready)history.replaceChildren(node('p','mh-system','Reloading conversation history…'));}}
      finally{clearTimeout(timer);if(current()&&visible)timer=setTimeout(load,5000);}
    }
    older.addEventListener('click',async()=>{
      if(!current()||olderLoading||!nextBefore)return;olderLoading=true;older.disabled=true;older.textContent='Loading…';
      try{const value=await api(historyPath(nextBefore));if(current())render(value,{prepend:true});}
      catch(error){if(current()){notice.textContent=error.message;notice.hidden=false;}}
      finally{olderLoading=false;if(current()){older.disabled=false;older.textContent='Earlier messages';}}
    });
    form.addEventListener('submit',async event=>{
      event.preventDefault();if(!current()||!ready||loading||!text.value.trim()||customerId&&data?.delivery_ready!==true)return;
      const submitted=text.value,content=submitted.trim();
      if(!pending||pending.text!==content)pending={text:content,idempotency_key:crypto.randomUUID()};
      try{if(draftKey)sessionStorage.setItem(draftKey+':submission',JSON.stringify(pending));}catch{}
      const payload={...pending,...(orderId?{order_id:orderId}:{})};loading=true;keepDraft();form.setAttribute('aria-busy','true');notice.hidden=true;
      try{await api(path+'/messages',payload);if(!current())return;if(text.value===submitted){text.value='';resizeText();}pending=null;try{if(draftKey)sessionStorage.removeItem(draftKey+':submission');}catch{}keepDraft();signature='';await load();}
      catch(error){if(current()){notice.textContent=error.message;notice.hidden=false;}}
      finally{loading=false;form.setAttribute('aria-busy','false');keepDraft();}
    });
    const visibility=()=>{if(!document.hidden&&visible)load();};document.addEventListener('visibilitychange',visibility);
    load();return{focus(){text.focus({preventScroll:true});},show(){const changed=!visible;visible=true;if(changed)load();},hide(){visible=false;clearTimeout(timer);},dispose(){disposed=true;epoch++;clearTimeout(timer);document.removeEventListener('visibilitychange',visibility);keepDraft();}};
  }

  window.RocotoManufacturerConversations={install(host){
    workspaceHost=host;
    const panel=node('aside','mh-panel'),scrim=node('button','mh-scrim');panel.hidden=true;scrim.hidden=true;scrim.type='button';scrim.setAttribute('aria-label','Close conversation');panel.setAttribute('aria-label','Customer conversation');document.body.append(scrim,panel);let view,opener,open=false;
    function sync(){const modal=matchMedia('(max-width:1199px)').matches;document.body.classList.toggle('mh-panel-open',open);scrim.hidden=!open||!modal;panel.setAttribute('role',modal?'dialog':'complementary');if(modal)panel.setAttribute('aria-modal','true');else panel.removeAttribute('aria-modal');const main=document.querySelector('body > .workspace'),sidebar=document.getElementById('sidebar');if(main)main.inert=open&&modal;if(sidebar)sidebar.inert=open&&modal;}
    function close(){open=false;panel.hidden=true;panel.classList.remove('mh-expanded');view?.dispose();view=null;sync();if(opener?.isConnected)opener.focus({preventScroll:true});}
    function show(detail={}){if(!host.session)return;const trigger=document.activeElement;close();opener=trigger;open=true;panel.hidden=false;sync();const identity=host.storageIdentity;view=conversationView(panel,{customerId:detail.customerId||detail.context?.customer_id,orderId:detail.orderId||detail.context?.id,identity:host.storageIdentity,isCurrent:()=>Boolean(host.session)&&host.storageIdentity===identity,onClose:close,onExpand:()=>panel.classList.toggle('mh-expanded')});panel.querySelector('[aria-label="Close"]')?.focus();}
    scrim.addEventListener('click',close);window.addEventListener('resize',sync);document.addEventListener('keydown',e=>{if(e.key==='Escape'&&open&&!document.querySelector('dialog[open]')){e.preventDefault();close();}});panel.addEventListener('keydown',e=>{if(e.key!=='Tab'||!matchMedia('(max-width:1199px)').matches)return;const nodes=[...panel.querySelectorAll('button:not([disabled]),textarea,a[href],[tabindex="0"]')],first=nodes[0],last=nodes.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus();}});
    document.addEventListener('manufacturer:customer-chat',e=>show(e.detail));return{open:show,close,reset:close};
  }};
  window.RocotoWorkspaceTabs.register('manufacturer',{service:{mount(root,context){root.classList.add('mh-service-page');const identity=workspaceHost?.storageIdentity||'';const view=conversationView(root,{identity,isCurrent:()=>context.isCurrent()&&Boolean(workspaceHost?.session)&&workspaceHost.storageIdentity===identity});return{show:()=>view.show(),hide:()=>view.hide(),unmount(){view.dispose();root.classList.remove('mh-service-page');root.replaceChildren();}};}}});
})();
