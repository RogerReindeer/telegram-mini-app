begin;

-- One purchase creates one debit, but the same purchase also needs a separate
-- refund row during the test rollback. Keep external grants and store debits
-- unique while allowing exactly-once refunds through idempotency_key.
drop index if exists public.reader_coin_ledger_purchase_idx;
create unique index if not exists reader_coin_ledger_purchase_debit_idx
  on public.reader_coin_ledger(purchase_id)
  where purchase_id is not null
    and operation_type in ('qinghe_grant', 'store_spend');

do $$
begin
  if not exists (
    select 1
    from pg_catalog.pg_constraint
    where conrelid = 'public.reader_store_products'::regclass
      and conname = 'reader_store_products_target_shape'
  ) then
    alter table public.reader_store_products
      add constraint reader_store_products_target_shape check (
        (
          product_type = 'chapter_unlock'
          and novel_id is not null
          and chapter_id is not null
          and subscription_role is null
          and duration_days is null
        )
        or (
          product_type = 'novel_unlock'
          and novel_id is not null
          and chapter_id is null
          and subscription_role is null
          and duration_days is null
        )
        or (
          product_type in ('subscription', 'subscription_upgrade')
          and novel_id is null
          and chapter_id is null
          and subscription_role in ('traveler', 'keeper')
          and duration_days is not null
          and duration_days > 0
        )
      );
  end if;
end $$;

create or replace function public.reader_grant_test_coins(
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
  v_key text := 'test-grant:' || p_client_action_id::text;
begin
  if p_telegram_user_id <= 0
     or p_amount < 10
     or p_amount > 100000
     or p_client_action_id is null then
    raise exception 'reader_invalid_test_grant';
  end if;

  perform pg_catalog.pg_advisory_xact_lock(p_telegram_user_id);

  select ledger.* into v_existing
  from public.reader_coin_ledger as ledger
  where ledger.idempotency_key = v_key
  limit 1;

  if found then
    if v_existing.telegram_user_id = p_telegram_user_id
       and v_existing.amount = p_amount
       and v_existing.operation_type = 'admin_adjustment'
       and coalesce(v_existing.metadata ->> 'test_mode', 'false') = 'true' then
      return query select 0::bigint, v_existing.balance_after, true;
      return;
    end if;
    raise exception 'reader_test_grant_conflict';
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

create or replace function public.reader_purchase_product(
  p_telegram_user_id bigint,
  p_product_code text,
  p_client_action_id uuid
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
begin
  p_product_code := pg_catalog.btrim(coalesce(p_product_code, ''));
  if p_telegram_user_id <= 0
     or p_product_code = ''
     or p_client_action_id is null then
    raise exception 'reader_invalid_purchase';
  end if;

  perform pg_catalog.pg_advisory_xact_lock(p_telegram_user_id);

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
    pg_catalog.jsonb_build_object('test_mode', true, 'exchange_rate_rub', 1)
  )
  returning id into v_purchase_id;

  insert into public.reader_coin_ledger (
    telegram_user_id, amount, balance_after, operation_type,
    purchase_id, idempotency_key, metadata, created_at
  ) values (
    p_telegram_user_id, -v_product.coin_price, v_balance, 'store_spend',
    v_purchase_id, 'store:' || p_client_action_id::text,
    pg_catalog.jsonb_build_object(
      'test_mode', true,
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
      'test_mode', true,
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

create or replace function public.reader_rollback_test_purchases(
  p_telegram_user_id bigint default null
)
returns table(
  reversed_purchases bigint,
  refunded_coins bigint,
  affected_users bigint
)
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_purchase public.reader_store_purchases%rowtype;
  v_user_id bigint;
  v_balance bigint;
  v_reversed bigint := 0;
  v_refunded bigint := 0;
  v_users bigint := 0;
begin
  if p_telegram_user_id is not null and p_telegram_user_id <= 0 then
    raise exception 'reader_invalid_rollback_user';
  end if;

  for v_user_id in
    select distinct purchase.telegram_user_id
    from public.reader_store_purchases as purchase
    where purchase.status = 'completed'
      and coalesce(purchase.metadata ->> 'test_mode', 'false') = 'true'
      and (p_telegram_user_id is null or purchase.telegram_user_id = p_telegram_user_id)
    order by purchase.telegram_user_id
  loop
    perform pg_catalog.pg_advisory_xact_lock(v_user_id);
    v_users := v_users + 1;
  end loop;

  for v_purchase in
    select purchase.*
    from public.reader_store_purchases as purchase
    where purchase.status = 'completed'
      and coalesce(purchase.metadata ->> 'test_mode', 'false') = 'true'
      and (p_telegram_user_id is null or purchase.telegram_user_id = p_telegram_user_id)
    order by purchase.telegram_user_id, purchase.purchased_at, purchase.id
    for update
  loop
    update public.reader_commerce_entitlements
    set revoked_at = now(),
        metadata = metadata || pg_catalog.jsonb_build_object('rollback', true)
    where purchase_id = v_purchase.id
      and revoked_at is null;

    update public.reader_coin_wallets as wallet
    set balance = wallet.balance + v_purchase.coin_price,
        lifetime_spent = greatest(0, wallet.lifetime_spent - v_purchase.coin_price),
        updated_at = now()
    where wallet.telegram_user_id = v_purchase.telegram_user_id
    returning wallet.balance into v_balance;

    if not found then
      raise exception 'reader_wallet_missing_for_rollback';
    end if;

    insert into public.reader_coin_ledger (
      telegram_user_id, amount, balance_after, operation_type,
      purchase_id, idempotency_key, metadata, created_at
    ) values (
      v_purchase.telegram_user_id,
      v_purchase.coin_price,
      v_balance,
      'refund_reversal',
      v_purchase.id,
      'rollback:' || v_purchase.id::text,
      pg_catalog.jsonb_build_object(
        'test_mode', true,
        'product_code', v_purchase.product_code,
        'reason', 'test_rollback'
      ),
      now()
    )
    on conflict (idempotency_key) do nothing;

    update public.reader_store_purchases
    set status = 'reversed',
        reversed_at = now(),
        metadata = metadata || pg_catalog.jsonb_build_object('rollback', true)
    where id = v_purchase.id;

    v_reversed := v_reversed + 1;
    v_refunded := v_refunded + v_purchase.coin_price;
  end loop;

  return query select v_reversed, v_refunded, v_users;
end;
$$;

alter table public.reader_coin_wallets enable row level security;
alter table public.reader_coin_ledger enable row level security;
alter table public.reader_store_products enable row level security;
alter table public.reader_store_purchases enable row level security;
alter table public.reader_commerce_entitlements enable row level security;

revoke all on table public.reader_coin_wallets, public.reader_coin_ledger,
  public.reader_store_products, public.reader_store_purchases,
  public.reader_commerce_entitlements
  from public, anon, authenticated;
grant all on table public.reader_coin_wallets, public.reader_coin_ledger,
  public.reader_store_products, public.reader_store_purchases,
  public.reader_commerce_entitlements
  to service_role;

revoke execute on function public.reader_grant_test_coins(bigint, bigint, uuid)
  from public, anon, authenticated;
grant execute on function public.reader_grant_test_coins(bigint, bigint, uuid)
  to service_role;

revoke execute on function public.reader_purchase_product(bigint, text, uuid)
  from public, anon, authenticated;
grant execute on function public.reader_purchase_product(bigint, text, uuid)
  to service_role;

revoke execute on function public.reader_rollback_test_purchases(bigint)
  from public, anon, authenticated;
grant execute on function public.reader_rollback_test_purchases(bigint)
  to service_role;

commit;
notify pgrst, 'reload schema';
