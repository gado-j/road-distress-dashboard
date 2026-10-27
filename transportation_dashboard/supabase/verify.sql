-- Read-only checks after applying schema and creating private buckets.
select c.relname as table_name, c.relrowsecurity as rls_enabled,
  has_table_privilege('anon', c.oid, 'SELECT') as anonymous_select,
  has_table_privilege('authenticated', c.oid, 'SELECT') as browser_select,
  has_table_privilege('service_role', c.oid, 'INSERT') as backend_insert
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relname in
  ('roads', 'inspections', 'media', 'analysis_runs', 'predictions', 'expert_reviews', 'analysis_artifacts')
order by c.relname;

select id, public, file_size_limit, allowed_mime_types from storage.buckets
where id in ('inspection-media', 'analysis-artifacts');

select tablename, policyname, roles, cmd from pg_policies
where (schemaname = 'public' and tablename in
  ('roads', 'inspections', 'media', 'analysis_runs', 'predictions', 'expert_reviews', 'analysis_artifacts'))
  or (schemaname = 'storage' and tablename = 'objects');
