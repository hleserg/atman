-- Migration 0021: accept fact_entity_link jobs in the shared maintenance queue.
--
-- Entity-link enrichment after fact writes schedules JobName.fact_entity_link.
-- Existing databases created by migrations 0011/0018 reject the new enum value.
--
-- Usage:
--   psql -d atman -f migrations/versions/0021_maintenance_fact_entity_link_job.sql
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
