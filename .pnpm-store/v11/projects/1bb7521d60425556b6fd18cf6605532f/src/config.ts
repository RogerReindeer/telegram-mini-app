import 'dotenv/config';
import { z } from 'zod';

const booleanEnv = z.enum(['true', 'false']).default('false').transform((value) => value === 'true');

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
  CALENDAR_REAL_MINUTES_PER_DAY: z.coerce.number().positive().max(1440).default(240),
  DEV_TELEGRAM_USER_ID: z.coerce.number().int().positive().default(990001),
  DEV_TELEGRAM_USERNAME: z.string().default('local_tester'),
  STARS_PAYMENTS_ENABLED: booleanEnv,
  TELEGRAM_WEBHOOK_SECRET: z.string().min(16).optional(),
  READER_COMMERCE_ENABLED: booleanEnv,
  READER_API_URL: z.string().url().optional(),
  READER_COMMERCE_SHARED_SECRET: z.string().min(32).optional(),
  READER_COMMERCE_SERVICE_ID: z.string().min(1).max(80).default('qinghe-api'),
  READER_COMMERCE_TIMEOUT_SECONDS: z.coerce.number().int().min(1).max(30).default(8),
  READER_COMMERCE_WORKER_INTERVAL_MS: z.coerce.number().int().min(1000).max(60000).default(5000),
  READER_COMMERCE_BATCH_SIZE: z.coerce.number().int().min(1).max(20).default(5),
  READER_COMMERCE_PROCESSING_TIMEOUT_SECONDS: z.coerce.number().int().min(60).max(3600).default(300)
}).superRefine((value, context) => {
  if (value.STARS_PAYMENTS_ENABLED && !value.TELEGRAM_WEBHOOK_SECRET) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['TELEGRAM_WEBHOOK_SECRET'],
      message: 'TELEGRAM_WEBHOOK_SECRET is required when Stars payments are enabled'
    });
  }
  if (value.READER_COMMERCE_ENABLED) {
    if (!value.READER_API_URL) {
      context.addIssue({ code: z.ZodIssueCode.custom, path: ['READER_API_URL'], message: 'READER_API_URL is required' });
    }
    if (!value.READER_COMMERCE_SHARED_SECRET) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['READER_COMMERCE_SHARED_SECRET'],
        message: 'READER_COMMERCE_SHARED_SECRET is required'
      });
    }
  }
});

export const config = schema.parse(process.env);
