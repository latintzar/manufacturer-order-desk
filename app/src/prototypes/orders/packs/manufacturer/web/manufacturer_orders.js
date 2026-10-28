(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const orders = $('orders'), message = $('message'), more = $('more');
  let cursor = null, loading = false;

  const text = (tag, className, value) => {
    const node = document.createElement(tag);
    node.className = className;
    node.textContent = value;
    return node;
  };
  const date = value => new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
  const money = pricing => new Intl.NumberFormat(undefined, {
    style: 'currency', currency: pricing.currency || 'EUR', maximumFractionDigits: 2
  }).format(pricing.gross);
  const labels = {
    requested: 'Requested', accepted: 'Accepted', in_progress: 'In progress', ready: 'Ready',
    completed: 'Completed', cancelled: 'Cancelled'
  };

  function priceBlock(pricing) {
    const root = text('div', 'price', '');
    if (pricing.confirmation) {
      if (Number.isFinite(pricing.gross) && pricing.gross > 0) {
        root.append(text('strong', '', money(pricing)), text('span', '', 'Priced items · balance on confirmation'));
      } else root.append(text('strong', '', 'Price on confirmation'));
    } else if (Number.isFinite(pricing.gross)) root.append(text('strong', '', money(pricing)));
    else root.append(text('strong', '', 'Price on confirmation'));
    return root;
  }

  function dateBlock(item) {
    const root = text('div', 'date', '');
    if (!item.date?.earliest) {
      root.append(text('strong', '', 'Ready date on confirmation'));
      return root;
    }
    const kind = item.date.kind === 'promise' ? 'Promised ready' : 'Estimated ready';
    root.append(text('strong', '', kind), text('span', '', date(item.date.earliest)));
    if (item.date.latest && item.date.latest !== item.date.earliest) root.append(text('span', '', `Latest ${date(item.date.latest)}`));
    return root;
  }

  function fulfilmentBlock(value) {
    const root = text('div', 'fulfilment', '');
    if (value.fulfilment === 'delivery') {
      const status = value.delivery === 'confirmed' ? 'Delivery confirmed' :
        value.delivery === 'estimated' ? 'Delivery estimate' : 'Delivery date on confirmation';
      root.append(text('strong', '', status));
    } else if (value.fulfilment === 'pickup') root.append(text('strong', '', 'Pickup'));
    else root.append(text('strong', '', 'Fulfilment on confirmation'));
    return root;
  }

  function row(item) {
    const root = document.createElement('article'); root.className = 'order';
    const identity = text('div', '', '');
    identity.append(text('h2', '', `Order ${item.id.slice(0, 10)}`), text('p', 'order-id', item.id));
    const state = text('div', '', '');
    state.append(text('span', 'state', labels[item.status] || item.status), text('p', 'meta', date(item.created_at)));
    const delivery = text('div', 'delivery', '');
    delivery.append(dateBlock(item), fulfilmentBlock(item.fulfilment || {}));
    root.append(identity, state, priceBlock(item.pricing || {}), delivery);
    if (item.files?.length) {
      const files = text('div', 'files', '');
      files.append(text('strong', '', item.files.length === 1 ? 'Design file' : 'Design files'));
      for (const file of item.files) {
        const link = text('a', '', `${file.name} · ${Math.max(1, Math.ceil(file.size / 1024))} KB`);
        link.href = file.download_url;
        files.append(link);
      }
      root.append(files);
    }
    return root;
  }

  async function load(reset = false) {
    if (loading) return;
    loading = true; more.disabled = true; $('refresh').disabled = true;
    if (reset) { cursor = null; orders.replaceChildren(); }
    message.hidden = false; message.textContent = reset ? 'Loading orders…' : 'Loading more orders…';
    try {
      const query = new URLSearchParams({ limit: '25' });
      if (cursor) query.set('before', cursor);
      const response = await fetch(`/api/manufacturer/orders?${query}`, { cache: 'no-store' });
      if (!response.ok) throw new Error(response.status === 403 ? 'Open this page with company order access.' : 'Orders are reconnecting. Try again.');
      const data = await response.json();
      for (const item of data.orders || []) orders.append(row(item));
      cursor = data.next_before;
      more.hidden = !cursor;
      message.hidden = orders.childElementCount > 0;
      if (!orders.childElementCount) message.textContent = 'Order requests appear here.';
    } catch (error) { message.hidden = false; message.textContent = error.message; }
    finally { loading = false; more.disabled = false; $('refresh').disabled = false; }
  }

  async function openOffice() {
    const button = $('office'); button.disabled = true;
    try {
      const shell = await fetch('/api/harness?collection=company', { cache: 'no-store' });
      if (!shell.ok) throw new Error();
      const harness = await shell.json();
      let office = (harness.fixed_chats || []).find(chat => chat.purpose === 'office');
      if (!office?.chat_id) {
        const response = await fetch('/api/organization/chats', {
          method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Video-Demo': '1' },
          body: JSON.stringify({ purpose: 'office', collection: 'company' })
        });
        if (!response.ok) throw new Error();
        office = await response.json();
      }
      const id = office.chat_id || office.id;
      if (!id) throw new Error();
      location.assign(`/?chat=${encodeURIComponent(id)}`);
    } catch { message.hidden = false; message.textContent = 'Office is reconnecting. Try again.'; button.disabled = false; }
  }

  $('refresh').addEventListener('click', () => load(true));
  more.addEventListener('click', () => load(false));
  $('office').addEventListener('click', openOffice);
  load(true);
})();
