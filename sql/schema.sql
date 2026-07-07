-- Zefirki MiniApp — Supabase schema.
--
-- Собрано напрямую из фактического использования таблиц/колонок в коде
-- этого репозитория (app/services/*.py, app/routers/*.py) по состоянию
-- на текущую версию сайта — не по старым архивным дампам.
--
-- Безопасно выполнять повторно: все команды идемпотентны
-- (create table if not exists / add column if not exists).

-- =====================================================================
-- novels
-- =====================================================================
-- "slug" в коде — это колонка code (см. catalog.py: get_novel_by_slug
-- фильтрует по code). Отдельной колонки slug/title в БД нет, они
-- вычисляются на лету в adapt_novel_from_db().

create table if not exists public.novels (
  novel_id bigint primary key,
  code text unique,
  novel_short text,
  title_ru text,
  title_en text,
  title_original text,
  original_language text,
  post_icons text,
  status text,
  access_model text,
  schedule_mode text,
  early_access_mode text,
  release_year integer,
  author_original text,
  author_latin text,
  author_cyrillic text,
  author_translated text,
  cover_url text,
  description text,
  top_description text,
  bottom_description text,
  miniapp_tags jsonb,
  tags_tg_catalog text,
  tags_app_catalog jsonb,
  miniapp_visible boolean not null default true,
  total_chapters integer not null default 0,
  translated_chapters integer not null default 0,
  free_chapters integer not null default 0,
  subscriber_chapters integer not null default 0,
  keeper_chapters integer not null default 0,
  early_access_chapters integer not null default 0,
  progress_percent double precision not null default 0,
  source_url_novelupdates text,
  source_url_official text,
  source_chapter_url text,
  telegram_post_url text,
  boosty_url text,
  boosty_premium_url text,
  telegraph_catalog_url text,
  created_at timestamptz not null default now()
);

alter table public.novels add column if not exists code text;
alter table public.novels add column if not exists novel_short text;
alter table public.novels add column if not exists title_en text;
alter table public.novels add column if not exists title_original text;
alter table public.novels add column if not exists original_language text;
alter table public.novels add column if not exists post_icons text;
alter table public.novels add column if not exists status text;
alter table public.novels add column if not exists access_model text;
alter table public.novels add column if not exists schedule_mode text;
alter table public.novels add column if not exists early_access_mode text;
alter table public.novels add column if not exists release_year integer;
alter table public.novels add column if not exists author_original text;
alter table public.novels add column if not exists author_latin text;
alter table public.novels add column if not exists author_cyrillic text;
alter table public.novels add column if not exists author_translated text;
alter table public.novels add column if not exists cover_url text;
alter table public.novels add column if not exists description text;
alter table public.novels add column if not exists top_description text;
alter table public.novels add column if not exists bottom_description text;
alter table public.novels add column if not exists miniapp_tags jsonb;
alter table public.novels add column if not exists tags_tg_catalog text;
alter table public.novels add column if not exists tags_app_catalog jsonb;
alter table public.novels add column if not exists miniapp_visible boolean not null default true;
alter table public.novels add column if not exists total_chapters integer not null default 0;
alter table public.novels add column if not exists translated_chapters integer not null default 0;
alter table public.novels add column if not exists free_chapters integer not null default 0;
alter table public.novels add column if not exists subscriber_chapters integer not null default 0;
alter table public.novels add column if not exists keeper_chapters integer not null default 0;
alter table public.novels add column if not exists early_access_chapters integer not null default 0;
alter table public.novels add column if not exists progress_percent double precision not null default 0;
alter table public.novels add column if not exists source_url_novelupdates text;
alter table public.novels add column if not exists source_url_official text;
alter table public.novels add column if not exists source_chapter_url text;
alter table public.novels add column if not exists telegram_post_url text;
alter table public.novels add column if not exists boosty_url text;
alter table public.novels add column if not exists boosty_premium_url text;
alter table public.novels add column if not exists telegraph_catalog_url text;
alter table public.novels add column if not exists created_at timestamptz not null default now();

-- =====================================================================
-- chapters
-- =====================================================================

create table if not exists public.chapters (
  chapter_id text primary key,
  novel_id bigint references public.novels(novel_id),
  volume_no integer,
  volume_title text,
  chapter_no integer not null default 0,
  source_chapter_no integer,
  part_no integer,
  chapter_title text,
  planned_translation_date date,
  translation_date date,
  free_release_date date,
  premium_release_date date,
  prepared_platforms text,
  scheduled_platforms text,
  publishing_platforms text,
  telegraph_premium_url text,
  telegraph_premium_code text,
  telegraph_free_url text,
  telegraph_free_code text,
  qa_status boolean not null default false,
  constraint chapters_chapter_id_format check (chapter_id ~ '^\d+-\d+(-\d+)?$')
);

alter table public.chapters add column if not exists volume_no integer;
alter table public.chapters add column if not exists volume_title text;
alter table public.chapters add column if not exists source_chapter_no integer;
alter table public.chapters add column if not exists part_no integer;
alter table public.chapters add column if not exists chapter_title text;
alter table public.chapters add column if not exists planned_translation_date date;
alter table public.chapters add column if not exists translation_date date;
alter table public.chapters add column if not exists free_release_date date;
alter table public.chapters add column if not exists premium_release_date date;
alter table public.chapters add column if not exists prepared_platforms text;
alter table public.chapters add column if not exists scheduled_platforms text;
alter table public.chapters add column if not exists publishing_platforms text;
alter table public.chapters add column if not exists telegraph_premium_url text;
alter table public.chapters add column if not exists telegraph_premium_code text;
alter table public.chapters add column if not exists telegraph_free_url text;
alter table public.chapters add column if not exists telegraph_free_code text;
alter table public.chapters add column if not exists qa_status boolean not null default false;

-- =====================================================================
-- fox (декоративные лисички библиотеки)
-- =====================================================================
-- Код читает/пишет только name и url (см. catalog.py:430, sync.py fox
-- upsert). Если в БД остался старый image_url — можно оставить как есть,
-- код его больше не использует.

create table if not exists public.fox (
  name text primary key,
  url text
);

alter table public.fox add column if not exists url text;

-- =====================================================================
-- Синхронизация из Google Sheets / MiniAppSync.gs
-- =====================================================================

create table if not exists public.sync_runs (
  sync_id bigint generated always as identity primary key,
  source text,
  schema_version integer,
  status text,
  novels_count integer default 0,
  chapters_count integer default 0,
  fox_count integer default 0,
  warnings jsonb default '[]'::jsonb,
  error_message text,
  started_at timestamptz default now(),
  finished_at timestamptz
);

-- =====================================================================
-- Состояние читателя (библиотека, прогресс главы)
-- =====================================================================

create table if not exists public.user_novel_state (
  telegram_user_id bigint not null,
  novel_id bigint not null references public.novels(novel_id),
  is_favorite boolean not null default false,
  is_finished boolean not null default false,
  is_hidden boolean not null default false,
  is_reading boolean not null default false,
  last_chapter_id text references public.chapters(chapter_id),
  last_read_at timestamptz,
  updated_at timestamptz not null default now(),
  primary key (telegram_user_id, novel_id)
);

create table if not exists public.user_chapter_progress (
  telegram_user_id bigint not null,
  chapter_id text not null references public.chapters(chapter_id),
  progress_percent double precision not null default 0,
  scroll_position integer not null default 0,
  completed boolean not null default false,
  last_read_at timestamptz,
  primary key (telegram_user_id, chapter_id)
);

-- =====================================================================
-- Оплаты, подписки Tribute, бандлы Boosty, ручные бандлы
-- =====================================================================

create table if not exists public.payment_events (
  provider text not null,
  event_hash text not null,
  event_name text,
  telegram_user_id bigint,
  external_plan_id text,
  payload jsonb,
  status text,
  error_message text,
  processed_at timestamptz,
  created_at timestamptz not null default now(),
  primary key (provider, event_hash)
);

create table if not exists public.user_subscriptions (
  telegram_user_id bigint not null,
  provider text not null,
  external_plan_id text not null,
  access_role text,
  status text,
  subscription_type text,
  auto_renew boolean,
  started_at timestamptz,
  expires_at timestamptz,
  cancelled_at timestamptz,
  renewed_at timestamptz,
  telegram_username text,
  provider_user_id text,
  primary key (telegram_user_id, provider, external_plan_id)
);

create table if not exists public.boosty_products (
  boosty_bundle_key text primary key,
  novel_id bigint references public.novels(novel_id),
  access_type text,
  product_name text
);

create table if not exists public.boosty_orders (
  boosty_order_id text primary key,
  boosty_bundle_key text references public.boosty_products(boosty_bundle_key),
  buyer_email text,
  buyer_name text,
  amount numeric,
  currency text,
  payment_status text,
  purchased_at timestamptz,
  telegram_user_id bigint,
  claimed_at timestamptz,
  raw_email jsonb
);

-- user_entitlements — полный доступ к книге (Boosty-бандл или ручная
-- выдача по telegram_user_id, см. PROJECT-память "manual full_book grant").
create table if not exists public.user_entitlements (
  telegram_user_id bigint not null,
  novel_id bigint not null references public.novels(novel_id),
  source_type text not null,
  source_id text not null,
  access_type text,
  granted_at timestamptz not null default now(),
  expires_at timestamptz,
  revoked_at timestamptz,
  metadata jsonb,
  primary key (telegram_user_id, novel_id, source_type, source_id)
);

alter table public.user_entitlements add column if not exists access_type text;
alter table public.user_entitlements add column if not exists granted_at timestamptz not null default now();
alter table public.user_entitlements add column if not exists expires_at timestamptz;
alter table public.user_entitlements add column if not exists revoked_at timestamptz;
alter table public.user_entitlements add column if not exists metadata jsonb;

-- Ручная выдача полного доступа конкретному пользователю к конкретной книге:
-- insert into public.user_entitlements
--   (telegram_user_id, novel_id, source_type, source_id, access_type, granted_at)
-- values
--   (ЕГО_TELEGRAM_ID, ID_НОВЕЛЛЫ, 'manual', 'manual-'||ЕГО_TELEGRAM_ID||'-'||ID_НОВЕЛЛЫ, 'full_book', now());

NOTIFY pgrst, 'reload schema';
