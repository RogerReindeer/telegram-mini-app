# Supabase schema

This directory is the reproducible database contract for the Mini App.

For a new empty project, run `schema.sql` once and then run every file in
`migrations/` in numeric order. **Do not run `schema.sql` against an existing
project.** For the existing `itvirexpgztwivqavpxt` project, run migrations
`001`, `002`, and `003` in numeric order. Migration `001` contains the explicit
legacy-column conversion required by that project. Every migration is written
to be safe to retry, but it should still be tested on a staging project first.

The backend uses only the Supabase `service_role` key. Browser roles (`anon`
and `authenticated`) receive no direct table or RPC access. Never expose the
service-role key in JavaScript or Telegram WebView configuration.

After applying migrations:

1. Run the Supabase Security Advisor and Performance Advisor.
2. Call `/ready` and confirm HTTP 200.
3. Send a validation-only sync, then one small full snapshot.
4. Verify `sync_runs` and compare catalog counts before enabling scheduled sync.

`002_atomic_catalog_snapshot.sql` is required before deploying the matching
application code: full snapshots now call `apply_catalog_snapshot` instead of
performing multiple independent REST writes.
