# Database Migrations

Run these files in filename order.

From the host, using the current PostgreSQL container:

```powershell
cmd /c "type app\migrations\000_create_schema_migrations.sql | docker exec -i postgres-fts psql -U postgres -d postgres -v ON_ERROR_STOP=1"
cmd /c "type app\migrations\001_create_model_results_central.sql | docker exec -i postgres-fts psql -U postgres -d postgres -v ON_ERROR_STOP=1"
cmd /c "type app\migrations\002_add_model_results_central_indexes.sql | docker exec -i postgres-fts psql -U postgres -d postgres -v ON_ERROR_STOP=1"
```

The files are idempotent: they can be run again without recreating existing tables or indexes.
