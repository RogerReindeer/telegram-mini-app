// Run with: node --test tests/frontend-regressions.cjs
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function harness(file, exports) {
  const nodes = new Map();
  const listeners = new Map();
  function node(selector) {
    if (!nodes.has(selector)) nodes.set(selector, {
      dataset: {}, hidden: true, textContent: '', disabled: false,
      classList: { add() {}, remove() {} },
      querySelector: node, querySelectorAll: () => [], focus() {},
      addEventListener() {}, setAttribute() {},
    });
    return nodes.get(selector);
  }
  const document = {
    readyState: 'loading', querySelector: node, querySelectorAll: (s) => [node(s)],
    addEventListener(name, cb) { listeners.set(name, cb); },
  };
  const context = {
    document, URL, console, Intl, Map, Math,
    CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options.detail; } },
  };
  context.window = {
    location: { origin: 'https://reader.test' },
    sessionStorage: { getItem() { throw Error('blocked'); }, setItem() { throw Error('blocked'); }, removeItem() { throw Error('blocked'); } },
    addEventListener() {}, dispatchEvent() {},
  };
  let source = fs.readFileSync(path.join(__dirname, '../static', file), 'utf8');
  source = source.replace('  initialize();', '');
  const end = source.lastIndexOf('})();');
  source = source.slice(0, end) + `globalThis.api = {${exports}};\n` + source.slice(end);
  vm.runInNewContext(source, context);
  return { api: context.api, context, node, listeners };
}

for (const [file, methods] of [
  ['reader-store.js', 'actionId, clearAction'],
  ['settings-panel.js', 'walletActionId, clearWalletAction'],
]) {
  test(`${file}: blocked storage still produces stable UUIDs for retry`, () => {
    const { api } = harness(file, methods);
    const create = api.actionId || api.walletActionId;
    const clear = api.clearAction || api.clearWalletAction;
    const first = create('operation');
    assert.match(first, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
    assert.equal(create('operation'), first);
    clear('operation');
    assert.notEqual(create('operation'), first);
  });
}

test('reader topup ignores double submission while the first request is pending', async () => {
  const { api, context } = harness('reader-store.js', 'state, grantTestCoins');
  api.state.testTopupEnabled = true;
  let resolve;
  let requests = 0;
  context.window.fetch = () => {
    requests += 1;
    return new Promise((done) => { resolve = done; });
  };
  const first = api.grantTestCoins(10);
  await api.grantTestCoins(10);
  assert.equal(requests, 1);
  resolve({ ok: true, json: async () => ({ credited: 10, balance: 10 }) });
  await first;
  assert.equal(api.state.balance, 10);
  assert.equal(api.state.busy, false);
});

test('settings preserve wallet balance when only the product catalog fails', async () => {
  const { api, context, node } = harness('settings-panel.js', 'loadWalletBalance');
  context.fetch = async (url) => {
    if (url.includes('/wallet')) return { ok: true, json: async () => ({ balance: 137 }) };
    throw Error('catalog offline');
  };
  await api.loadWalletBalance(true);
  assert.equal(node('[data-zb-wallet-balance]').textContent, '137');
  assert.match(node('[data-zb-wallet-status]').textContent, /Баланс загружен/);
});

test('read-only settings cannot grant test coins even if catalog enables the test', async () => {
  const { api, context } = harness('settings-panel.js', 'renderWalletTopup, grantWalletTestCoins');
  let requests = 0;
  context.fetch = () => { requests += 1; throw Error('unexpected request'); };
  api.renderWalletTopup({ test_topup_enabled: true }, true);
  await api.grantWalletTestCoins(10);
  assert.equal(requests, 0);
});
