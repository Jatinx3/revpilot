-- Drop the rate_plan_code FK that the source data cannot satisfy (granular booking
-- rate codes are a superset of the 8-row rate_plan_lookup reference). See the note
-- in schema.sql. Idempotent — safe to run repeatedly.
alter table public.reservations_hackathon
  drop constraint if exists reservations_hackathon_rate_plan_code_fkey;
