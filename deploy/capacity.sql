-- Load report: numbers for scaling decisions (docs/OPERATIONS.md §4).
-- Run: docker compose exec db psql -U sportintel -f /capacity.sql
-- Read-only. The window is the last 7 days unless stated otherwise.
\pset footer off
\echo '== 1. Database size and largest tables =='
SELECT pg_size_pretty(pg_database_size(current_database())) AS database_size;
SELECT schemaname || '.' || relname AS "table",
       pg_size_pretty(pg_total_relation_size(relid)) AS total,
       n_live_tup AS rows
FROM pg_stat_user_tables ORDER BY pg_total_relation_size(relid) DESC LIMIT 10;

\echo '== 2. Data flow per day (articles, events) =='
SELECT d::date AS day,
       (SELECT count(*) FROM ingestion.articles a
         WHERE a.discovered_at >= d AND a.discovered_at < d + interval '1 day') AS articles,
       (SELECT count(*) FROM events.events e
         WHERE e.first_seen_at >= d AND e.first_seen_at < d + interval '1 day') AS events
FROM generate_series(date_trunc('day', now()) - interval '6 days', date_trunc('day', now()), interval '1 day') d
ORDER BY day;

\echo '== 3. Freshness: delay from publication to ingestion (p50/p95, min) =='
SELECT round(percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM discovered_at - published_at)) / 60) AS p50_min,
       round(percentile_cont(0.95) WITHIN GROUP (ORDER BY extract(epoch FROM discovered_at - published_at)) / 60) AS p95_min
FROM ingestion.articles
WHERE discovered_at > now() - interval '7 days' AND published_at IS NOT NULL
  AND published_at <= discovered_at AND discovered_at - published_at < interval '2 days';

\echo '== 4. Job queue: waiting and failed =='
SELECT queue_name, status, count(*) AS jobs,
       max(now() - scheduled_at) FILTER (WHERE status = 'todo') AS oldest_waiting
FROM procrastinate.procrastinate_jobs
WHERE status IN ('todo', 'doing', 'failed')
GROUP BY 1, 2 ORDER BY 1, 2;

\echo '== 5. Sources: polls and errors over 24 h =='
SELECT count(*) AS runs,
       count(*) FILTER (WHERE status = 'error') AS errors,
       round(avg(extract(epoch FROM finished_at - started_at))::numeric, 1) AS avg_s,
       sum(items_new) AS new_items
FROM sources.fetch_runs WHERE started_at > now() - interval '24 hours';

\echo '== 6. AI: calls, errors and duration by kind (7 days) =='
SELECT kind, model, count(*) AS calls,
       count(*) FILTER (WHERE ok IS FALSE) AS failed,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM finished_at - started_at))::numeric, 1) AS p50_s,
       round(percentile_cont(0.95) WITHIN GROUP (ORDER BY extract(epoch FROM finished_at - started_at))::numeric, 1) AS p95_s
FROM platform.ai_calls
WHERE started_at > now() - interval '7 days' AND finished_at IS NOT NULL
GROUP BY 1, 2 ORDER BY calls DESC;

\echo '== 7. Users and sessions =='
SELECT (SELECT count(*) FROM identity.users WHERE active) AS active_users,
       (SELECT count(DISTINCT user_id) FROM identity.sessions WHERE last_seen_at > now() - interval '1 day') AS users_24h,
       (SELECT count(*) FROM identity.sessions WHERE absolute_expires_at > now()) AS open_sessions;

\echo '== 8. Telegram publications (7 days) =='
SELECT count(*) AS publications FROM editorial.publications
WHERE created_at > now() - interval '7 days';

\echo '== 9. Current database connections =='
SELECT count(*) AS connections,
       current_setting('max_connections') AS max_connections
FROM pg_stat_activity WHERE datname = current_database();
