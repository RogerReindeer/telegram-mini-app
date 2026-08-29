import { config } from '../config.js';
import { processReaderCoinOutboxBatch } from '../services/readerCoinDelivery.js';

export function startReaderCoinOutboxWorker(): () => void {
  if (!config.READER_COMMERCE_ENABLED) return () => undefined;

  let running = false;
  let stopped = false;
  const tick = async () => {
    if (stopped || running) return;
    running = true;
    try {
      const result = await processReaderCoinOutboxBatch();
      if (result.claimed > 0) console.log('reader coin outbox processed', result);
    } catch (error) {
      console.error('reader coin outbox worker failed', error instanceof Error ? error.message : 'unknown_error');
    } finally {
      running = false;
    }
  };

  const timer = setInterval(() => void tick(), config.READER_COMMERCE_WORKER_INTERVAL_MS);
  timer.unref();
  void tick();

  return () => {
    stopped = true;
    clearInterval(timer);
  };
}

