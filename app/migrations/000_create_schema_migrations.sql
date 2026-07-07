-- Tracks which SQL migrations have already been applied.

CREATE TABLE IF NOT EXISTS public.schema_migrations (
    filename text PRIMARY KEY,
    applied_at timestamp without time zone NOT NULL DEFAULT now()
);
