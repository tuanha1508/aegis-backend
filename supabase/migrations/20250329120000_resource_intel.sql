-- Track whether crowdsourced resource-status intel has been applied from a report.
ALTER TABLE reports ADD COLUMN IF NOT EXISTS resource_intel_applied BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_reports_resource_intel
  ON reports (processed, incident_type, resource_intel_applied)
  WHERE processed = TRUE;
