/* Company pages use native tab admission, cancellation and visibility lifecycles. */
(() => {
  'use strict';
  const API = '/api/manufacturer';
  const labels = {requested:'New', quoted:'Quoted', accepted:'Accepted', in_progress:'In progress', ready:'Ready', completed:'Completed', cancelled:'Declined',preparing:'Preparing',dispatched:'Dispatched',review_pending:'Awaiting customer',customer_confirmed:'Customer confirmed',changes_requested:'Change requested'};
  const node = (tag, className = '', text) => { const el = document.createElement(tag); el.className = className; if (text !== undefined) el.textContent = text; return el; };
  const icon = name => { const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); svg.setAttribute('class', 'icon'); svg.setAttribute('aria-hidden', 'true'); const use = document.createElementNS('http://www.w3.org/2000/svg', 'use'); use.setAttribute('href', `#i-${name}`); svg.append(use); return svg; };
  const button = (label, action, symbol, primary = false) => { const el = node('button', primary ? 'mf-button mf-primary' : 'mf-button', label); el.type = 'button'; if (symbol) el.prepend(icon(symbol)); el.addEventListener('click', action); return el; };
  const iconButton = (label, action, symbol) => { const el = button(label, action, symbol); el.classList.add('mf-tool-button'); el.setAttribute('aria-label', label); el.title = label; el.replaceChildren(icon(symbol)); return el; };
  const safeUrl = value => { try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? url.href : null; } catch { return null; } };
  const date = (value, short = false) => { const time = new Date(typeof value === 'number' && value < 1e12 ? value * 1000 : value); return Number.isFinite(time.valueOf()) ? new Intl.DateTimeFormat('en-GB', short ? {day:'numeric', month:'short', timeZone:'Europe/Sofia'} : {dateStyle:'medium', timeStyle:'short', timeZone:'Europe/Sofia'}).format(time) : 'Date to confirm'; };
  const money = (value, currency = 'EUR') => Number.isFinite(Number(value)) && value !== null && value !== '' ? new Intl.NumberFormat('en-GB', {style:'currency', currency:/^[A-Z]{3}$/.test(currency) ? currency : 'EUR'}).format(Number(value)) : 'To confirm';
  const slug = value => String(value || '').replace(/[^a-zA-Z0-9_-]/g, '');
  function link(label, target, className = '') { const url = safeUrl(target); if (!url) return node('span', className, label); const el = node('a', className, label); el.href = url; el.target = '_blank'; el.rel = 'noopener noreferrer'; return el; }
  async function request(path, context, payload) {
    const response = await fetch(API + path, {signal:context.signal, cache:'no-store', ...(payload ? {method:'POST', headers:{'Content-Type':'application/json', 'X-Rocoto-Page':'1'}, body:JSON.stringify(payload)} : {})});
    let value; try { value = await response.json(); } catch { value = {}; }
    if (!response.ok) {
      const raw = typeof value.detail === 'string' ? value.detail : typeof value.message === 'string' ? value.message : '';
      const known = {'This configuration changed. Review the latest version and save again.':'A newer version is available. Review it and save your changes again.','Use a six-digit hexadecimal accent colour.':'Enter a colour in #123456 format.','Use plain text within the field length.':'Use plain text within the field limit.','Keep these labels on one line.':'Enter the text on one line.','Choose a saved version identifier.':'Choose a version from history.','Use the editable appearance fields.':'Edit a display setting.'};
      const message = known[raw] || (/[A-Za-z][^]*\s/.test(raw) ? raw : response.status === 409 ? 'A newer version is available. Reload the page.' : response.status === 401 || response.status === 403 ? 'Sign in to your company workspace.' : response.status === 400 || response.status === 422 ? 'Check your details and try again.' : 'Reconnecting. Try again.');
      const error = new Error(message); error.status = response.status; throw error;
    }
    return value;
  }
  function heading(title, description, actions) { const el = node('header', 'mf-heading'), text = node('div'); text.append(node('h1', '', title)); if (description) text.append(node('p', 'mf-muted', description)); el.append(text); if (actions) el.append(actions); return el; }
  function badge(value, className = '') { const el = node('span', `mf-badge ${className}`, value); return el; }
  function field(label, control, help) { const el = node('label', 'mf-field'); el.append(node('span', 'mf-label', label), control); if (help) el.append(node('small', 'mf-muted', help)); return el; }
  function input(name, value = '', type = 'text') { const el = node('input', 'mf-input'); el.name = name; el.type = type; el.value = value || ''; return el; }
  function facts(rows) { const el = node('dl', 'mf-facts'); for (const [label, value] of rows) if (value !== undefined && value !== null && value !== '') { const pair = node('div'); pair.append(node('dt', '', label), value instanceof Node ? value : node('dd', '', String(value))); if (value instanceof Node) { const dd = node('dd'); dd.append(value); pair.replaceChildren(node('dt', '', label), dd); } el.append(pair); } return el; }
  function empty(title, message, symbol = 'list') { const box = node('div', 'mf-empty'); box.append(icon(symbol), node('h2', '', title), node('p', 'mf-muted', message)); return box; }
  function notice() { const el = node('p', 'mf-notice'); el.setAttribute('role', 'status'); el.hidden = true; return el; }
  function showNotice(el, text) { if (el.textContent !== text) el.textContent = text; el.hidden = !text; }
  function layout(root) { const page = node('section', 'mf-page'); root.replaceChildren(page); window.RocotoManufacturerFooter?.(page); return page; }

  const orderNumber = order => order.display_number || (/^(?:#|[a-z]{1,8}-)?\d{1,10}$/i.test(order.number || '') ? order.number : 'Order');
  const companyName = order => order.customer?.display_company || order.customer?.company || order.customer?.company_name || '';
  const customerName = order => companyName(order) || order.customer?.name || 'Customer';
  const toQuote = value => ['to_quote', 'partially_priced'].includes(value?.pricing_state) || value?.total === null || (value?.pricing_state !== 'priced' && Number(value?.total) === 0);
  const orderAmount = order => toQuote(order) ? 'Needs quote' : money(order.total, order.currency);
  const timeOnly = value => { const time = new Date(typeof value === 'number' && value < 1e12 ? value * 1000 : value); return Number.isFinite(time.valueOf()) ? new Intl.DateTimeFormat('en-GB', {hour:'numeric', minute:'2-digit', timeZone:'Europe/Sofia'}).format(time) : ''; };
  const itemCount = order => `${order.items_count || order.lines?.length || 0} ${(order.items_count || order.lines?.length) === 1 ? 'item' : 'items'}`;
  const usefulResearch = value => Boolean(value && (value.summary?.trim() || value.email_snippet?.trim() || value.facts?.some(fact => fact.value || fact.text) || value.sources?.some(source => safeUrl(source.url))));
  const orderHref = id => { const url = new URL(location.href); url.searchParams.set('view', 'orders'); url.searchParams.set('order', id); return url.pathname + url.search; };
  function orderRow(order, open) {
    const row = node('a', 'mf-order-row'); row.href = orderHref(order.id); row.dataset.orderId = order.id;
    row.setAttribute('aria-label', `Order ${orderNumber(order)}, ${customerName(order)}`);
    const identity = node('span', 'mo-order-number', orderNumber(order));
    const customer = node('span', 'mf-order-customer'); customer.append(node('strong', '', customerName(order)));
    const secondary = order.brief?.title || order.brief?.summary || (companyName(order) ? order.customer?.name || order.customer?.email : order.customer?.email);
    if (secondary) { const summary = node('small', '', `${order.is_demo === true ? 'Demo · ' : ''}${secondary}`); summary.title = secondary; customer.append(summary); }
    const count = node('span', 'mo-order-count'); count.append(badge(({review_pending:'With customer',customer_confirmed:'Confirmed',changes_requested:'Change requested',preparing:'Preparation'})[order.status] || labels[order.status] || 'New','mo-status')); count.title=(labels[order.status]||'New')+' · '+itemCount(order);
    const amount = node('span', 'mo-order-total', orderAmount(order)); amount.classList.toggle('mo-quote', toQuote(order));
    const received = node('span', 'mo-order-date'); received.append(node('span', '', date(order.created_at, true)), node('small', '', timeOnly(order.created_at)));
    row.append(identity, customer, count, amount, received, icon('chevron'));
    row.addEventListener('click', event => { if (event.button || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return; event.preventDefault(); open(order.id); }); return row;
  }
  function enrichmentCard(enrichment = {}, company = '') {
    if (!usefulResearch(enrichment)) return null;
    const card = node('div', 'mf-research mo-profile-findings');
    if (enrichment.status === 'needs_review') { card.append(node('p', 'mo-company-pending', 'Add a company name and website to create a company profile.')); return card; }
    const sources = [...new Map((enrichment.sources || []).filter(source => safeUrl(source.url)).map(source => [source.url, source])).values()];
    const used = new Set();
    if (enrichment.summary?.trim()) {
      const summary = node('p', 'mf-research-summary', enrichment.summary), source = sources[0];
      if (source) { const citation = link(new URL(source.url).hostname.replace(/^www\./, ''), source.url, 'mf-source-inline'); citation.prepend(icon('link')); summary.append(' ', citation); used.add(source.url); }
      card.append(summary);
    }
    const findings = (enrichment.facts || []).filter(fact => (fact.value || fact.text) && !(['company name','business name','organization name','company name','company'].includes(String(fact.label || '').toLowerCase()) && String(fact.value || fact.text).toLowerCase() === company.toLowerCase()));
    if (findings.length) {
      const grid = node('dl', 'mf-research-facts');
      for (const fact of findings) {
        const pair = node('div'), value = node('dd'), raw = fact.value ?? fact.text;
        const text = typeof raw === 'object' ? Object.values(raw).join(' · ') : String(raw), source = fact.source_url || fact.source_urls?.find(safeUrl);
        const content = safeUrl(source) ? link(text, source, 'mo-sourced-value') : node('span', '', text);
        if (safeUrl(source)) { content.append(icon('link')); used.add(source); }
        value.append(content); pair.append(node('dt', '', fact.label || 'Details'), value); grid.append(pair);
      } card.append(grid);
    }
    const remaining = sources.filter(source => !used.has(source.url));
    if (remaining.length) { const links = node('div', 'mo-visible-sources'); for (const source of remaining) { const item = link(source.title || new URL(source.url).hostname, source.url, 'mf-source'); item.prepend(icon('link')); links.append(item); } card.append(links); }
    if (enrichment.basis === 'operator_demo_research') card.append(node('p', 'mo-research-provenance', `Public information${enrichment.as_of ? ` · ${date(enrichment.as_of, true)}` : ''}`));
    return card;
  }
  function addressText(value) {
    if (!value || typeof value === 'string') return value || '';
    return [value.line1 || value.street || value.address, value.line2, [value.postcode || value.zip, value.city].filter(Boolean).join(' '), value.country].filter(part => typeof part === 'string' && part.trim()).join(', ');
  }
  function contactLink(value, kind) {
    const text = String(value || '').trim(); if (!text) return null;
    const valid = kind === 'email' ? /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(text) && !/\.(?:example|invalid)$/i.test(text) : /^[+\d\s().-]{5,40}$/.test(text);
    const el = node(valid ? 'a' : 'span', 'mo-contact-link', text);
    if (valid) el.href = kind === 'email' ? `mailto:${text}` : `tel:${text.replace(/[^+\d]/g, '')}`;
    return el;
  }
  function discussOrder(order) {
    document.dispatchEvent(new CustomEvent('manufacturer:customer-chat', {detail:{customerId:order.customer_id, orderId:order.id}}));
  }
  function detailHeading(order, back) {
    const header = node('header', 'mo-detail-heading'), backButton = iconButton('Orders', () => back(), 'chevron'); backButton.classList.add('mo-back');
    const text = node('div', 'mo-heading-identity'); text.append(node('h1', '', orderNumber(order)));
    const currentStatus = order.status === 'cancelled' ? 'cancelled' : order._fulfillment?.status && order._fulfillment.status !== 'requested' ? order._fulfillment.status : order._review?.review_status || order.status;
    if (currentStatus) text.append(badge(labels[currentStatus] || currentStatus, 'mo-status'));
    if (order.is_demo === true) text.append(node('span', 'mo-demo-label', 'Demo'));
    if (order.created_at) text.append(node('p', 'mf-muted', date(order.created_at)));
    header.append(backButton, text); const actions = node('div', 'mo-order-actions');
    if (order.id && order._fulfillment?.allowed_actions?.length) { const next = order._fulfillment.allowed_actions[0], names = {accepted:'Accept order',preparing:'Start preparation',dispatched:'Dispatch order'}; actions.append(button(names[next],()=>window.RocotoManufacturerOrderReview?.advance(order,next),'check',true)); }
    if (order.id && order._can_edit !== false) { const edit=iconButton('Edit request',()=>window.RocotoManufacturerOrderReview?.open(order),'edit');edit.classList.add('mr-request-edit');actions.append(edit); }
    if (order.id) { const action = button('Contact customer', () => discussOrder(order), 'chat'); action.classList.add('mo-order-agent'); actions.append(action); }
    if (actions.childElementCount) header.append(actions); return header;
  }
  function briefData(order) {
    const brief = order.brief || {}, customer = order.customer || {};
    return {...brief, summary:brief.summary || customer.project || customer.specification || `${itemCount(order)} in the order.`, facts:Array.isArray(brief.facts) ? brief.facts : [], open_questions:Array.isArray(brief.open_questions) ? brief.open_questions : [], next_steps:Array.isArray(brief.next_steps) ? brief.next_steps : []};
  }
  function requestText(order) {
    const brief = briefData(order), lines = [`${orderNumber(order)} · ${customerName(order)}`, ...(order.is_demo === true ? ['Demo order'] : []), '', 'Project', brief.title, brief.summary];
    for (const fact of brief.facts) if (fact.value) lines.push(`${fact.label}: ${fact.value}`);
    if (brief.open_questions.length) lines.push('', 'To confirm', ...brief.open_questions.map(value => `• ${value}`));
    lines.push('', 'Items');
    for (const item of order.lines || []) lines.push(`${item.quantity != null || item.qty != null ? `${item.quantity ?? item.qty} ${unitLabel(item.unit)}` : 'Quantity to confirm'} · ${item.name || item.title || 'Item'}${item.code ? ` · ${item.code}` : ''}`);
    return lines.filter(value => value !== undefined && value !== null).join('\n');
  }
  const unitLabel = value => ({pc:'pcs',pcs:'pcs',piece:'pcs',kg:'kg',m:'m',set:'set'}[value] || value || 'pcs');
  function customerNeeds(order) {
    const brief = briefData(order), section = node('section', 'mo-panel mo-needs'), title = node('div', 'mo-panel-heading');
    title.append(icon('building'), node('h2', '', 'Project'));
    const provenance = {questionnaire:'From questionnaire', specification:'From specification', selection:'From customer'}[brief.source];
    if (provenance) title.append(node('span', 'mo-brief-provenance', provenance)); section.append(title);
    if (brief.project) section.append(node('p', 'mo-needs-summary', brief.project));
    else if (brief.source !== 'selection' && brief.summary) section.append(node('p', 'mo-needs-summary', brief.summary));
    const values = brief.facts.filter(fact => fact.value !== undefined && fact.value !== null && String(fact.value).trim() && String(fact.value).trim() !== brief.title && !['project','проект','type of work','business','дейност','required date','requested date','желана дата'].includes(String(fact.label).toLowerCase()));
    if (values.length) { const grid = node('dl', 'mo-needs-facts'); for (const fact of values) { const pair = node('div'); pair.append(node('dt', '', fact.label), node('dd', '', String(fact.value))); grid.append(pair); } section.append(grid); }
    const questions = brief.open_questions.filter(value => !/(delivery date|дата на доставка|дата за доставка)/i.test(value));
    if (questions.length) { const block = node('div', 'mo-order-clarifications'); block.append(node('h3', '', 'To confirm')); const list = node('div'); for (const item of questions) list.append(node('span', 'mo-open-question', String(item).replace(/^(?:Confirm:|Уточнете:|To confirm:)\s*/i, ''))); block.append(list); section.append(block); }
    return section.childElementCount > 1 ? section : null;
  }
  function lineTable(order, items, priced, partial = false) {
    const panel = node('section', 'mo-panel mo-items'), title = node('div', 'mo-panel-heading');
    panel.classList.toggle('mo-products-unpriced', !priced); panel.dataset.pricing = priced ? 'priced' : 'to_quote';
    title.append(node('h2', '', priced ? (partial ? 'Priced' : 'Products') : 'Needs quote'), node('span', 'mo-section-count', String(items.length))); panel.append(title);
    const table = node('table', 'mo-products mo-checkout-products'), caption = node('caption', 'mo-sr-only', `Items in order ${orderNumber(order)}`), head = node('thead', 'mo-sr-only'), headings = node('tr');
    for (const label of ['Product', priced ? 'Amount' : 'Quantity']) { const cell = node('th', '', label); cell.scope = 'col'; headings.append(cell); } head.append(headings);
    const body = node('tbody');
    for (const line of items) {
      const row = node('tr'), product = node('td', 'mo-product'), content = node('div', 'mo-product-copy');
      const name = line.name || line.title || line.product_name || line.data?.name || 'Item from specification';
      const imageURL = safeUrl(line.image_url);
      if (imageURL) {
        const picture = node('div', 'mo-product-image'), image = node('img'); image.src = imageURL; image.alt = ''; image.loading = 'lazy'; image.decoding = 'async';
        image.addEventListener('load', () => picture.classList.add('mo-image-ready'));
        image.addEventListener('error', () => picture.remove(), {once:true}); picture.append(image); product.append(picture);
      }
      content.append(node('strong', '', name));
      const code = line.code || line.article || line.sku || line.c;
      if (code) { const article = node('a', 'mo-product-code', `Item ${code}`); article.href = `?view=products&product=${encodeURIComponent(code)}`; article.dataset.manufacturerRoute = 'products'; content.append(article); }
      const description = line.description || line.specification || line.why || line.data?.description;
      if (description && description !== name && String(description).replace(/^[№#\s]+/, '') !== String(code)) content.append(node('p', 'mf-muted', typeof description === 'string' ? description : Object.values(description).join(' · ')));
      const unit = unitLabel(line.unit), quantity = line.quantity ?? line.qty, currency = order.currency || order.quote?.currency;
      const quantityText = quantity == null ? 'Quantity to confirm' : `${quantity} ${unit}`;
      if (priced) {
        const calculation = node('div', 'mo-product-calculation'); calculation.append(node('span', '', quantityText));
        if (line.unit_price != null) calculation.append(node('span', 'mo-unit-price', `${money(line.unit_price, currency)} / ${unit}`));
        content.append(calculation);
      }
      product.append(content); row.append(product);
      const amount = node('td', 'mo-product-value mo-checkout-amount', priced ? money(line.total ?? line.line_total ?? line.gross ?? line.data?.total, currency) : quantityText);
      amount.dataset.label = priced ? 'Amount' : 'Quantity'; row.append(amount); body.append(row);
    }
    table.append(caption, head, body); panel.append(table);
    if (!items.length) panel.append(node('p', 'mo-specification-note', 'Choose items to continue.'));
    if (priced) { const totals = node('dl', 'mo-totals'), total = node('div'); total.append(node('dt', '', partial ? 'Priced item subtotal' : order._proposal ? 'Item subtotal' : 'Total'), node('dd', '', money(partial ? order.priced_total : order.total, order.currency))); totals.append(total); panel.append(totals); }
    else panel.append(node('p', 'mo-price-help', 'Unit prices are set in the quote.'));
    return panel;
  }
  function reviewedOrder(result, workflow) {
    const order = {...result.order, _review:result.review, _fulfillment:workflow, _can_edit:result.actor?.role !== 'browse'};
    const proposal = result.proposal?.document;
    if (proposal) {
      const lines = proposal.lines.map(line => ({...line, total:line.line_total ?? line.total ?? null, pricing_state:line.unit_price == null ? 'to_quote' : 'priced'}));
      const priced = lines.filter(line => line.unit_price != null), subtotal = priced.reduce((sum,line)=>sum+Number(line.total||0),0);
      Object.assign(order, {_proposal:true, lines, delivery:proposal.delivery, notes:proposal.notes, currency:proposal.currency,
        total:priced.length===lines.length?subtotal:null, priced_total:subtotal,
        pricing_state:priced.length===lines.length?'priced':priced.length?'partially_priced':'to_quote'});
    }
    return order;
  }
  function allocationTable(order) {
    const review = order.customer?.capture?.specification?.allocation_review;
    if (review?.schema !== 'rocoto.orders.allocations.v1' || !Array.isArray(review.allocations) || !review.allocations.length) return null;
    const destinations = new Map((review.destinations || []).map(item => [item.id, item.label]));
    const section = node('section', 'mo-panel mo-allocations'), heading = node('div', 'mo-panel-heading');
    heading.append(node('h2', '', 'Allocation by location')); section.append(heading, node('p', 'mf-muted mo-allocation-source', 'From original request'));
    const table = node('table', 'mo-allocation-table'), head = node('thead'), headings = node('tr');
    for (const label of ['Item', 'Collection location', 'Quantity']) { const cell = node('th', '', label); cell.scope = 'col'; headings.append(cell); } head.append(headings);
    const body = node('tbody');
    for (const item of review.allocations) {
      const row = node('tr'), article = node('td', '', item.selected_code || item.sku || 'To confirm'), destination = node('td', '', destinations.get(item.destination_id) || item.destination_id || 'To confirm');
      if (item.source_cell) row.title = `Cell: ${item.source_cell}`;
      row.append(article, destination, node('td', '', typeof item.quantity === 'number' ? new Intl.NumberFormat('en-GB').format(item.quantity) : 'To confirm')); body.append(row);
    }
    table.append(head, body); section.append(table); return section;
  }
  function orderDetail(order, back) {
    const detail = node('div', 'mf-order-detail'); detail.append(detailHeading(order, back));
    const columns = node('div', 'mo-detail-layout'), main = node('div', 'mo-detail-main'), side = node('aside', 'mo-detail-side'); side.setAttribute('aria-label', 'Customer');
    const items = order.lines || [], priced = items.filter(item => !toQuote(item)), unpriced = items.filter(toQuote);
    if (priced.length) main.append(lineTable(order, priced, true, unpriced.length > 0 || toQuote(order)));
    if (unpriced.length || !items.length) main.append(lineTable(order, unpriced, false));
    const allocations = allocationTable(order); if (allocations) main.append(allocations);
    const customer = order.customer || {}, quote = order.quote || {}, delivery = order.delivery || quote.delivery || {}, method = delivery.method || order.fulfilment || quote.fulfilment, address = addressText(delivery.address || customer.address || order.address || [customer.line1,customer.zip,customer.city].filter(Boolean).join(', ')), requested = delivery.date || customer.date || customer.requested_date || customer.needBy;
    const deliverySection = node('section', 'mo-panel mo-delivery'), deliveryTitle = node('div', 'mo-panel-heading'); deliveryTitle.append(icon('pin'), node('h2', '', 'Delivery')); deliverySection.append(deliveryTitle);
    const deliverySummary = node('div', 'mo-delivery-summary'), destination = node('div', 'mo-delivery-destination'), schedule = node('div', 'mo-delivery-schedule');
    destination.append(node('strong', '', method === 'delivery' ? 'Deliver to address' : method === 'pickup' ? 'Collect in person' : method || 'Fulfilment to confirm'));
    if (address) destination.append(node('p', '', address));
    schedule.append(node('span', 'mf-muted', 'Date'), node('strong', '', requested || 'To confirm'));
    deliverySummary.append(destination, schedule); deliverySection.append(deliverySummary); main.append(deliverySection);
    if (customer.warehouseName) { const warehouse = node('div', 'mo-delivery-warehouse'); warehouse.append(icon('building'), node('div')); const text = warehouse.lastElementChild; text.append(node('span', 'mf-muted', 'Fulfilment warehouse'), node('strong', '', customer.warehouseName)); if (customer.warehouseErpCode) text.append(node('small', 'mf-muted', `ERP: ${customer.warehouseErpCode}`)); deliverySection.append(warehouse); }
    if (customer.poNumber || customer.coName || customer.eik) { const billing=node('section','mo-panel mo-billing'), title=node('div','mo-panel-heading'); title.append(icon('list'),node('h2','','Billing')); billing.append(title,facts([['Purchase order number (PO)',customer.poNumber],['Company',customer.coName||customer.company],['Company registration number',customer.eik],['VAT number',customer.vatNo],['Address',addressText([customer.bline1,customer.bzip,customer.bcity].filter(Boolean).join(', '))]])); if(customer.is_demo===true||order.is_demo===true)billing.append(node('small','mf-muted','Sample details for this demo.')); main.append(billing); }
    const project = customerNeeds(order); if (project) main.append(project);
    const specificationFiles = window.RocotoManufacturerOrderFiles?.(order); if (specificationFiles) main.append(specificationFiles);
    const notes = order._proposal ? order.notes : customer.notes || order.notes; if (notes) { const section = node('section', 'mo-panel mo-order-notes'); section.append(node('h2', '', order._proposal ? 'Note to customer' : 'Customer note'), node('p', '', notes)); main.append(section); }
    if (customer.specification && customer.specification !== order.brief?.summary) { const section = node('section', 'mo-panel mo-specification'); section.append(node('h2', '', 'Specification'), node('p', '', customer.specification)); main.append(section); }
    const company = companyName(order), researchCard = order.capabilities?.customer_research === false ? null : enrichmentCard(order.enrichment, company), contact = node('section', 'mo-panel mo-customer'), title = node('div', 'mo-panel-heading'); title.append(icon('building'), node('h2', '', 'Customer')); contact.append(title);
    const name = node(order.customer_id ? 'a' : 'strong', 'mo-company-name', customerName(order)); if (order.customer_id) { name.href = `?view=customers&customer=${encodeURIComponent(order.customer_id)}`; name.dataset.manufacturerRoute = 'customers'; } contact.append(name);
    if (safeUrl(customer.website)) { const url = new URL(customer.website); contact.append(link(url.hostname.replace(/^www\./, ''), url.href, 'mo-company-website')); }
    if (researchCard) contact.append(researchCard);
    const links = node('div', 'mo-contact-links'); if (company && customer.name) links.append(node('span', 'mo-contact-name', customer.name));
    for (const [kind, value] of [['email', customer.email], ['phone', customer.phone]]) { const item = contactLink(value, kind); if (item) {if(kind==='phone'&&order.customer_id)item.addEventListener('click',event=>{if(innerWidth>=700){event.preventDefault();window.RocotoManufacturerOrderReview?.phone(order.customer_id, customer.phone);}});links.append(item);} } if (links.childElementCount) contact.append(links);
    if (!company && order.enrichment?.status !== 'needs_review') contact.append(node('p', 'mo-contact-pending', 'Company to confirm.'));
    side.append(contact); columns.append(main, side); detail.append(columns); return detail;
  }
  function skeleton(width = 'full', shape = '') { const el = node('span', `mo-skeleton mo-skeleton-${width} ${shape}`); el.setAttribute('aria-hidden', 'true'); return el; }
  function listSkeleton() {
    const fragment = document.createDocumentFragment();
    for (let index = 0; index < 4; index++) { const row = node('div', 'mf-order-row mo-skeleton-row'); row.setAttribute('aria-hidden', 'true'); const company = node('span', 'mf-order-customer'); company.append(skeleton('long'), skeleton('medium')); row.append(skeleton('short'), company, skeleton('short'), skeleton('medium'), skeleton('medium'), skeleton('dot')); fragment.append(row); } return fragment;
  }
  function detailSkeleton(order, back) {
    const detail = node('div', 'mf-order-detail'), header = detailHeading(order || {}, back); if (!order) { const text = header.querySelector('div'); text.replaceChildren(skeleton('short', 'mo-skeleton-title'), skeleton('long')); } detail.append(header); const columns = node('div', 'mo-detail-layout'), main = node('div', 'mo-detail-main'), side = node('aside', 'mo-detail-side');
    const needs = node('section', 'mo-panel mo-needs mo-needs-skeleton'); needs.append(node('h2', '', 'Project'), skeleton('full', 'mo-skeleton-title'), skeleton('full'), skeleton('long')); const needsFacts = node('div', 'mo-needs-facts'); for (let index = 0; index < 3; index++) { const pair = node('div'); pair.append(skeleton('short'), skeleton('medium')); needsFacts.append(pair); } needs.append(needsFacts); const needsActions = node('div', 'mo-brief-actions'); needsActions.append(skeleton('long', 'mo-skeleton-button'), skeleton('long', 'mo-skeleton-button')); needs.append(needsActions); if (order?.brief) { const known = customerNeeds(order) || needs; known.classList.add('mo-needs-known-loading'); known.setAttribute('aria-hidden', 'true'); known.querySelectorAll('button').forEach(control => { control.disabled = true; }); main.append(known); } else main.append(needs);
    const items = node('section', 'mo-panel mo-items mo-skeleton-items'); items.append(node('h2', '', 'Products'));
    for (let index = 0; index < Math.min(4, Math.max(2, order?.items_count || 2)); index++) { const row = node('div', 'mo-skeleton-product'), content = node('div'); content.append(skeleton('long'), skeleton('medium')); row.append(skeleton('image'), content, skeleton('short'), skeleton('short')); items.append(row); }
    const total = node('div', 'mo-skeleton-total'); total.append(skeleton('short'), skeleton('medium')); items.append(total); main.prepend(items);
    const contact = node('section', 'mo-panel mo-customer'); contact.append(node('h2', '', 'Customer'), skeleton('long'), skeleton('medium'), skeleton('long')); const delivery = node('section', 'mo-panel'); delivery.append(node('h2', '', 'Delivery'), skeleton('medium'), skeleton('long')); side.append(contact); main.append(delivery); columns.append(main, side); detail.append(columns); return detail;
  }
  function ordersTab(root, context) {
    const page = layout(root); page.classList.add('mf-orders-page'); const pageHeading = heading('Orders'); page.append(pageHeading);
    const listView = node('div'), detailView = node('div', 'mf-order-detail-view'); detailView.hidden = true;
    const toolbar = node('div', 'mf-toolbar'), search = input('search', '', 'search'), searchBox = node('label', 'mf-search');
    search.placeholder = 'Search by order or company'; search.setAttribute('aria-label', 'Search by order or company'); searchBox.append(icon('search'), search);
    const filter = node('select', 'mf-input mf-filter'); filter.setAttribute('aria-label', 'Order status'); filter.hidden = true; toolbar.append(searchBox, filter); listView.append(toolbar);
    const columns = node('div', 'mf-order-columns'); columns.setAttribute('aria-hidden', 'true'); for (const title of ['Order', 'Customer', 'Status', 'Value', 'Received', '']) columns.append(node('span', '', title)); listView.append(columns);
    const rows = node('div', 'mf-order-list'), message = notice(), loadingLabel = node('span', 'mo-sr-only'); loadingLabel.setAttribute('role', 'status'); rows.setAttribute('aria-label', 'Orders'); rows.setAttribute('aria-busy', 'true'); loadingLabel.textContent = 'Loading orders'; rows.append(listSkeleton()); listView.append(rows);
    const more = button('More orders', () => { wanted += 100; load(); }, 'plus'); more.hidden = true; more.classList.add('mf-load-more'); listView.append(more); page.append(message, loadingLabel, listView, detailView);
    let wanted = 100, data = null, selected = new URL(location.href).searchParams.get('order'), timer = null, visible = false, loading = false, detailEpoch = 0, detailLoadingId = null, detailController = null, disposed = false, detailSignature = '', listSignature = '';
    const detailCache = new Map(), current = () => !disposed && context.isCurrent();
    const newOrder = window.RocotoManufacturerNewOrder?.({context, onCreated(id) { open(id); load(); }});
    const createButton = button('New order', () => newOrder?.open(data, createButton), 'plus', true); createButton.classList.add('mn-new-order'); createButton.hidden = true; pageHeading.append(createButton);
    function focusSearch() { if (!selected && matchMedia('(min-width: 761px) and (pointer: fine)').matches) requestAnimationFrame(() => { if (current() && !selected) search.focus({preventScroll:true}); }); }
    function drawFilters() {
      const available = [...new Set((data.orders || []).map(order => order.status).filter(value => labels[value]))];
      const signature = JSON.stringify(available); if (filter.dataset.options === signature) return; filter.dataset.options = signature;
      const selectedStatus = filter.value; filter.replaceChildren(); for (const value of ['', ...available]) { const option = node('option', '', value ? labels[value] : 'All orders'); option.value = value; filter.append(option); } filter.value = available.includes(selectedStatus) ? selectedStatus : ''; filter.hidden = available.length < 2;
    }
    function drawList() {
      if (!data) return; const query = search.value.trim().toLocaleLowerCase();
      const found = data.orders.filter(order => (!filter.value || order.status === filter.value) && (!query || [orderNumber(order), order.customer?.name, companyName(order), order.customer?.email, order.brief?.title, order.brief?.summary].filter(Boolean).join(' ').toLocaleLowerCase().includes(query)));
      const demoSlots=found.map((order,index)=>order.is_demo===true?index:-1).filter(index=>index>=0), demos=demoSlots.map(index=>found[index]).sort((a,b)=>Number(b.customer?.demo_scenario==='praktiker')-Number(a.customer?.demo_scenario==='praktiker'));demoSlots.forEach((slot,index)=>{found[slot]=demos[index]});
      const signature = JSON.stringify([found, query, filter.value]); if (signature === listSignature) return; listSignature = signature;
      const focus = document.activeElement?.dataset?.orderId; rows.replaceChildren(...found.map(order => orderRow(order, open)));
      if (!found.length) rows.append(empty(query || filter.value ? 'Results' : 'Orders', query || filter.value ? 'Search by company name or order number.' : 'Customer products, contacts and requirements appear here.'));
      if (focus) [...rows.querySelectorAll('[data-order-id]')].find(row => row.dataset.orderId === focus)?.focus({preventScroll:true});
    }
    function route(id, mode = 'replace') { if (mode === 'none') return; const url = new URL(location.href); url.searchParams.set('view', 'orders'); if (id) url.searchParams.set('order', id); else url.searchParams.delete('order'); if (mode === 'push' && url.href === location.href) return; history[mode === 'push' ? 'pushState' : 'replaceState']({...history.state, manufacturerOrderParent:mode === 'push' && Boolean(id)}, '', url); }
    function back(mode = 'auto') { if (mode === 'auto' && history.state?.manufacturerOrderParent) { history.back(); return; } const previous = selected; selected = null; detailEpoch++; detailController?.abort(); detailLoadingId = null; detailSignature = ''; detailView.replaceChildren(); detailView.hidden = true; listView.hidden = false; pageHeading.hidden = false; route(null, mode === 'none' ? 'none' : 'replace'); if (matchMedia('(min-width: 761px) and (pointer: fine)').matches) focusSearch(); else rows.querySelector(`[data-order-id="${CSS.escape(previous || '')}"]`)?.focus({preventScroll:true}); }
    async function loadDetail() {
      if (!selected || detailLoadingId === selected || !current()) return;
      const id = selected, epoch = ++detailEpoch; detailController?.abort(); detailController = new AbortController(); detailLoadingId = id;
      try { const detailContext = {...context, signal:detailController.signal}; let result, workflow; try { [result, workflow] = await Promise.all([request(`/orders/${encodeURIComponent(id)}/review`, detailContext), request(`/orders/${encodeURIComponent(id)}/fulfillment`, detailContext)]); } catch(error) { if(error.status!==403)throw error; result=await request(`/orders/${encodeURIComponent(id)}`,detailContext); } result.order=reviewedOrder(result,workflow); if (!current() || selected !== id || epoch !== detailEpoch) return; detailCache.set(id, result.order); const signature = JSON.stringify(result.order); if (signature !== detailSignature) { detailSignature = signature; const focused = detailView.contains(document.activeElement) ? document.activeElement : null, href = focused?.getAttribute('href'), label = focused?.textContent; detailView.replaceChildren(orderDetail(result.order, back)); if (focused && focused !== detailView) { const replacement = [...detailView.querySelectorAll('a,button')].find(el => href ? el.getAttribute('href') === href : el.tagName === focused.tagName && el.textContent === label); (replacement || detailView).focus({preventScroll:true}); } } detailView.setAttribute('aria-busy', 'false'); loadingLabel.textContent = ''; showNotice(message, ''); }
      catch (error) { if (current() && selected === id && error.name !== 'AbortError') {
        loadingLabel.textContent = ''; detailView.setAttribute('aria-busy', 'false');
        if (error.status === 404) { back('replace'); showNotice(message, 'Showing current orders.'); }
        else if (detailCache.has(id)) showNotice(message, error.message);
        else { const fallback = node('div', 'mf-order-detail'), panel = node('section', 'mo-panel mo-order-retry'); fallback.append(detailHeading(data?.orders.find(order => order.id === id) || {}, back)); panel.append(node('h2', '', 'Order'), node('p', 'mf-muted', error.message), button('Try again', () => open(id, 'none'), 'refresh')); fallback.append(panel); detailView.replaceChildren(fallback); }
      } }
      finally { if (epoch === detailEpoch) detailLoadingId = null; }
    }
    function open(id, mode = 'push') { detailController?.abort(); detailLoadingId = null; selected = id; detailEpoch++; detailSignature = ''; listView.hidden = true; detailView.hidden = false; pageHeading.hidden = true; const cached = detailCache.get(id); detailView.replaceChildren(cached ? orderDetail(cached, back) : detailSkeleton(data?.orders.find(order => order.id === id), back)); detailView.setAttribute('aria-busy', String(!cached)); loadingLabel.textContent = cached ? '' : 'Loading order'; detailView.tabIndex = -1; detailView.setAttribute('aria-label', 'Order'); detailView.focus({preventScroll:true}); route(id, mode); loadDetail(); root.scrollTop = 0; }
    const requestChanged = () => { if(current() && selected) {detailSignature='';loadDetail();} }; document.addEventListener('manufacturer:order-changed', requestChanged);
    function schedule() { clearTimeout(timer); if (visible && document.visibilityState !== 'hidden' && current()) timer = setTimeout(load, 5000); }
    async function load() {
      if (loading || !current() || document.visibilityState === 'hidden') return; loading = true; more.disabled = true;
      try { const result = await request('/overview', context); if (!current()) return;
        let combined = result.orders || [], lastCount = combined.length;
        for (let offset = 100; offset < wanted && lastCount === 100; offset += 100) { const next = await request(`/overview?limit=100&offset=${offset}`, context); if (!current()) return; lastCount = (next.orders || []).length; combined.push(...(next.orders || [])); }
        createButton.hidden = !newOrder || result.actor?.can_create_orders !== true;
        data = {...result, orders:[...new Map(combined.map(order => [order.id, order])).values()]}; more.hidden = lastCount < 100; drawFilters(); drawList(); rows.setAttribute('aria-busy', 'false'); if (!selected) loadingLabel.textContent = ''; showNotice(message, ''); if (selected) await loadDetail(); }
      catch (error) { if (current() && error.name !== 'AbortError') { showNotice(message, error.message); if (!data) { rows.replaceChildren(button('Try again', load, 'refresh')); rows.setAttribute('aria-busy', 'false'); loadingLabel.textContent = ''; } } }
      finally { loading = false; more.disabled = false; schedule(); }
    }
    search.addEventListener('input', drawList); filter.addEventListener('change', drawList);
    const visibility = () => { clearTimeout(timer); if (visible && document.visibilityState !== 'hidden') load(); }; document.addEventListener('visibilitychange', visibility);
    const popstate = () => { if (!current()) return; const url = new URL(location.href); if (url.searchParams.get('view') !== 'orders') return; const id = url.searchParams.get('order'); if (id === selected) return; if (id) open(id, 'none'); else back('none'); }; window.addEventListener('popstate', popstate);
    if (selected) open(selected, 'replace'); else route(null); load();
    return {show() { visible = true; popstate(); focusSearch(); schedule(); }, hide() { visible = false; clearTimeout(timer); newOrder?.hide(); }, unmount() { disposed = true; newOrder?.destroy(); document.removeEventListener('manufacturer:order-changed', requestChanged); clearTimeout(timer); detailController?.abort(); document.removeEventListener('visibilitychange', visibility); window.removeEventListener('popstate', popstate); root.replaceChildren(); }};
  }

  async function configuratorTab(root, context) {
    const page = layout(root); page.classList.add('mf-configurator-page');
    const editStatus = node('span', 'mf-save-state'); editStatus.setAttribute('role', 'status');
    const historyButton = iconButton('Version history', () => openHistory(), 'clock');
    const actions = node('div', 'mf-actions mf-configurator-actions'); actions.append(editStatus, historyButton);
    const title = heading('Configurator', '', actions);
    const message = notice(), editor = node('div', 'mf-configurator-editor'), historyView = node('section', 'mf-version-history'); historyView.hidden = true;
    page.append(title, message, editor, historyView);
    let data; try { data = await request('/configurator', context); } catch (error) { if (context.isCurrent()) showNotice(message, error.message); return; }
    if (!context.isCurrent()) return;
    const clone = value => JSON.parse(JSON.stringify(value || {}));
    let revision = data.revision, versionId = data.version_id, draftDocument = clone(data.document), changed = 0, dirty = false, saving = null, timer = null, disposed = false, historyOpen = false, previewReady = false, selectionEpoch = 0, selectedVersion = null;
    let form, controls, frame, draftLabel, retry, versionList, versionPicker, versions = [], historyFrame, restoreButton, inspectorResize;
    const canEdit = data.actor?.can_edit_settings === true && new URL(location.href).searchParams.get('operator') === '1';
    const current = () => !disposed && context.isCurrent();
    const draftKey = `manufacturer-configurator-draft:${data.company_id || ''}:${data.actor?.id || ''}`;
    let recovered = false, recoveredConflict = false;
    try {
      const kept = JSON.parse(sessionStorage.getItem(draftKey) || 'null');
      if (kept && kept.settings && kept.questionnaire !== undefined) {
        recovered = true; recoveredConflict = kept.revision !== revision; dirty = true;
        data.settings = {...data.settings, ...kept.settings}; draftDocument.configuration ||= {};
        draftDocument.configuration.questionnaire = kept.questionnaire;
        if (recoveredConflict) revision = kept.revision;
      }
    } catch { /* The live form remains available if browser storage is unavailable. */ }
    function keepDraft() {
      try { sessionStorage.setItem(draftKey, JSON.stringify({revision, settings:settings(), questionnaire:questionnaire(), saved_at:Date.now()})); }
      catch { showNotice(message, 'Keep this page open while changes save.'); }
    }
    function clearDraft() { try { sessionStorage.removeItem(draftKey); } catch {} }
    const snapshotURL = id => id === undefined || id === null || id === '' ? safeUrl(data.settings?.preview_url) : `${API}/preview/${encodeURIComponent(id)}`;
    const settings = () => Object.fromEntries(['accent', 'headline', 'description', 'button_label'].map(key => [key, controls[key].value.trim()]));
    function previewSettings() { const value = settings(); if (previewReady) frame.contentWindow?.postMessage({type:'rocoto:preview-settings',settings:value}, '*'); }
    function state(text) { editStatus.title = text; editStatus.setAttribute('aria-label', text); editStatus.replaceChildren(icon(text === 'Saving…' ? 'refresh' : text === 'All changes saved' ? 'check' : 'info'), node('span', 'mo-sr-only', text)); }
    function savedLabel() { return data.published || data.state === 'published' ? 'Published on website' : data.state === 'pending' ? 'Saved · awaiting publication' : 'Draft saved'; }
    function setSavedStatus() { state('All changes saved'); }
    function schedule() { clearTimeout(timer); if (current() && !historyOpen && dirty && canEdit) timer = setTimeout(() => saveNow(), 700); }
    function change() { dirty = true; changed++; keepDraft(); state('Saving…'); draftLabel.textContent = 'Current changes'; previewSettings(); schedule(); }
    async function saveNow() {
      clearTimeout(timer);
      if (saving) { const ok = await saving; if (!ok) return false; if (dirty) return saveNow(); return true; }
      if (!dirty || !current() || !canEdit) return true;
      if (!form.checkValidity()) { state('Complete the highlighted fields'); return false; }
      const sequence = changed, payload = {settings:settings(), document:clone(draftDocument), expected_revision:revision};
      state('Saving…'); retry.hidden = true;
      saving = (async () => {
        try {
          const result = await request('/configurator', context, payload); if (!current()) return false;
          data = result; revision = result.revision; versionId = result.version_id;
          if (sequence === changed) { dirty = false; clearDraft(); const editedQuestions = draftDocument.configuration.questionnaire; draftDocument = clone(result.document); draftDocument.configuration.questionnaire = editedQuestions; setSavedStatus(); draftLabel.textContent = savedLabel(); previewReady = false; frame.src = snapshotURL(versionId); }
          else { keepDraft(); state('Saving…'); schedule(); }
          showNotice(message, ''); return true;
        } catch (error) { if (current()) { state('Changes saved on this page'); showNotice(message, error.message); retry.hidden = false; } return false; }
      })();
      const result = await saving; saving = null; return result;
    }
    function textValue(value) { return typeof value === 'string' ? value : value?.en || value?.bg || ''; }
    function setLocalizedText(target, key, text) { target[key] = typeof target[key] === 'string' ? text : {...target[key], en:text}; }
    function questionnaire() { draftDocument.configuration ||= {}; draftDocument.configuration.questionnaire ||= {id:'manufacturer', title:{en:'Choose a product'}, questions:[]}; draftDocument.configuration.questionnaire.questions ||= []; return draftDocument.configuration.questionnaire; }
    function questionEditor() {
      const section = node('section', 'mf-card mf-questionnaire'), top = node('div', 'mf-section-heading'); top.append(node('h2', '', 'Questions'), iconButton('Edit with agent', () => document.dispatchEvent(new CustomEvent('manufacturer:chat', {detail:{message:'Help me improve the customer questionnaire. Review the questions, answers and matching products, then help me edit the questions.'}})), 'agent')); if (data.capabilities?.agent_editing === false) top.querySelector('button')?.remove(); section.append(top);
      const questions = questionnaire().questions, list = node('div', 'mf-questions'); section.append(list);
      function drawQuestions() {
        list.replaceChildren();
        questions.forEach((question, index) => {
          const card = node('section', 'mf-question'), heading = node('div', 'mf-question-heading'), actions = node('div', 'mf-question-actions');
          heading.append(node('strong', '', `Question ${index + 1}`));
          for (const [direction, label] of [[-1, 'Move up'], [1, 'Move down']]) { const move = button(label, () => { const destination = index + direction; [questions[index], questions[destination]] = [questions[destination], questions[index]]; drawQuestions(); change(); }, 'chevron'); move.classList.add('mf-icon-action', direction < 0 ? 'mf-up' : 'mf-down'); move.disabled = !canEdit || index + direction < 0 || index + direction >= questions.length; actions.append(move); }
          const remove = button('Remove question', () => { questions.splice(index, 1); drawQuestions(); change(); }, 'close'); remove.classList.add('mf-icon-action'); remove.disabled = !canEdit; actions.append(remove); heading.append(actions); card.append(heading);
          const title = input(`question-${index}`, textValue(question.title)); title.required = true; title.maxLength = 200; title.addEventListener('input', () => { setLocalizedText(question, 'title', title.value); change(); }); card.append(field('Question', title));
          const kind = node('select', 'mf-input'); for (const [value, label] of [['single','Single choice'], ['multiple','Multiple choice'], ['text','Free text'], ['number','Number'], ['file','File upload']]) { const option = node('option', '', label); option.value = value; kind.append(option); } kind.value = question.kind || 'single'; kind.addEventListener('change', () => { question.kind = kind.value; change(); }); card.append(field('Answer type', kind));
          const options = node('div', 'mf-question-options'); question.options ||= [];
          question.options.forEach((option, optionIndex) => { const row = node('div', 'mf-question-option'), text = input(`option-${index}-${optionIndex}`, textValue(option.label)); text.required = true; text.maxLength = 160; text.setAttribute('aria-label', `Question ${index + 1}, answer ${optionIndex + 1}`); text.addEventListener('input', () => { setLocalizedText(option, 'label', text.value); change(); }); const remove = button('Remove answer', () => { question.options.splice(optionIndex, 1); drawQuestions(); change(); }, 'close'); remove.classList.add('mf-icon-action'); remove.disabled = !canEdit || question.options.length <= 2; row.append(text, remove); options.append(row); });
          const add = button('Add answer', () => { question.options.push({id:`option-${crypto.randomUUID().slice(0,8)}`,label:{en:''}}); drawQuestions(); change(); }, 'plus'); add.disabled = !canEdit; card.append(node('span', 'mf-label', 'Answers'), options, add); list.append(card);
        });
        if (!questions.length) list.append(node('p', 'mf-footnote', 'Add a question to help customers choose.'));
        if (!canEdit) list.querySelectorAll('input,select').forEach(control => { control.disabled = true; });
      }
      const add = button('Add question', () => { questions.push({id:`question-${crypto.randomUUID().slice(0,8)}`,kind:'single',title:{en:''},options:[{id:'first',label:{en:''}},{id:'second',label:{en:''}}]}); drawQuestions(); change(); }, 'plus'); add.disabled = !canEdit; section.append(add); drawQuestions(); return section;
    }
    function renderEditor() {
      const saved = data.settings || {}, split = node('div', 'mf-configurator-layout'), inspector = node('aside', 'mf-inspector'); inspector.setAttribute('aria-label', 'Configurator editor'); form = node('form', 'mf-configurator-controls'); form.addEventListener('submit', event => { event.preventDefault(); saveNow(); });
      const appearance = node('section', 'mf-card'); appearance.dataset.panel = 'appearance'; appearance.append(node('h2', '', 'Appearance'));
      const headline = input('headline', saved.headline), description = node('textarea', 'mf-input'), cta = input('button_label', saved.button_label), colour = input('accent', saved.accent, 'color'), colourValue = input('accent_text', saved.accent);
      headline.maxLength = 160; headline.required = true; cta.maxLength = 60; cta.required = true; description.name = 'description'; description.value = saved.description || ''; description.maxLength = 500; description.rows = 3;
      colour.setAttribute('aria-label', 'Primary colour'); colourValue.setAttribute('aria-label', 'Primary colour code'); colourValue.pattern = '#[a-fA-F0-9]{6}'; colourValue.maxLength = 7;
      const colourRow = node('div', 'mf-colour-control'); colourRow.append(colour, colourValue); controls = {headline, description, button_label:cta, accent:colour};
      appearance.append(field('Primary colour', colourRow), field('Title', headline), field('Description', description), field('Button text', cta));
      retry = button('Save again', saveNow, 'refresh'); retry.hidden = true; appearance.append(retry); const questionsPanel = questionEditor(); questionsPanel.dataset.panel = 'questions'; form.append(appearance, questionsPanel);
      const cats = draftDocument.catalogue?.cats || [], count = cats.reduce((total, category) => total + (category.items?.length || 0), 0);
      const products = node('a', 'mf-products-shortcut'); products.href = '?view=products'; products.dataset.manufacturerRoute = 'products'; products.append(icon('package'), node('span', '', 'Products'), node('small', 'mf-muted', count.toLocaleString('en-GB')), icon('chevron'));
      const install = node('section', 'mf-card'); install.dataset.panel = 'install'; install.append(node('h2', '', 'Add to website'), node('p', 'mf-muted', 'Add this code to your website’s <head>. The order button opens the configurator.'));
      const embed = safeUrl(saved.embed_url), snippet = embed ? `<script src="${embed.replace(/&/g, '&amp;').replace(/"/g, '&quot;')}" data-rocoto="${slug(saved.company_slug)}" defer><\/script>` : '';
      const code = node('textarea', 'mf-snippet'); code.readOnly = true; code.rows = 4; code.value = snippet; code.setAttribute('aria-label', 'Configurator embed code');
      const copy = button('Copy code', async () => { try { await navigator.clipboard.writeText(code.value); copy.replaceChildren(icon('check'), document.createTextNode('Copied')); } catch { code.focus(); code.select(); showNotice(message, 'Code selected and ready to copy.'); } }, 'copy'); copy.disabled = !embed; install.append(code, copy); form.append(install);
      const inspectorTabs = node('div', 'mf-inspector-tabs'); inspectorTabs.setAttribute('role', 'tablist'); inspectorTabs.setAttribute('aria-label', 'Configurator tools');
      const choosePanel = id => { for (const panel of form.children) panel.hidden = panel.dataset.panel !== id; for (const control of inspectorTabs.querySelectorAll('[role=tab]')) { const active = control.dataset.panel === id; control.setAttribute('aria-selected', String(active)); control.tabIndex = active ? 0 : -1; } };
      for (const [id, label, symbol] of [['appearance','Appearance','settings'], ['questions','Questions','list'], ['install','Add to website','terminal']]) { const tab = iconButton(label, () => choosePanel(id), symbol); tab.dataset.panel = id; tab.setAttribute('role', 'tab'); tab.id = `mf-tool-${id}`; tab.setAttribute('aria-controls', `mf-panel-${id}`); const panel = form.querySelector(`[data-panel=${id}]`); panel.id = `mf-panel-${id}`; panel.setAttribute('role', 'tabpanel'); panel.setAttribute('aria-labelledby', tab.id); inspectorTabs.append(tab); }
      inspectorTabs.addEventListener('keydown', event => { const tabs = [...inspectorTabs.querySelectorAll('[role=tab]')], at = tabs.indexOf(document.activeElement); if (at < 0 || !['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return; event.preventDefault(); const index = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (at + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length; tabs[index].click(); tabs[index].focus(); });
      const closeInspector = iconButton('Close editor', () => toggleInspector(false), 'close'); closeInspector.classList.add('mf-inspector-close'); inspectorTabs.append(closeInspector); inspector.append(inspectorTabs, form, products); choosePanel('appearance');
      const preview = node('section', 'mf-preview'), previewBar = node('div', 'mf-preview-toolbar'), modes = node('div', 'mf-preview-modes'); modes.setAttribute('role', 'group'); modes.setAttribute('aria-label', 'Preview size');
      const stage = node('div', 'mf-preview-stage'); frame = node('iframe', 'mf-preview-frame'); frame.title = 'Saved configurator'; frame.setAttribute('sandbox', 'allow-scripts'); frame.referrerPolicy = 'no-referrer'; frame.src = snapshotURL(versionId);
      for (const [id, title, symbol] of [['desktop','Desktop preview','fullscreen'], ['mobile','Phone preview','document']]) { const control = iconButton(title, () => { stage.dataset.device = id; for (const other of modes.querySelectorAll('button')) other.setAttribute('aria-pressed', String(other === control)); }, symbol); const svg = document.createElementNS('http://www.w3.org/2000/svg','svg'); svg.setAttribute('class','icon'); svg.setAttribute('viewBox','0 0 24 24'); svg.setAttribute('aria-hidden','true'); const shape = document.createElementNS(svg.namespaceURI,'rect'); for (const [key,value] of Object.entries(id === 'desktop' ? {x:3,y:4,width:18,height:13,rx:2} : {x:7,y:2,width:10,height:20,rx:2})) shape.setAttribute(key,String(value)); const stroke = document.createElementNS(svg.namespaceURI,'path'); stroke.setAttribute('d',id === 'desktop' ? 'M8 21h8M12 17v4' : 'M11 18h2'); svg.append(shape,stroke); control.replaceChildren(svg); control.setAttribute('aria-pressed', String(id === 'desktop')); modes.append(control); }
      draftLabel = node('span', 'mf-preview-state', savedLabel());
      const edit = iconButton('Edit configurator', () => toggleInspector(!split.classList.contains('mf-inspector-open')), 'settings'); edit.classList.add('mf-edit-toggle'); edit.setAttribute('aria-expanded','false'); edit.setAttribute('aria-controls','mf-config-inspector'); inspector.id = 'mf-config-inspector';
      const backdrop = button('Close editor', () => toggleInspector(false)); backdrop.className = 'mf-inspector-backdrop'; backdrop.tabIndex = -1; backdrop.setAttribute('aria-hidden','true');
      function toggleInspector(open, focus = true) { split.classList.toggle('mf-inspector-open', open); edit.setAttribute('aria-expanded', String(open)); preview.inert = open; title.inert = open; inspector.setAttribute('role', open ? 'dialog' : 'complementary'); if (open) inspector.setAttribute('aria-modal','true'); else inspector.removeAttribute('aria-modal'); if (focus) { if (open) inspector.querySelector('[role=tab][aria-selected=true]').focus(); else edit.focus(); } }
      if (inspectorResize) window.removeEventListener('resize', inspectorResize); inspectorResize = () => { if (innerWidth > 1050 && split.classList.contains('mf-inspector-open')) toggleInspector(false, false); }; window.addEventListener('resize', inspectorResize);
      inspector.addEventListener('keydown', event => { if (!split.classList.contains('mf-inspector-open')) return; if (event.key === 'Escape') { event.preventDefault(); toggleInspector(false); } if (event.key === 'Tab') { const targets = [...inspector.querySelectorAll('button:not([disabled]),input:not([disabled]),textarea:not([disabled]),select:not([disabled]),a[href]')].filter(el => el.getClientRects().length && el.tabIndex >= 0), first = targets[0], last = targets.at(-1); if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); } else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); } } });
      previewBar.append(draftLabel, modes, edit); const live = saved.company_slug && safeUrl(saved.embed_url) ? `${new URL(saved.embed_url).origin}/${encodeURIComponent(saved.company_slug)}/#order` : safeUrl(saved.preview_url); if (live) { const open = link('', live, 'mf-open-preview mf-tool-button'); open.append(icon('link')); open.title = 'Open website'; open.setAttribute('aria-label','Open website'); previewBar.append(open); } stage.dataset.device = 'desktop'; stage.append(frame); preview.append(previewBar, stage);
      if(canEdit)split.append(preview, backdrop, inspector);else{split.append(preview);split.classList.add('mf-preview-only');edit.hidden=true;draftLabel.hidden=true;const requestChange=button(data.capabilities?.agent_editing === false ? 'Team chat' : 'Edit with agent',()=>document.dispatchEvent(new CustomEvent('manufacturer:service')),'chat');previewBar.append(requestChange);}
      editor.replaceChildren(split); previewSettings();
      colour.addEventListener('input', () => { colourValue.value = colour.value; change(); }); colourValue.addEventListener('input', () => { if (/^#[a-fA-F0-9]{6}$/.test(colourValue.value)) { colour.value = colourValue.value; change(); } }); for (const control of [headline, description, cta]) control.addEventListener('input', change);
      if (!canEdit) form.querySelectorAll('input,select,textarea:not([readonly])').forEach(control => { control.disabled = true; });
    }
    function historyRoute(open) { const url = new URL(location.href); if (url.searchParams.get('view') !== 'configurator') return; if (open) url.searchParams.set('history','1'); else url.searchParams.delete('history'); history.replaceState(history.state, '', url); }
    function closeHistory() { historyRoute(false); historyOpen = false; historyView.hidden = true; editor.hidden = false; title.hidden = false; page.classList.remove('mf-history-active'); selectionEpoch++; if (historyFrame) historyFrame.src = 'about:blank'; schedule(); }
    function versionTime(value) { const time = new Date(typeof value === 'number' && value < 1e12 ? value * 1000 : value); if (!Number.isFinite(time.valueOf())) return 'Saved version'; const sameDay = time.toDateString() === new Date().toDateString(); return new Intl.DateTimeFormat('en-GB', sameDay ? {hour:'numeric',minute:'2-digit'} : {month:'short',day:'numeric',hour:'numeric',minute:'2-digit'}).format(time); }
    function versionName(version) { return ({'Restored version':'Restored version','Original configuration':'Initial configuration'})[version.name] || version.name; }
    function versionAuthor(version) { return version.author?.type === 'agent' ? 'Company agent' : version.author?.type === 'system' ? '' : version.author?.name || 'Member'; }
    function drawTimeline() {
      versionList.replaceChildren(); versionPicker.replaceChildren();
      for (const version of versions) {
        const item = node('button', 'mf-version-entry'); item.type = 'button'; item.dataset.versionId = String(version.id); item.title = date(version.created_at); item.setAttribute('aria-pressed', String(String(selectedVersion?.id) === String(version.id)));
        const label = versionName(version) || versionTime(version.created_at), author = versionAuthor(version), top = node('span', 'mf-version-entry-top'); top.append(node('strong', '', label)); if (version.is_current) top.append(node('small', 'mf-version-current', 'Current')); item.append(top);
        const metadata = [version.name ? versionTime(version.created_at) : '', author].filter(Boolean).join(' · '); if (metadata) item.append(node('span', 'mf-version-author', metadata));
        item.addEventListener('click', () => selectVersion(version.id)); versionList.append(item); const option = node('option', '', `${label}${version.is_current ? ' · Current' : ''}${author ? ` · ${author}` : ''}`); option.value = String(version.id); versionPicker.append(option);
      }
      if (selectedVersion) versionPicker.value = String(selectedVersion.id);
    }
    async function selectVersion(id) {
      const epoch = ++selectionEpoch; restoreButton.disabled = true; historyView.querySelector('.mf-version-preview').setAttribute('aria-busy','true');
      try { const result = await request(`/configurator/versions/${encodeURIComponent(id)}`, context); if (!current() || !historyOpen || epoch !== selectionEpoch) return;
        selectedVersion = result.version; historyFrame.src = snapshotURL(selectedVersion.id); historyFrame.title = `Configurator version ${date(selectedVersion.created_at)}`;
        historyView.querySelector('.mf-version-title').textContent = versionName(selectedVersion) || versionTime(selectedVersion.created_at); historyView.querySelector('.mf-version-byline').textContent = [versionAuthor(selectedVersion), selectedVersion.is_current ? 'Current version' : ''].filter(Boolean).join(' · ');
        historyFrame.addEventListener('load', () => { if (current() && epoch === selectionEpoch) historyView.querySelector('.mf-version-preview')?.setAttribute('aria-busy','false'); }, {once:true}); restoreButton.hidden = Boolean(selectedVersion.is_current); restoreButton.disabled = !canEdit; drawTimeline();
      } catch (error) { if (current()) { historyView.querySelector('.mf-version-preview')?.setAttribute('aria-busy','false'); showNotice(message, error.message); } }
    }
    async function restore() {
      if (!selectedVersion || selectedVersion.is_current || !canEdit) return;
      restoreButton.disabled = true;
      // Preserve an unfinished manual edit as its own saved version before restoring an older one.
      if (dirty && !await saveNow()) { restoreButton.disabled = false; return; }
      try { const result = await request(`/configurator/versions/${encodeURIComponent(selectedVersion.id)}/restore`, context, {expected_revision:revision}); if (!current()) return;
        data = result; revision = result.revision; versionId = result.version_id; draftDocument = clone(result.document); dirty = false; clearDraft(); changed++; previewReady = false; renderEditor(); setSavedStatus(); closeHistory(); showNotice(message, 'Version restored.');
      } catch (error) { if (current()) { showNotice(message, error.message); restoreButton.disabled = false; } }
    }
    async function openHistory() {
      if (!current() || historyOpen) return; historyRoute(true); clearTimeout(timer); historyOpen = true; editor.hidden = true; title.hidden = true; historyView.hidden = false; page.classList.add('mf-history-active');
      const header = node('header', 'mf-history-header'), back = button('Back to configurator', closeHistory, 'chevron'); back.classList.add('mf-history-back'); header.append(back, node('h1', '', 'Version history')); versionPicker = node('select', 'mf-input mf-version-picker'); versionPicker.setAttribute('aria-label', 'Selected version'); versionPicker.addEventListener('change', () => selectVersion(versionPicker.value)); header.append(versionPicker);
      const surface = node('div', 'mf-history-workspace'), documentPanel = node('section', 'mf-version-preview'), detail = node('div', 'mf-version-meta'), text = node('div');
      text.append(node('h2', 'mf-version-title', 'Loading version…'), node('p', 'mf-version-byline mf-muted')); restoreButton = button('Restore version', restore, 'refresh', true); restoreButton.disabled = true; restoreButton.hidden = true; restoreButton.title = 'Restore version'; restoreButton.setAttribute('aria-label','Restore version'); detail.append(text, restoreButton);
      historyFrame = node('iframe', 'mf-version-frame'); historyFrame.title = 'Selected configurator version'; historyFrame.setAttribute('sandbox', 'allow-scripts'); historyFrame.referrerPolicy = 'no-referrer'; documentPanel.append(detail, historyFrame);
      const timeline = node('aside', 'mf-version-timeline'); timeline.setAttribute('aria-label', 'Configurator versions'); timeline.append(node('h2', '', 'Versions')); if (dirty) timeline.append(node('p', 'mf-footnote', 'Your current changes stay saved while you review.')); versionList = node('div', 'mf-version-list'); timeline.append(versionList); surface.append(documentPanel, timeline); historyView.replaceChildren(header, surface);
      try { if (saving) await saving; const result = await request('/configurator/versions', context); if (!current() || !historyOpen) return; versions = result.versions || []; drawTimeline(); const latest = versions.find(item => item.is_current) || versions[0]; if (latest) selectVersion(latest.id); else historyView.querySelector('.mf-version-title').textContent = 'Saved versions appear here.'; }
      catch (error) { if (current()) showNotice(message, error.message); }
    }
    const onMessage = event => { if (!current() || event.source !== frame?.contentWindow || event.origin !== 'null' || event.data?.type !== 'rocoto:preview-ready' || !Array.isArray(event.data.capabilities) || !event.data.capabilities.includes('settings')) return; previewReady = true; if (dirty) previewSettings(); };
    const beforeUnload = event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } };
    window.addEventListener('message', onMessage); window.addEventListener('beforeunload', beforeUnload);
    renderEditor(); setSavedStatus();
    const syncHistoryRoute = () => { if (!current() || new URL(location.href).searchParams.get('view') !== 'configurator') return; if (new URL(location.href).searchParams.get('history') === '1') openHistory(); else if (historyOpen) closeHistory(); }; window.addEventListener('popstate', syncHistoryRoute); syncHistoryRoute();
    if (recovered) { state('Page changes restored'); draftLabel.textContent = 'Current changes'; if (recoveredConflict) showNotice(message, 'Your text is saved. Review the other configurator change in history before saving.'); else schedule(); }
    return {show() { syncHistoryRoute(); }, hide() { if (dirty) saveNow(); }, unmount() { window.removeEventListener('popstate', syncHistoryRoute); disposed = true; clearTimeout(timer); window.removeEventListener('message', onMessage); window.removeEventListener('beforeunload', beforeUnload); if (inspectorResize) window.removeEventListener('resize', inspectorResize); if (frame) frame.src = 'about:blank'; if (historyFrame) historyFrame.src = 'about:blank'; root.replaceChildren(); }};
  }

  async function companyTab(root, context) {
    const page = layout(root); page.classList.add('mf-company-page');
    page.append(heading('Company and team')); const message = notice(); page.append(message);
    let data, accessState = {}, senderState = {}, pending = false, disposed = false;
    const content = node('div', 'mf-company-content'); page.append(content);
    const current = () => context.isCurrent() && !disposed;
    function setPending(value) {
      pending = value;
      content.querySelectorAll('form input,form select,form button').forEach(control => { control.disabled = value || !accessState.can_invite; });
    }
    async function shared(path, payload) {
      const response = await fetch(path, {signal:context.signal, cache:'no-store', ...(payload ? {method:'POST', headers:{'Content-Type':'application/json','X-Rocoto-Page':'1'}, body:JSON.stringify(payload)} : {})});
      if (!response.ok) throw Error(response.status === 403 ? 'Use an account with team-management access.' : 'Reconnecting. Try again.');
      return response.json();
    }
    async function inviteMember(email) {
      if (pending || !accessState.can_invite) return;
      setPending(true);
      try {
        const result = await shared('/api/workspaces/invitations', {environment_id:accessState.environment_id, email});
        if (!current()) return;
        data.invitations ||= []; data.invitations.push({...result, role:'operator', state:'sent'});
        draw(); showNotice(message, 'Invitation sent.');
      } catch (error) { if(current()) showNotice(message, error.message); }
      finally { if(current()) setPending(false); }
    }
    function draw() {
      const company = data.company || {}, policy = data.policy || {};
      const overview = node('section', 'mf-card mf-company-overview'), mark = node('span', 'mf-company-mark'); mark.append(icon('building'));
      const identity = node('div', 'mf-company-identity'); identity.append(node('h2', '', company.name || 'Company'));
      if (company.website) identity.append(link(company.website.replace(/^https?:\/\//, '').replace(/\/$/, ''), company.website));
      overview.append(mark, identity);
      const access = node('section', 'mf-card mf-company-access'); access.append(node('h2', '', 'Workspace access'));
      const codeRow = node('div', 'mf-access-row'), codeCopy = node('div');
      codeCopy.append(node('strong', '', 'Access code'), node('p', 'mf-muted', 'Sign in with your workspace code.'));
      const openSignIn = button('Preview sign-in', () => document.dispatchEvent(new CustomEvent('manufacturer:signin', {detail:{company:company.name}})), 'eye');
      codeRow.append(codeCopy, openSignIn);
      const domainForm = node('div', 'mf-company-domain'), domainCopy = node('div');
      domainCopy.append(node('strong', '', 'Work email'), node('p', 'mf-muted', `@${policy.domain || company.domain || ''}`));
      domainForm.append(domainCopy, badge(accessState.hosted_login ? 'Sign in with Google or email' : 'Sign-in setup'));
      access.append(codeRow, domainForm);
      const emailConnection = node('div', 'mf-access-row'), emailCopy = node('div');
      emailCopy.append(node('strong', '', 'Customer email'), node('p', 'mf-muted', senderState.ready ? senderState.sender : 'Set up your company email.'));
      emailConnection.append(emailCopy, badge(senderState.ready ? 'Connected' : 'Setup in progress'));
      access.append(emailConnection);
      const people = node('section', 'mf-card mf-company-people'), peopleHeading = node('div', 'mf-company-section-heading');
      peopleHeading.append(node('h2', '', 'Team'), node('span', 'mf-muted', String((data.members || []).length))); people.append(peopleHeading);
      const members = node('div', 'mf-members');
      for (const member of data.members || []) {
        const row = node('div', 'mf-member'), name = member.name || member.display_name || member.email || 'Member';
        const avatar = node('span', 'mf-person-avatar', name.slice(0, 1).toUpperCase()), text = node('div');
        text.append(node('strong', '', name)); if (member.email) text.append(node('small', 'mf-muted', member.email));
        row.append(avatar, text, badge(member.role === 'owner' ? 'Owner' : member.role === 'browse' ? 'Viewer' : 'Member')); members.append(row);
      }
      if (!members.childElementCount) members.append(node('p', 'mf-muted', 'Team members appear here.')); people.append(members);
      if (accessState.can_invite) {
        const invite = node('form', 'mf-invite-form'), email = input('email', '', 'email');
        email.required = true; email.placeholder = `name@${company.domain || 'company.com'}`; email.autocomplete = 'email';
        const inviteButton = button('Send invitation', () => {}, 'plus', true); inviteButton.type = 'submit';
        invite.append(field('Email address', email), inviteButton);
        invite.addEventListener('submit', event => {event.preventDefault(); if(invite.reportValidity()) inviteMember(email.value.trim());});
        people.append(invite);
      }
      if (data.invitations?.length) {
        const invitations = node('div', 'mf-invitations'); invitations.append(node('h3', '', 'Invite'));
        for (const invitation of data.invitations) {
          const row = node('div', 'mf-invitation'), copy = node('div');
          copy.append(node('span', '', invitation.email), node('small', 'mf-muted', invitation.role === 'browse' ? 'Viewer' : 'Member'));
          const status = {sent:'Sent', accepted:'Joined', revoked:'Cancelled'}[invitation.state] || 'Draft';
          row.append(copy, badge(status)); invitations.append(row);
        }
        people.append(invitations);
      }
      const warehouses=node('section','mf-card mf-company-warehouses');warehouses.append(node('h2','','Warehouses'));for(const warehouse of company.warehouses||[]){const row=node('div','mo-warehouse-setting');row.append(node('strong','',typeof warehouse.name==='object'?(warehouse.name.en||warehouse.name.bg):warehouse.name));if(warehouse.erpCode)row.append(node('code','',warehouse.erpCode));if(warehouse.address)row.append(node('p','mf-muted',typeof warehouse.address==='object'?(warehouse.address.en||warehouse.address.bg):warehouse.address));warehouses.append(row);}content.replaceChildren(overview,...((company.warehouses||[]).length?[warehouses]:[]),access, people); setPending(pending);
    }
    try { const values = await Promise.all([request('/team', context), shared('/api/workspaces/access'), shared('/api/manufacturer/mail/status').catch(() => ({}))]); [data, accessState, senderState] = values; if (current()) draw(); } catch (error) { if (current()) showNotice(message, error.message); }
    return {unmount() { disposed = true; root.replaceChildren(); }};
  }

  window.RocotoWorkspaceTabs.register('manufacturer', {orders:{mount:ordersTab}, configurator:{mount:configuratorTab}, company:{mount:companyTab}});
})();
