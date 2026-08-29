import crypto from 'node:crypto';
import { Router } from 'express';
import { z } from 'zod';
import { config } from '../config.js';
import { signAdminSession } from '../auth/adminSession.js';
import { requireAdmin } from '../auth/adminMiddleware.js';
import { asyncRoute, HttpError } from '../utils/http.js';
import { getAdminOverview, getAdminPlayer, searchAdminPlayers, updateAdminInventory, updateAdminLife, updateAdminSkill } from '../services/adminService.js';
export const adminRouter = Router();
const attempts = new Map();
const WINDOW_MS = 15 * 60_000;
const BLOCK_MS = 15 * 60_000;
const MAX_ATTEMPTS = 5;
function safeEqual(a, b) {
    const ah = crypto.createHash('sha256').update(a).digest();
    const bh = crypto.createHash('sha256').update(b).digest();
    return crypto.timingSafeEqual(ah, bh);
}
adminRouter.post('/login', asyncRoute(async (req, res) => {
    const adminPassword = config.ADMIN_PASSWORD;
    if (!adminPassword)
        throw new HttpError(503, 'admin_not_configured', 'Admin password is not configured');
    const key = req.ip || req.socket.remoteAddress || 'unknown';
    const now = Date.now();
    let attempt = attempts.get(key) ?? { count: 0, windowStart: now, blockedUntil: 0 };
    if (attempt.blockedUntil > now)
        throw new HttpError(429, 'admin_login_blocked', 'Too many login attempts');
    if (now - attempt.windowStart > WINDOW_MS)
        attempt = { count: 0, windowStart: now, blockedUntil: 0 };
    const { password } = z.object({ password: z.string().min(1).max(256) }).parse(req.body);
    if (!safeEqual(password, adminPassword)) {
        attempt.count += 1;
        if (attempt.count >= MAX_ATTEMPTS)
            attempt.blockedUntil = now + BLOCK_MS;
        attempts.set(key, attempt);
        throw new HttpError(401, 'admin_login_failed', 'Invalid credentials');
    }
    attempts.delete(key);
    res.json({ token: signAdminSession() });
}));
adminRouter.use(requireAdmin);
adminRouter.get('/overview', asyncRoute(async (_req, res) => { res.json(await getAdminOverview()); }));
adminRouter.get('/players', asyncRoute(async (req, res) => {
    const query = z.object({ search: z.string().optional().default(''), limit: z.coerce.number().int().min(1).max(100).optional().default(50) }).parse(req.query);
    res.json({ players: await searchAdminPlayers(query.search, query.limit) });
}));
adminRouter.get('/players/:playerId', asyncRoute(async (req, res) => {
    const { playerId } = z.object({ playerId: z.string().uuid() }).parse(req.params);
    res.json(await getAdminPlayer(playerId));
}));
adminRouter.patch('/lives/:lifeId', asyncRoute(async (req, res) => {
    const { lifeId } = z.object({ lifeId: z.string().uuid() }).parse(req.params);
    const body = z.object({
        health: z.number().int().min(0).optional(),
        maxHealth: z.number().int().min(1).max(100000).optional(),
        money: z.number().int().min(0).max(1000000000).optional(),
        currentWorldDay: z.number().int().min(0).max(10000000).optional()
    }).strict().refine((v) => Object.keys(v).length > 0, 'Empty patch').parse(req.body);
    res.json(await updateAdminLife(lifeId, body));
}));
adminRouter.put('/lives/:lifeId/skills/:skillId', asyncRoute(async (req, res) => {
    const { lifeId, skillId } = z.object({ lifeId: z.string().uuid(), skillId: z.enum(['blacksmithing', 'herbalism', 'tracking', 'trade']) }).parse(req.params);
    const { level } = z.object({ level: z.number().int().min(0).max(3) }).parse(req.body);
    res.json(await updateAdminSkill(lifeId, skillId, level));
}));
adminRouter.put('/lives/:lifeId/inventory/:itemId', asyncRoute(async (req, res) => {
    const { lifeId, itemId } = z.object({ lifeId: z.string().uuid(), itemId: z.string().min(1).max(120) }).parse(req.params);
    const { quantity } = z.object({ quantity: z.number().int().min(0).max(9999) }).parse(req.body);
    res.json(await updateAdminInventory(lifeId, itemId, quantity));
}));
