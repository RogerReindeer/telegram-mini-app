-- DRAFT: Reader coins, store and entitlements for Supabase PostgreSQL.
-- Review RLS/grants and test against the live v241 schema before production.

begin;

create table if not exists public.reader_coin_wallets (
  telegram_user_id bigint primary key,
  balance bigint not null default 0 check (balance >= 0),
  updated_at timestamptz not null default now()
);

create table if not exists public.reader_coin_ledger (
  id uuid primary key default gen_random_uuid(),
  telegram_user_id bigint not null,
  amount bigint not null check (amount <> 0),
  balance_after bigint not null check (balance_after >= 0),
  operation_type text not null
    check (operation_type in ('qinghe_grant','store_spend','admin_adjustment','refund_reversal')),
  purchase_id uuid,
  event_id uuid,
  idempotency_key text not null unique,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists reader_coin_ledger_user_created_idx
  on public.reader_coin_ledger(telegram_user_id, created_at desc);

create unique index if not exists reader_coin_ledger_event_idx
  on public.reader_coin_ledger(event_id)
  where event_id is not null;

create table if not exists public.reader_store_products (
  product_code text primary key,
  product_type text not null
    check (product_type in ('chapter_unlock','novel_unlock','subscription','subscription_upgrade')),
  title text not null,
  coin_price integer not null check (coin_price > 0),
  novel_id bigint references public.novels(novel_id) on delete cascade,
  chapter_id text references public.chapters(chapter_id) on delete cascade,
  subscription_role text,
  duration_days integer check (duration_days is null or duration_days > 0),
  upgrade_from_role text,
  is_active boolean not null default true,
  sort_order integer not null default 0,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.reader_store_purchases (
  id uuid primary key default gen_random_uuid(),
  telegram_user_id bigint not null,
  product_code text not null references public.reader_store_products(product_code),
  client_action_id uuid not null,
  coin_price integer not null check (coin_price > 0),
  status text not null default 'completed'
    check (status in ('completed','reversed','failed')),
  purchased_at timestamptz not null default now(),
  reversed_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  unique(telegram_user_id, client_action_id)
);

create index if not exists reader_store_purchases_user_time_idx
  on public.reader_store_purchases(telegram_user_id, purchased_at desc);

create table if not exists public.reader_commerce_entitlements (
  id uuid primary key default gen_random_uuid(),
  telegram_user_id bigint not null,
  purchase_id uuid not null references public.reader_store_purchases(id) on delete restrict,
  entitlement_type text not null
    check (entitlement_type in ('chapter','novel','subscription')),
  novel_id bigint references public.novels(novel_id) on delete cascade,
  chapter_id text references public.chapters(chapter_id) on delete cascade,
  subscription_role text,
  starts_at timestamptz not null default now(),
  expires_at timestamptz,
  revoked_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique(telegram_user_id, purchase_id)
);

create index if not exists reader_commerce_entitlements_active_idx
  on public.reader_commerce_entitlements(telegram_user_id, novel_id, chapter_id, expires_at)
  where revoked_at is null;

create table if not exists public.reader_commerce_nonces (
  nonce uuid primary key,
  service_id text not null,
  expires_at timestamptz not null,
  created_at timestamptz not null default now()
);

create index if not exists reader_commerce_nonces_expiry_idx
  on public.reader_commerce_nonces(expires_at);

-- Backend uses the service role. Explicitly deny direct client access until reviewed policies exist.
alter table public.reader_coin_wallets enable row level security;
alter table public.reader_coin_ledger enable row level security;
alter table public.reader_store_products enable row level security;
alter table public.reader_store_purchases enable row level security;
alter table public.reader_commerce_entitlements enable row level security;
alter table public.reader_commerce_nonces enable row level security;

revoke all on public.reader_coin_wallets from anon, authenticated;
revoke all on public.reader_coin_ledger from anon, authenticated;
revoke all on public.reader_store_products from anon, authenticated;
revoke all on public.reader_store_purchases from anon, authenticated;
revoke all on public.reader_commerce_entitlements from anon, authenticated;
revoke all on public.reader_commerce_nonces from anon, authenticated;

commit;

