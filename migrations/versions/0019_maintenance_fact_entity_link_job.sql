-- Migration 0019: accept fact_entity_link jobs in the shared maintenance queue.
--
-- Post-write scheduling enqueues JobName.fact_entity_link after fact writes.
-- Without widening the CHECK constraint, inserts fail on existing DBs created
-- from migrations 0011/0018.
--
-- Usage:
--   psql -d atman -f migrations/versions/0019_maintenance_fact_entity_link_job.sql
--
-- Rollback:
--   ALTER TABLE public.maintenance_jobs DROP CONSTRAINT IF EXISTS maintenance_jobs_job_name_check;
--   ALTER TABLE public.maintenance_jobs ADD CONSTRAINT maintenance_jobs_job_name_check
--     CHECK (job_name IN (
--       'salience_decay',
--       'memory_guardian_scan',
--       'mrebel_extract',
--       'lingvo_enrich',
--       'reflection_overload_check',
--       'entity_merge',
--       'other'
--     ));

ALTER TABLE public.maintenance_jobs
    DROP CONSTRAINT IF EXISTS maintenance_jobs_job_name_check;

ALTER TABLE public.maintenance_jobs
    ADD CONSTRAINT maintenance_jobs_job_name_check
    CHECK (job_name IN (
        'salience_decay',
        'memory_guardian_scan',
        'mrebel_extract',
        'lingvo_enrich',
        'fact_entity_link',
        'reflection_overload_check',
        'entity_merge',
        'other'
    ));
