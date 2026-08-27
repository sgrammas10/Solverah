-- Deletes a user and everything tied to them, identified by email.
-- Usage: psql "$DATABASE_URL" -v email="'someone@example.com'" -f Scripts/delete_user_by_email.sql
--   (the quotes around the email in -v are required — psql substitutes :'email' as a literal)

BEGIN;

WITH target AS (
    SELECT id FROM "user" WHERE email = :email
)
DELETE FROM job_recommendation WHERE user_id IN (SELECT id FROM target);

WITH target AS (
    SELECT id FROM "user" WHERE email = :email
)
DELETE FROM user_intake WHERE user_id IN (SELECT id FROM target);

WITH target AS (
    SELECT id FROM "user" WHERE email = :email
)
DELETE FROM resume_parse_correction WHERE user_id IN (SELECT id FROM target);

WITH target AS (
    SELECT id FROM "user" WHERE email = :email
)
DELETE FROM assessment_response WHERE user_id IN (SELECT id FROM target);

WITH target AS (
    SELECT id FROM "user" WHERE email = :email
)
DELETE FROM person_dimension_score WHERE user_id IN (SELECT id FROM target);

-- audit_log.actor_user_id is nullable — null it out instead of deleting so the log survives
WITH target AS (
    SELECT id FROM "user" WHERE email = :email
)
UPDATE audit_log SET actor_user_id = NULL WHERE actor_user_id IN (SELECT id FROM target);

DELETE FROM "user" WHERE email = :email;

COMMIT;
