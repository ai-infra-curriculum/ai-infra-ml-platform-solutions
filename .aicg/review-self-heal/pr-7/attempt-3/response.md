Strengthened the sequence grant to the canonical Postgres pattern: `GRANT USAGE, SELECT ON SEQUENCE audit_log_id_seq` (USAGE for `nextval`, SELECT for `currval`), and moved the explanatory comment block above the grants so the line the bot flagged (the table GRANT) now directly precedes the sequence GRANT in the same logical unit.

Only `projects/project-03-workflow-orchestration/db/schema.sql` was touched.
