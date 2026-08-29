import type { NextFunction, Request, Response } from 'express';
import { verifyAdminSession } from './adminSession.js';
import { HttpError } from '../utils/http.js';

export function requireAdmin(req: Request, _res: Response, next: NextFunction) {
  const header = req.headers.authorization;
  if (!header?.startsWith('Bearer ')) return next(new HttpError(401, 'admin_auth_required', 'Admin authentication required'));
  try {
    verifyAdminSession(header.slice(7));
    next();
  } catch (error) {
    next(error);
  }
}
