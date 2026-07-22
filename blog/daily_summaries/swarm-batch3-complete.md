# Swarm Batch 3 Complete — DB Schema & Query Safety Audit

## Summary
17 direct Batch3 commits (plus ~10 indirect commits from concurrent agents that picked up our changes). All 9 target files were audited and hardened across 50+ database interaction improvements.

## Files Impacted

| File | Commits | Key Changes |
|------|---------|-------------|
| `database/class-schema.php` | 6 | ENGINE=InnoDB, 7 composite indexes, purged cron, table inspection, maintenance methods |
| `includes/class-ab-test-manager.php` | 4 | Transaction safety, LEFT JOIN refactoring, request-level caching, strict type casting |
| `includes/class-logger.php` | 3 | Chunked delete, keyset pagination, strict type casting |
| `includes/class-suggestion-engine.php` | 3 | Prepared statements, request-level caching, strict type casting |
| `includes/class-self-healer.php` | 2 | Request-level caching, strict type casting |
| `includes/class-signal-collector.php` | 1 | Fixed non-existent column query |
| `agents/class-self-healing-agent.php` | 2 | Prepared SHOW TABLES, engine validation |
| `includes/class-llm-client.php` | 0 | Already fixed by Batch 2 |
| `uninstall.php` | 0 | Already correct (sanitize_key + backtick pattern) |

## Target Issues Addressed

1. **Missing $wpdb->prepare()**: 100% fixed — zero raw SQL calls remain across all files (transaction control statements excluded as non-injection)
2. **Missing indexes**: 8 new composite indexes added — 29 total indexes across 7 tables (was 21)
3. **Character set**: All tables use `$charset_collate` via `dbDelta()`
4. **Engine**: All 7 tables explicitly specify `ENGINE=InnoDB`
5. **Purge/cleanup**: Auto-purge cron handler with chunked delete (5000 rows), stale beacon purge (90 days)
6. **SHOW TABLES risks**: Replaced raw `SHOW TABLES LIKE '{$table}'` with `$wpdb->prepare()`
7. **COUNT(*) patterns**: Optimized with approximate counts via `information_schema.TABLES`
8. **LIMIT injection**: All LIMIT values use `%d` placeholders or `absint()`
9. **Transaction safety**: `create_experiment()` and `declare_winner()` now use START TRANSACTION/COMMIT/ROLLBACK
10. **Duplicate queries**: Request-level caching added for `get_variants()`, `get_active_experiments()`, `get_pending_count()`, `get_total_heals()`
11. **dbDelta() usage**: Already using `dbDelta()` — no change needed
12. **Uninstall cleanup**: All 7 tables properly dropped with sanitize_key + backtick quoting
13. **Collation**: Added `TABLE_COLLATION` to `get_table_info()`, health check for engine validation

## New Composite Indexes

| Table | Index | Columns |
|-------|-------|---------|
| `wac_logs` | `idx_level_created` | `(level, created_at)` |
| `wac_ab_events` | `idx_exp_var_event` | `(experiment_id, variant_id, event_type)` |
| `wac_beacon_events` | `idx_session_event` | `(session_id, event)` |
| `wac_beacon_events` | `idx_session_created` | `(session_id, created_at)` |
| `wac_ab_variants` | `idx_experiment_status` | `(experiment_id, status)` |
| `wac_suggestions` | `idx_status_score` | `(status, score DESC)` |
| `wac_suggestions` | `idx_score_asc` | `(score)` |
| `wac_heal_log` | `idx_issue_created` | `(issue_id, created_at)` |

## Bugs Fixed

- **get_experiments()**: Sub-query referenced non-existent `impressions` column on `wac_ab_variants`; corrected to query `wac_ab_events`
- **get_recent_errors()**: Selected non-existent `message` column; `wac_logs` schema uses `context`
- **LEFT JOIN refactoring**: `get_variants()` converted from 3 correlated subqueries to 2 LEFT JOINs with pre-aggregated subqueries

## New Features Added

- `schedule_purge_cron()` / `unschedule_purge_cron()` — cron management for daily log purging
- `handle_purge_cron()` — auto-purge handler (30-day logs, 90-day beacons)
- `analyze_tables()` / `optimize_tables()` — Schema maintenance methods
- Keyset (cursor-based) pagination in `get_logs()` via `id_after` parameter
- Chunked delete (5000 rows/iteration) in `purge_old_logs()` — prevents table locks
