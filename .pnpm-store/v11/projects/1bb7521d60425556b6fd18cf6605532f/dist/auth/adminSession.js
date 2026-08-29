import crypto from 'node:crypto';
import { config } from '../config.js';
import { HttpError } from '../utils/http.js';
function b64(input) {
    return Buffer.from(input).toString('base64url');
}
export function signAdminSession() {
    const payload = {
        role: 'admin',
        exp: Math.floor(Date.now() / 1000) + 60 * 60 * 12
    };
    const body = b64(JSON.stringify(payload));
    const sig = crypto.createHmac('sha256', config.SESSION_SECRET).update(`admin.${body}`).digest('base64url');
    return `admin.${body}.${sig}`;
}
export function verifyAdminSession(token) {
    const [prefix, body, sig] = token.split('.');
    if (prefix !== 'admin' || !body || !sig)
        throw new HttpError(401, 'invalid_admin_session', 'Invalid admin session');
    const expected = crypto.createHmac('sha256', config.SESSION_SECRET).update(`admin.${body}`).digest('base64url');
    const a = Buffer.from(sig);
    const b = Buffer.from(expected);
    if (a.length !== b.length || !crypto.timingSafeEqual(a, b))
        throw new HttpError(401, 'invalid_admin_session', 'Invalid admin session');
    const payload = JSON.parse(Buffer.from(body, 'base64url').toString('utf8'));
    if (payload.role !== 'admin' || payload.exp < Math.floor(Date.now() / 1000))
        throw new HttpError(401, 'admin_session_expired', 'Admin session expired');
    return payload;
}
