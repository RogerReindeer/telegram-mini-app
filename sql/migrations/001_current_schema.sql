begin;

-- Bring the legacy commerce tables used by the current production project to
-- the column names expected by app/services/payments.py. CREATE TABLE IF NOT
-- EXISTS does not add missing columns to an already existing table.
alter table public.payment_events add column if not exists event_name text;
alter table public.payment_events add column if not exists telegram_user_id bigint;
alter table public.payment_events add column if not exists external_plan_id text;
alter table public.payment_events add column if not exists status text;
alter table public.payment_events add column if not exists error_message text;
alter table public.payment_events add column if not exists processed_at timestamptz;
create unique index if not exists payment_events_provider_hash_uidx
  on public.payment_events(provider, event_hash);

alter table public.user_subscriptions add column if not exists provider text;
alter table public.user_subscriptions add column if not exists external_plan_id text;
alter table public.user_subscriptions add column if not exists access_role text;
alter table public.user_subscriptions add column if not exists subscription_type text;
alter table public.user_subscriptions add column if not exists auto_renew boolean default false;
alter table public.user_subscriptions add column if not exists started_at timestamptz;
alter table public.user_subscriptions add column if not exists cancelled_at timestamptz;
alter table public.user_subscriptions add column if not exists renewed_at timestamptz;
alter table public.user_subscriptions add column if not exists telegram_username text;
alter table public.user_subscriptions add column if not exists provider_user_id text;
alter table public.user_subscriptions add column if not exists updated_at timestamptz not null default now();
create unique index if not exists user_subscriptions_provider_plan_uidx
  on public.user_subscriptions(telegram_user_id, provider, external_plan_id);

alter table public.boosty_products add column if not exists boosty_bundle_key text;
alter table public.boosty_products add column if not exists novel_id bigint;
alter table public.boosty_products add column if not exists access_type text;
alter table public.boosty_products add column if not exists product_name text;
update public.boosty_products
set boosty_bundle_key = coalesce(boosty_bundle_key, product_id),
    product_name = coalesce(product_name, title),
    access_type = coalesce(access_type, role)
where boosty_bundle_key is null or product_name is null or access_type is null;
alter table public.boosty_products drop constraint if exists boosty_products_pkey;
alter table public.boosty_products alter column product_id drop not null;
alter table public.boosty_products alter column boosty_bundle_key set not null;
alter table public.boosty_products add constraint boosty_products_pkey primary key (boosty_bundle_key);

alter table public.boosty_orders add column if not exists boosty_order_id text;
alter table public.boosty_orders add column if not exists boosty_bundle_key text;
alter table public.boosty_orders add column if not exists buyer_email text;
alter table public.boosty_orders add column if not exists buyer_name text;
alter table public.boosty_orders add column if not exists amount numeric;
alter table public.boosty_orders add column if not exists currency text;
alter table public.boosty_orders add column if not exists payment_status text;
alter table public.boosty_orders add column if not exists purchased_at timestamptz;
alter table public.boosty_orders add column if not exists claimed_at timestamptz;
alter table public.boosty_orders add column if not exists raw_email jsonb;
update public.boosty_orders
set boosty_order_id = coalesce(boosty_order_id, order_id),
    boosty_bundle_key = coalesce(
      boosty_bundle_key,
      payload ->> 'boosty_bundle_key',
      payload ->> 'product_id'
    ),
    purchased_at = coalesce(purchased_at, created_at),
    raw_email = coalesce(raw_email, payload)
where boosty_order_id is null
   or boosty_bundle_key is null
   or purchased_at is null
   or raw_email is null;
alter table public.boosty_orders drop constraint if exists boosty_orders_pkey;
alter table public.boosty_orders alter column order_id drop not null;
alter table public.boosty_orders alter column boosty_order_id set not null;
alter table public.boosty_orders add constraint boosty_orders_pkey primary key (boosty_order_id);
alter table public.boosty_orders drop constraint if exists boosty_orders_boosty_bundle_key_fkey;
alter table public.boosty_orders add constraint boosty_orders_boosty_bundle_key_fkey
  foreign key (boosty_bundle_key) references public.boosty_products(boosty_bundle_key);

alter table public.user_entitlements add column if not exists source_type text;
alter table public.user_entitlements add column if not exists source_id text;
update public.user_entitlements
set source_type = coalesce(source_type, 'legacy'),
    source_id = coalesce(
      source_id,
      'legacy-' || md5(concat_ws(
        '|', telegram_user_id::text, novel_id::text, role,
        expires_at::text, ctid::text
      ))
    )
where source_type is null or source_id is null;
create unique index if not exists user_entitlements_source_uidx
  on public.user_entitlements(telegram_user_id, novel_id, source_type, source_id);

-- Columns introduced after the restored baseline schema.
alter table public.novels add column if not exists release_free_count integer not null default 0;
alter table public.novels add column if not exists premium_lead_weeks integer not null default 0;
alter table public.novels add column if not exists premium_count integer not null default 0;
alter table public.novels add column if not exists keeper_extra_chapters integer not null default 0;
alter table public.novels add column if not exists traveler_access_through text;
alter table public.novels add column if not exists keeper_access_through text;

alter table public.chapters alter column source_chapter_no type text using source_chapter_no::text;
alter table public.chapters add column if not exists traveler_access boolean not null default false;
alter table public.chapters add column if not exists traveler_access_source text;
alter table public.chapters add column if not exists keeper_access boolean not null default false;
alter table public.chapters add column if not exists keeper_access_order integer;
alter table public.chapters add column if not exists keeper_access_source text;

alter table public.user_chapter_progress add column if not exists novel_id bigint;
update public.user_chapter_progress p
set novel_id = c.novel_id
from public.chapters c
where p.chapter_id = c.chapter_id and p.novel_id is null;
alter table public.user_chapter_progress alter column novel_id set not null;
-- Full-snapshot pruning must not be blocked by reader state. User state tied
-- to removed catalog records is discarded; the last-chapter pointer is reset.
alter table public.chapters drop constraint if exists chapters_novel_id_fkey;
alter table public.chapters add constraint chapters_novel_id_fkey
  foreign key (novel_id) references public.novels(novel_id) on delete cascade;
alter table public.user_novel_state drop constraint if exists user_novel_state_novel_id_fkey;
alter table public.user_novel_state add constraint user_novel_state_novel_id_fkey
  foreign key (novel_id) references public.novels(novel_id) on delete cascade;
alter table public.user_novel_state drop constraint if exists user_novel_state_last_chapter_id_fkey;
alter table public.user_novel_state add constraint user_novel_state_last_chapter_id_fkey
  foreign key (last_chapter_id) references public.chapters(chapter_id) on delete set null;
alter table public.user_chapter_progress drop constraint if exists user_chapter_progress_chapter_id_fkey;
alter table public.user_chapter_progress add constraint user_chapter_progress_chapter_id_fkey
  foreign key (chapter_id) references public.chapters(chapter_id) on delete cascade;
alter table public.user_chapter_progress drop constraint if exists user_chapter_progress_novel_id_fkey;
alter table public.user_chapter_progress add constraint user_chapter_progress_novel_id_fkey
  foreign key (novel_id) references public.novels(novel_id) on delete cascade;
alter table public.boosty_products drop constraint if exists boosty_products_novel_id_fkey;
alter table public.boosty_products add constraint boosty_products_novel_id_fkey
  foreign key (novel_id) references public.novels(novel_id) on delete set null;
alter table public.user_entitlements drop constraint if exists user_entitlements_novel_id_fkey;
alter table public.user_entitlements add constraint user_entitlements_novel_id_fkey
  foreign key (novel_id) references public.novels(novel_id) on delete cascade;

create table if not exists public.analytics_events (
  event_id text primary key,
  telegram_user_id bigint not null,
  session_id text,
  event_name text not null,
  novel_id bigint,
  chapter_id text,
  source text not null default 'direct',
  section text,
  action text,
  access_type text,
  subscription_type text,
  value_int bigint,
  value_float double precision,
  value_text text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.analytics_user_profiles (
  telegram_user_id bigint primary key,
  first_seen_at timestamptz not null,
  last_seen_at timestamptz not null,
  first_source text not null default 'direct',
  current_source text not null default 'direct',
  total_events bigint not null default 0
);

create or replace function public.update_analytics_user_profile()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  insert into public.analytics_user_profiles (
    telegram_user_id, first_seen_at, last_seen_at, first_source, current_source, total_events
  ) values (
    new.telegram_user_id, new.created_at, new.created_at, new.source, new.source, 1
  )
  on conflict (telegram_user_id) do update set
    last_seen_at = greatest(public.analytics_user_profiles.last_seen_at, excluded.last_seen_at),
    current_source = excluded.current_source,
    total_events = public.analytics_user_profiles.total_events + 1;
  return new;
end;
$$;

drop trigger if exists analytics_events_profile_trigger on public.analytics_events;
create trigger analytics_events_profile_trigger
after insert on public.analytics_events
for each row execute function public.update_analytics_user_profile();

create index if not exists chapters_novel_order_idx
  on public.chapters(novel_id, chapter_no, part_no);
create index if not exists user_chapter_progress_user_time_idx
  on public.user_chapter_progress(telegram_user_id, last_read_at desc);
create index if not exists user_subscriptions_user_status_expiry_idx
  on public.user_subscriptions(telegram_user_id, status, expires_at);
create index if not exists user_entitlements_user_novel_idx
  on public.user_entitlements(telegram_user_id, novel_id);
create index if not exists analytics_events_created_idx on public.analytics_events(created_at desc);
create index if not exists analytics_events_user_created_idx
  on public.analytics_events(telegram_user_id, created_at desc);
create index if not exists analytics_events_name_created_idx
  on public.analytics_events(event_name, created_at desc);

-- The browser never connects to these tables directly; the FastAPI backend
-- uses the service role. RLS plus explicit grants make that boundary visible.
alter table public.novels enable row level security;
alter table public.chapters enable row level security;
alter table public.fox enable row level security;
alter table public.sync_runs enable row level security;
alter table public.user_novel_state enable row level security;
alter table public.user_chapter_progress enable row level security;
alter table public.payment_events enable row level security;
alter table public.user_subscriptions enable row level security;
alter table public.boosty_products enable row level security;
alter table public.boosty_orders enable row level security;
alter table public.user_entitlements enable row level security;
alter table public.analytics_events enable row level security;
alter table public.analytics_user_profiles enable row level security;

revoke all on table public.novels, public.chapters, public.fox, public.sync_runs,
  public.user_novel_state, public.user_chapter_progress, public.payment_events,
  public.user_subscriptions, public.boosty_products, public.boosty_orders,
  public.user_entitlements, public.analytics_events, public.analytics_user_profiles
  from anon, authenticated;
grant all on table public.novels, public.chapters, public.fox, public.sync_runs,
  public.user_novel_state, public.user_chapter_progress, public.payment_events,
  public.user_subscriptions, public.boosty_products, public.boosty_orders,
  public.user_entitlements, public.analytics_events, public.analytics_user_profiles
  to service_role;
grant usage, select on all sequences in schema public to service_role;

revoke execute on function public.update_analytics_user_profile() from public, anon, authenticated;
grant execute on function public.update_analytics_user_profile() to service_role;

commit;
notify pgrst, 'reload schema';
