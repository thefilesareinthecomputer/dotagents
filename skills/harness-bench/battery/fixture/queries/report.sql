CREATE TABLE zone_flow (
  name TEXT PRIMARY KEY,
  flow INTEGER NOT NULL
);

CREATE VIEW flow_summary AS
SELECT count(*) AS zones, sum(flow) AS total FROM zone_flow;
