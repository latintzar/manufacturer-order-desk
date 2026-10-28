/* A copied script opens the same company configurator on its own origin. */
window.RocotoEmbed=function(){
  'use strict';
  const script=document.currentScript;
  if(!script?.src)return false;
  const source=new URL(script.src);
  if(source.origin===location.origin)return false;
  const config=window.RocotoConfig||{},language=document.documentElement.lang.startsWith('bg')?'bg':'en';
  const labels=config.strings?.[language]||{},label=labels.launchGo||(language==='bg'?'Конфигурирай':'Configure');
  const frameURL=new URL('embed.html',source);frameURL.searchParams.set('rocoto_embed','1');frameURL.searchParams.set('lang',language);frameURL.hash='order';
  function mount(){
    if(document.getElementById('rocoto-embed'))return;
    const host=document.createElement('div');host.id='rocoto-embed';
    const shadow=host.attachShadow({mode:'open'}),style=document.createElement('style');
    style.textContent=':host{all:initial;position:fixed;right:24px;bottom:24px;z-index:2147483000;font-family:Arial,sans-serif}button{display:flex;align-items:center;gap:12px;min-height:48px;padding:12px 20px;border:1px solid #d8dce1;border-radius:8px;background:white;color:#20242a;font:600 16px Arial,sans-serif;box-shadow:0 4px 20px #0002;cursor:pointer}button img{width:72px;height:28px;object-fit:contain}button:focus-visible{outline:3px solid #3267b1;outline-offset:3px}dialog{position:fixed;inset:0;width:100vw;height:100dvh;max-width:none;max-height:none;margin:0;padding:0;border:0;background:transparent}dialog::backdrop{background:#0006}iframe{display:block;width:100%;height:100%;border:0;background:transparent}@media(max-width:480px){:host{right:16px;bottom:16px}}';
    const button=document.createElement('button');button.type='button';button.setAttribute('aria-haspopup','dialog');
    if(config.logo){const logo=document.createElement('img');logo.src=new URL(config.logo,source).href;logo.alt='';button.append(logo)}
    button.append(document.createTextNode(label));shadow.append(style,button);document.body.append(host);
    let dialog=null,frame=null,overflow='';
    function close(notify=true){if(!dialog?.open)return;dialog.close();if(notify)frame.contentWindow.postMessage({type:'rocoto:hide'},source.origin);document.documentElement.style.overflow=overflow;button.focus()}
    button.addEventListener('click',()=>{
      if(dialog?.open)return;
      if(!dialog){dialog=document.createElement('dialog');dialog.setAttribute('aria-label',language==='bg'?'Поръчка':'Order configurator');
      frame=document.createElement('iframe');frame.src=frameURL.href;frame.title=dialog.getAttribute('aria-label');
      frame.setAttribute('allow','clipboard-write');frame.referrerPolicy='strict-origin-when-cross-origin';
      dialog.append(frame);shadow.append(dialog);dialog.addEventListener('cancel',event=>{event.preventDefault();close()});}
      overflow=document.documentElement.style.overflow;document.documentElement.style.overflow='hidden';dialog.showModal();frame.focus();frame.contentWindow.postMessage({type:'rocoto:open'},source.origin);
    });
    window.addEventListener('message',event=>{if(frame&&event.source===frame.contentWindow&&event.origin===source.origin&&event.data?.type==='rocoto:close')close(false)});
  }
  if(document.body)mount();else document.addEventListener('DOMContentLoaded',mount,{once:true});
  return true;
};
