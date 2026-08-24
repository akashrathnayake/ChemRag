-- Runs automatically on first container start (mounted into
-- /docker-entrypoint-initdb.d/ of the postgres image).
-- Table creation itself is handled by SQLAlchemy (db/database.py:init_db),
-- this file only guarantees the extension exists as early as possible.
CREATE EXTENSION IF NOT EXISTS vector;
