-- scripts/db_health.sql — Diagnostic de santé PostgreSQL (Chap 23 §3.1).
-- Usage : docker exec -i {nom}_db psql -U <user> <db> < scripts/db_health.sql
--
-- Interprétation :
--   pct_mortes > 20% + dernier_vacuum ancien  -> VACUUM ANALYZE recommandé
--   taille_index > taille_donnees             -> indices potentiellement redondants

\echo '=== État des tables (lignes mortes vs vivantes) ==='
SELECT
    schemaname,
    relname                                           AS table_name,
    n_live_tup                                        AS lignes_vivantes,
    n_dead_tup                                        AS lignes_mortes,
    CASE WHEN n_live_tup > 0
         THEN round(100.0 * n_dead_tup / n_live_tup, 1)
         ELSE 0 END                                   AS pct_mortes,
    last_autovacuum::date                             AS dernier_vacuum,
    last_autoanalyze::date                            AS dernier_analyze,
    pg_size_pretty(pg_total_relation_size(relid))     AS taille_totale
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 15;

\echo ''
\echo '=== Taille de la base ==='
SELECT pg_size_pretty(pg_database_size(current_database())) AS taille_base;

\echo ''
\echo '=== 10 plus grosses tables ==='
SELECT
    relname                                           AS table_name,
    pg_size_pretty(pg_total_relation_size(relid))     AS taille_totale,
    pg_size_pretty(pg_relation_size(relid))           AS taille_donnees,
    pg_size_pretty(pg_total_relation_size(relid)
                   - pg_relation_size(relid))         AS taille_index
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC
LIMIT 10;
