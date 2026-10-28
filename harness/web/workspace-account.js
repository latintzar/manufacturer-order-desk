/* Shared hosted sign-in and workspace billing. Provider secrets stay on the server. */
(() => {
  'use strict';
  const n = (tag, cls='', text) => { const el=document.createElement(tag); el.className=cls; if(text!==undefined)el.textContent=text; return el; };
  const bg=()=>document.body.classList.contains('manufacturer-workspace');
  const t=(en,bulgarian)=>bg()?bulgarian:en;
  const money=(v,currency='USD')=>Number.isFinite(Number(v))?new Intl.NumberFormat(bg()?'bg-BG':'en',{style:'currency',currency}).format(Number(v)):'—';
  const date=v=>v?new Intl.DateTimeFormat(bg()?'bg-BG':'en',{day:'numeric',month:'short',year:'numeric'}).format(new Date(Number(v)*1000)):'';
  let loginConfig=null, billingIdentity='', billingEpoch=0,accountIdentity='',accountEpoch=0,loginEpoch=0;
  const sessionIdentity=session=>JSON.stringify([session?.environment?.id,session?.principal?.id]);
  async function api(path,body){const response=await fetch(path,{cache:'no-store',...(body?{method:'POST',headers:{'Content-Type':'application/json','X-Rocoto-Page':'1'},body:JSON.stringify(body)}:{})});let data;try{data=await response.json();}catch{data={};}if(!response.ok)throw Error(response.status===403?t('Ask your workspace administrator to manage billing.','Свържете се с администратора за управление на плащанията.'):response.status===503?t('Setup is in progress. Contact your service team.','Настройката е в процес. Свържете се с екипа.'):t('Please try again.','Опитайте отново.'));return data;}
  async function mountLogin(){
    const form=document.getElementById('session-form');if(!form)return;const epoch=++loginEpoch;
    form.querySelector('#workspace-sign-in')?.remove();form.querySelector('.wa-divider')?.remove();
    const explore=document.getElementById('explore-demo');if(explore)explore.textContent=t('Explore demo','Разгледай демото');
    const label=form.querySelector('label[for="session-code"]');if(label)label.textContent=t('Demo code','Демо код');
    try{const value=await api('/api/auth/config');if(epoch!==loginEpoch)return;loginConfig=value;}catch{return;}
    form.classList.toggle('wa-hosted-login',Boolean(loginConfig.enabled));
    const brand=loginConfig.workspaces?.[0], title=form.querySelector('h1');
    if(brand?.name&&title)title.textContent=brand.name;
    if(brand?.logo){try{const url=new URL(brand.logo,location.origin);if(url.protocol==='https:'||url.origin===location.origin){const img=n('img');img.src=url.href;img.alt=brand.name||'';const mark=form.querySelector('.mf-signin-brand');if(mark)mark.replaceChildren(img);else form.querySelector(':scope > img')?.replaceWith(img);}}catch{}}
    if(loginConfig.enabled){
      const link=n('a','wa-signin',t('Continue with Google or email','Вход с Google или имейл'));link.href=loginConfig.login_url||'/auth/login';link.id='workspace-sign-in';
      const divider=n('div','wa-divider',t('or use a demo code','или с демо код'));label.before(link,divider);
      const intro=document.getElementById('session-intro');if(intro)intro.textContent=t('Sign in to your workspace.','Влезте в работното си пространство.');
    }
    const error=new URL(location.href).searchParams.get('auth_error');if(error){document.getElementById('session-message').textContent=t('Start sign-in again to continue.','Започнете входа отново.');const url=new URL(location.href);url.searchParams.delete('auth_error');history.replaceState({},'',url);}
  }
  function renderBilling(root,{session,icon,onUsage}={}){
    const identity=sessionIdentity(session);
    if(root.dataset.billingIdentity===identity&&root.childElementCount)return;
    billingIdentity=identity;root.dataset.billingIdentity=identity;const epoch=++billingEpoch;
    const page=n('div','wa-billing'), header=n('header','wa-heading');const publicBrand=loginConfig?.workspaces?.find(row=>row.id===session?.environment?.id);header.append(n('h1','',publicBrand?.name||session?.environment?.name||t('Workspace','Работно пространство')));page.append(header);root.replaceChildren(page);
    for(let i=0;i<3;i++){const skeleton=n('div','wa-card wa-skeleton');skeleton.setAttribute('aria-hidden','true');page.append(skeleton);}page.setAttribute('aria-busy','true');
    const current=()=>billingIdentity===identity&&billingEpoch===epoch&&root.isConnected;
    const button=(label,action,primary=false,symbol,compact=false)=>{const el=n('button',primary?'wa-button wa-primary':'wa-button',label);el.type='button';if(symbol&&icon)el.prepend(icon(symbol));if(compact){el.classList.add('wa-icon-button');el.title=label;el.setAttribute('aria-label',label);if(icon){el.replaceChildren(icon(symbol));}}el.addEventListener('click',action);return el;};
    const notice=n('p','wa-notice');notice.setAttribute('role','status');notice.hidden=true;
    async function redirect(path){notice.hidden=true;const controls=[...page.querySelectorAll('button')];controls.forEach(b=>b.disabled=true);try{const value=await api(path,{request_id:crypto.randomUUID()});const url=new URL(value.url);if(url.protocol!=='https:'||!['billing.stripe.com','checkout.stripe.com'].includes(url.hostname))throw Error(t('Open billing again.','Отворете плащанията отново.'));if(current())location.assign(url.href);}catch(error){if(current()){notice.textContent=error.message;notice.hidden=false;controls.forEach(b=>b.disabled=false);}}}
    api('/api/billing/status').then(data=>{
      if(!current())return;page.replaceChildren(header);page.setAttribute('aria-busy','false');
      const plan=n('section','wa-card'), top=n('div','wa-card-top'), identityBox=n('div'), status=n('span','wa-status',data.mode==='uncommissioned'?t('Setup','Настройка'):data.mode==='demo'?(data.operational?t('Demo workspace','Демо пространство'):t('Demo ended','Демо периодът приключи')):data.operational?t('Active','Активен'):t('Payment required','Плащане'));
      identityBox.append(n('h2','',data.plan_name||t('Your subscription','Вашият абонамент')));top.append(identityBox,status);plan.append(top);
      const sub=data.subscription||{};if(data.amount!=null){const amount=n('p','wa-price',money(data.amount,data.currency));amount.append(n('span','',data.interval==='year'?t(' / year',' / година'):t(' / month',' / месец')));plan.append(amount);}
      if(data.mode==='demo')plan.append(n('p','wa-muted',data.demo_expires_at?t(`Available through ${date(data.demo_expires_at)}`,`Достъп до ${date(data.demo_expires_at)}`):t('Prepared for your company.','Подготвено за вашата фирма.')));
      else if(sub.current_period_end)plan.append(n('p','wa-muted',sub.cancel_at_period_end?t(`Available through ${date(sub.current_period_end)}`,`Достъп до ${date(sub.current_period_end)}`):t(`Next renewal ${date(sub.current_period_end)}`,`Следващо подновяване ${date(sub.current_period_end)}`)));
      const actions=n('div','wa-actions');if(data.portal_available)actions.append(button(t('Manage subscription','Управление на абонамента'),()=>redirect('/api/billing/portal'),true));else if(data.checkout_available)actions.append(button(t('Activate subscription','Активиране на абонамент'),()=>redirect('/api/billing/checkout'),true));
      if(actions.childElementCount)plan.append(actions);page.append(plan);
      if(data.credits){const card=n('section','wa-card'), row=n('div','wa-card-top');row.append(n('h2','',t('Usage credits','Кредити за потребление')),button(t('Usage','Потребление'),()=>onUsage?.(),false,'chart',true));card.append(row,n('p','wa-price',money(data.credits.available_usd)));if(data.credit_checkout_available)card.append(button(t('Add credits','Добавяне на кредити'),()=>redirect('/api/billing/credits'),false,'plus'));page.append(card);}
      const payments=n('section','wa-card'), line=n('div','wa-card-top');line.append(n('h2','',t('Invoices & payment method','Фактури и начин на плащане')));payments.append(line);
      if(data.portal_available){payments.append(n('p','wa-muted',t('View invoices and update your card securely in Stripe.','Преглеждайте фактурите и обновявайте картата си в Stripe.')),button(t('Open billing details','Фактури и карта'),()=>redirect('/api/billing/portal'),false,'external'));}
      else payments.append(n('p','wa-muted',t('Your billing details appear when your subscription is activated.','Данните за плащане се показват при активиране на абонамента.')));
      page.append(payments,notice);
    }).catch(error=>{if(!current())return;page.replaceChildren(header,n('p','wa-notice',error.message),button(t('Try again','Опитайте отново'),()=>{delete root.dataset.billingIdentity;renderBilling(root,{session,icon,onUsage});}));page.setAttribute('aria-busy','false');});
  }
  async function sessionReady(session){
    if(!session?.authenticated)return;
    const identity=sessionIdentity(session);
    if(accountIdentity!==identity){accountIdentity=identity;accountEpoch++;document.querySelector('.wa-workspace-dialog')?.close();}
    if(new URL(location.href).searchParams.get('workspaces')!=='1'||document.querySelector('.wa-workspace-dialog'))return;
    const epoch=++accountEpoch;let result;try{result=await api('/api/workspaces');}catch{return;}
    if(epoch!==accountEpoch||identity!==accountIdentity)return;
    const rows=result.workspaces||result.environments||[];if(!rows.length)return;
    const dialog=n('dialog','wa-workspace-dialog'),heading=n('h1','',t('Your workspaces','Вашите пространства')),notice=n('p','wa-notice');
    notice.hidden=true;notice.setAttribute('role','status');dialog.setAttribute('aria-labelledby','wa-workspace-heading');heading.id='wa-workspace-heading';dialog.append(heading);
    for(const workspace of rows){
      const b=n('button','wa-workspace-option'),avatar=n('span','wa-workspace-avatar',(workspace.name||'W').slice(0,1)),copy=n('span','wa-workspace-name',workspace.name||workspace.id);b.type='button';b.append(avatar,copy);
      if(workspace.selected){b.setAttribute('aria-current','true');b.append(n('span','wa-workspace-current',t('Current','Текущо')));}
      b.addEventListener('click',async()=>{
        const controls=[...dialog.querySelectorAll('button')];controls.forEach(control=>control.disabled=true);notice.hidden=true;
        try{await api('/api/workspaces/select',{environment_id:workspace.id||workspace.environment_id});if(epoch===accountEpoch&&identity===accountIdentity)location.assign('/');}
        catch(error){if(!dialog.isConnected)return;controls.forEach(control=>control.disabled=false);notice.textContent=error.message;notice.hidden=false;}
      });dialog.append(b);
    }
    const close=n('button','wa-button',t('Continue','Продължи'));close.type='button';close.addEventListener('click',()=>dialog.close());dialog.append(notice,close);
    dialog.addEventListener('close',()=>{if(epoch===accountEpoch)accountEpoch++;if(identity===accountIdentity){const u=new URL(location.href);u.searchParams.delete('workspaces');history.replaceState({},'',u);}dialog.remove();});document.body.append(dialog);dialog.showModal();
  }

  window.RocotoWorkspaceAccount=Object.freeze({mountLogin,renderBilling,sessionReady,reset(){accountEpoch++;accountIdentity='';document.querySelector('.wa-workspace-dialog')?.close();billingEpoch++;billingIdentity='';document.querySelectorAll('[data-billing-identity]').forEach(el=>delete el.dataset.billingIdentity);}});
})();
