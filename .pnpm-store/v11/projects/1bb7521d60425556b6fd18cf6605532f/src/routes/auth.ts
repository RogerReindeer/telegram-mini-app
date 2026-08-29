import { Router } from 'express';
import { z } from 'zod';
import { config } from '../config.js';
import { verifyTelegramInitData } from '../auth/telegram.js';
import { signSession } from '../auth/session.js';
import { getOrCreatePlayer } from '../services/gameService.js';
import { asyncRoute, HttpError } from '../utils/http.js';

export const authRouter = Router();

const telegramBody = z.object({ initData: z.string().min(1) });

authRouter.post('/telegram', asyncRoute(async (req, res) => {
  const { initData } = telegramBody.parse(req.body);
  const tg = verifyTelegramInitData(initData);
  const player = await getOrCreatePlayer(tg.id, tg.username);
  res.json({ token: signSession(player.id, tg.id) });
}));

authRouter.post('/dev', asyncRoute(async (_req, res) => {
  if (config.NODE_ENV === 'production') throw new HttpError(404, 'not_found', 'Not found');
  const player = await getOrCreatePlayer(config.DEV_TELEGRAM_USER_ID, config.DEV_TELEGRAM_USERNAME);
  res.json({ token: signSession(player.id, config.DEV_TELEGRAM_USER_ID), dev: true });
}));
