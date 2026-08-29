import express from 'express';
import cors from 'cors';
import { ZodError } from 'zod';
import { config } from './config.js';
import { pool } from './db.js';
import { authRouter } from './routes/auth.js';
import { gameRouter } from './routes/game.js';
import { adminRouter } from './routes/admin.js';
import { HttpError } from './utils/http.js';
const app = express();
app.set('trust proxy', 1);
app.disable('x-powered-by');
app.use(cors({ origin: config.FRONTEND_ORIGIN, credentials: false, methods: ['GET', 'POST', 'PUT', 'PATCH', 'OPTIONS'], allowedHeaders: ['content-type', 'authorization'] }));
app.use((_req, res, next) => { res.setHeader('X-Content-Type-Options', 'nosniff'); res.setHeader('Referrer-Policy', 'no-referrer'); res.setHeader('Cache-Control', 'no-store'); next(); });
app.use(express.json({ limit: '64kb' }));
app.get('/health', (_req, res) => res.json({ status: 'ok' }));
app.get('/ready', async (_req, res) => {
    try {
        await pool.query(`select 1 from world_clock where id=1`);
        await pool.query(`select 1 from life_item_instances limit 1`);
        await pool.query(`select interrupt_policy from open_life_activities limit 1`);
        await pool.query(`select open_life_world_time_normalized from lives limit 1`);
        await pool.query(`select title,details,world_day from open_life_notices limit 1`);
        res.json({ status: 'ok', database: 'ok', open_life_schema: 'ok', materiality_schema: 'ok', open_life_ux_schema: 'ok' });
    }
    catch {
        res.status(503).json({ status: 'degraded', database: 'error' });
    }
});
app.get('/version', (_req, res) => res.json({ app: 'qinghe-api', version: '0.3.1', release: 'openlife-ux-r4', content_version: config.CONTENT_VERSION }));
app.use('/api/auth', authRouter);
app.use('/api/game', gameRouter);
app.use('/api/admin', adminRouter);
app.use((error, _req, res, _next) => {
    if (error instanceof HttpError) {
        res.status(error.status).json({ error: error.code, message: error.message, details: error.details });
        return;
    }
    if (error instanceof ZodError) {
        res.status(400).json({ error: 'validation_error', issues: error.issues });
        return;
    }
    console.error(error);
    res.status(500).json({ error: 'internal_error', message: 'Internal server error' });
});
const server = app.listen(config.PORT, '0.0.0.0', () => {
    console.log(`Qinghe API listening on :${config.PORT}`);
});
let shuttingDown = false;
async function shutdown(signal) {
    if (shuttingDown)
        return;
    shuttingDown = true;
    console.log(`${signal}: shutting down Qinghe API`);
    server.close(async () => {
        await pool.end().catch(() => undefined);
        process.exit(0);
    });
    setTimeout(() => process.exit(1), 10_000).unref();
}
process.on('SIGTERM', () => void shutdown('SIGTERM'));
process.on('SIGINT', () => void shutdown('SIGINT'));
