/* Original customer specifications, scoped to the current company's order. */
(() => {
  'use strict';
  const make = (tag, cls = '', text = '') => { const el = document.createElement(tag); el.className = cls; el.textContent = text; return el; };
  function icon(name) { const el = document.createElementNS('http://www.w3.org/2000/svg', 'svg'), use = document.createElementNS(el.namespaceURI, 'use'); el.classList.add('icon'); el.setAttribute('aria-hidden', 'true'); use.setAttribute('href', '#i-' + name); el.append(use); return el; }
  function control(label, name) { const el = make('button', 'mof-icon'); el.type = 'button'; el.title = label; el.setAttribute('aria-label', label); el.append(icon(name)); return el; }
  const size = bytes => bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  function preview(file, trigger) {
    const modal = make('dialog', 'mof-drawer'), head = make('header'), title = make('div', 'mof-title');
    const heading = make('h2', '', file.name); heading.id = 'mof-preview-title'; modal.setAttribute('aria-labelledby', heading.id);
    title.append(heading, make('p', '', `Original file · ${size(file.size)}`));
    const download = make('a', 'mof-icon'); download.href = file.url + '?download=true'; download.download = file.name; download.title = 'Download original'; download.setAttribute('aria-label', 'Download original'); download.append(icon('download'));
    const close = control('Close preview', 'close'); head.append(title, download, close);
    const body = make('div', 'mof-preview'), loading = make('div', 'mof-loading', 'Opening specification…'); loading.setAttribute('role', 'status'); body.append(loading); modal.append(head, body); document.body.append(modal);
    const controller = new AbortController(); 
    function finish() { controller.abort(); modal.remove(); if (trigger.isConnected) trigger.focus(); }
    close.addEventListener('click', () => modal.close()); modal.addEventListener('close', finish, {once:true}); modal.addEventListener('click', event => { if (event.target === modal && event.clientX < modal.getBoundingClientRect().left) modal.close(); }); modal.showModal(); close.focus();
    let selectedPage = 1, pageCount = 1;
    const pager = make('div', 'mof-pager'), previous = control('Previous page', 'chevron'), next = control('Next page', 'chevron'), pageLabel = make('span'); previous.classList.add('mof-previous'); const zoom = make('select', 'mof-zoom'); zoom.setAttribute('aria-label', 'Document zoom'); for (const [value, label] of [['fit', 'Fit width'], ['100', '100%'], ['150', '150%']]) { const option = make('option', '', label); option.value = value; zoom.append(option); } zoom.addEventListener('change', () => body.style.setProperty('--page-width', zoom.value === 'fit' ? '100%' : (Number(zoom.value) * 8) + 'px')); pager.append(previous, pageLabel, next, zoom); pager.hidden = true; modal.append(pager);
    previous.addEventListener('click', () => { if (selectedPage > 1) { selectedPage--; load(); } });
    next.addEventListener('click', () => { if (selectedPage < pageCount) { selectedPage++; load(); } });
    async function load() {
      previous.disabled = next.disabled = true;
      body.replaceChildren(loading);
      try {
        const pdf = file.content_type === 'application/pdf';
        const response = await fetch(file.url + (pdf ? '/page/' + selectedPage : ''), {signal:controller.signal, credentials:'same-origin'});
        if (!response.ok) throw new Error(response.status === 401 || response.status === 403 ? 'Sign in to your company workspace to open the document.' : 'The document preview is loading. Try again.');
        const mime = response.headers.get('content-type') || '';
        if (pdf && mime.startsWith('image/png')) {
          const blob = await response.blob(), image = make('img', 'mof-page');
          image.alt = `${file.name}, page ${selectedPage}`;
          image.src = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = reject; reader.readAsDataURL(blob); });
          await image.decode(); if (controller.signal.aborted) return;
          body.replaceChildren(image); body.scrollTop = 0;
          pageCount = Math.max(1, Number(response.headers.get('x-total-pages')) || 1);
          pageLabel.textContent = `${selectedPage} / ${pageCount}`; pager.hidden = false;
          previous.disabled = selectedPage === 1; next.disabled = selectedPage === pageCount;
        } else if (mime.startsWith('text/plain')) {
          body.replaceChildren(make('pre', 'mof-text', await response.text()));
        } else {
          const empty = make('div', 'mof-file-ready'); empty.append(icon('document'), make('strong', '', file.name), make('p', '', 'Download the original to open this format.')); body.replaceChildren(empty);
        }
      } catch (error) {
        if (error.name === 'AbortError') return;
        const errorBox = make('div', 'mof-file-ready'), retry = make('button', 'mf-button', 'Try again'); retry.type = 'button'; retry.addEventListener('click', load); errorBox.append(make('p', '', error.message), retry); body.replaceChildren(errorBox);
      }
    }
    load();
  }
  window.RocotoManufacturerOrderFiles = order => {
    const spec = order.request_context?.specification || order.customer?.capture?.specification;
    if (!spec?.file_id && !spec?.file && !order.customer?.specification_file) return null;
    const panel = make('section', 'mo-panel mof-files'); panel.append(make('h2', '', 'Specification'));
    const list = make('div', 'mof-list'), loading = make('div', 'mof-skeleton'); loading.setAttribute('aria-label', 'Loading specification'); list.append(loading); panel.append(list);
    async function load() {
      try {
        const response = await fetch('/api/manufacturer/orders/' + encodeURIComponent(order.id) + '/files', {credentials:'same-origin'});
        if (!response.ok) throw new Error(response.status === 401 || response.status === 403 ? 'Sign in to your company workspace to open the specification.' : 'The specification is loading. Try again.');
        const data = await response.json(); list.replaceChildren();
        for (const file of data.files || []) {
          const row = make('button', 'mof-file'); row.type = 'button'; row.setAttribute('aria-label', 'Preview ' + file.name);
          const copy = make('span', 'mof-file-copy'); copy.append(make('strong', '', file.name), make('small', '', `${file.content_type === 'application/pdf' ? 'PDF' : 'Original file'} · ${size(file.size)}`)); row.append(icon('document'), copy, icon('chevron')); row.addEventListener('click', () => preview(file, row)); list.append(row);
        }
        if (!list.childElementCount) list.append(make('p', 'mf-muted', 'Attach the customer’s specification.'));
      } catch (error) {
        const retry = make('button', 'mf-button', 'Try again'); retry.type = 'button'; retry.addEventListener('click', () => { list.replaceChildren(loading); load(); }); list.replaceChildren(make('p', 'mf-muted', error.message), retry);
      }
    }
    load(); return panel;
  };
})();
