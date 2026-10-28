/* A customer capability lives in this page's memory, separate from workspace sessions. */
(() => {
  'use strict';
  const root = document.getElementById('portal');
  let session = '', environment = '', current = null, generation = 0;
  const node = (tag, className, text) => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  };
  const button = (text, className, action) => {
    const element = node('button', `portal-button ${className || ''}`, text);
    element.type = 'button';
    element.addEventListener('click', action);
    return element;
  };
  const text = value => typeof value === 'string' || typeof value === 'number' ? String(value) : '';
  const money = (value, currency) => {
    if (typeof value !== 'number' || !Number.isFinite(value)) return 'Price to agree';
    try { return new Intl.NumberFormat('en-GB', {style: 'currency', currency: currency || 'EUR'}).format(value); }
    catch { return new Intl.NumberFormat('en-GB', {maximumFractionDigits: 2}).format(value); }
  };
  const date = value => {
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? '' : new Intl.DateTimeFormat('en-GB', {day: 'numeric', month: 'long', year: 'numeric'}).format(parsed);
  };
  function icon(name) {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 24 24'); svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor'); svg.setAttribute('stroke-width', '1.6');
    svg.setAttribute('stroke-linecap', 'round'); svg.setAttribute('stroke-linejoin', 'round');
    svg.setAttribute('aria-hidden', 'true');
    const path = document.createElementNS(svg.namespaceURI, 'path');
    path.setAttribute('d', ({check: 'm5 12 4 4L19 6', close: 'm6 6 12 12M6 18 18 6',
      phone: 'M6.5 3h3l1.5 5-2 2a16 16 0 0 0 5 5l2-2 5 1.5v3A3.5 3.5 0 0 1 17.5 21 17 17 0 0 1 3 6.5 3.5 3.5 0 0 1 6.5 3Z',
      box: 'm3 7 9-4 9 4v10l-9 4-9-4V7Zm0 0 9 4 9-4M12 11v10M7.5 5l9 4'})[name]);
    svg.append(path); return svg;
  }
  async function api(action, payload = {}) {
    const response = await fetch(`/api/manufacturer/customer-portal/${environment}/${action}`, {
      method: 'POST', credentials: 'omit', cache: 'no-store', referrerPolicy: 'no-referrer',
      headers: {'Content-Type': 'application/json', 'X-Rocoto-Page': '1', ...(session ? {Authorization: `Bearer ${session}`} : {})},
      body: JSON.stringify(payload),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(text(result.detail) || 'Try again shortly.');
    return result;
  }
  function status(message, target = root) {
    const existing = target.querySelector('.portal-feedback');
    if (existing) existing.remove();
    const note = node('p', 'portal-feedback', message);
    note.setAttribute('role', 'status'); target.append(note);
  }
  function heading(data, title) {
    const header = node('header', 'portal-header');
    header.append(node('div', 'portal-brand', text(data.display.company)), node('h1', '', title));
    const sub = node('div', 'portal-subtitle');
    sub.append(node('span', '', text(data.display.customer)));
    header.append(sub); return header;
  }
  function row(label, value) {
    const result = node('div', 'portal-detail'); result.append(node('dt', '', label), node('dd', '', value)); return result;
  }
  function renderPhone(data) {
    root.className = 'portal-phone';
    const title = text(data.display.contact_name) || text(data.display.customer);
    root.append(heading(data, 'Phone call'));
    const card = node('section', 'portal-card phone-card');
    const mark = node('div', 'phone-mark'); mark.append(icon('phone'));
    const link = node('a', 'portal-button primary', 'Call'); link.href = `tel:${data.phone}`;
    link.prepend(icon('phone'));
    const copy = button('Copy number', '', async () => {
      try { await navigator.clipboard.writeText(data.phone); status('Number copied.', card); }
      catch { status('Select the number to copy it.', card); }
    });
    card.append(mark, node('h2', '', title), node('p', 'phone-number', data.phone), link, copy);
    root.append(card, node('p', 'portal-footnote', 'Your private link expires in 10 minutes.'));
  }
  function product(line, currency) {
    const article = node('li', 'portal-product');
    const visual = node('div', 'portal-product-image');
    let image;
    try {
      const url = new URL(line.image_url, location.origin);
      if (line.image_url && (url.origin === location.origin || url.origin === 'https://orders.example.test')) {
        image = node('img'); image.src = url.href; image.alt = ''; image.loading = 'lazy'; image.referrerPolicy = 'no-referrer';
        image.addEventListener('error', () => { visual.replaceChildren(icon('box')); }, {once: true});
      }
    } catch { /* Missing photographs use a quiet product symbol. */ }
    visual.append(image || icon('box'));
    const description = node('div', 'portal-product-copy');
    description.append(node('strong', '', text(line.name) || 'Item'));
    if (line.code) description.append(node('span', 'portal-product-code', text(line.code)));
    const detail = [line.description, line.finish, line.size].map(text).filter(Boolean).join(' · ');
    if (detail) description.append(node('span', 'portal-product-description', detail));
    const amounts = node('div', 'portal-product-amounts');
    const unit = ({pc: 'pcs', pcs: 'pcs', kg: 'kg', m: 'm', set: 'set'})[line.unit] || text(line.unit) || 'pcs';
    amounts.append(node('span', 'portal-quantity', `${text(line.quantity)} ${unit}`));
    if (typeof line.unit_price === 'number') amounts.append(node('span', 'portal-unit-price', `${money(line.unit_price, currency)} / ${unit}`));
    amounts.append(node('strong', 'portal-line-total', money(line.line_total ?? line.total, currency)));
    article.append(visual, description, amounts); return article;
  }
  function renderReview(data) {
    const proposal = data.proposal, document = proposal.document;
    root.className = 'portal-review';
    const header = heading(data, `Order ${text(data.display.order_number || document.display_number || document.number)}`.trim());
    const meta = node('div', 'portal-meta');
    const label = data.confirmed ? 'Confirmed' : !data.is_current ? 'Reference version' : data.review_status === 'changes_requested' ? 'Change sent' : 'Awaiting confirmation';
    const badge = node('span', `portal-badge${data.confirmed ? ' confirmed' : ''}`, label);
    if (data.confirmed) badge.prepend(icon('check'));
    meta.append(badge, node('span', '', `Version ${proposal.version} · ${date(proposal.created_at)}`));
    header.append(meta); root.append(header);
    const card = node('section', 'portal-card');
    card.append(node('h2', '', 'Items'));
    const items = node('ul', 'portal-products');
    for (const line of document.lines || []) items.append(product(line, document.currency));
    card.append(items);
    const totals = node('dl', 'portal-totals');
    for (const [key, label] of [['subtotal', 'Subtotal'], ['shipping', 'Delivery'], ['tax', 'VAT'], ['total', 'Total']]) {
      if (typeof document[key] === 'number') totals.append(row(label, money(document[key], document.currency)));
    }
    if (totals.children.length) card.append(totals);
    root.append(card);
    const delivery = document.delivery || {};
    const details = node('section', 'portal-card portal-delivery');
    details.append(node('h2', '', 'Delivery and terms'));
    const values = node('dl');
    for (const [key, label] of [['method', 'Fulfilment'], ['address', 'Address'], ['date', 'Delivery date'], ['notes', 'Note']]) {
      if (text(delivery[key])) values.append(row(label, text(delivery[key])));
    }
    if (!delivery.method && document.fulfilment) values.prepend(row('Fulfilment', ({pickup: 'From warehouse', delivery: 'Deliver to address'})[document.fulfilment] || text(document.fulfilment)));
    if (text(document.notes)) values.append(row('Order note', text(document.notes)));
    if (text(document.terms)) values.append(row('Terms', text(document.terms)));
    if (values.children.length) { details.append(values); root.append(details); }
    const actions = node('section', 'portal-actions');
    if (data.can_confirm) {
      const confirm = button('Confirm this version', 'primary', async () => {
        confirm.disabled = true; confirm.textContent = 'Confirming…';
        try { await api('confirm', {version_id: proposal.id}); await refresh(); }
        catch (error) { status(error.message, actions); confirm.disabled = false; confirm.textContent = 'Confirm this version'; }
      });
      actions.append(confirm, button('Request a change', '', event => changeDialog(event.currentTarget, proposal.id)));
      actions.append(node('p', 'portal-footnote', 'Confirmation covers the items and terms in this version.'));
    } else if (!data.is_current) {
      actions.append(node('p', 'portal-footnote', 'Open the latest link from the team to confirm.'));
    } else if (data.confirmed) {
      actions.append(node('p', 'portal-confirmed-note', 'The team received your confirmation.'));
      actions.append(button('Request a change', '', event => changeDialog(event.currentTarget, proposal.id)));
    } else {
      actions.append(node('p', 'portal-confirmed-note', 'The team will prepare the next version.'));
    }
    root.append(actions);
  }
  function changeDialog(trigger, version) {
    const dialog = node('dialog', 'portal-sheet');
    dialog.setAttribute('aria-labelledby', 'change-title');
    const header = node('div', 'portal-sheet-heading');
    const title = node('h2', '', 'Order change'); title.id = 'change-title';
    const close = button('', 'icon-button', () => dialog.close()); close.setAttribute('aria-label', 'Close'); close.append(icon('close'));
    header.append(title, close);
    const form = node('form');
    const label = node('label', '', 'What would you like to change?'); label.htmlFor = 'change-text';
    const input = node('textarea'); input.id = 'change-text'; input.required = true; input.maxLength = 4000; input.rows = 5;
    input.placeholder = 'Quantity, finish, delivery date…';
    const send = node('button', 'portal-button primary', 'Send change'); send.type = 'submit';
    const key = crypto.randomUUID();
    form.append(label, input, send); dialog.append(header, form); document.body.append(dialog);
    dialog.addEventListener('close', () => { dialog.remove(); if (trigger.isConnected) trigger.focus(); }, {once: true});
    dialog.addEventListener('click', event => { if (event.target === dialog) { const box = dialog.getBoundingClientRect(); if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) dialog.close(); } });
    form.addEventListener('submit', async event => {
      event.preventDefault(); if (!input.value.trim()) { input.focus(); return; }
      send.disabled = true;
      try { await api('change', {version_id: version, text: input.value.trim(), idempotency_key: key}); dialog.close(); await refresh(); }
      catch (error) { status(error.message, form); send.disabled = false; }
    });
    dialog.showModal(); input.focus();
  }
  async function refresh() {
    const pending = generation, result = await api('read');
    if (pending !== generation) return;
    current = result; root.replaceChildren(); root.setAttribute('aria-busy', 'false');
    if (current.purpose === 'phone') renderPhone(current); else renderReview(current);
  }
  async function start(pending) {
    session = '';
    let fragment = location.hash.slice(1);
    history.replaceState(null, '', location.pathname);
    const match = /^([a-z0-9][a-z0-9-]{0,63})\.([A-Za-z0-9_-]{43})$/.exec(fragment);
    fragment = '';
    if (!match) throw new Error('Open the private link in the team’s message.');
    environment = match[1];
    const result = await api('redeem', {token: match[2]});
    match[2] = '';
    if (pending !== generation) return;
    session = result.session_token;
    await refresh();
  }
  function boot() {
    const pending = ++generation;
    root.setAttribute('aria-busy', 'true');
    const loading = node('div', 'portal-loading'); loading.setAttribute('aria-label', 'Loading');
    loading.append(node('div', 'skeleton short'), node('div', 'skeleton title'), node('div', 'skeleton block'));
    root.replaceChildren(loading);
    start(pending).catch(error => {
      if (pending !== generation) return;
      root.replaceChildren(node('h1', '', 'Your private link'), node('p', 'portal-error', error.message));
      root.setAttribute('aria-busy', 'false');
    });
  }
  window.addEventListener('hashchange', () => { if (location.hash) boot(); });
  boot();
})();
