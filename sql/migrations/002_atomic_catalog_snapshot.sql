begin;

create or replace function public.apply_catalog_snapshot(
  p_novels jsonb,
  p_chapters jsonb,
  p_fox jsonb
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_novels integer := 0;
  v_chapters integer := 0;
  v_fox integer := 0;
  v_deleted_chapters integer := 0;
  v_deleted_current_chapters integer := 0;
  v_deleted_novels integer := 0;
  v_deleted_fox integer := 0;
begin
  if jsonb_typeof(p_novels) <> 'array'
     or jsonb_typeof(p_chapters) <> 'array'
     or jsonb_typeof(p_fox) <> 'array' then
    raise exception 'snapshot arguments must be JSON arrays';
  end if;
  if jsonb_array_length(p_novels) = 0 then
    raise exception 'refusing to apply an empty novels snapshot';
  end if;

  perform pg_catalog.set_config('lock_timeout', '5s', true);
  perform pg_catalog.set_config('statement_timeout', '60s', true);
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('zefirki:catalog_snapshot', 0)
  );

  create temporary table snapshot_novels on commit drop as
  select * from pg_catalog.jsonb_to_recordset(p_novels) as x(
    novel_id bigint, code text, novel_short text, title_ru text, title_en text,
    title_original text, original_language text, post_icons text, status text,
    access_model text, schedule_mode text, early_access_mode text,
    release_year integer, author_original text, author_latin text,
    author_cyrillic text, author_translated text, cover_url text,
    description text, top_description text, bottom_description text,
    miniapp_tags jsonb, tags_tg_catalog text, tags_app_catalog jsonb,
    miniapp_visible boolean, total_chapters integer, translated_chapters integer,
    free_chapters integer, subscriber_chapters integer, keeper_chapters integer,
    early_access_chapters integer, release_free_count integer,
    premium_lead_weeks integer, premium_count integer,
    keeper_extra_chapters integer, traveler_access_through text,
    keeper_access_through text, progress_percent double precision,
    source_url_novelupdates text, source_url_official text,
    source_chapter_url text, telegram_post_url text, boosty_url text,
    boosty_premium_url text, telegraph_catalog_url text
  );

  create unique index snapshot_novels_pk on snapshot_novels(novel_id);

  -- Remove absent parents before upsert so a code may be reassigned from a
  -- removed novel. Child rows are deleted explicitly to keep accurate counts.
  delete from public.chapters c
  where not exists (
    select 1 from snapshot_novels s where s.novel_id = c.novel_id
  );
  get diagnostics v_deleted_chapters = row_count;

  delete from public.novels n
  where not exists (select 1 from snapshot_novels s where s.novel_id = n.novel_id);
  get diagnostics v_deleted_novels = row_count;

  -- Codes are nullable and unique. Clearing them inside this transaction lets
  -- two existing novels safely exchange codes in one snapshot.
  update public.novels n
  set code = null
  where exists (select 1 from snapshot_novels s where s.novel_id = n.novel_id);

  insert into public.novels (
    novel_id, code, novel_short, title_ru, title_en, title_original,
    original_language, post_icons, status, access_model, schedule_mode,
    early_access_mode, release_year, author_original, author_latin,
    author_cyrillic, author_translated, cover_url, description,
    top_description, bottom_description, miniapp_tags, tags_tg_catalog,
    tags_app_catalog, miniapp_visible, total_chapters, translated_chapters,
    free_chapters, subscriber_chapters, keeper_chapters,
    early_access_chapters, release_free_count, premium_lead_weeks,
    premium_count, keeper_extra_chapters, traveler_access_through,
    keeper_access_through, progress_percent, source_url_novelupdates,
    source_url_official, source_chapter_url, telegram_post_url, boosty_url,
    boosty_premium_url, telegraph_catalog_url
  )
  select
    novel_id, code, novel_short, title_ru, title_en, title_original,
    original_language, post_icons, status, access_model, schedule_mode,
    early_access_mode, release_year, author_original, author_latin,
    author_cyrillic, author_translated, cover_url, description,
    top_description, bottom_description, miniapp_tags, tags_tg_catalog,
    tags_app_catalog, coalesce(miniapp_visible, true),
    coalesce(total_chapters, 0), coalesce(translated_chapters, 0),
    coalesce(free_chapters, 0), coalesce(subscriber_chapters, 0),
    coalesce(keeper_chapters, 0), coalesce(early_access_chapters, 0),
    coalesce(release_free_count, 0), coalesce(premium_lead_weeks, 0),
    coalesce(premium_count, 0), coalesce(keeper_extra_chapters, 0),
    traveler_access_through, keeper_access_through,
    coalesce(progress_percent, 0), source_url_novelupdates,
    source_url_official, source_chapter_url, telegram_post_url, boosty_url,
    boosty_premium_url, telegraph_catalog_url
  from snapshot_novels
  on conflict (novel_id) do update set
    code=excluded.code, novel_short=excluded.novel_short, title_ru=excluded.title_ru,
    title_en=excluded.title_en, title_original=excluded.title_original,
    original_language=excluded.original_language, post_icons=excluded.post_icons,
    status=excluded.status, access_model=excluded.access_model,
    schedule_mode=excluded.schedule_mode, early_access_mode=excluded.early_access_mode,
    release_year=excluded.release_year, author_original=excluded.author_original,
    author_latin=excluded.author_latin, author_cyrillic=excluded.author_cyrillic,
    author_translated=excluded.author_translated, cover_url=excluded.cover_url,
    description=excluded.description, top_description=excluded.top_description,
    bottom_description=excluded.bottom_description, miniapp_tags=excluded.miniapp_tags,
    tags_tg_catalog=excluded.tags_tg_catalog, tags_app_catalog=excluded.tags_app_catalog,
    miniapp_visible=excluded.miniapp_visible, total_chapters=excluded.total_chapters,
    translated_chapters=excluded.translated_chapters, free_chapters=excluded.free_chapters,
    subscriber_chapters=excluded.subscriber_chapters, keeper_chapters=excluded.keeper_chapters,
    early_access_chapters=excluded.early_access_chapters,
    release_free_count=excluded.release_free_count,
    premium_lead_weeks=excluded.premium_lead_weeks, premium_count=excluded.premium_count,
    keeper_extra_chapters=excluded.keeper_extra_chapters,
    traveler_access_through=excluded.traveler_access_through,
    keeper_access_through=excluded.keeper_access_through,
    progress_percent=excluded.progress_percent,
    source_url_novelupdates=excluded.source_url_novelupdates,
    source_url_official=excluded.source_url_official,
    source_chapter_url=excluded.source_chapter_url,
    telegram_post_url=excluded.telegram_post_url, boosty_url=excluded.boosty_url,
    boosty_premium_url=excluded.boosty_premium_url,
    telegraph_catalog_url=excluded.telegraph_catalog_url;
  get diagnostics v_novels = row_count;

  create temporary table snapshot_chapters on commit drop as
  select * from pg_catalog.jsonb_to_recordset(p_chapters) as x(
    chapter_id text, novel_id bigint, volume_no integer, volume_title text,
    chapter_no integer, source_chapter_no text, part_no integer,
    chapter_title text, planned_translation_date date, translation_date date,
    free_release_date date, premium_release_date date, prepared_platforms text,
    scheduled_platforms text, publishing_platforms text,
    telegraph_premium_url text, telegraph_premium_code text,
    telegraph_free_url text, telegraph_free_code text,
    traveler_access boolean, traveler_access_source text,
    keeper_access boolean, keeper_access_order integer,
    keeper_access_source text, qa_status boolean
  );
  create unique index snapshot_chapters_pk on snapshot_chapters(chapter_id);

  insert into public.chapters (
    chapter_id, novel_id, volume_no, volume_title, chapter_no,
    source_chapter_no, part_no, chapter_title, planned_translation_date,
    translation_date, free_release_date, premium_release_date,
    prepared_platforms, scheduled_platforms, publishing_platforms,
    telegraph_premium_url, telegraph_premium_code, telegraph_free_url,
    telegraph_free_code, traveler_access, traveler_access_source,
    keeper_access, keeper_access_order, keeper_access_source, qa_status
  )
  select
    chapter_id, novel_id, volume_no, volume_title, coalesce(chapter_no, 0),
    source_chapter_no, part_no, chapter_title, planned_translation_date,
    translation_date, free_release_date, premium_release_date,
    prepared_platforms, scheduled_platforms, publishing_platforms,
    telegraph_premium_url, telegraph_premium_code, telegraph_free_url,
    telegraph_free_code, coalesce(traveler_access, false), traveler_access_source,
    coalesce(keeper_access, false), keeper_access_order, keeper_access_source,
    coalesce(qa_status, false)
  from snapshot_chapters
  on conflict (chapter_id) do update set
    novel_id=excluded.novel_id, volume_no=excluded.volume_no,
    volume_title=excluded.volume_title, chapter_no=excluded.chapter_no,
    source_chapter_no=excluded.source_chapter_no, part_no=excluded.part_no,
    chapter_title=excluded.chapter_title,
    planned_translation_date=excluded.planned_translation_date,
    translation_date=excluded.translation_date,
    free_release_date=excluded.free_release_date,
    premium_release_date=excluded.premium_release_date,
    prepared_platforms=excluded.prepared_platforms,
    scheduled_platforms=excluded.scheduled_platforms,
    publishing_platforms=excluded.publishing_platforms,
    telegraph_premium_url=excluded.telegraph_premium_url,
    telegraph_premium_code=excluded.telegraph_premium_code,
    telegraph_free_url=excluded.telegraph_free_url,
    telegraph_free_code=excluded.telegraph_free_code,
    traveler_access=excluded.traveler_access,
    traveler_access_source=excluded.traveler_access_source,
    keeper_access=excluded.keeper_access,
    keeper_access_order=excluded.keeper_access_order,
    keeper_access_source=excluded.keeper_access_source,
    qa_status=excluded.qa_status;
  get diagnostics v_chapters = row_count;

  delete from public.chapters c
  where not exists (select 1 from snapshot_chapters s where s.chapter_id = c.chapter_id);
  get diagnostics v_deleted_current_chapters = row_count;
  v_deleted_chapters := v_deleted_chapters + v_deleted_current_chapters;

  create temporary table snapshot_fox on commit drop as
  select * from pg_catalog.jsonb_to_recordset(p_fox) as x(name text, url text);
  create unique index snapshot_fox_pk on snapshot_fox(name);
  insert into public.fox(name, url)
  select name, url from snapshot_fox
  on conflict (name) do update set url=excluded.url;
  get diagnostics v_fox = row_count;

  delete from public.fox f
  where not exists (select 1 from snapshot_fox s where s.name = f.name);
  get diagnostics v_deleted_fox = row_count;

  return pg_catalog.jsonb_build_object(
    'novels_upserted', v_novels,
    'chapters_upserted', v_chapters,
    'fox_upserted', v_fox,
    'stale_chapters_deleted', v_deleted_chapters,
    'stale_novels_deleted', v_deleted_novels,
    'stale_fox_deleted', v_deleted_fox
  );
end;
$$;

revoke execute on function public.apply_catalog_snapshot(jsonb, jsonb, jsonb)
  from public, anon, authenticated;
grant execute on function public.apply_catalog_snapshot(jsonb, jsonb, jsonb)
  to service_role;

commit;
notify pgrst, 'reload schema';
