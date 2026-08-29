import crypto from 'node:crypto';
import { config } from '../config.js';
import { inTransaction, pool, type DbClient } from '../db.js';
import { HttpError } from '../utils/http.js';
import { createStarsInvoiceLink } from './telegramBotApi.js';

export type CommerceProduct = {
  productCode: string;
  title: string;
  description: string;
  starsPaid: number;
  platinumGrant: number;
  readerCoinsGrant: number;
};

type PurchaseRow = {
  purchase_id: string;
  player_id: string;
  telegram_user_id: string | number;
  provider_payment_id: string | null;
  invoice_payload: string;
  product_code: string;
  stars_paid: number;
  platinum_grant: number;
  reader_coins_grant: number;
  payment_status: string;
  paid_at: Date | string | null;
};

export type StarsPreCheckout = {
  id: string;
  telegramUserId: number;
  currency: string;
  totalAmount: number;
  invoicePayload: string;
};

export type SuccessfulStarsPayment = {
  telegramUserId: number;
  currency: string;
  totalAmount: number;
  invoicePayload: string;
  telegramPaymentChargeId: string;
};

function productFromRow(row: Record<string, unknown>): CommerceProduct {
  return {
    productCode: String(row.product_code),
    title: String(row.title),
    description: String(row.description),
    starsPaid: Number(row.stars_paid),
    platinumGrant: Number(row.platinum_grant),
    readerCoinsGrant: Number(row.reader_coins_grant)
  };
}

export async function listActiveCurrencyBundles(): Promise<CommerceProduct[]> {
  const result = await pool.query(`
    select product_code,title,description,stars_paid,platinum_grant,reader_coins_grant
    from commerce_products
    where is_active=true
    order by sort_order,product_code
  `);
  return result.rows.map(productFromRow);
}

export async function getPlatinumWallet(playerId: string) {
  const result = await pool.query(`
    select balance,lifetime_credited,lifetime_spent,updated_at
    from platinum_wallets where player_id=$1
  `, [playerId]);
  const row = result.rows[0];
  return row ? {
    balance: Number(row.balance),
    lifetimeCredited: Number(row.lifetime_credited),
    lifetimeSpent: Number(row.lifetime_spent),
    updatedAt: row.updated_at
  } : { balance: 0, lifetimeCredited: 0, lifetimeSpent: 0, updatedAt: null };
}

async function createPurchaseSnapshot(
  playerId: string,
  telegramUserId: number,
  productCode: string
): Promise<{ purchase: PurchaseRow; product: CommerceProduct }> {
  return inTransaction(async (client) => {
    const productResult = await client.query(`
      select product_code,title,description,stars_paid,platinum_grant,reader_coins_grant
      from commerce_products
      where product_code=$1 and is_active=true
      for share
    `, [productCode]);
    const productRow = productResult.rows[0];
    if (!productRow) throw new HttpError(404, 'commerce_product_not_found', 'Currency package is unavailable');
    const product = productFromRow(productRow);
    if (product.starsPaid <= 0) throw new HttpError(409, 'commerce_product_not_priced', 'Currency package has no Stars price');

    const purchaseId = crypto.randomUUID();
    const invoicePayload = `qinghe:${purchaseId}`;
    const purchaseResult = await client.query(`
      insert into commerce_purchases (
        purchase_id,player_id,telegram_user_id,invoice_payload,product_code,
        stars_paid,platinum_grant,reader_coins_grant,payment_status
      ) values ($1,$2,$3,$4,$5,$6,$7,$8,'created')
      returning *
    `, [
      purchaseId,
      playerId,
      telegramUserId,
      invoicePayload,
      product.productCode,
      product.starsPaid,
      product.platinumGrant,
      product.readerCoinsGrant
    ]);
    return { purchase: purchaseResult.rows[0] as PurchaseRow, product };
  });
}

export async function createCurrencyBundleInvoice(
  playerId: string,
  telegramUserId: number,
  productCode: string
) {
  if (!config.STARS_PAYMENTS_ENABLED) {
    throw new HttpError(503, 'stars_payments_disabled', 'Telegram Stars payments are disabled');
  }
  const { purchase, product } = await createPurchaseSnapshot(playerId, telegramUserId, productCode);
  try {
    const invoiceUrl = await createStarsInvoiceLink({
      title: product.title,
      description: product.description,
      invoicePayload: purchase.invoice_payload,
      stars: product.starsPaid
    });
    await pool.query(`
      update commerce_purchases
      set payment_status='invoice_created',updated_at=now()
      where purchase_id=$1 and payment_status='created'
    `, [purchase.purchase_id]);
    return {
      purchaseId: purchase.purchase_id,
      invoiceUrl,
      product
    };
  } catch (error) {
    await pool.query(`
      update commerce_purchases
      set payment_status='invoice_failed',updated_at=now()
      where purchase_id=$1 and payment_status='created'
    `, [purchase.purchase_id]).catch(() => undefined);
    throw error;
  }
}

export async function validateStarsPreCheckout(input: StarsPreCheckout): Promise<{ ok: boolean; error?: string }> {
  if (!config.STARS_PAYMENTS_ENABLED) return { ok: false, error: 'Покупки временно отключены.' };
  const result = await pool.query(`select * from commerce_purchases where invoice_payload=$1`, [input.invoicePayload]);
  const purchase = result.rows[0] as PurchaseRow | undefined;
  if (!purchase) return { ok: false, error: 'Заказ не найден.' };
  if (!['created', 'invoice_created'].includes(purchase.payment_status)) {
    return { ok: false, error: 'Этот заказ уже обработан.' };
  }
  if (Number(purchase.telegram_user_id) !== input.telegramUserId) return { ok: false, error: 'Заказ принадлежит другому пользователю.' };
  if (input.currency !== 'XTR' || input.totalAmount !== Number(purchase.stars_paid)) {
    return { ok: false, error: 'Стоимость заказа изменилась. Создайте заказ заново.' };
  }
  return { ok: true };
}

async function walletForUpdate(client: DbClient, playerId: string): Promise<number> {
  await client.query(`
    insert into platinum_wallets(player_id,balance,lifetime_credited,lifetime_spent)
    values($1,0,0,0)
    on conflict(player_id) do nothing
  `, [playerId]);
  const result = await client.query(`select balance from platinum_wallets where player_id=$1 for update`, [playerId]);
  return Number(result.rows[0]?.balance ?? 0);
}

export async function finalizeSuccessfulStarsPayment(input: SuccessfulStarsPayment) {
  return inTransaction(async (client) => {
    const purchaseResult = await client.query(`
      select * from commerce_purchases where invoice_payload=$1 for update
    `, [input.invoicePayload]);
    const purchase = purchaseResult.rows[0] as PurchaseRow | undefined;
    if (!purchase) throw new HttpError(409, 'stars_purchase_missing', 'Payment purchase was not found');

    if (purchase.payment_status === 'paid') {
      if (purchase.provider_payment_id !== input.telegramPaymentChargeId) {
        throw new HttpError(409, 'stars_purchase_conflict', 'Purchase already has another payment reference');
      }
      const outbox = await client.query(`select event_id,status from reader_coin_outbox where purchase_id=$1`, [purchase.purchase_id]);
      return { purchaseId: purchase.purchase_id, duplicate: true, outbox: outbox.rows[0] ?? null };
    }

    if (!['created', 'invoice_created'].includes(purchase.payment_status)) {
      throw new HttpError(409, 'stars_purchase_state_conflict', 'Purchase is not payable');
    }
    if (Number(purchase.telegram_user_id) !== input.telegramUserId) {
      throw new HttpError(409, 'stars_user_conflict', 'Payment user does not match purchase');
    }
    if (input.currency !== 'XTR' || input.totalAmount !== Number(purchase.stars_paid)) {
      throw new HttpError(409, 'stars_amount_conflict', 'Payment amount does not match purchase snapshot');
    }

    const reusedPayment = await client.query(`
      select purchase_id from commerce_purchases where provider_payment_id=$1 and purchase_id<>$2
    `, [input.telegramPaymentChargeId, purchase.purchase_id]);
    if (reusedPayment.rows[0]) throw new HttpError(409, 'stars_payment_reused', 'Payment reference was already used');

    const balanceBefore = await walletForUpdate(client, purchase.player_id);
    const balanceAfter = balanceBefore + Number(purchase.platinum_grant);

    await client.query(`
      update platinum_wallets
      set balance=$2,lifetime_credited=lifetime_credited+$3,updated_at=now()
      where player_id=$1
    `, [purchase.player_id, balanceAfter, purchase.platinum_grant]);

    await client.query(`
      insert into platinum_ledger (
        player_id,purchase_id,operation,amount,balance_before,balance_after,idempotency_key,metadata
      ) values ($1,$2,'stars_purchase_credit',$3,$4,$5,$6,$7)
    `, [
      purchase.player_id,
      purchase.purchase_id,
      purchase.platinum_grant,
      balanceBefore,
      balanceAfter,
      `telegram-stars:${input.telegramPaymentChargeId}`,
      JSON.stringify({ productCode: purchase.product_code })
    ]);

    const paidAt = new Date();
    await client.query(`
      update commerce_purchases
      set provider_payment_id=$2,payment_status='paid',paid_at=$3,updated_at=now()
      where purchase_id=$1
    `, [purchase.purchase_id, input.telegramPaymentChargeId, paidAt]);

    const eventId = crypto.randomUUID();
    const payload = {
      schema_version: 1,
      event_id: eventId,
      purchase_id: purchase.purchase_id,
      telegram_user_id: Number(purchase.telegram_user_id),
      product_code: purchase.product_code,
      amount: Number(purchase.reader_coins_grant),
      currency: 'reader_coins',
      provider: 'telegram_stars',
      occurred_at: paidAt.toISOString()
    };
    await client.query(`
      insert into reader_coin_outbox(event_id,purchase_id,event_type,status,payload,next_attempt_at)
      values($1,$2,'reader_coin_grant','pending',$3,now())
    `, [eventId, purchase.purchase_id, JSON.stringify(payload)]);

    return {
      purchaseId: purchase.purchase_id,
      duplicate: false,
      platinumCredited: Number(purchase.platinum_grant),
      platinumBalance: balanceAfter,
      outbox: { event_id: eventId, status: 'pending' }
    };
  });
}

export async function getPurchaseForPlayer(playerId: string, purchaseId: string) {
  const result = await pool.query(`
    select p.purchase_id,p.product_code,p.stars_paid,p.platinum_grant,p.reader_coins_grant,
      p.payment_status,p.paid_at,p.created_at,o.event_id,o.status as reader_delivery_status,
      o.attempt_count,o.last_error_code,o.delivered_at
    from commerce_purchases p
    left join reader_coin_outbox o on o.purchase_id=p.purchase_id
    where p.purchase_id=$1 and p.player_id=$2
  `, [purchaseId, playerId]);
  if (!result.rows[0]) throw new HttpError(404, 'purchase_not_found', 'Purchase not found');
  return result.rows[0];
}

