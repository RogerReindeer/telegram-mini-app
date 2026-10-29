begin;

create table if not exists public.reader_chapter_pricing_overrides (
  chapter_id text primary key
    references public.chapters(chapter_id) on delete cascade,
  coin_price integer not null
    check (coin_price > 0 and coin_price <= 1000000),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create or replace function public.reader_apply_chapter_pricing_rule()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_price integer;
  v_managed_by text;
  v_title text;
begin
  select price_override.coin_price, 'chapter_pricing_override'
  into v_price, v_managed_by
  from public.reader_chapter_pricing_overrides as price_override
  where price_override.chapter_id = new.chapter_id;

  if not found then
    select rule.chapter_coin_price, 'novel_pricing_rule'
    into v_price, v_managed_by
    from public.reader_novel_pricing_rules as rule
    where rule.novel_id = new.novel_id
      and rule.is_active is true;
  end if;

  if v_price is null then
    return new;
  end if;

  v_title := coalesce(
    nullif(pg_catalog.btrim(new.chapter_title), ''),
    nullif(pg_catalog.btrim(new.title), ''),
    'Глава ' || new.chapter_id
  );

  update public.reader_store_products as product
  set novel_id = new.novel_id,
      title = v_title,
      coin_price = v_price,
      metadata = coalesce(product.metadata, '{}'::jsonb) || pg_catalog.jsonb_build_object(
        'exchange_rate_rub', 1,
        'managed_by', v_managed_by
      ),
      updated_at = now()
  where product.product_type = 'chapter_unlock'
    and product.chapter_id = new.chapter_id
    and product.is_active is true;

  if not found then
    insert into public.reader_store_products (
      product_code, product_type, title, coin_price, novel_id, chapter_id,
      is_active, sort_order, metadata, updated_at
    ) values (
      'chapter:' || new.chapter_id,
      'chapter_unlock',
      v_title,
      v_price,
      new.novel_id,
      new.chapter_id,
      true,
      0,
      pg_catalog.jsonb_build_object(
        'exchange_rate_rub', 1,
        'managed_by', v_managed_by
      ),
      now()
    )
    on conflict (product_code) do update set
      product_type = excluded.product_type,
      title = excluded.title,
      coin_price = excluded.coin_price,
      novel_id = excluded.novel_id,
      chapter_id = excluded.chapter_id,
      subscription_role = null,
      duration_days = null,
      upgrade_from_role = null,
      is_active = true,
      metadata = coalesce(public.reader_store_products.metadata, '{}'::jsonb) || excluded.metadata,
      updated_at = now();
  end if;

  return new;
end;
$$;

create or replace function public.reader_set_bulk_novel_pricing(
  p_novel_ids bigint[],
  p_chapter_coin_price integer,
  p_bundle_coin_price integer
)
returns table(
  novels_updated bigint,
  chapters_priced bigint,
  bundles_priced bigint
)
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_ids bigint[];
  v_missing bigint[];
  v_novel_id bigint;
  v_chapter_count bigint;
begin
  select pg_catalog.array_agg(item.novel_id order by item.novel_id)
  into v_ids
  from (
    select distinct requested_id as novel_id
    from pg_catalog.unnest(p_novel_ids) as requested_id
    where requested_id is not null
  ) as item;

  if coalesce(pg_catalog.cardinality(v_ids), 0) = 0
     or pg_catalog.cardinality(v_ids) > 100
     or p_chapter_coin_price <= 0
     or p_chapter_coin_price > 1000000
     or p_bundle_coin_price <= 0
     or p_bundle_coin_price > 1000000 then
    raise exception 'reader_invalid_bulk_pricing';
  end if;

  select pg_catalog.array_agg(requested.novel_id order by requested.novel_id)
  into v_missing
  from pg_catalog.unnest(v_ids) as requested(novel_id)
  left join public.novels as novel on novel.novel_id = requested.novel_id
  where novel.novel_id is null;

  if coalesce(pg_catalog.cardinality(v_missing), 0) > 0 then
    raise exception 'reader_unknown_novel_ids:%', pg_catalog.array_to_string(v_missing, ',');
  end if;

  foreach v_novel_id in array v_ids
  loop
    perform pg_catalog.pg_advisory_xact_lock(
      pg_catalog.hashtextextended('reader-pricing:' || v_novel_id::text, 0)
    );
  end loop;

  insert into public.reader_novel_pricing_rules (
    novel_id, chapter_coin_price, bundle_coin_price, is_active, updated_at
  )
  select novel_id, p_chapter_coin_price, p_bundle_coin_price, true, now()
  from pg_catalog.unnest(v_ids) as novel_id
  on conflict (novel_id) do update set
    chapter_coin_price = excluded.chapter_coin_price,
    bundle_coin_price = excluded.bundle_coin_price,
    is_active = true,
    updated_at = now();

  update public.reader_store_products as product
  set novel_id = chapter.novel_id,
      title = coalesce(
        nullif(pg_catalog.btrim(chapter.chapter_title), ''),
        nullif(pg_catalog.btrim(chapter.title), ''),
        'Глава ' || chapter.chapter_id
      ),
      coin_price = coalesce(price_override.coin_price, p_chapter_coin_price),
      metadata = coalesce(product.metadata, '{}'::jsonb) || pg_catalog.jsonb_build_object(
        'exchange_rate_rub', 1,
        'managed_by', case
          when price_override.chapter_id is null then 'novel_pricing_rule'
          else 'chapter_pricing_override'
        end
      ),
      updated_at = now()
  from public.chapters as chapter
  left join public.reader_chapter_pricing_overrides as price_override
    on price_override.chapter_id = chapter.chapter_id
  where chapter.novel_id = any(v_ids)
    and product.product_type = 'chapter_unlock'
    and product.chapter_id = chapter.chapter_id
    and product.is_active is true;

  insert into public.reader_store_products (
    product_code, product_type, title, coin_price, novel_id, chapter_id,
    is_active, sort_order, metadata, updated_at
  )
  select
    'chapter:' || chapter.chapter_id,
    'chapter_unlock',
    coalesce(
      nullif(pg_catalog.btrim(chapter.chapter_title), ''),
      nullif(pg_catalog.btrim(chapter.title), ''),
      'Глава ' || chapter.chapter_id
    ),
    coalesce(price_override.coin_price, p_chapter_coin_price),
    chapter.novel_id,
    chapter.chapter_id,
    true,
    0,
    pg_catalog.jsonb_build_object(
      'exchange_rate_rub', 1,
      'managed_by', case
        when price_override.chapter_id is null then 'novel_pricing_rule'
        else 'chapter_pricing_override'
      end
    ),
    now()
  from public.chapters as chapter
  left join public.reader_chapter_pricing_overrides as price_override
    on price_override.chapter_id = chapter.chapter_id
  where chapter.novel_id = any(v_ids)
    and not exists (
      select 1
      from public.reader_store_products as existing
      where existing.product_type = 'chapter_unlock'
        and existing.chapter_id = chapter.chapter_id
        and existing.is_active is true
    )
  on conflict (product_code) do update set
    product_type = excluded.product_type,
    title = excluded.title,
    coin_price = excluded.coin_price,
    novel_id = excluded.novel_id,
    chapter_id = excluded.chapter_id,
    subscription_role = null,
    duration_days = null,
    upgrade_from_role = null,
    is_active = true,
    metadata = coalesce(public.reader_store_products.metadata, '{}'::jsonb) || excluded.metadata,
    updated_at = now();

  select count(*) into v_chapter_count
  from public.chapters as chapter
  where chapter.novel_id = any(v_ids);

  update public.reader_store_products as product
  set title = 'Вся книга · ' || coalesce(
        nullif(pg_catalog.btrim(novel.title_ru), ''),
        nullif(pg_catalog.btrim(novel.title), ''),
        'Новелла ' || novel.novel_id::text
      ),
      coin_price = p_bundle_coin_price,
      metadata = coalesce(product.metadata, '{}'::jsonb) || pg_catalog.jsonb_build_object(
        'exchange_rate_rub', 1,
        'managed_by', 'novel_pricing_rule'
      ),
      updated_at = now()
  from public.novels as novel
  where novel.novel_id = any(v_ids)
    and product.product_type = 'novel_unlock'
    and product.novel_id = novel.novel_id
    and product.is_active is true;

  insert into public.reader_store_products (
    product_code, product_type, title, coin_price, novel_id,
    is_active, sort_order, metadata, updated_at
  )
  select
    'novel:' || novel.novel_id::text,
    'novel_unlock',
    'Вся книга · ' || coalesce(
      nullif(pg_catalog.btrim(novel.title_ru), ''),
      nullif(pg_catalog.btrim(novel.title), ''),
      'Новелла ' || novel.novel_id::text
    ),
    p_bundle_coin_price,
    novel.novel_id,
    true,
    0,
    pg_catalog.jsonb_build_object(
      'exchange_rate_rub', 1,
      'managed_by', 'novel_pricing_rule'
    ),
    now()
  from public.novels as novel
  where novel.novel_id = any(v_ids)
    and not exists (
      select 1
      from public.reader_store_products as existing
      where existing.product_type = 'novel_unlock'
        and existing.novel_id = novel.novel_id
        and existing.is_active is true
    )
  on conflict (product_code) do update set
    product_type = excluded.product_type,
    title = excluded.title,
    coin_price = excluded.coin_price,
    novel_id = excluded.novel_id,
    chapter_id = null,
    subscription_role = null,
    duration_days = null,
    upgrade_from_role = null,
    is_active = true,
    metadata = coalesce(public.reader_store_products.metadata, '{}'::jsonb) || excluded.metadata,
    updated_at = now();

  return query select
    pg_catalog.cardinality(v_ids)::bigint,
    v_chapter_count,
    pg_catalog.cardinality(v_ids)::bigint;
end;
$$;

create or replace function public.reader_set_selected_chapter_prices(
  p_chapter_ids text[],
  p_coin_price integer,
  p_reset_to_default boolean default false
)
returns table(
  chapters_priced bigint,
  novels_affected bigint,
  overrides_reset boolean
)
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_ids text[];
  v_missing text[];
  v_novel_ids bigint[];
  v_novel_id bigint;
begin
  select pg_catalog.array_agg(item.chapter_id order by item.chapter_id)
  into v_ids
  from (
    select distinct pg_catalog.btrim(requested_id) as chapter_id
    from pg_catalog.unnest(p_chapter_ids) as requested_id
    where nullif(pg_catalog.btrim(requested_id), '') is not null
  ) as item;

  if p_reset_to_default is null
     or coalesce(pg_catalog.cardinality(v_ids), 0) = 0
     or pg_catalog.cardinality(v_ids) > 500
     or (p_reset_to_default is false and (
       p_coin_price is null or p_coin_price <= 0 or p_coin_price > 1000000
     ))
     or (p_reset_to_default is true and p_coin_price is not null) then
    raise exception 'reader_invalid_selected_chapter_pricing';
  end if;

  select pg_catalog.array_agg(requested.chapter_id order by requested.chapter_id)
  into v_missing
  from pg_catalog.unnest(v_ids) as requested(chapter_id)
  left join public.chapters as chapter on chapter.chapter_id = requested.chapter_id
  where chapter.chapter_id is null;

  if coalesce(pg_catalog.cardinality(v_missing), 0) > 0 then
    raise exception 'reader_unknown_chapter_ids:%', pg_catalog.array_to_string(v_missing, ',');
  end if;

  select pg_catalog.array_agg(item.novel_id order by item.novel_id)
  into v_novel_ids
  from (
    select distinct chapter.novel_id
    from public.chapters as chapter
    where chapter.chapter_id = any(v_ids)
      and chapter.novel_id is not null
  ) as item;

  if coalesce(pg_catalog.cardinality(v_novel_ids), 0) > 0 then
    foreach v_novel_id in array v_novel_ids
    loop
      perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('reader-pricing:' || v_novel_id::text, 0)
      );
    end loop;
  end if;

  if p_reset_to_default is true then
    if exists (
      select 1
      from public.chapters as chapter
      left join public.reader_novel_pricing_rules as rule
        on rule.novel_id = chapter.novel_id and rule.is_active is true
      where chapter.chapter_id = any(v_ids)
        and rule.novel_id is null
    ) then
      raise exception 'reader_missing_novel_pricing_rule';
    end if;

    delete from public.reader_chapter_pricing_overrides
    where chapter_id = any(v_ids);

    update public.reader_store_products as product
    set coin_price = rule.chapter_coin_price,
        metadata = coalesce(product.metadata, '{}'::jsonb) || pg_catalog.jsonb_build_object(
          'exchange_rate_rub', 1,
          'managed_by', 'novel_pricing_rule'
        ),
        updated_at = now()
    from public.chapters as chapter
    join public.reader_novel_pricing_rules as rule
      on rule.novel_id = chapter.novel_id and rule.is_active is true
    where chapter.chapter_id = any(v_ids)
      and product.product_type = 'chapter_unlock'
      and product.chapter_id = chapter.chapter_id
      and product.is_active is true;

    insert into public.reader_store_products (
      product_code, product_type, title, coin_price, novel_id, chapter_id,
      is_active, sort_order, metadata, updated_at
    )
    select
      'chapter:' || chapter.chapter_id,
      'chapter_unlock',
      coalesce(
        nullif(pg_catalog.btrim(chapter.chapter_title), ''),
        nullif(pg_catalog.btrim(chapter.title), ''),
        'Глава ' || chapter.chapter_id
      ),
      rule.chapter_coin_price,
      chapter.novel_id,
      chapter.chapter_id,
      true,
      0,
      pg_catalog.jsonb_build_object(
        'exchange_rate_rub', 1,
        'managed_by', 'novel_pricing_rule'
      ),
      now()
    from public.chapters as chapter
    join public.reader_novel_pricing_rules as rule
      on rule.novel_id = chapter.novel_id and rule.is_active is true
    where chapter.chapter_id = any(v_ids)
      and not exists (
        select 1
        from public.reader_store_products as existing
        where existing.product_type = 'chapter_unlock'
          and existing.chapter_id = chapter.chapter_id
          and existing.is_active is true
      )
    on conflict (product_code) do update set
      product_type = excluded.product_type,
      title = excluded.title,
      coin_price = excluded.coin_price,
      novel_id = excluded.novel_id,
      chapter_id = excluded.chapter_id,
      subscription_role = null,
      duration_days = null,
      upgrade_from_role = null,
      is_active = true,
      metadata = coalesce(public.reader_store_products.metadata, '{}'::jsonb) || excluded.metadata,
      updated_at = now();
  else
    insert into public.reader_chapter_pricing_overrides (
      chapter_id, coin_price, updated_at
    )
    select chapter_id, p_coin_price, now()
    from pg_catalog.unnest(v_ids) as chapter_id
    on conflict (chapter_id) do update set
      coin_price = excluded.coin_price,
      updated_at = now();

    update public.reader_store_products as product
    set novel_id = chapter.novel_id,
        title = coalesce(
          nullif(pg_catalog.btrim(chapter.chapter_title), ''),
          nullif(pg_catalog.btrim(chapter.title), ''),
          'Глава ' || chapter.chapter_id
        ),
        coin_price = p_coin_price,
        metadata = coalesce(product.metadata, '{}'::jsonb) || pg_catalog.jsonb_build_object(
          'exchange_rate_rub', 1,
          'managed_by', 'chapter_pricing_override'
        ),
        updated_at = now()
    from public.chapters as chapter
    where chapter.chapter_id = any(v_ids)
      and product.product_type = 'chapter_unlock'
      and product.chapter_id = chapter.chapter_id
      and product.is_active is true;

    insert into public.reader_store_products (
      product_code, product_type, title, coin_price, novel_id, chapter_id,
      is_active, sort_order, metadata, updated_at
    )
    select
      'chapter:' || chapter.chapter_id,
      'chapter_unlock',
      coalesce(
        nullif(pg_catalog.btrim(chapter.chapter_title), ''),
        nullif(pg_catalog.btrim(chapter.title), ''),
        'Глава ' || chapter.chapter_id
      ),
      p_coin_price,
      chapter.novel_id,
      chapter.chapter_id,
      true,
      0,
      pg_catalog.jsonb_build_object(
        'exchange_rate_rub', 1,
        'managed_by', 'chapter_pricing_override'
      ),
      now()
    from public.chapters as chapter
    where chapter.chapter_id = any(v_ids)
      and not exists (
        select 1
        from public.reader_store_products as existing
        where existing.product_type = 'chapter_unlock'
          and existing.chapter_id = chapter.chapter_id
          and existing.is_active is true
      )
    on conflict (product_code) do update set
      product_type = excluded.product_type,
      title = excluded.title,
      coin_price = excluded.coin_price,
      novel_id = excluded.novel_id,
      chapter_id = excluded.chapter_id,
      subscription_role = null,
      duration_days = null,
      upgrade_from_role = null,
      is_active = true,
      metadata = coalesce(public.reader_store_products.metadata, '{}'::jsonb) || excluded.metadata,
      updated_at = now();
  end if;

  return query select
    pg_catalog.cardinality(v_ids)::bigint,
    coalesce(pg_catalog.cardinality(v_novel_ids), 0)::bigint,
    p_reset_to_default;
end;
$$;

alter table public.reader_chapter_pricing_overrides enable row level security;

revoke all on table public.reader_chapter_pricing_overrides
  from public, anon, authenticated;
grant all on table public.reader_chapter_pricing_overrides
  to service_role;

revoke execute on function public.reader_set_selected_chapter_prices(text[], integer, boolean)
  from public, anon, authenticated;
grant execute on function public.reader_set_selected_chapter_prices(text[], integer, boolean)
  to service_role;

revoke execute on function public.reader_set_bulk_novel_pricing(bigint[], integer, integer)
  from public, anon, authenticated;
grant execute on function public.reader_set_bulk_novel_pricing(bigint[], integer, integer)
  to service_role;

commit;
notify pgrst, 'reload schema';
