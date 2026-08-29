import crypto from 'node:crypto';
import { config } from '../config.js';
import { inTransaction, pool } from '../db.js';
import { HttpError } from '../utils/http.js';

export type ReaderCoinGrantPayload = {
  schema_version: 1;
  event_id: string;
  purchase_id: string;
  telegram_user_id: number;
  product_code: string;
  amount: number;
  currency: 'reader_coins';
  provider: 'telegram_stars';
  occurred_at: string;
};

type OutboxRow = {
  event_id: string;
  purchase_id: string;
  payload: ReaderCoinGrantPayload;
  attempt_count: number | string;
};

export type ReaderDeliveryDisposition = 'delivered' | 'retry' | 'failed';

export function retryDelaySeconds(attemptCount: number): number {
  const schedule = [30, 120, 600, 1800, 7200, 21600];
  return schedule[Math.max(0, attemptCount - 1)] ?? 43200;
}

export function classifyReaderHttpStatus(status: number): ReaderDeliveryDisposition {
  if (status >= 200 && status < 300) return 'delivered';
  if (status === 429 || [500, 502, 503, 504].includes(status)) return 'retry';
  return 'failed';
}

export function signReaderBody(input: {
  timestamp: string;
  nonce: string;
  body: Buffer;
  secret: string;
}): string {
  const bodyHash = crypto.createHash('sha256').update(input.body).digest('hex');
  const signingString = `${input.timestamp}.${input.nonce}.${bodyHash}`;
  return crypto.createHmac('sha256', input.secret).update(signingString).digest('hex');
}

export function buildSignedReaderRequest(
  payload: ReaderCoinGrantPayload,
  options?: { nowSeconds?: number; nonce?: string; secret?: string; serviceId?: string }
) {
  const timestamp = String(options?.nowSeconds ?? Math.floor(Date.now() / 1000));
  const nonce = options?.nonce ?? crypto.randomUUID();
  const secret = options?.secret ?? config.READER_COMMERCE_SHARED_SECRET ?? '';
  const serviceId = options?.serviceId ?? config.READER_COMMERCE_SERVICE_ID;
  const body = Buffer.from(JSON.stringify(payload), 'utf8');
  const signature = signReaderBody({ timestamp, nonce, body, secret });
  return {
    body,
    headers: {
      'content-type': 'application/json',
      'x-service-id': serviceId,
      'x-timestamp': timestamp,
      'x-nonce': nonce,
      'x-signature': signature
    }
  };
}

function validReaderSuccess(data: unknown, event: OutboxRow): boolean {
  if (!data || typeof data !== 'object') return false;
  const value = data as Record<string, unknown>;
  return value.status === 'completed'
    && value.event_id === event.event_id
    && value.purchase_id === event.purchase_id
    && typeof value.duplicate === 'boolean'
    && Number.isInteger(value.credited)
    && Number.isInteger(value.balance);
}

export async function claimReaderCoinEvent(): Promise<OutboxRow | null> {
  return inTransaction(async (client) => {
    const result = await client.query(`
      with candidate as (
        select event_id
        from reader_coin_outbox
        where (
          (status='pending' and next_attempt_at <= now())
          or (
            status='processing'
            and last_attempt_at < now() - ($1::int * interval '1 second')
          )
        )
        order by next_attempt_at,created_at
        limit 1
        for update skip locked
      )
      update reader_coin_outbox o
      set status='processing',
          attempt_count=o.attempt_count+1,
          last_attempt_at=now(),
          updated_at=now(),
          last_error_code=null
      from candidate c
      where o.event_id=c.event_id
      returning o.event_id,o.purchase_id,o.payload,o.attempt_count
    `, [config.READER_COMMERCE_PROCESSING_TIMEOUT_SECONDS]);
    return (result.rows[0] as OutboxRow | undefined) ?? null;
  });
}

async function markDelivered(event: OutboxRow): Promise<void> {
  await pool.query(`
    update reader_coin_outbox
    set status='delivered',delivered_at=now(),last_error_code=null,updated_at=now()
    where event_id=$1 and status='processing'
  `, [event.event_id]);
}

async function markRetry(event: OutboxRow, errorCode: string): Promise<void> {
  const delaySeconds = retryDelaySeconds(Number(event.attempt_count));
  await pool.query(`
    update reader_coin_outbox
    set status='pending',
        next_attempt_at=now()+($2::int * interval '1 second'),
        last_error_code=$3,
        updated_at=now()
    where event_id=$1 and status='processing'
  `, [event.event_id, delaySeconds, errorCode.slice(0, 120)]);
}

async function markFailed(event: OutboxRow, errorCode: string): Promise<void> {
  await pool.query(`
    update reader_coin_outbox
    set status='failed',last_error_code=$2,updated_at=now()
    where event_id=$1 and status='processing'
  `, [event.event_id, errorCode.slice(0, 120)]);
}

export async function deliverReaderCoinEvent(
  event: OutboxRow,
  fetchImpl: typeof fetch = fetch
): Promise<ReaderDeliveryDisposition> {
  if (!config.READER_COMMERCE_ENABLED || !config.READER_API_URL || !config.READER_COMMERCE_SHARED_SECRET) {
    await markRetry(event, 'reader_commerce_not_configured');
    return 'retry';
  }

  const { body, headers } = buildSignedReaderRequest(event.payload);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), config.READER_COMMERCE_TIMEOUT_SECONDS * 1000);
  try {
    const endpoint = new URL('/api/internal/commerce/coin-grants', config.READER_API_URL);
    const response = await fetchImpl(endpoint, {
      method: 'POST',
      headers,
      body,
      signal: controller.signal
    });
    const disposition = classifyReaderHttpStatus(response.status);
    if (disposition === 'delivered') {
      const data = await response.json().catch(() => null);
      if (!validReaderSuccess(data, event)) {
        await markFailed(event, 'invalid_reader_success_response');
        return 'failed';
      }
      await markDelivered(event);
      return 'delivered';
    }
    if (disposition === 'retry') {
      await markRetry(event, `reader_http_${response.status}`);
      return 'retry';
    }
    await markFailed(event, `reader_http_${response.status}`);
    return 'failed';
  } catch (error) {
    const code = error instanceof Error && error.name === 'AbortError'
      ? 'reader_timeout'
      : 'reader_network_error';
    await markRetry(event, code);
    return 'retry';
  } finally {
    clearTimeout(timeout);
  }
}

export async function processReaderCoinOutboxBatch(limit = config.READER_COMMERCE_BATCH_SIZE) {
  const summary = { claimed: 0, delivered: 0, retry: 0, failed: 0 };
  for (let index = 0; index < Math.max(1, limit); index += 1) {
    const event = await claimReaderCoinEvent();
    if (!event) break;
    summary.claimed += 1;
    const disposition = await deliverReaderCoinEvent(event);
    summary[disposition] += 1;
  }
  return summary;
}

export async function retryFailedReaderCoinEvent(eventId: string) {
  const result = await pool.query(`
    update reader_coin_outbox
    set status='pending',next_attempt_at=now(),last_error_code=null,updated_at=now()
    where event_id=$1 and status='failed'
    returning event_id,purchase_id,status
  `, [eventId]);
  if (!result.rows[0]) throw new HttpError(404, 'reader_delivery_not_retryable', 'Failed delivery event not found');
  return result.rows[0];
}

export async function getReaderDeliveryOverview() {
  const result = await pool.query(`
    select status,count(*)::int as count,min(created_at) as oldest_created_at
    from reader_coin_outbox
    group by status
    order by status
  `);
  return { statuses: result.rows };
}

