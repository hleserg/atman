-- db/schema.sql
-- Full schema reference — union of all migrations for documentation.
-- DO NOT run this directly. Use db/migrations/ instead.
-- See Makefile target: make db-migrate
--
-- This file is kept in sync for reference purposes.
-- The canonical source is the individual migration files.

-- Generated from:
-- 001_init.sql    — memories, agents, api_keys, audit_log, schema_migrations
-- 002_trust.sql   — pending_review, trust_scores, human_review_queue, quarantine
-- 003_graph.sql   — entities, relations, conflicts, graph_snapshots, memory_entities

-- See ARCHITECTURE.md §4.1-4.4 for full component documentation.

-- To view current schema of a running DB:
--   sqlite3 ./data/memoryhub.sqlite ".schema"
-- Or via Makefile:
--   make db-schema
