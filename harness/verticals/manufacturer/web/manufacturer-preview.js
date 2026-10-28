/* Read a saved document through the real widget in an opaque sandbox. */
(() => {
  'use strict';
  const saved = window.__manufacturerPreview;
  const reply = (body, status = 200) => Promise.resolve(new Response(JSON.stringify(body), {status, headers:{'Content-Type':'application/json'}}));
  window.fetch = (input, options = {}) => {
    const value = typeof input === 'string' ? input : input.url;
    let path; try { path = new URL(value, location.href).pathname; } catch { return reply({ok:false,message:'Open the website configurator to send an order.'},400); }
    const relative = path.split('/rocoto/')[1] || '';
    if (relative === 'catalog.json') return reply(structuredClone(saved.catalogue));
    if (relative === 'api/supply') return reply({items:{},ready:null});
    if (relative === 'g/index.json' || relative === 't/index.json') return reply(saved.indexes[relative] || {});
    return reply({ok:false,message:'Send the order through the website configurator.'},409);
  };
  let ready = false;
  function apply(settings) {
    const root = document.getElementById('rocoto-configurator')?.shadowRoot;
    if (!root) return;
    if (/^#[a-f0-9]{6}$/i.test(settings.accent || '')) root.querySelector('.r')?.style.setProperty('--accent',settings.accent);
    if (typeof settings.headline === 'string') { const heading = root.querySelector('.a-intro h1, .a-hero h1, .ask h1, .pick-entry .pick-heading h1'); if (heading) heading.textContent = settings.headline; }
    if (typeof settings.description === 'string') { const description = root.querySelector('.a-intro p, .a-hero p, .pick-entry .pick-heading p'); if (description) description.textContent = settings.description; }
  }
  window.addEventListener('message',event => {
    if(event.source !== parent || event.data?.type !== 'rocoto:preview-settings' || !event.data.settings || typeof event.data.settings !== 'object') return;
    saved.settings = {...saved.settings,...event.data.settings}; apply(saved.settings);
  });
  const timer = setInterval(() => {
    const root = document.getElementById('rocoto-configurator')?.shadowRoot;
    if (!root?.querySelector('#launch') || !root.querySelector('#sheet') || !window.RocotoConfigurator?.open) return;
    clearInterval(timer);
    document.getElementById('preview-status')?.remove();
    window.RocotoConfigurator?.open();
    const style = document.createElement('style');
    style.textContent = '.sheet{inset:0!important;width:100%!important;max-width:100%!important;height:100dvh!important;max-height:100dvh!important;border-radius:0!important}.scrim,.launch,.head .x{display:none!important}';
    root.append(style);
    apply(saved.settings); ready = true;
    parent.postMessage({type:'rocoto:preview-ready',capabilities:['settings']},'*');
  },80);
  setTimeout(() => { if(!ready){clearInterval(timer);const status=document.getElementById('preview-status');if(status)status.textContent='The saved configurator preview is loading.';} },12000);
})();
