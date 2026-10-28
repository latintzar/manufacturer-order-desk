/* The laser-cutting estimate for the order page: the arithmetic of laser_quote.py, in the same order.

     net   = the larger of: the minimum, or setup + quantity x (material + cutting + piercing)
     gross = net + VAT

   RocotoLaserQuote.quote(check, material, check.tariff, thickness, quantity) takes the answer of
   POST api/laser as it arrives: `check.bounds`, `check.cut`, one entry of `check.materials` and
   `check.tariff`. tests/fixtures/laser-price-vectors.json holds this file and laser_quote.py to
   the same cent. Written as a plain script, so a bundle can carry it as it is; Node imports it
   for the test and reads the same object from globalThis. */
(function (root) {
'use strict';
const MAX_QUANTITY = 999;
const cents = value => Math.floor(value * 100 + 0.5) / 100;
const grams = value => Math.floor(value * 1000 + 0.5) / 1000;
const number = (value, least, most) => typeof value === 'number' && Number.isFinite(value) && least <= value && value <= most;
function quote(measure, material, tariff, thickness, quantity) {
  const rate = tariff && tariff.rates ? tariff.rates[material && material.id] : null;
  const thicknesses = (material && material.thicknesses) || [];
  const index = thicknesses.indexOf(thickness);
  if (!rate || index < 0) return {ok: false};
  if (!Number.isInteger(quantity) || quantity < 1 || quantity > MAX_QUANTITY) return {ok: false};
  const bounds = (measure && measure.bounds) || {}, cut = (measure && measure.cut) || {};
  const width = bounds.w, height = bounds.h, length = cut.length_mm, pierces = cut.pierces;
  if (![width, height, length, pierces].every(value => number(value, 0, 1e7))) return {ok: false};
  const weight = width * height * thickness * material.density / 1e9;
  const materialCost = cents(weight * rate.kg * quantity);
  const cutting = cents(length / 1000 * rate.cut[index] * quantity);
  const piercing = cents(pierces * rate.pierce[index] * quantity);
  const setup = cents(tariff.setup);
  const subtotal = cents(materialCost + cutting + piercing + setup);
  const least = cents(tariff.minimum);
  const net = subtotal < least ? least : subtotal;
  const vat = cents(net * tariff.vat);
  return {
    ok: true, quantity, weight_kg: grams(weight),
    material: materialCost, cutting, piercing, setup,
    minimum: subtotal < least, piece: cents(net / quantity),
    net, vat, gross: cents(net + vat),
    vat_rate: tariff.vat, currency: tariff.currency,
  };
}
root.RocotoLaserQuote = {quote, MAX_QUANTITY};
})(typeof module !== 'undefined' && module && module.exports ? module.exports
  : typeof window !== 'undefined' ? window : globalThis);
