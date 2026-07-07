# Database Migrations

The API can run these migrations on startup against the database configured in `.env`.
This behavior is controlled with `RUN_MIGRATIONS`. The Docker stack sets it to `false`
so containers can be created without applying migrations.

Applied files are tracked in `public.schema_migrations`, so already-applied
migrations are skipped. The current SQL files also use `IF NOT EXISTS`, so they
do not recreate existing tables or indexes.

To run them manually from the host, using the current PostgreSQL container:

```powershell
cmd /c "type app\migrations\000_create_schema_migrations.sql | docker exec -i postgres-fts psql -U postgres -d postgres -v ON_ERROR_STOP=1"
cmd /c "type app\migrations\001_create_model_results_central.sql | docker exec -i postgres-fts psql -U postgres -d postgres -v ON_ERROR_STOP=1"
cmd /c "type app\migrations\002_add_model_results_central_indexes.sql | docker exec -i postgres-fts psql -U postgres -d postgres -v ON_ERROR_STOP=1"
```
