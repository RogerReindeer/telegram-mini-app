begin;

create table if not exists public.reader_coin_wallets (
  telegram_user_id bigint primary key,
  balance bigint not null default 0 check (balance >= 0),
  lifetime_credited bigint not null default 0 check (lifetime_credited >= 0),
  lifetime_spent bigint not null default 0 check (lifetime_spent >= 0),
  updated_at timestamptz not null default now()
);
alter table public.reader_coin_wallets add column if not exists lifetime_credited bigint not null default 0;
alter table public.reader_coin_wallets add column if not exists lifetime_spent bigint not null default 0;

create table if not exists public.reader_coin_ledger (
  id uuid primary key default gen_random_uuid(),
  telegram_user_id bigint not null,
  amount bigint not null check (amount <> 0),
  balance_after bigint not null check (balance_after >= 0),
  operation_type text not null check (
    operation_type in ('qinghe_grant','store_spend','admin_adjustment','refund_reversal')
  ),
  purchase_id uuid,
  event_id uuid,
  idempotency_key text not null unique,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

-- The production reader project already had an earlier ledger shape. Rename
-- compatible columns instead of creating duplicate data, then fill the fields
-- required by the current Reader Coins RPC. CREATE TABLE IF NOT EXISTS does
-- not reconcile an existing table.
do $$
begin
  if exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'reader_coin_ledger'
      and column_name = 'ledger_id'
  ) and not exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'reader_coin_ledger'
      and column_name = 'id'
  ) then
    alter table public.reader_coin_ledger rename column ledger_id to id;
  end if;

  if exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'reader_coin_ledger'
      and column_name = 'operation'
  ) and not exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'reader_coin_ledger'
      and column_name = 'operation_type'
  ) then
    alter table public.reader_coin_ledger rename column operation to operation_type;
  end if;

  if exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'reader_coin_ledger'
      and column_name = 'source_event_id'
  ) and not exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'reader_coin_ledger'
      and column_name = 'event_id'
  ) then
    alter table public.reader_coin_ledger rename column source_event_id to event_id;
  end if;

  if exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'reader_coin_ledger'
      and column_name = 'source_purchase_id'
  ) and not exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'reader_coin_ledger'
      and column_name = 'purchase_id'
  ) then
    alter table public.reader_coin_ledger rename column source_purchase_id to purchase_id;
  end if;
end $$;

alter table public.reader_coin_ledger add column if not exists id uuid default gen_random_uuid();
alter table public.reader_coin_ledger add column if not exists operation_type text;
alter table public.reader_coin_ledger add column if not exists purchase_id uuid;
alter table public.reader_coin_ledger add column if not exists event_id uuid;
alter table public.reader_coin_ledger add column if not exists idempotency_key text;

-- These constraints belong to the legacy positive-only ledger and would reject
-- the signed amounts and renamed operation values used by the current model.
alter table public.reader_coin_ledger drop constraint if exists reader_coin_ledger_operation;
alter table public.reader_coin_ledger drop constraint if exists reader_coin_ledger_amount_positive;
drop index if exists public.reader_coin_ledger_qinghe_event_uidx;
drop index if exists public.reader_coin_ledger_qinghe_purchase_uidx;

do $$
begin
  if exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'reader_coin_ledger'
      and column_name = 'balance_before'
  ) then
    alter table public.reader_coin_ledger alter column balance_before drop not null;
  end if;
end $$;

update public.reader_coin_ledger
set amount = case
      when operation_type in ('debit', 'adjustment_debit') and amount > 0 then -amount
      else amount
    end,
    operation_type = case operation_type
      when 'qinghe_credit' then 'qinghe_grant'
      when 'debit' then 'store_spend'
      when 'refund_credit' then 'refund_reversal'
      when 'adjustment_credit' then 'admin_adjustment'
      when 'adjustment_debit' then 'admin_adjustment'
      else operation_type
    end,
    idempotency_key = coalesce(idempotency_key, 'legacy-ledger:' || id::text)
where operation_type in (
    'qinghe_credit', 'debit', 'refund_credit',
    'adjustment_credit', 'adjustment_debit'
  )
   or idempotency_key is null;

alter table public.reader_coin_ledger alter column id set not null;
alter table public.reader_coin_ledger alter column operation_type set not null;
alter table public.reader_coin_ledger alter column idempotency_key set not null;

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'public.reader_coin_ledger'::regclass
      and conname in (
        'reader_coin_ledger_operation_type_allowed',
        'reader_coin_ledger_operation_type_check'
      )
  ) then
    alter table public.reader_coin_ledger
      add constraint reader_coin_ledger_operation_type_allowed check (
        operation_type in ('qinghe_grant','store_spend','admin_adjustment','refund_reversal')
      );
  end if;

  if not exists (
    select 1 from pg_constraint
    where conrelid = 'public.reader_coin_ledger'::regclass
      and conname in (
        'reader_coin_ledger_amount_nonzero',
        'reader_coin_ledger_amount_check'
      )
  ) then
    alter table public.reader_coin_ledger
      add constraint reader_coin_ledger_amount_nonzero check (amount <> 0);
  end if;
end $$;

create unique index if not exists reader_coin_ledger_idempotency_key_idx
  on public.reader_coin_ledger(idempotency_key);
create index if not exists reader_coin_ledger_user_created_idx
  on public.reader_coin_ledger(telegram_user_id, created_at desc);
create unique index if not exists reader_coin_ledger_event_idx
  on public.reader_coin_ledger(event_id) where event_id is not null;
create unique index if not exists reader_coin_ledger_purchase_idx
  on public.reader_coin_ledger(purchase_id) where purchase_id is not null;

create table if not exists public.reader_store_products (
  product_code text primary key,
  product_type text not null check (
    product_type in ('chapter_unlock','novel_unlock','subscription','subscription_upgrade')
  ),
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
  status text not null default 'completed' check (status in ('completed','reversed','failed')),
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
  entitlement_type text not null check (entitlement_type in ('chapter','novel','subscription')),
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

create or replace function public.reader_credit_coins_from_qinghe(
  p_event_id uuid,
  p_purchase_id uuid,
  p_telegram_user_id bigint,
  p_product_code text,
  p_amount bigint,
  p_provider text,
  p_occurred_at timestamptz
)
returns table(credited bigint, balance bigint, duplicate boolean)
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_existing public.reader_coin_ledger%rowtype;
  v_balance bigint;
begin
  if p_telegram_user_id <= 0 or p_amount <= 0 then
    raise exception 'invalid_reader_coin_grant';
  end if;

  perform pg_catalog.pg_advisory_xact_lock(p_telegram_user_id);

  select * into v_existing
  from public.reader_coin_ledger
  where event_id = p_event_id or purchase_id = p_purchase_id
  order by created_at
  limit 1;

  if found then
    if v_existing.event_id = p_event_id
       and v_existing.purchase_id = p_purchase_id
       and v_existing.telegram_user_id = p_telegram_user_id
       and v_existing.amount = p_amount then
      return query select 0::bigint, v_existing.balance_after, true;
      return;
    end if;
    if v_existing.event_id = p_event_id then
      raise exception 'reader_event_conflict';
    end if;
    raise exception 'reader_purchase_conflict';
  end if;

  insert into public.reader_coin_wallets (
    telegram_user_id, balance, lifetime_credited, lifetime_spent, updated_at
  ) values (p_telegram_user_id, p_amount, p_amount, 0, now())
  on conflict (telegram_user_id) do update set
    balance = public.reader_coin_wallets.balance + excluded.balance,
    lifetime_credited = public.reader_coin_wallets.lifetime_credited + excluded.lifetime_credited,
    updated_at = now()
  returning public.reader_coin_wallets.balance into v_balance;

  insert into public.reader_coin_ledger (
    telegram_user_id, amount, balance_after, operation_type, purchase_id,
    event_id, idempotency_key, metadata, created_at
  ) values (
    p_telegram_user_id, p_amount, v_balance, 'qinghe_grant', p_purchase_id,
    p_event_id, 'qinghe:' || p_event_id::text,
    pg_catalog.jsonb_build_object(
      'product_code', p_product_code,
      'provider', p_provider,
      'occurred_at', p_occurred_at
    ),
    coalesce(p_occurred_at, now())
  );

  return query select p_amount, v_balance, false;
end;
$$;

alter table public.reader_coin_wallets enable row level security;
alter table public.reader_coin_ledger enable row level security;
alter table public.reader_store_products enable row level security;
alter table public.reader_store_purchases enable row level security;
alter table public.reader_commerce_entitlements enable row level security;
alter table public.reader_commerce_nonces enable row level security;
revoke all on table public.reader_coin_wallets, public.reader_coin_ledger,
  public.reader_store_products, public.reader_store_purchases,
  public.reader_commerce_entitlements, public.reader_commerce_nonces
  from anon, authenticated;
grant all on table public.reader_coin_wallets, public.reader_coin_ledger,
  public.reader_store_products, public.reader_store_purchases,
  public.reader_commerce_entitlements, public.reader_commerce_nonces
  to service_role;
revoke execute on function public.reader_credit_coins_from_qinghe(
  uuid, uuid, bigint, text, bigint, text, timestamptz
) from public, anon, authenticated;
grant execute on function public.reader_credit_coins_from_qinghe(
  uuid, uuid, bigint, text, bigint, text, timestamptz
) to service_role;

commit;
notify pgrst, 'reload schema';
