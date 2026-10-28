// The laser estimate in the order page's language answers the hand-worked vectors to the cent,
// the same vectors tests/test_laser.py holds laser_quote.py to.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';

const here = new URL('.', import.meta.url);
const source = readFileSync(new URL('../laser_quote.mjs', here), 'utf8');
const fixture = JSON.parse(readFileSync(new URL('fixtures/laser-price-vectors.json', here), 'utf8'));

// Loaded twice: as the plain script a bundle carries, and as the module Node imports.
const sandbox = { module: { exports: {} } };
vm.runInNewContext(source, sandbox);
const bundled = sandbox.module.exports.RocotoLaserQuote;
await import('../laser_quote.mjs');
const imported = globalThis.RocotoLaserQuote;

const material = id => fixture.materials.find(entry => entry.id === id) || { id, thicknesses: [1, 2, 5], density: 7850 };
const plain = value => JSON.parse(JSON.stringify(value));

for (const vector of fixture.vectors) {
  test(`laser estimate: ${vector.what}`, () => {
    for (const engine of [bundled, imported]) {
      const answer = engine.quote(vector.measure, material(vector.material), fixture.tariff, vector.thickness, vector.quantity);
      assert.deepEqual(plain(answer), vector.expect);
    }
  });
}

test('the estimate follows the tariff: a dearer metre is a dearer cut', () => {
  const vector = fixture.vectors[2];
  const dearer = plain(fixture.tariff);
  dearer.rates.steel.cut[1] = 1.55;
  const before = imported.quote(vector.measure, material('steel'), fixture.tariff, 2, 1);
  const after = imported.quote(vector.measure, material('steel'), dearer, 2, 1);
  assert.equal(before.cutting, 1.13);
  assert.equal(after.cutting, 3.18);                    // 2.05229 m x 1.55
  assert.equal(after.net, 18.83);
  assert.notDeepEqual(after, before);
});

test('every amount of a summary adds up to its net', () => {
  for (const vector of fixture.vectors.filter(entry => entry.expect.ok && !entry.expect.minimum)) {
    const answer = imported.quote(vector.measure, material(vector.material), fixture.tariff, vector.thickness, vector.quantity);
    const sum = Math.round((answer.material + answer.cutting + answer.piercing + answer.setup) * 100) / 100;
    assert.equal(sum, answer.net);
    assert.equal(Math.round((answer.net + answer.vat) * 100) / 100, answer.gross);
  }
});
