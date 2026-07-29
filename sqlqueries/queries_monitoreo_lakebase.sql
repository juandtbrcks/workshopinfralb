-- Queries de monitoreo para el proyecto Lakebase (grupo-infra-ws / infra_ws_jgordon)
-- Nota: estas queries corren directamente contra la base Postgres de Lakebase, no contra un warehouse SQL de Databricks.

-- 1. Consultar las tablas y su tamaño en la base de datos infra_ws_jgordon
SELECT
  current_database() AS table_catalog,
  n.nspname AS table_schema,
  c.relname AS table_name,
  pg_total_relation_size(c.oid) / (1024*1024) AS size_mb
FROM
  pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE
  c.relkind = 'r'
  AND n.nspname = 'public'
ORDER BY
  size_mb DESC;

-- 2. Consultar el número de filas por tabla en la base de datos infra_ws_jgordon
SELECT 
  relname AS table_name,
  n_live_tup AS row_count
FROM  
  pg_stat_user_tables
WHERE  
  schemaname = 'public'
ORDER BY  
  row_count DESC;

-- 3. Consultar las últimas consultas ejecutadas sobre la base de datos infra_ws_jgordon
SELECT 
  usename AS user_name,
  query AS query_text,
  query_start AS start_time,
  state_change AS end_time,
  state AS status
FROM  
  pg_stat_activity
WHERE  
  datname = current_database()
ORDER BY  
  query_start DESC
LIMIT 50;

-- 4. Queries frecuentemente ejecutados
SELECT
    query,
    calls,
    total_exec_time,
    rows,
    100.0 * shared_blks_hit / nullif(shared_blks_hit + shared_blks_read, 0) AS hit_percent
FROM pg_stat_statements
ORDER BY calls DESC
LIMIT 20;
