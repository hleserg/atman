-- Migration 0018: accept reflection overload jobs in the shared maintenance queue.
--
-- HLE-30 added JobName.reflection_overload_check. Existing databases created by
-- migration 0011 have a CHECK constraint that rejects the new enum value, so the
-- scheduler crashes before a worker can process the overload monitor job.
--
-- Usage:
--   psql -d atman -f migrations/versions/0018_maintenance_reflection_overload_job.sql
--
-- Rollback:
--   ALTER TABLE public.maintenance_jobs DROP CONSTRAINT IF EXISTS maintenance_jobs_job_name_check;
--   ALTER TABLE public.maintenance_jobs ADD CONSTRAINT maintenance_jobs_job_name_check
--     CHECK (job_name IN (
--       'salience_decay',
--       'memory_guardian_scan',
--       'mrebel_extract',
--       'lingvo_enrich',
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
        'reflection_overload_check',
        'entity_merge',
        'other'
    ));
