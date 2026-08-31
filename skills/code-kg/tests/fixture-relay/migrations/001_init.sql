-- Base schema for relay memory. Applied by relay.tools.sql_tool.
CREATE TABLE IF NOT EXISTS records (
  id      INTEGER PRIMARY KEY,
  key     TEXT NOT NULL,
  kind    TEXT NOT NULL DEFAULT 'note',
  body    TEXT NOT NULL,
  meta    TEXT NOT NULL DEFAULT '{}',
  created REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS records_key ON records(key);

CREATE VIEW IF NOT EXISTS latest_records AS
SELECT r.key, r.kind, r.body, r.created
FROM records r
JOIN (SELECT key, max(id) AS max_id FROM records GROUP BY key) m
  ON m.max_id = r.id;
