import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import test from 'node:test';

process.env.NODE_ENV = 'test';
process.env.DATABASE_URL = 'postgresql://test:test@127.0.0.1:5432/test';
process.env.BOT_TOKEN = 'test-bot-token';
process.env.SESSION_SECRET = 'test-session-secret-at-least-16';
process.env.FRONTEND_ORIGIN = 'http://localhost:5173';
process.env.READER_COMMERCE_SHARED_SECRET = 'reader-secret-at-least-32-characters-long';

const delivery = await import('../dist/services/readerCoinDelivery.js');

const payload = {
  schema_version: 1,
  event_id: 'c46020a0-d3bb-40b0-88c3-1d641f5e0fc3',
  purchase_id: '7da789b8-8915-4e49-a5ae-5f86ba305fde',
  telegram_user_id: 123456789,
  product_code: 'currency_bundle_500',
  amount: 500,
  currency: 'reader_coins',
  provider: 'telegram_stars',
  occurred_at: '2026-08-29T12:10:00.000Z'
};

test('HMAC signs the exact body bytes required by Reader v242', () => {
  const secret = 'shared-secret-value';
  const timestamp = '1788000000';
  const nonce = '3e69c06c-ecfc-47aa-9034-9b448ba25808';
  const body = Buffer.from(JSON.stringify(payload), 'utf8');
  const bodyHash = crypto.createHash('sha256').update(body).digest('hex');
  const expected = crypto.createHmac('sha256', secret)
    .update(`${timestamp}.${nonce}.${bodyHash}`)
    .digest('hex');

  assert.equal(delivery.signReaderBody({ timestamp, nonce, body, secret }), expected);
  const request = delivery.buildSignedReaderRequest(payload, {
    nowSeconds: Number(timestamp), nonce, secret, serviceId: 'qinghe-api'
  });
  assert.deepEqual(request.body, body);
  assert.equal(request.headers['x-timestamp'], timestamp);
  assert.equal(request.headers['x-nonce'], nonce);
  assert.equal(request.headers['x-service-id'], 'qinghe-api');
  assert.equal(request.headers['x-signature'], expected);
});

test('retry schedule matches the Reader v242 integration contract', () => {
  assert.deepEqual(
    [1, 2, 3, 4, 5, 6, 7, 20].map(delivery.retryDelaySeconds),
    [30, 120, 600, 1800, 7200, 21600, 43200, 43200]
  );
});

test('only network-like Reader statuses are retried', () => {
  for (const status of [429, 500, 502, 503, 504]) {
    assert.equal(delivery.classifyReaderHttpStatus(status), 'retry');
  }
  for (const status of [400, 401, 409, 422]) {
    assert.equal(delivery.classifyReaderHttpStatus(status), 'failed');
  }
  assert.equal(delivery.classifyReaderHttpStatus(200), 'delivered');
});

test('migration enforces purchase/outbox idempotency and server-only access', () => {
  const sql = fs.readFileSync(new URL('../../database/migrations/005_reader_coins_delivery.sql', import.meta.url), 'utf8');
  assert.match(sql, /provider_payment_id text unique/i);
  assert.match(sql, /purchase_id uuid not null unique references public\.commerce_purchases/i);
  assert.match(sql, /event_id uuid primary key/i);
  assert.match(sql, /enable row level security/i);
  assert.match(sql, /revoke all on table public\.reader_coin_outbox from anon, authenticated/i);
  const deliverySource = fs.readFileSync(new URL('../src/services/readerCoinDelivery.ts', import.meta.url), 'utf8');
  assert.match(deliverySource, /for update skip locked/i);
});

test('successful payment code keeps Platinum credit and outbox creation in one transaction', () => {
  const source = fs.readFileSync(new URL('../src/services/commerceService.ts', import.meta.url), 'utf8');
  const start = source.indexOf('export async function finalizeSuccessfulStarsPayment');
  const finish = source.indexOf('export async function getPurchaseForPlayer');
  const body = source.slice(start, finish);
  assert.match(body, /return inTransaction/);
  assert.match(body, /update platinum_wallets/);
  assert.match(body, /insert into platinum_ledger/);
  assert.match(body, /insert into reader_coin_outbox/);
});
