begin;

create table if not exists public.reader_store_runtime_settings (
  id smallint primary key default 1 check (id = 1),
  test_mode_enabled boolean not null default true,
  stars_coins_per_star integer not null default 1 check (stars_coins_per_star between 1 and 100),
  stars_min_coin_amount integer not null default 10 check (stars_min_coin_amount between 10 and 100000),
  updated_at timestamptz not null default now()
);

insert into public.reader_store_runtime_settings (
  id, test_mode_enabled, stars_coins_per_star, stars_min_coin_amount
) values (1, true, 1, 10)
on conflict (id) do nothing;

create or replace function public.reader_grant_test_coins_v2(
  p_telegram_user_id bigint,
  p_amount bigint,
  p_client_action_id uuid
)
returns table(credited bigint, balance bigint, duplicate boolean)
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_existing public.reader_coin_ledger%rowtype;
  v_balance bigint;
  v_key text;
  v_test_mode boolean;
begin
  if p_telegram_user_id <= 0 or p_amount < 10 or p_amount > 100000 or p_client_action_id is null then
    raise exception 'reader_invalid_test_grant';
  end if;
  v_key := 'test-grant:' || p_telegram_user_id::text || ':' || p_client_action_id::text;

  perform pg_catalog.pg_advisory_xact_lock_shared(7265616465727465::bigint);
  perform pg_catalog.pg_advisory_xact_lock(p_telegram_user_id);

  select settings.test_mode_enabled into v_test_mode
  from public.reader_store_runtime_settings as settings
  where settings.id = 1
  for share;
  if not found or v_test_mode is not true then
    raise exception 'reader_test_mode_disabled';
  end if;

  select * into v_existing
  from public.reader_coin_ledger
  where idempotency_key = v_key
  limit 1;
  if found then
    if v_existing.telegram_user_id <> p_telegram_user_id
       or v_existing.amount <> p_amount then
      raise exception 'reader_test_grant_conflict';
    end if;
    return query select 0::bigint, v_existing.balance_after, true;
    return;
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
    telegram_user_id, amount, balance_after, operation_type,
    idempotency_key, metadata, created_at
  ) values (
    p_telegram_user_id, p_amount, v_balance, 'admin_adjustment',
    v_key,
    pg_catalog.jsonb_build_object(
      'test_mode', true,
      'client_action_id', p_client_action_id,
      'exchange_rate_rub', 1
    ),
    now()
  );

  return query select p_amount, v_balance, false;
end;
$$;

-- This additive v2 RPC leaves the established purchase function untouched.
-- The database switch decides whether newly created rows are revocable test data.
create or replace function public.reader_purchase_product_v2(
  p_telegram_user_id bigint,
  p_product_code text,
  p_client_action_id uuid,
  p_test_mode boolean
)
returns table(
  purchase_id uuid,
  product_code text,
  product_type text,
  spent bigint,
  balance bigint,
  duplicate boolean,
  purchase_status text
)
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_product public.reader_store_products%rowtype;
  v_existing public.reader_store_purchases%rowtype;
  v_purchase_id uuid;
  v_balance bigint;
  v_entitlement_type text;
  v_starts_at timestamptz := now();
  v_expires_at timestamptz;
  v_chapter_novel_id bigint;
  v_test_mode boolean;
begin
  p_product_code := pg_catalog.btrim(coalesce(p_product_code, ''));
  if p_telegram_user_id <= 0
     or p_product_code = ''
     or p_client_action_id is null
     or p_test_mode is null then
    raise exception 'reader_invalid_purchase';
  end if;

  perform pg_catalog.pg_advisory_xact_lock_shared(7265616465727465::bigint);
  perform pg_catalog.pg_advisory_xact_lock(p_telegram_user_id);

  select settings.test_mode_enabled into v_test_mode
  from public.reader_store_runtime_settings as settings
  where settings.id = 1
  for share;
  if not found then
    raise exception 'reader_store_runtime_settings_missing';
  end if;
  if v_test_mode is distinct from p_test_mode then
    raise exception 'reader_store_mode_changed';
  end if;

  select purchase.* into v_existing
  from public.reader_store_purchases as purchase
  where purchase.telegram_user_id = p_telegram_user_id
    and purchase.client_action_id = p_client_action_id
  limit 1;

  if found then
    if v_existing.product_code <> p_product_code then
      raise exception 'reader_purchase_action_conflict';
    end if;
    select wallet.balance into v_balance
    from public.reader_coin_wallets as wallet
    where wallet.telegram_user_id = p_telegram_user_id;
    select product.* into v_product
    from public.reader_store_products as product
    where product.product_code = v_existing.product_code;
    return query select
      v_existing.id,
      v_existing.product_code,
      v_product.product_type,
      0::bigint,
      coalesce(v_balance, 0),
      true,
      v_existing.status;
    return;
  end if;

  select product.* into v_product
  from public.reader_store_products as product
  where product.product_code = p_product_code
    and product.is_active is true
  for share;

  if not found then
    raise exception 'reader_product_not_found';
  end if;

  if v_product.product_type = 'chapter_unlock' then
    select chapter.novel_id into v_chapter_novel_id
    from public.chapters as chapter
    where chapter.chapter_id = v_product.chapter_id;
    if v_chapter_novel_id is null or v_chapter_novel_id <> v_product.novel_id then
      raise exception 'reader_product_target_invalid';
    end if;
    if exists (
      select 1
      from public.reader_commerce_entitlements as entitlement
      where entitlement.telegram_user_id = p_telegram_user_id
        and entitlement.revoked_at is null
        and (entitlement.expires_at is null or entitlement.expires_at > now())
        and (
          (entitlement.entitlement_type = 'chapter' and entitlement.chapter_id = v_product.chapter_id)
          or (entitlement.entitlement_type = 'novel' and entitlement.novel_id = v_product.novel_id)
        )
    ) then
      raise exception 'reader_product_already_owned';
    end if;
    v_entitlement_type := 'chapter';
  elsif v_product.product_type = 'novel_unlock' then
    if exists (
      select 1
      from public.reader_commerce_entitlements as entitlement
      where entitlement.telegram_user_id = p_telegram_user_id
        and entitlement.entitlement_type = 'novel'
        and entitlement.novel_id = v_product.novel_id
        and entitlement.revoked_at is null
        and (entitlement.expires_at is null or entitlement.expires_at > now())
    ) then
      raise exception 'reader_product_already_owned';
    end if;
    v_entitlement_type := 'novel';
  elsif v_product.product_type in ('subscription', 'subscription_upgrade') then
    v_entitlement_type := 'subscription';
    select coalesce(max(entitlement.expires_at), now()) into v_starts_at
    from public.reader_commerce_entitlements as entitlement
    where entitlement.telegram_user_id = p_telegram_user_id
      and entitlement.entitlement_type = 'subscription'
      and entitlement.subscription_role = v_product.subscription_role
      and entitlement.revoked_at is null
      and entitlement.expires_at > now();
    v_starts_at := greatest(coalesce(v_starts_at, now()), now());
    v_expires_at := v_starts_at + pg_catalog.make_interval(days => v_product.duration_days);
  else
    raise exception 'reader_product_target_invalid';
  end if;

  insert into public.reader_coin_wallets (
    telegram_user_id, balance, lifetime_credited, lifetime_spent, updated_at
  ) values (p_telegram_user_id, 0, 0, 0, now())
  on conflict (telegram_user_id) do nothing;

  update public.reader_coin_wallets as wallet
  set balance = wallet.balance - v_product.coin_price,
      lifetime_spent = wallet.lifetime_spent + v_product.coin_price,
      updated_at = now()
  where wallet.telegram_user_id = p_telegram_user_id
    and wallet.balance >= v_product.coin_price
  returning wallet.balance into v_balance;

  if not found then
    raise exception 'reader_insufficient_balance';
  end if;

  insert into public.reader_store_purchases (
    telegram_user_id, product_code, client_action_id, coin_price,
    status, purchased_at, metadata
  ) values (
    p_telegram_user_id, v_product.product_code, p_client_action_id,
    v_product.coin_price, 'completed', now(),
    pg_catalog.jsonb_build_object('test_mode', v_test_mode, 'exchange_rate_rub', 1)
  )
  returning id into v_purchase_id;

  insert into public.reader_coin_ledger (
    telegram_user_id, amount, balance_after, operation_type,
    purchase_id, idempotency_key, metadata, created_at
  ) values (
    p_telegram_user_id, -v_product.coin_price, v_balance, 'store_spend',
    v_purchase_id, 'store:' || p_client_action_id::text,
    pg_catalog.jsonb_build_object(
      'test_mode', v_test_mode,
      'product_code', v_product.product_code,
      'product_type', v_product.product_type,
      'exchange_rate_rub', 1
    ),
    now()
  );

  insert into public.reader_commerce_entitlements (
    telegram_user_id, purchase_id, entitlement_type, novel_id, chapter_id,
    subscription_role, starts_at, expires_at, metadata, created_at
  ) values (
    p_telegram_user_id,
    v_purchase_id,
    v_entitlement_type,
    v_product.novel_id,
    v_product.chapter_id,
    v_product.subscription_role,
    v_starts_at,
    v_expires_at,
    pg_catalog.jsonb_build_object(
      'test_mode', v_test_mode,
      'product_code', v_product.product_code
    ),
    now()
  );

  return query select
    v_purchase_id,
    v_product.product_code,
    v_product.product_type,
    v_product.coin_price::bigint,
    v_balance,
    false,
    'completed'::text;
end;
$$;

create or replace function public.reader_finish_test_commerce(
  p_confirmation text
)
returns table(
  reset_wallets bigint,
  cleared_coins bigint,
  reversed_purchases bigint,
  revoked_entitlements bigint
)
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_wallet public.reader_coin_wallets%rowtype;
  v_reset_wallets bigint := 0;
  v_cleared_coins bigint := 0;
  v_reversed_purchases bigint := 0;
  v_revoked_entitlements bigint := 0;
  v_test_mode_enabled boolean;
begin
  if coalesce(p_confirmation, '') <> 'FINISH_READER_COMMERCE_TEST' then
    raise exception 'reader_invalid_test_finish_confirmation';
  end if;

  -- A global transaction lock prevents two administrators from finishing the
  -- test at the same time; per-user locks serialize against grants/purchases.
  perform pg_catalog.pg_advisory_xact_lock(7265616465727465::bigint);

  select settings.test_mode_enabled into v_test_mode_enabled
  from public.reader_store_runtime_settings as settings
  where settings.id = 1
  for update;
  if not found then
    raise exception 'reader_store_runtime_settings_missing';
  end if;
  if v_test_mode_enabled is not true then
    raise exception 'reader_test_mode_already_finished';
  end if;

  if exists (
    select 1
    from public.reader_coin_ledger as ledger
    where ledger.operation_type = 'qinghe_grant'
       or (
         ledger.operation_type = 'store_spend'
         and coalesce(ledger.metadata ->> 'test_mode', 'false') <> 'true'
       )
  ) or exists (
    select 1
    from public.reader_store_purchases as purchase
    where coalesce(purchase.metadata ->> 'test_mode', 'false') <> 'true'
  ) then
    raise exception 'reader_real_commerce_present';
  end if;

  update public.reader_store_runtime_settings
  set test_mode_enabled = false,
      updated_at = now()
  where id = 1;
  if not found then
    raise exception 'reader_store_runtime_settings_missing';
  end if;

  for v_wallet in
    select wallet.*
    from public.reader_coin_wallets as wallet
    order by wallet.telegram_user_id
  loop
    perform pg_catalog.pg_advisory_xact_lock(v_wallet.telegram_user_id);
  end loop;

  update public.reader_commerce_entitlements as entitlement
  set revoked_at = now(),
      metadata = entitlement.metadata || pg_catalog.jsonb_build_object(
        'test_reset', true,
        'test_reset_at', now()
      )
  where entitlement.revoked_at is null
    and coalesce(entitlement.metadata ->> 'test_mode', 'false') = 'true';
  get diagnostics v_revoked_entitlements = row_count;

  update public.reader_store_purchases as purchase
  set status = 'reversed',
      reversed_at = now(),
      metadata = purchase.metadata || pg_catalog.jsonb_build_object(
        'test_reset', true,
        'test_reset_at', now()
      )
  where purchase.status = 'completed'
    and coalesce(purchase.metadata ->> 'test_mode', 'false') = 'true';
  get diagnostics v_reversed_purchases = row_count;

  for v_wallet in
    select wallet.*
    from public.reader_coin_wallets as wallet
    order by wallet.telegram_user_id
    for update
  loop
    if v_wallet.balance <> 0 then
      insert into public.reader_coin_ledger (
        telegram_user_id, amount, balance_after, operation_type,
        idempotency_key, metadata, created_at
      ) values (
        v_wallet.telegram_user_id,
        -v_wallet.balance,
        0,
        'admin_adjustment',
        'test-finish:' || pg_catalog.gen_random_uuid()::text,
        pg_catalog.jsonb_build_object(
          'test_mode', true,
          'test_reset', true,
          'reason', 'reader_commerce_test_finished'
        ),
        now()
      );
      v_cleared_coins := v_cleared_coins + v_wallet.balance;
    end if;

    update public.reader_coin_wallets as wallet
    set balance = 0,
        lifetime_credited = 0,
        lifetime_spent = 0,
        updated_at = now()
    where wallet.telegram_user_id = v_wallet.telegram_user_id;
    v_reset_wallets := v_reset_wallets + 1;
  end loop;

  -- Catch a real grant that committed for a new wallet while the reset was
  -- running. Raising here rolls this transaction back and preserves that grant.
  if exists (
    select 1
    from public.reader_coin_ledger as ledger
    where ledger.operation_type = 'qinghe_grant'
       or (
         ledger.operation_type = 'store_spend'
         and coalesce(ledger.metadata ->> 'test_mode', 'false') <> 'true'
       )
  ) then
    raise exception 'reader_real_commerce_present';
  end if;

  return query select
    v_reset_wallets,
    v_cleared_coins,
    v_reversed_purchases,
    v_revoked_entitlements;
end;
$$;

alter table public.reader_store_runtime_settings enable row level security;
revoke all on table public.reader_store_runtime_settings from public, anon, authenticated;
grant all on table public.reader_store_runtime_settings to service_role;

revoke execute on function public.reader_purchase_product_v2(bigint, text, uuid, boolean)
  from public, anon, authenticated;
grant execute on function public.reader_purchase_product_v2(bigint, text, uuid, boolean)
  to service_role;

revoke execute on function public.reader_grant_test_coins_v2(bigint, bigint, uuid)
  from public, anon, authenticated;
grant execute on function public.reader_grant_test_coins_v2(bigint, bigint, uuid)
  to service_role;

revoke execute on function public.reader_finish_test_commerce(text)
  from public, anon, authenticated;
grant execute on function public.reader_finish_test_commerce(text)
  to service_role;

commit;
notify pgrst, 'reload schema';
