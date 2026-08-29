import type { NextFunction, Request, Response } from 'express';
import { verifySession } from './session.js';
import { HttpError } from '../utils/http.js';

declare global {
  namespace Express {
    interface Request {
      auth?: { playerId: string; telegramUserId: number };
    }
  }
}

export function requireAuth(req: Request, _res: Response, next: NextFunction) {
  try {
    const header = req.header('authorization');
    if (!header?.startsWith('Bearer ')) throw new HttpError(401, 'auth_required', 'Authorization required');
    req.auth = verifySession(header.slice(7));
    next();
  } catch (error) {
    next(error);
  }
}
