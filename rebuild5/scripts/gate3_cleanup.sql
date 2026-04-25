-- fix5 audit: this one-off cleanup script was intentionally neutered.
-- The original version contained hard-coded TRUNCATE/DROP statements against
-- rb5.* tables. Keep reset/rerun cleanup in the reviewed reset scripts instead.
\echo 'gate3_cleanup.sql is disabled by fix5 audit; use reviewed reset scripts only.'
