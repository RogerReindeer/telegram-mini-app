-- DRAFT: Qinghe RPG dual-currency commerce.
-- Review against the live schema and run on staging first.

begin;

create table if not exists currency_wallets (
  player_id uuid primary key references players(id) on delete cascade,
  platinum_balance bigint not null default 0 check (platinum_balance >= 0),
  updated_at timestamptz not null default now()
);

create table if not exists commerce_products (
  product_code text primary key,
  title text not null,
  product_type text not null check (product_type = 'currency_bundle'),
  price_stars integer not null check (price_stars > 0),
  platinum_grant integer not null check (platinum_grant > 0),
  reader_coins_grant integer not null check (reader_coins_grant > 0),
  is_active boolean not null default true,
  sort_order integer not null default 0,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists commerce_checkouts (
  id uuid primary key default gen_random_uuid(),
  opaque_token_hash text not null unique,
  player_id uuid references players(id) on delete set null,
  telegram_user_id bigint,
  source text not null default 'qinghe',
  return_path text,
  status text not null default 'created'
    check (status in ('created','authenticated','invoice_created','paid','expired','cancelled')),
  selected_product_code text references commerce_products(product_code),
  expires_at timestamptz not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists commerce_purchases (
  id uuid primary key default gen_random_uuid(),
  checkout_id uuid references commerce_checkouts(id) on delete set null,
  player_id uuid not null references players(id) on delete restrict,
  telegram_user_id bigint not null,
  product_code text not null references commerce_products(product_code),
  provider text not null check (provider in ('telegram_stars','tribute')),
  provider_payment_reference text not null,
  status text not null default 'paid'
    check (status in ('paid','partially_delivered','completed','refund_pending','refunded','failed')),
  price_amount integer not null check (price_amount > 0),
  price_currency text not null,
  platinum_grant integer not null check (platinum_grant > 0),
  reader_coins_grant integer not null check (reader_coins_grant > 0),
  paid_at timestamptz not null,
  refunded_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(provider, provider_payment_reference)
);

create table if not exists currency_ledger (
  id uuid primary key default gen_random_uuid(),
  player_id uuid not null references players(id) on delete restrict,
  currency text not null check (currency = 'platinum'),
  amount bigint not null check (amount <> 0),
  balance_after bigint not null check (balance_after >= 0),
  operation_type text not null
    check (operation_type in ('purchase_grant','game_spend','admin_adjustment','refund_reversal')),
  purchase_id uuid references commerce_purchases(id) on delete restrict,
  idempotency_key text not null unique,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists currency_ledger_player_created_idx
  on currency_ledger(player_id, created_at desc);

create table if not exists purchase_grants (
  purchase_id uuid primary key references commerce_purchases(id) on delete restrict,
  platinum_status text not null default 'pending'
    check (platinum_status in ('pending','completed','reversed','failed')),
  reader_coins_status text not null default 'pending'
    check (reader_coins_status in ('pending','processing','completed','retry','manual_review','reversed','failed')),
  reader_event_id uuid not null unique default gen_random_uuid(),
  reader_attempts integer not null default 0 check (reader_attempts >= 0),
  reader_last_attempt_at timestamptz,
  reader_completed_at timestamptz,
  last_error_code text,
  last_error_message text,
  updated_at timestamptz not null default now()
);

create table if not exists commerce_outbox (
  id uuid primary key default gen_random_uuid(),
  event_type text not null check (event_type in ('reader.coin_grant','reader.coin_reversal')),
  aggregate_id uuid not null references commerce_purchases(id) on delete restrict,
  payload jsonb not null,
  status text not null default 'pending'
    check (status in ('pending','processing','retry','completed','manual_review')),
  attempts integer not null default 0 check (attempts >= 0),
  available_at timestamptz not null default now(),
  locked_at timestamptz,
  completed_at timestamptz,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(event_type, aggregate_id)
);

create index if not exists commerce_outbox_delivery_idx
  on commerce_outbox(status, available_at)
  where status in ('pending','retry');

insert into commerce_products (
  product_code, title, product_type, price_stars,
  platinum_grant, reader_coins_grant, sort_order
) values
  ('currency_bundle_100', '100 Платины + 100 Монеток', 'currency_bundle', 1, 100, 100, 10),
  ('currency_bundle_200', '200 Платины + 200 Монеток', 'currency_bundle', 1, 200, 200, 20),
  ('currency_bundle_500', '500 Платины + 500 Монеток', 'currency_bundle', 1, 500, 500, 30),
  ('currency_bundle_1000', '1000 Платины + 1000 Монеток', 'currency_bundle', 1, 1000, 1000, 40)
on conflict (product_code) do nothing;

-- IMPORTANT: price_stars=1 is a staging placeholder. Set approved production prices before enabling sales.

commit;

