import 'dotenv/config';
import { z } from 'zod';
const schema = z.object({
    NODE_ENV: z.enum(['development', 'test', 'production']).default('development'),
    PORT: z.coerce.number().int().positive().default(3000),
    DATABASE_URL: z.string().min(1),
    BOT_TOKEN: z.string().min(1),
    SESSION_SECRET: z.string().min(16),
    FRONTEND_ORIGIN: z.string().url(),
    CONTENT_VERSION: z.string().default('qinghe-v3.1'),
    ADMIN_PASSWORD: z.string().min(12).optional(),
    ACTION_TIME_SCALE: z.coerce.number().positive().max(1).default(0.1),
    PRESENCE_TTL_SECONDS: z.coerce.number().int().min(30).max(600).default(120),
    AVAILABILITY_UTC_OFFSET: z.coerce.number().int().min(-12).max(14).default(8),
    WORLD_EVENT_REAL_MINUTES_PER_WORLD_DAY: z.coerce.number().positive().max(180).default(30),
    SEASON_REAL_DAYS: z.coerce.number().positive().max(90).default(7),
    DEV_TELEGRAM_USER_ID: z.coerce.number().int().positive().default(990001),
    DEV_TELEGRAM_USERNAME: z.string().default('local_tester')
});
export const config = schema.parse(process.env);
