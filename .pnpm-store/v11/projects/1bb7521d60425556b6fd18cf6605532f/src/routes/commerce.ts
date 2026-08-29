import crypto from 'node:crypto';
import { Router } from 'express';
import { z } from 'zod';
import { requireAuth } from '../auth/middleware.js';
import { config } from '../config.js';
import {
  createCurrencyBundleInvoice,
  finalizeSuccessfulStarsPayment,
  getPlatinumWallet,
  getPurchaseForPlayer,
  listActiveCurrencyBundles,
  validateStarsPreCheckout
} from '../services/commerceService.js';
import { answerStarsPreCheckout } from '../services/telegramBotApi.js';
import { asyncRoute, HttpError } from '../utils/http.js';

export const commerceRouter = Router();

function safeSecretEqual(left: string, right: string): boolean {
  const leftHash = crypto.createHash('sha256').update(left).digest();
  const rightHash = crypto.createHash('sha256').update(right).digest();
  return crypto.timingSafeEqual(leftHash, rightHash);
}

const preCheckoutSchema = z.object({
  id: z.string().min(1),
  from: z.object({ id: z.number().int().positive() }),
  currency: z.string(),
  total_amount: z.number().int().positive(),
  invoice_payload: z.string().min(1).max(128)
});

const successfulPaymentSchema = z.object({
  from: z.object({ id: z.number().int().positive() }).optional(),
  successful_payment: z.object({
    currency: z.string(),
    total_amount: z.number().int().positive(),
    invoice_payload: z.string().min(1).max(128),
    telegram_payment_charge_id: z.string().min(1).max(256)
  }).optional()
}).passthrough();

const telegramUpdateSchema = z.object({
  update_id: z.number().int(),
  pre_checkout_query: preCheckoutSchema.optional(),
  message: successfulPaymentSchema.optional()
}).passthrough();

commerceRouter.post('/telegram/webhook', asyncRoute(async (req, res) => {
  if (!config.STARS_PAYMENTS_ENABLED || !config.TELEGRAM_WEBHOOK_SECRET) {
    throw new HttpError(503, 'stars_payments_disabled', 'Telegram Stars payments are disabled');
  }
  const providedSecret = req.header('x-telegram-bot-api-secret-token') ?? '';
  if (!providedSecret || !safeSecretEqual(providedSecret, config.TELEGRAM_WEBHOOK_SECRET)) {
    throw new HttpError(401, 'telegram_webhook_unauthorized', 'Invalid Telegram webhook secret');
  }

  const update = telegramUpdateSchema.parse(req.body);
  if (update.pre_checkout_query) {
    const query = update.pre_checkout_query;
    let decision: { ok: boolean; error?: string };
    try {
      decision = await validateStarsPreCheckout({
        id: query.id,
        telegramUserId: query.from.id,
        currency: query.currency,
        totalAmount: query.total_amount,
        invoicePayload: query.invoice_payload
      });
    } catch {
      decision = { ok: false, error: 'Не удалось проверить заказ. Попробуйте создать его заново.' };
    }
    await answerStarsPreCheckout(query.id, decision.ok, decision.error);
    res.json({ ok: true, handled: 'pre_checkout_query', accepted: decision.ok });
    return;
  }

  if (update.message?.successful_payment && update.message.from) {
    const payment = update.message.successful_payment;
    const result = await finalizeSuccessfulStarsPayment({
      telegramUserId: update.message.from.id,
      currency: payment.currency,
      totalAmount: payment.total_amount,
      invoicePayload: payment.invoice_payload,
      telegramPaymentChargeId: payment.telegram_payment_charge_id
    });
    res.json({ ok: true, handled: 'successful_payment', purchaseId: result.purchaseId, duplicate: result.duplicate });
    return;
  }

  res.json({ ok: true, handled: 'ignored' });
}));

commerceRouter.use(requireAuth);

commerceRouter.get('/products', asyncRoute(async (_req, res) => {
  res.json({ products: await listActiveCurrencyBundles() });
}));

commerceRouter.get('/wallet', asyncRoute(async (req, res) => {
  res.json(await getPlatinumWallet(req.auth!.playerId));
}));

commerceRouter.post('/stars/invoice-link', asyncRoute(async (req, res) => {
  const body = z.object({ productCode: z.string().min(1).max(120) }).strict().parse(req.body);
  res.json(await createCurrencyBundleInvoice(req.auth!.playerId, req.auth!.telegramUserId, body.productCode));
}));

commerceRouter.get('/purchases/:purchaseId', asyncRoute(async (req, res) => {
  const params = z.object({ purchaseId: z.string().uuid() }).parse(req.params);
  res.json(await getPurchaseForPlayer(req.auth!.playerId, params.purchaseId));
}));
