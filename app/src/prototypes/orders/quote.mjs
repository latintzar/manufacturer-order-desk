// Server quotes use the exact pricing engine loaded by the order page.
import fs from 'node:fs';
globalThis.window = {};
const pricing = await import('./widget/pricing.js');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const {catalog, lines} = input;
const engine = pricing.RocotoPricing || pricing.default?.RocotoPricing || window.RocotoPricing;
engine.configure(catalog.rules);
if (!Array.isArray(lines) || !lines.length || lines.length > 100) throw Error('Choose 1 to 100 order lines.');
const items = new Map(catalog.cats.flatMap(cat => cat.items.map(i => [i.c, {...i, cat}])));
// Laser lines arrive beside the order, measured and priced by the server (quote.py with laser.py).
const measured = input.measured || {};
const priced = lines.map((line, index) => {
  if (Object.hasOwn(measured, index)) return measured[index];
  if (line.custom) {
    if (typeof line.custom !== 'string' || line.custom.length > 4000) throw Error('Describe the custom item in up to 4000 characters.');
    const upload = line.upload_id;
    if (upload != null && (typeof upload !== 'string' || !/^[a-f0-9]{32}$/.test(upload))) throw Error('Choose the design file again.');
    return {item_id:null, kind:'custom', description:line.custom, quantity:1, configuration:{custom:line.custom}, cuts:0, gross:0, confirmation:true,
      ...(upload ? {upload_id:upload} : {})};
  }
  const item = items.get(line.code);
  if (!item) throw Error('Choose an item from the current catalogue.');
  const mode = engine.lineMode(item);
  const rows = line.rows || [{x:0,n:1}];
  if (!Array.isArray(rows) || !rows.length || rows.length > 100) throw Error('Choose 1 to 100 cut sizes.');
  if (rows.some(r => !Number.isFinite(r.x) || !Number.isInteger(r.n) || r.n < 1 || r.n > 999 || r.x < 0 || r.x > 100000)) throw Error('Enter valid lengths and quantities.');
  const configuration = {rows, sheet:line.sheet, angle:line.angle};
  const plan = engine.quoteLine(item, configuration);
  if (!plan.ok || !Number.isFinite(plan.total)) throw Error('Check this item’s sizes and quantities.');
  const requested = mode === 'sheet' ? line.sheet.n : rows.reduce((n,r)=>n+r.n,0);
  const stockBasis = item.stockBasis || (item.u === 'kg' ? 'kilogram' : item.u === 'm' || (item.q && mode === 'bar' && item.L <= 1 && item.r.k !== 'len') || item.rate?.[1] === 'm' ? 'metre' : 'stock_unit');
  // Partial bars reserve whole stock units conservatively; offcuts remain uncounted.
  const purchased = stockBasis === 'metre'
    ? (plan.bought || plan.units?.reduce((n,u)=>n+u.len*u.count,0) || rows.reduce((n,r)=>n+r.x*r.n,0))/1000
    : plan.units?.reduce((n,u)=>n+u.count,0) || requested;
  return {item_id:item.c, quantity:purchased, requested_quantity:requested, cuts:plan.cuts||0,
    kind:mode, configuration, gross:plan.total, confirmation:!!(item.q||plan.ask||plan.pending),
    plan, stock_basis:stockBasis, source:catalog.source, resource_id:'workshop'};
});
const gross = Math.round(priced.reduce((n,l)=>n+l.gross,0)*100)/100;
const net = Math.round(gross/(1+catalog.vat)*100)/100;
process.stdout.write(JSON.stringify({lines:priced, quote:{currency:catalog.currency, gross, net,
  vat:Math.round((gross-net)*100)/100, vat_rate:catalog.vat, price_date:catalog.asOf,
  price_date_kind:catalog.asOfKind||'source_displayed_date', price_revision_verified:catalog.priceRevisionVerified===true,
  confirmation:priced.some(l=>l.confirmation), delivery:'confirmation', source:catalog.source}}));
