/* Staff entry uses deterministic catalogue selection and an idempotent source command. */
(() => {
  'use strict';
  const node = (tag, cls = '', text) => { const el = document.createElement(tag); el.className = cls; if (text !== undefined) el.textContent = text; return el; };
  const text = value => typeof value === 'string' ? value : value?.en || value?.bg || '';
  const unit = value => ({pc:'pcs',pcs:'pcs',set:'set',pair:'pair',m:'m',kg:'kg'})[value] || value || 'pcs';
  const button = (label, fn, primary = false) => { const el = node('button', primary ? 'mf-button mf-primary' : 'mf-button', label); el.type = 'button'; el.addEventListener('click', fn); return el; };
  window.RocotoManufacturerNewOrder = ({context, onCreated}) => {
    const dialog = node('dialog', 'mn-dialog'); dialog.setAttribute('aria-labelledby', 'mn-title'); document.body.append(dialog);
    const header = node('header', 'mn-header'), title = node('h2', '', 'New order'); title.id = 'mn-title';
    const close = button('Close', () => dialog.close()); header.append(title, close);
    const form = node('form', 'mn-form'), content = node('div', 'mn-content'), footer = node('footer', 'mn-footer');
    const status = node('p', 'mn-status'); status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite'); status.hidden = true;
    const submit = button('Create order', () => form.requestSubmit(), true); footer.append(status, submit); form.append(content, footer); dialog.append(header, form);
    let company, data, catalogue = [], chosen = [], controls = {}, file = null, fileLabel, key = '', pending = null, busy = false, disposed = false, trigger;
    const alive = () => !disposed && context.isCurrent();
    const say = value => { status.textContent = value; status.hidden = !value; };
    function section(label) { const box = node('section', 'mn-section'); box.append(node('h3', '', label)); content.append(box); return box; }
    function field(box, name, label, options = {}) {
      const wrap = node('label', 'mf-field'), input = node(options.type === 'textarea' ? 'textarea' : 'input', 'mf-input');
      input.name = name; if (input.tagName === 'INPUT') input.type = options.type || 'text';
      input.required = Boolean(options.required); input.maxLength = ({company:200, poNumber:100, notes:2000, project:2000})[name] || 300;
      if (options.autocomplete) input.autocomplete = options.autocomplete;
      wrap.append(node('span', 'mf-label', label), input); box.append(wrap); controls[name] = input;
      return input;
    }
    function remember() {
      if (!key) return;
      const customer = Object.fromEntries(Object.entries(controls).map(([name, input]) => [name, input.value]));
      try { sessionStorage.setItem(key, JSON.stringify({customer, lines:chosen.map(row => ({article:row.item.c, quantity:row.quantity}))})); }
      catch { say('Keep this form open until the save is confirmed.'); }
    }
    function pendingStore(operation, value) {
      return new Promise((resolve, reject) => {
        const request = indexedDB.open('manufacturer-order-drafts', 1);
        request.onupgradeneeded = () => request.result.createObjectStore('commands');
        request.onerror = () => reject(Error('Enable browser storage to save the order.'));
        request.onsuccess = () => {
          const database = request.result, transaction = database.transaction('commands', operation === 'get' ? 'readonly' : 'readwrite');
          const store = transaction.objectStore('commands'), action = operation === 'get' ? store.get(key) : operation === 'put' ? store.put(value, key) : store.delete(key);
          transaction.oncomplete = () => { database.close(); resolve(action.result); };
          transaction.onerror = () => { database.close(); reject(Error('Free some browser storage and try again.')); };
          transaction.onabort = transaction.onerror;
        };
      });
    }
    function lock() {
      content.querySelectorAll('input,select,textarea,button').forEach(el => { el.disabled = busy || Boolean(pending) || el.dataset.selected === 'true'; });
      submit.disabled = busy || !chosen.length; submit.textContent = busy ? 'Saving…' : pending ? 'Try again' : 'Create order';
    }
    const currency = () => /^[A-Z]{3}$/.test(data?.document?.catalogue?.currency) ? data.document.catalogue.currency : 'EUR';
    function rate(row) {
      const override = data.document.catalogue.price_overrides?.find(item => item.item_id === row.item.c && item.basis === 'p');
      const value = override?.amount ?? row.item.p;
      return (override || !row.item.q) && typeof value === 'number' && Number.isFinite(value) && value >= 0 ? new Intl.NumberFormat('en-GB', {style:'currency', currency:currency()}).format(value) + ' / ' + unit(row.item.u) : 'Needs quote';
    }
    function photo(row) {
      const wrap = node('span', 'mn-photo'), raw = row.item.img || row.category.img;
      try {
        const origin = new URL(data.settings.embed_url).origin, slug = data.settings.company_slug;
        const path = typeof raw === 'string' && raw.startsWith('/') && !raw.startsWith('//') ? origin + (raw.startsWith('/' + slug + '/') ? '' : '/' + slug) + raw : raw;
        const url = new URL(path); if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) return wrap;
        const image = node('img'); image.src = url.href; image.alt = ''; image.loading = 'lazy'; image.referrerPolicy = 'no-referrer'; wrap.append(image);
      } catch {} return wrap;
    }
    function build(saved) {
      content.replaceChildren(); controls = {};
      const customer = section('Customer'), grid = node('div', 'mn-grid'); customer.append(grid);
      field(grid, 'company', 'Company *', {required:true, autocomplete:'organization'});
      field(grid, 'name', 'Contact name *', {required:true, autocomplete:'name'});
      const email = field(grid, 'email', 'Email', {type:'email', autocomplete:'email'}), phone = field(grid, 'phone', 'Phone', {type:'tel', autocomplete:'tel'});
      customer.append(node('p', 'mf-muted mn-hint', 'Add a contact email or phone number.'));
      const contactsValid = () => {
        email.setCustomValidity(email.value.trim() || phone.value.trim() ? '' : 'Add a contact email or phone number.');
        phone.setCustomValidity(!email.value.trim() && phone.value.trim() && !/^\+?[0-9][0-9 ()-]{5,30}$/.test(phone.value.trim()) ? 'Enter a valid contact phone number.' : '');
      };
      email.addEventListener('input', contactsValid); phone.addEventListener('input', contactsValid);
      const products = section('Products'), search = node('input', 'mf-input mn-search'); search.type = 'search'; search.placeholder = 'Search by item code or name'; search.setAttribute('aria-label', search.placeholder); search.maxLength = 150;
      const results = node('div', 'mn-results'), selected = node('div', 'mn-selected'); selected.setAttribute('aria-label', 'Selected items'); products.append(search, results, selected);
      function drawChosen() {
        selected.replaceChildren();
        for (const row of chosen) {
          const line = node('div', 'mn-line'), identity = node('div', 'mn-product-copy'); identity.append(node('strong', '', row.name), node('small', 'mf-muted', [row.item.c, row.description].filter(Boolean).join(' · ')), node('small', 'mn-rate', rate(row)));
          const quantity = node('input', 'mf-input mn-quantity'); quantity.type = 'number'; quantity.min = '1'; quantity.max = '9999'; quantity.step = '1'; quantity.required = true; quantity.value = row.quantity; quantity.setAttribute('aria-label', `Quantity for ${row.item.c}`); quantity.addEventListener('input', () => { row.quantity = Number(quantity.value); remember(); });
          const qty = node('label', 'mn-qty'); qty.append(node('span', 'mf-label', unit(row.item.u)), quantity);
          const remove = button('Remove', () => { chosen = chosen.filter(item => item !== row); drawChosen(); drawResults(); remember(); lock(); }); remove.classList.add('mn-remove'); remove.setAttribute('aria-label', `Remove ${row.item.c}`);
          line.append(photo(row), identity, qty, remove); selected.append(line);
        }
        if (!chosen.length) selected.append(node('p', 'mf-muted mn-empty', 'Choose catalogue items and enter quantities.'));
      }
      function drawResults() {
        const query = search.value.trim().toLocaleLowerCase(); results.replaceChildren(); results.hidden = !query;
        if (!query) return;
        const matches = catalogue.filter(row => [row.item.c, row.name, row.description, ...Object.values(row.item.a || {}).flat()].join(' ').toLocaleLowerCase().includes(query)).slice(0, 12);
        for (const row of matches) {
          const add = button('', () => { if (chosen.length >= 100) { say('Each order can include up to 100 items.'); return; } chosen.push({...row, quantity:1}); drawChosen(); drawResults(); remember(); lock(); }); add.className = 'mn-result';
          const label = node('span', 'mn-product-copy'); label.append(node('strong', '', row.name), node('small', 'mf-muted', [row.item.c, row.description].filter(Boolean).join(' · ')));
          const exists = chosen.some(item => item.item.c === row.item.c); add.disabled = exists; add.dataset.selected = String(exists); add.setAttribute('aria-label', `${exists ? 'Added' : 'Add'} ${row.item.c}`); add.append(photo(row), label, node('span', 'mn-result-action', exists ? 'Added' : 'Add')); results.append(add);
        }
        if (!matches.length) results.append(node('p', 'mf-muted mn-empty', 'Search by another item code or name.'));
      }
      search.addEventListener('input', drawResults); drawChosen(); drawResults();
      const delivery = section('Delivery'), deliveryGrid = node('div', 'mn-grid'); delivery.append(deliveryGrid);
      const select = (name, label, options) => { const wrap = node('label', 'mf-field'), input = node('select', 'mf-input'); input.name = name; for (const [value, title] of options) { const option = node('option', '', title); option.value = value; input.append(option); } wrap.append(node('span', 'mf-label', label), input); deliveryGrid.append(wrap); controls[name] = input; return input; };
      const fulfilment = select('fulfilment', 'Fulfilment', [['delivery', 'Deliver to address'], ['pickup', 'Collect from warehouse']]);
      const warehouses = company.warehouses || []; select('warehouseId', 'Dispatch warehouse', [['', 'Choose a warehouse'], ...warehouses.map(item => [item.id, item.name])]).required = warehouses.length > 0;
      const address = field(deliveryGrid, 'line1', 'Delivery address', {autocomplete:'shipping street-address'}), city = field(deliveryGrid, 'city', 'City', {autocomplete:'shipping address-level2'}), zip = field(deliveryGrid, 'zip', 'Postcode', {autocomplete:'shipping postal-code'});
      field(deliveryGrid, 'needBy', 'Requested date', {type:'date'});
      const deliveryValidity = () => { for (const el of [address, city, zip]) { el.required = fulfilment.value === 'delivery'; el.closest('label').hidden = fulfilment.value !== 'delivery'; } };
      fulfilment.addEventListener('change', deliveryValidity);
      const billing = section('Billing and reference'), billingGrid = node('div', 'mn-grid'); billing.append(billingGrid);
      field(billingGrid, 'poNumber', 'Customer purchase order number (PO)'); field(billingGrid, 'coName', 'Billing company'); field(billingGrid, 'eik', 'Company registration number'); field(billingGrid, 'vatNo', 'VAT number'); field(billingGrid, 'bline1', 'Billing address'); field(billingGrid, 'bcity', 'Billing city'); field(billingGrid, 'bzip', 'Billing postcode');
      const details = section('Original document and notes'); field(details, 'notes', 'Order notes', {type:'textarea'});
      const attachment = node('input', 'mf-input'); attachment.type = 'file'; attachment.accept = '.pdf,.csv,.xlsx,.docx,.txt'; attachment.setAttribute('aria-label', 'Original document');
      fileLabel = node('p', 'mf-muted mn-hint', pending?.original_file?.filename || file?.name || 'PDF, spreadsheet or text document up to 4 MB.');
      attachment.addEventListener('change', () => { const next = attachment.files[0]; if (next && (next.size > 4 * 1024 * 1024 || next.size === 0)) { attachment.value = ''; say('Choose an original document up to 4 MB.'); return; } file = next || null; fileLabel.textContent = file?.name || 'PDF, spreadsheet or text document up to 4 MB.'; }); details.append(attachment, fileLabel);
      for (const [name, value] of Object.entries(saved?.customer || {})) if (controls[name] && typeof value === 'string') controls[name].value = value;
      contactsValid(); deliveryValidity(); lock();
    }
    async function fetchJSON(path, payload) {
      const response = await fetch('/api/manufacturer' + path, {cache:'no-store', signal:context.signal, ...(payload ? {method:'POST', headers:{'Content-Type':'application/json', 'X-Rocoto-Page':'1'}, body:JSON.stringify(payload)} : {})});
      let value = {}; try { value = await response.json(); } catch {}
      if (!response.ok) { const error = new Error(typeof value.detail === 'string' && /[A-Za-z][^]*\s/.test(value.detail) ? value.detail : response.status === 401 || response.status === 403 ? 'Sign in to your current company workspace.' : response.status < 500 ? 'Check the fields and try again.' : 'Choose “Try again” to confirm the save. Your details are saved.'); error.status = response.status; throw error; } return value;
    }
    async function encodeFile() { if (!file) return undefined; return new Promise((resolve, reject) => { const reader = new FileReader(); reader.onerror = () => reject(Error('Attach the original document again.')); reader.onload = () => resolve({filename:file.name, content_type:file.type || 'application/octet-stream', content_base64:String(reader.result).split(',')[1]}); reader.readAsDataURL(file); }); }
    form.addEventListener('input', remember); form.addEventListener('change', remember);
    form.addEventListener('submit', async event => {
      event.preventDefault(); if (busy || !chosen.length || (!pending && !form.reportValidity())) return;
      busy = true; lock(); say('Saving order…');
      try {
        if (!pending) { const customer = Object.fromEntries(Object.entries(controls).filter(([name]) => name !== 'fulfilment').map(([name, input]) => [name, input.value.trim()])); pending = {idempotency_key:crypto.randomUUID(), customer, fulfilment:controls.fulfilment.value, lines:chosen.map(row => ({article:row.item.c, quantity:row.quantity})), original_file:await encodeFile()}; remember(); }
        await pendingStore('put', pending);
        const result = await fetchJSON('/orders', pending); if (!alive()) return;
        if (!result.order_id) throw Error('Choose “Try again” to confirm the save.');
        await pendingStore('delete');
        try { sessionStorage.removeItem(key); } catch {} pending = null; chosen = []; file = null; dialog.close(); onCreated(result.order_id);
      } catch (error) { if (!alive()) return; if (error.status && error.status >= 400 && error.status < 500 && ![401,403,408,409,429].includes(error.status)) { pending = null; await pendingStore('delete').catch(() => {}); remember(); } say(error.message); }
      finally { busy = false; if (alive()) lock(); }
    });
    dialog.addEventListener('close', () => trigger?.isConnected && trigger.focus({preventScroll:true}));
    return {
      async open(metadata, opener) {
        if (busy) { dialog.showModal(); return; }
        company = metadata.company; trigger = opener; key = `manufacturer-new-order:${company.id}:${metadata.actor.id}`; say('Loading catalogue…'); submit.disabled = true; content.replaceChildren(); dialog.showModal();
        try {
          data = await fetchJSON('/configurator'); if (!alive()) return;
          catalogue = (data.document?.catalogue?.cats || []).flatMap(category => (category.items || []).map(item => ({category, item, name:text(category.en || category.bg) || category.code, description:text(item.se || item.s)})));
          let saved; try { saved = JSON.parse(sessionStorage.getItem(key) || 'null'); } catch {}
          pending = await pendingStore('get'); if (!alive()) return;
          chosen = (pending?.lines || saved?.lines || []).map(line => { const row = catalogue.find(row => row.item.c === line.article); return row ? {...row, quantity:line.quantity} : null; }).filter(Boolean);
          build(pending ? {customer:{...pending.customer, fulfilment:pending.fulfilment}} : saved); say(pending ? 'Choose “Try again” to confirm the previous save.' : ''); controls.company.focus();
        } catch (error) { if (alive()) { say(error.message); content.append(button('Reload catalogue', () => { dialog.close(); this.open(metadata, opener); })); } }
      },
      hide() { if (dialog.open) dialog.close(); },
      destroy() { disposed = true; dialog.close(); dialog.remove(); },
    };
  };
})();
