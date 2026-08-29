import crypto from 'node:crypto';
import { z } from 'zod';
import { config } from '../config.js';
import { HttpError } from '../utils/http.js';
const telegramUserSchema = z.object({ id: z.number().int().positive(), username: z.string().max(64).optional(), first_name: z.string().max(128).optional() });
export function verifyTelegramInitData(initData) {
    const params = new URLSearchParams(initData);
    const hash = params.get('hash');
    if (!hash)
        throw new HttpError(401, 'telegram_hash_missing', 'Telegram hash missing');
    params.delete('hash');
    const dataCheckString = [...params.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([key, value]) => `${key}=${value}`).join('\n');
    const secretKey = crypto.createHmac('sha256', 'WebAppData').update(config.BOT_TOKEN).digest();
    const expected = crypto.createHmac('sha256', secretKey).update(dataCheckString).digest('hex');
    const a = Buffer.from(hash, 'hex');
    const b = Buffer.from(expected, 'hex');
    if (a.length !== b.length || !crypto.timingSafeEqual(a, b))
        throw new HttpError(401, 'telegram_signature_invalid', 'Telegram initData signature is invalid');
    const authDate = Number(params.get('auth_date') ?? '0');
    const now = Math.floor(Date.now() / 1000);
    if (!Number.isFinite(authDate) || authDate <= 0 || authDate > now + 60 || now - authDate > 60 * 60 * 24)
        throw new HttpError(401, 'telegram_init_data_expired', 'Telegram initData is too old');
    const rawUser = params.get('user');
    if (!rawUser)
        throw new HttpError(401, 'telegram_user_missing', 'Telegram user missing');
    try {
        return telegramUserSchema.parse(JSON.parse(rawUser));
    }
    catch {
        throw new HttpError(401, 'telegram_user_invalid', 'Telegram user data is invalid');
    }
}
