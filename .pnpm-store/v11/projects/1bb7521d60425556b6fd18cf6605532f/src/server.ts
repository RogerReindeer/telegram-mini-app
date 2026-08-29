import express from 'express';
import cors from 'cors';
import { ZodError } from 'zod';
import { config } from './config.js';
import { pool } from './db.js';
import { authRouter } from './routes/auth.js';
import { gameRouter } from './routes/game.js';
import { adminRouter } from './routes/admin.js';
import { commerceRouter } from './routes/commerce.js';
import { startReaderCoinOutboxWorker } from './workers/readerCoinOutboxWorker.js';
import { HttpError } from './utils/http.js';

const app = express();
app.set('trust proxy', 1);
app.disable('x-powered-by');
app.use(cors({ origin: config.FRONTEND_ORIGIN, credentials: false, methods: ['GET','POST','PUT','PATCH','OPTIONS'], allowedHeaders: ['content-type','authorization'] }));
app.use((_req,res,next)=>{res.setHeader('X-Content-Type-Options','nosniff');res.setHeader('Referrer-Policy','no-referrer');res.setHeader('Cache-Control','no-store');next();});
app.use(express.json({ limit: '64kb' }));

app.get('/health', (_req, res) => res.json({ status: 'ok' }));
app.get('/ready', async (_req, res) => {
  try {
    await pool.query(`select 1 from world_clock where id=1`);
    await pool.query(`select 1 from life_item_instances limit 1`);
    await pool.query(`select interrupt_policy from open_life_activities limit 1`);
    await pool.query(`select open_life_world_time_normalized from lives limit 1`);
    await pool.query(`select title,details,world_day from open_life_notices limit 1`);
    if (config.STARS_PAYMENTS_ENABLED || config.READER_COMMERCE_ENABLED) {
      await pool.query(`select purchase_id from commerce_purchases limit 1`);
      await pool.query(`select event_id from reader_coin_outbox limit 1`);
      await pool.query(`select player_id from platinum_wallets limit 1`);
    }
    res.json({
      status: 'ok',
      database: 'ok',
      open_life_schema: 'ok',
      materiality_schema: 'ok',
      open_life_ux_schema: 'ok',
      commerce_schema: config.STARS_PAYMENTS_ENABLED || config.READER_COMMERCE_ENABLED ? 'ok' : 'disabled'
    });
  } catch {
    res.status(503).json({ status: 'degraded', database: 'error' });
  }
});
app.get('/version', (_req, res) => res.json({
  app: 'qinghe-api',
  version: '0.4.0',
  release: 'reader-coins-delivery-v242',
  content_version: config.CONTENT_VERSION,
  stars_payments: config.STARS_PAYMENTS_ENABLED,
  reader_commerce: config.READER_COMMERCE_ENABLED
}));

app.use('/api/auth', authRouter);
app.use('/api/game', gameRouter);
app.use('/api/admin', adminRouter);
app.use('/api/commerce', commerceRouter);

app.use((error: unknown, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
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
const stopReaderCoinWorker = startReaderCoinOutboxWorker();

let shuttingDown = false;
async function shutdown(signal: string) {
  if (shuttingDown) return;
  shuttingDown = true;
  stopReaderCoinWorker();
  console.log(`${signal}: shutting down Qinghe API`);
  server.close(async () => {
    await pool.end().catch(() => undefined);
    process.exit(0);
  });
  setTimeout(() => process.exit(1), 10_000).unref();
}
process.on('SIGTERM', () => void shutdown('SIGTERM'));
process.on('SIGINT', () => void shutdown('SIGINT'));
