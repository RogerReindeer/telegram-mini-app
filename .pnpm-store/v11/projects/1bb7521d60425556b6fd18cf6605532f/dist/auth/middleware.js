import { verifySession } from './session.js';
import { HttpError } from '../utils/http.js';
export function requireAuth(req, _res, next) {
    try {
        const header = req.header('authorization');
        if (!header?.startsWith('Bearer '))
            throw new HttpError(401, 'auth_required', 'Authorization required');
        req.auth = verifySession(header.slice(7));
        next();
    }
    catch (error) {
        next(error);
    }
}
