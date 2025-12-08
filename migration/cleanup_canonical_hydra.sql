BEGIN;

-- 1. DROP CANONICAL-ONLY TABLES
-- These tables are replaced by Ory Hydra with 'hydra_oauth2_device_auth_codes'
DROP TABLE IF EXISTS hydra_oauth2_device_code CASCADE;
DROP TABLE IF EXISTS hydra_oauth2_user_code CASCADE;

-- 2. CLEANUP 'hydra_oauth2_flow'
-- We ONLY drop the column that Ory v25 does not use.
-- The other columns (device_challenge_id, device_verifier, etc.) were adopted by Ory.
ALTER TABLE hydra_oauth2_flow DROP COLUMN IF EXISTS device_user_code_accepted_at;

-- 3. REMOVE MIGRATION HISTORY
-- ==========================================================
-- Delete the version ID that corresponds to the Canonical
-- device flow migration. Otherwise, Ory v25.4.0 may
-- panic because it will see a version ID it doesn't recognize.
DELETE FROM schema_migration WHERE version = '20240202000001000000';

COMMIT;
