import crypto from 'node:crypto';
import { config } from '../config.js';
import { HttpError } from '../utils/http.js';

interface Payload {
  playerId: string;
  telegramUserId: number;
  exp: number;
}

function b64(input: string | Buffer): string {
  return Buffer.from(input).toString('base64url');
}

export function signSession(playerId: string, telegramUserId: number): string {
  const payload: Payload = {
    playerId,
    telegramUserId,
    exp: Math.floor(Date.now() / 1000) + 60 * 60 * 24 * 7
  };
  const body = b64(JSON.stringify(payload));
  const sig = crypto.createHmac('sha256', config.SESSION_SECRET).update(body).digest('base64url');
  return `${body}.${sig}`;
}

export function verifySession(token: string): Payload {
  const [body, sig] = token.split('.');
  if (!body || !sig) throw new HttpError(401, 'invalid_session', 'Invalid session');
  const expected = crypto.createHmac('sha256', config.SESSION_SECRET).update(body).digest('base64url');
  const a = Buffer.from(sig);
  const b = Buffer.from(expected);
  if (a.length !== b.length || !crypto.timingSafeEqual(a, b)) {
    throw new HttpError(401, 'invalid_session', 'Invalid session');
  }
  const payload = JSON.parse(Buffer.from(body, 'base64url').toString('utf8')) as Payload;
  if (payload.exp < Math.floor(Date.now() / 1000)) throw new HttpError(401, 'session_expired', 'Session expired');
  return payload;
}
