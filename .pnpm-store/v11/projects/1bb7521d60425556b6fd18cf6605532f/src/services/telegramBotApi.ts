import { config } from '../config.js';
import { HttpError } from '../utils/http.js';

type TelegramEnvelope<T> = {
  ok: boolean;
  result?: T;
  error_code?: number;
  description?: string;
};

async function telegramRequest<T>(method: string, payload: Record<string, unknown>): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 8_000);
  try {
    const response = await fetch(`https://api.telegram.org/bot${config.BOT_TOKEN}/${method}`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(payload),
      signal: controller.signal
    });
    const data = await response.json().catch(() => null) as TelegramEnvelope<T> | null;
    if (!response.ok || !data?.ok || data.result === undefined) {
      throw new HttpError(
        502,
        'telegram_api_error',
        'Telegram Bot API request failed',
        { method, status: response.status, telegramErrorCode: data?.error_code }
      );
    }
    return data.result;
  } catch (error) {
    if (error instanceof HttpError) throw error;
    throw new HttpError(502, 'telegram_api_unavailable', 'Telegram Bot API is unavailable');
  } finally {
    clearTimeout(timeout);
  }
}

export async function createStarsInvoiceLink(input: {
  title: string;
  description: string;
  invoicePayload: string;
  stars: number;
}): Promise<string> {
  // provider_token must be omitted for Telegram Stars invoices.
  return telegramRequest<string>('createInvoiceLink', {
    title: input.title.slice(0, 32),
    description: input.description.slice(0, 255),
    payload: input.invoicePayload,
    currency: 'XTR',
    prices: [{ label: input.title.slice(0, 32), amount: input.stars }]
  });
}

export async function answerStarsPreCheckout(
  preCheckoutQueryId: string,
  ok: boolean,
  errorMessage?: string
): Promise<void> {
  await telegramRequest<boolean>('answerPreCheckoutQuery', {
    pre_checkout_query_id: preCheckoutQueryId,
    ok,
    ...(ok ? {} : { error_message: errorMessage || 'Покупка сейчас недоступна. Попробуйте ещё раз.' })
  });
}

