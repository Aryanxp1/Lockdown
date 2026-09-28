-- Lockdown portal schema. Applied idempotently on every boot; there is no
-- migration tool because there is only one deployment: this one.
--
-- Conventions
--   * ids are TEXT with a type prefix (usr_, evt_, prj_ ...) so a row can be
--     identified by eye in a log line or a CSV export.
--   * every timestamp is ISO-8601 UTC text ending in Z (see timeutil.py).
--   * boolean columns are INTEGER 0/1.
--   * important records are append-only: project_versions, review_revisions,
--     result_publications and audit_log are never updated in place, only
--     appended to.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
  key        TEXT PRIMARY KEY,
  value      TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
  id            TEXT PRIMARY KEY,
  email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
  name          TEXT NOT NULL,
  role          TEXT NOT NULL CHECK (role IN ('participant','judge','organizer','admin')),
  password_hash TEXT,
  created_at    TEXT NOT NULL,
  last_login_at TEXT,
  is_active     INTEGER NOT NULL DEFAULT 1,
  bio           TEXT NOT NULL DEFAULT '',
  org           TEXT NOT NULL DEFAULT '',
  fixture_id    TEXT,
  notes         TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

CREATE TABLE IF NOT EXISTS sessions (
  token_hash   TEXT PRIMARY KEY,
  user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  csrf_token   TEXT NOT NULL,
  label        TEXT NOT NULL DEFAULT '',
  is_demo      INTEGER NOT NULL DEFAULT 0,
  created_at   TEXT NOT NULL,
  expires_at   TEXT NOT NULL,
  revoked_at   TEXT,
  last_seen_at TEXT,
  ip           TEXT NOT NULL DEFAULT '',
  user_agent   TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);

CREATE TABLE IF NOT EXISTS events (
  id                   TEXT PRIMARY KEY,
  slug                 TEXT NOT NULL UNIQUE,
  name                 TEXT NOT NULL,
  tagline              TEXT NOT NULL DEFAULT '',
  description          TEXT NOT NULL DEFAULT '',
  rules                TEXT NOT NULL DEFAULT '',
  seq                  INTEGER NOT NULL DEFAULT 100,
  status               TEXT NOT NULL DEFAULT 'published'
                       CHECK (status IN ('draft','published','archived')),
  registration_open    TEXT,
  registration_close   TEXT,
  team_formation_close TEXT,
  submissions_open     TEXT,
  submissions_close    TEXT,
  judging_open         TEXT,
  judging_close        TEXT,
  results_publish_at   TEXT,
  min_team_size        INTEGER NOT NULL DEFAULT 1,
  max_team_size        INTEGER NOT NULL DEFAULT 4,
  reviews_required     INTEGER NOT NULL DEFAULT 3,
  target_reviews       INTEGER NOT NULL DEFAULT 3,
  created_by           TEXT REFERENCES users(id),
  created_at           TEXT NOT NULL,
  updated_at           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS event_stages (
  id           TEXT PRIMARY KEY,
  event_id     TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  seq          INTEGER NOT NULL,
  key          TEXT NOT NULL,
  name         TEXT NOT NULL,
  description  TEXT NOT NULL DEFAULT '',
  opens_at     TEXT,
  closes_at    TEXT,
  status       TEXT NOT NULL DEFAULT 'scheduled'
               CHECK (status IN ('scheduled','open','closed','published')),
  published_at TEXT,
  UNIQUE (event_id, key)
);
CREATE INDEX IF NOT EXISTS idx_stages_event ON event_stages(event_id, seq);

CREATE TABLE IF NOT EXISTS tracks (
  id          TEXT PRIMARY KEY,
  event_id    TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  slug        TEXT NOT NULL,
  name        TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  seq         INTEGER NOT NULL DEFAULT 10,
  UNIQUE (event_id, slug)
);

CREATE TABLE IF NOT EXISTS prizes (
  id          TEXT PRIMARY KEY,
  event_id    TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  track_id    TEXT REFERENCES tracks(id) ON DELETE SET NULL,
  rank        INTEGER NOT NULL,
  title       TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  value       TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS teams (
  id          TEXT PRIMARY KEY,
  event_id    TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  name        TEXT NOT NULL,
  slug        TEXT NOT NULL,
  invite_code TEXT NOT NULL UNIQUE,
  created_by  TEXT NOT NULL REFERENCES users(id),
  status      TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','locked','disbanded')),
  seed_hint   TEXT NOT NULL DEFAULT '',
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL,
  UNIQUE (event_id, slug)
);

CREATE TABLE IF NOT EXISTS team_members (
  id        TEXT PRIMARY KEY,
  team_id   TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  user_id   TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role      TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('owner','member')),
  joined_at TEXT NOT NULL,
  UNIQUE (team_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_team_members_user ON team_members(user_id);

CREATE TABLE IF NOT EXISTS projects (
  id               TEXT PRIMARY KEY,
  event_id         TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  team_id          TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  track_id         TEXT REFERENCES tracks(id) ON DELETE SET NULL,
  title            TEXT NOT NULL DEFAULT 'Untitled draft',
  summary          TEXT NOT NULL DEFAULT '',
  description      TEXT NOT NULL DEFAULT '',
  repo_url         TEXT NOT NULL DEFAULT '',
  demo_url         TEXT NOT NULL DEFAULT '',
  video_url        TEXT NOT NULL DEFAULT '',
  tags             TEXT NOT NULL DEFAULT '',
  status           TEXT NOT NULL DEFAULT 'draft'
                   CHECK (status IN ('draft','submitted','withdrawn','disqualified')),
  submission_state TEXT NOT NULL DEFAULT 'open'
                   CHECK (submission_state IN ('open','closed','late')),
  current_version  INTEGER NOT NULL DEFAULT 0,
  submitted_at     TEXT,
  locked_at        TEXT,
  fixture_id       TEXT,
  fixture_rank     INTEGER,
  duplicate_of     TEXT REFERENCES projects(id) ON DELETE SET NULL,
  superseded_by    TEXT REFERENCES projects(id) ON DELETE SET NULL,
  created_by       TEXT NOT NULL REFERENCES users(id),
  created_at       TEXT NOT NULL,
  updated_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_projects_event ON projects(event_id, status);
CREATE INDEX IF NOT EXISTS idx_projects_team ON projects(team_id);
CREATE INDEX IF NOT EXISTS idx_projects_rank ON projects(fixture_rank);

CREATE TABLE IF NOT EXISTS project_versions (
  id          TEXT PRIMARY KEY,
  project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  version_no  INTEGER NOT NULL,
  title       TEXT NOT NULL,
  summary     TEXT NOT NULL DEFAULT '',
  description TEXT NOT NULL DEFAULT '',
  repo_url    TEXT NOT NULL DEFAULT '',
  demo_url    TEXT NOT NULL DEFAULT '',
  video_url   TEXT NOT NULL DEFAULT '',
  tags        TEXT NOT NULL DEFAULT '',
  status      TEXT NOT NULL DEFAULT 'draft',
  reason      TEXT NOT NULL DEFAULT 'save',
  created_by  TEXT REFERENCES users(id),
  created_at  TEXT NOT NULL,
  snapshot    TEXT NOT NULL DEFAULT '{}',
  UNIQUE (project_id, version_no)
);
CREATE INDEX IF NOT EXISTS idx_versions_project ON project_versions(project_id, version_no);

CREATE TABLE IF NOT EXISTS rubrics (
  id         TEXT PRIMARY KEY,
  event_id   TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  name       TEXT NOT NULL,
  notes      TEXT NOT NULL DEFAULT '',
  is_active  INTEGER NOT NULL DEFAULT 0,
  created_by TEXT REFERENCES users(id),
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rubric_criteria (
  id          TEXT PRIMARY KEY,
  rubric_id   TEXT NOT NULL REFERENCES rubrics(id) ON DELETE CASCADE,
  key         TEXT NOT NULL,
  label       TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  weight      REAL NOT NULL DEFAULT 0,
  min_score   INTEGER NOT NULL DEFAULT 1,
  max_score   INTEGER NOT NULL DEFAULT 5,
  seq         INTEGER NOT NULL DEFAULT 10,
  UNIQUE (rubric_id, key)
);
CREATE TABLE IF NOT EXISTS assignments (
  id            TEXT PRIMARY KEY,
  event_id      TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  project_id    TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  judge_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  track_id      TEXT REFERENCES tracks(id) ON DELETE SET NULL,
  status        TEXT NOT NULL DEFAULT 'assigned'
                CHECK (status IN ('assigned','accepted','declined','revoked')),
  origin        TEXT NOT NULL DEFAULT 'manual',
  due_at        TEXT,
  assigned_by   TEXT REFERENCES users(id),
  assigned_at   TEXT NOT NULL,
  updated_at    TEXT NOT NULL,
  UNIQUE (project_id, judge_user_id)
);
CREATE INDEX IF NOT EXISTS idx_assignments_judge ON assignments(judge_user_id, status);
CREATE INDEX IF NOT EXISTS idx_assignments_project ON assignments(project_id);

CREATE TABLE IF NOT EXISTS judge_invitations (
  id          TEXT PRIMARY KEY,
  event_id    TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  email       TEXT NOT NULL,
  name        TEXT NOT NULL DEFAULT '',
  token_hash  TEXT NOT NULL,
  token_hint  TEXT NOT NULL DEFAULT '',
  track_ids   TEXT NOT NULL DEFAULT '',
  status      TEXT NOT NULL DEFAULT 'pending'
              CHECK (status IN ('pending','accepted','revoked')),
  invited_by  TEXT REFERENCES users(id),
  user_id     TEXT REFERENCES users(id),
  created_at  TEXT NOT NULL,
  accepted_at TEXT
);

CREATE TABLE IF NOT EXISTS reviews (
  id            TEXT PRIMARY KEY,
  project_id    TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  judge_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  event_id      TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  rubric_id     TEXT REFERENCES rubrics(id) ON DELETE SET NULL,
  status        TEXT NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft','submitted','finalized','recused')),
  revision_no   INTEGER NOT NULL DEFAULT 1,
  comment       TEXT NOT NULL DEFAULT '',
  internal_note TEXT NOT NULL DEFAULT '',
  weighted_raw  REAL,
  normalized    REAL,
  norm_method   TEXT NOT NULL DEFAULT '',
  norm_flags    TEXT NOT NULL DEFAULT '',
  adjudication  TEXT NOT NULL DEFAULT '',
  signature     TEXT NOT NULL DEFAULT '',
  origin        TEXT NOT NULL DEFAULT 'portal',
  started_at    TEXT NOT NULL,
  submitted_at  TEXT,
  finalized_at  TEXT,
  updated_at    TEXT NOT NULL,
  UNIQUE (project_id, judge_user_id, revision_no)
);
CREATE INDEX IF NOT EXISTS idx_reviews_project ON reviews(project_id);
CREATE INDEX IF NOT EXISTS idx_reviews_judge ON reviews(judge_user_id, status);
CREATE INDEX IF NOT EXISTS idx_reviews_event ON reviews(event_id, status);

CREATE TABLE IF NOT EXISTS review_scores (
  id            TEXT PRIMARY KEY,
  review_id     TEXT NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
  criterion_id  TEXT REFERENCES rubric_criteria(id) ON DELETE SET NULL,
  criterion_key TEXT NOT NULL,
  value         REAL,
  weight        REAL NOT NULL DEFAULT 0,
  comment       TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_review_scores_review ON review_scores(review_id);

-- Every edit of a submitted or finalized review appends a revision instead of
-- overwriting the previous one. Nothing in the portal updates this table.
CREATE TABLE IF NOT EXISTS review_revisions (
  id           TEXT PRIMARY KEY,
  review_id    TEXT NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
  revision_no  INTEGER NOT NULL,
  scores_json  TEXT NOT NULL DEFAULT '[]',
  comment      TEXT NOT NULL DEFAULT '',
  weighted_raw REAL,
  status       TEXT NOT NULL DEFAULT 'draft',
  reason       TEXT NOT NULL DEFAULT 'edit',
  actor_id     TEXT REFERENCES users(id),
  created_at   TEXT NOT NULL,
  UNIQUE (review_id, revision_no)
);
CREATE TABLE IF NOT EXISTS votes (
  id         TEXT PRIMARY KEY,
  event_id   TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  weight     REAL NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  ip_hash    TEXT NOT NULL DEFAULT '',
  UNIQUE (project_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_votes_project ON votes(project_id);
CREATE INDEX IF NOT EXISTS idx_votes_event ON votes(event_id, user_id);

-- One ballot per voter per event. Candidate order is shuffled once and stored,
-- so a voter cannot re-roll the ballot looking for a favourable order.
CREATE TABLE IF NOT EXISTS vote_ballots (
  id           TEXT PRIMARY KEY,
  event_id     TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  order_json   TEXT NOT NULL DEFAULT '[]',
  created_at   TEXT NOT NULL,
  submitted_at TEXT,
  UNIQUE (event_id, user_id)
);

CREATE TABLE IF NOT EXISTS comments (
  id            TEXT PRIMARY KEY,
  project_id    TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  user_id       TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  parent_id     TEXT REFERENCES comments(id) ON DELETE CASCADE,
  body          TEXT NOT NULL,
  is_hidden     INTEGER NOT NULL DEFAULT 0,
  hidden_by     TEXT REFERENCES users(id),
  hidden_reason TEXT NOT NULL DEFAULT '',
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_comments_project ON comments(project_id, created_at);

CREATE TABLE IF NOT EXISTS pairwise_comparisons (
  id            TEXT PRIMARY KEY,
  event_id      TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  judge_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  project_a     TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  project_b     TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  winner        TEXT REFERENCES projects(id) ON DELETE SET NULL,
  reason        TEXT NOT NULL DEFAULT '',
  created_at    TEXT NOT NULL,
  CHECK (project_a <> project_b)
);

CREATE TABLE IF NOT EXISTS advancements (
  id                 TEXT PRIMARY KEY,
  event_id           TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  project_id         TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  from_stage         TEXT NOT NULL DEFAULT 'review',
  to_stage           TEXT NOT NULL,
  decision           TEXT NOT NULL
                     CHECK (decision IN ('advanced','eliminated','waitlisted','restored')),
  rank_at_decision   INTEGER,
  score_at_decision  REAL,
  note               TEXT NOT NULL DEFAULT '',
  decided_by         TEXT REFERENCES users(id),
  decided_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_advancements_event ON advancements(event_id, decided_at);

-- Published results are snapshots. Publishing again appends a new row, so an
-- earlier published result can always be reproduced and compared.
CREATE TABLE IF NOT EXISTS result_publications (
  id           TEXT PRIMARY KEY,
  event_id     TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  revision_no  INTEGER NOT NULL,
  published_by TEXT REFERENCES users(id),
  published_at TEXT NOT NULL,
  methodology  TEXT NOT NULL DEFAULT '',
  rows_json    TEXT NOT NULL DEFAULT '[]',
  checksum     TEXT NOT NULL DEFAULT '',
  note         TEXT NOT NULL DEFAULT '',
  is_current   INTEGER NOT NULL DEFAULT 1,
  UNIQUE (event_id, revision_no)
);
CREATE TABLE IF NOT EXISTS certificates (
  id           TEXT PRIMARY KEY,
  event_id     TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  project_id   TEXT REFERENCES projects(id) ON DELETE CASCADE,
  team_id      TEXT REFERENCES teams(id) ON DELETE CASCADE,
  kind         TEXT NOT NULL DEFAULT 'participation',
  code         TEXT NOT NULL UNIQUE,
  title        TEXT NOT NULL DEFAULT '',
  payload_json TEXT NOT NULL DEFAULT '{}',
  issued_by    TEXT REFERENCES users(id),
  issued_at    TEXT NOT NULL,
  revoked_at   TEXT
);

CREATE TABLE IF NOT EXISTS webhooks (
  id         TEXT PRIMARY KEY,
  event_id   TEXT REFERENCES events(id) ON DELETE CASCADE,
  url        TEXT NOT NULL,
  secret     TEXT NOT NULL,
  topics     TEXT NOT NULL DEFAULT '["*"]',
  is_active  INTEGER NOT NULL DEFAULT 1,
  created_by TEXT REFERENCES users(id),
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS webhook_deliveries (
  id            TEXT PRIMARY KEY,
  webhook_id    TEXT NOT NULL REFERENCES webhooks(id) ON DELETE CASCADE,
  event_type    TEXT NOT NULL,
  payload_json  TEXT NOT NULL DEFAULT '{}',
  signature     TEXT NOT NULL DEFAULT '',
  status        TEXT NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued','delivered','failed','skipped')),
  attempts      INTEGER NOT NULL DEFAULT 0,
  response_code INTEGER,
  last_error    TEXT NOT NULL DEFAULT '',
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_webhook_deliveries ON webhook_deliveries(status, created_at);

CREATE TABLE IF NOT EXISTS audit_log (
  id          TEXT PRIMARY KEY,
  at          TEXT NOT NULL,
  actor_id    TEXT,
  actor_label TEXT NOT NULL DEFAULT 'anonymous',
  actor_role  TEXT NOT NULL DEFAULT 'visitor',
  action      TEXT NOT NULL,
  entity_type TEXT NOT NULL DEFAULT '',
  entity_id   TEXT NOT NULL DEFAULT '',
  outcome     TEXT NOT NULL DEFAULT 'ok',
  summary     TEXT NOT NULL DEFAULT '',
  before_json TEXT NOT NULL DEFAULT '',
  after_json  TEXT NOT NULL DEFAULT '',
  ip          TEXT NOT NULL DEFAULT '',
  user_agent  TEXT NOT NULL DEFAULT '',
  meta_json   TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_audit_at ON audit_log(at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action);

CREATE TABLE IF NOT EXISTS rate_limits (
  bucket       TEXT NOT NULL,
  window_start TEXT NOT NULL,
  hits         INTEGER NOT NULL DEFAULT 0,
  first_at     TEXT NOT NULL,
  last_at      TEXT NOT NULL,
  PRIMARY KEY (bucket, window_start)
);

INSERT OR IGNORE INTO schema_meta(key, value) VALUES ('schema_version', '1');
