-- Run accounting, added in 0.4.
CREATE TABLE IF NOT EXISTS runs (
  id        INTEGER PRIMARY KEY,
  goal      TEXT NOT NULL,
  completed INTEGER NOT NULL DEFAULT 0,
  failed    INTEGER NOT NULL DEFAULT 0,
  stopped   TEXT NOT NULL DEFAULT 'done',
  started   REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS runs_started ON runs(started);

CREATE VIEW IF NOT EXISTS run_failure_rate AS
SELECT count(*) AS total,
       sum(CASE WHEN failed > 0 THEN 1 ELSE 0 END) AS with_failures
FROM runs;
