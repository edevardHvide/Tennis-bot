-- Example Athena queries for Steep reports
-- Data source: dynamodb | Workgroup: tennis-bot
--
-- Table reference:
--   dynamodb.default."tennis-users"          — registered subscribers
--   dynamodb.default."tennis-preferences"    — per-user alert preferences
--   dynamodb.default."tennis-availability"   — scraped court availability snapshots
--   dynamodb.default."tennis-notifications"  — sent notification log (24h TTL)
--   dynamodb.default."tennis-feedback"       — user feature requests


-- ═══════════════════════════════════════════════════════════════════════
-- USERS
-- ═══════════════════════════════════════════════════════════════════════

-- Total registered users
SELECT COUNT(*) AS total_users
FROM "dynamodb"."default"."tennis-users";

-- All registered users
SELECT userid, createdat
FROM "dynamodb"."default"."tennis-users"
ORDER BY createdat DESC;


-- ═══════════════════════════════════════════════════════════════════════
-- PREFERENCES — what are users monitoring?
-- ═══════════════════════════════════════════════════════════════════════

-- Preferences per sport
SELECT sport, COUNT(*) AS preference_count
FROM "dynamodb"."default"."tennis-preferences"
GROUP BY sport;

-- Most popular facilities
SELECT facilityid, sport, COUNT(*) AS watchers
FROM "dynamodb"."default"."tennis-preferences"
GROUP BY facilityid, sport
ORDER BY watchers DESC;

-- Preferences by day of week (which days do users care about?)
-- Note: 'dates' is stored as a DynamoDB list, connector flattens it
SELECT facilityid, sport, dates, timefrom, timeto
FROM "dynamodb"."default"."tennis-preferences"
LIMIT 50;

-- Users with the most active preferences
SELECT userid, COUNT(*) AS num_preferences
FROM "dynamodb"."default"."tennis-preferences"
GROUP BY userid
ORDER BY num_preferences DESC
LIMIT 20;


-- ═══════════════════════════════════════════════════════════════════════
-- AVAILABILITY — court slot snapshots
-- ═══════════════════════════════════════════════════════════════════════

-- Recent availability snapshots (check what the scraper is finding)
SELECT facilityid, date, slots
FROM "dynamodb"."default"."tennis-availability"
LIMIT 20;

-- Availability by facility+sport
SELECT facilityid, COUNT(*) AS snapshot_count
FROM "dynamodb"."default"."tennis-availability"
GROUP BY facilityid
ORDER BY snapshot_count DESC;


-- ═══════════════════════════════════════════════════════════════════════
-- NOTIFICATIONS — alert history
-- ═══════════════════════════════════════════════════════════════════════

-- Recent notifications sent
SELECT notificationid, sentat
FROM "dynamodb"."default"."tennis-notifications"
ORDER BY sentat DESC
LIMIT 50;


-- ═══════════════════════════════════════════════════════════════════════
-- FEEDBACK — feature requests
-- ═══════════════════════════════════════════════════════════════════════

-- All feature requests
SELECT feedbackid, userid, message, createdat
FROM "dynamodb"."default"."tennis-feedback"
ORDER BY createdat DESC;

-- Feature requests per user
SELECT userid, COUNT(*) AS request_count
FROM "dynamodb"."default"."tennis-feedback"
GROUP BY userid
ORDER BY request_count DESC;
