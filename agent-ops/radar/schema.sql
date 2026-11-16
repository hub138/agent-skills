-- 技术雷达借鉴台账（索引层）。
-- 设计原则：SQLite 只做查询索引；可追溯的正文一律落 Markdown 并进 git。
-- 因此这里不存长文，只存路径、结论、证据坐标。
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS briefs (
  id           INTEGER PRIMARY KEY,
  brief_date   TEXT NOT NULL,                 -- YYYY-MM-DD
  slot         TEXT NOT NULL DEFAULT '',      -- 同日多期：11:00 / 15:00
  title        TEXT NOT NULL,
  source       TEXT NOT NULL DEFAULT '',      -- 粘贴 / tech-radar / url
  source_path  TEXT NOT NULL DEFAULT '',
  raw_sha256   TEXT NOT NULL,
  item_count   INTEGER NOT NULL DEFAULT 0,
  ingested_at  TEXT NOT NULL,
  UNIQUE (brief_date, raw_sha256)
);

CREATE TABLE IF NOT EXISTS candidates (
  id          INTEGER PRIMARY KEY,
  brief_id    INTEGER NOT NULL REFERENCES briefs(id) ON DELETE CASCADE,
  seq         INTEGER NOT NULL,
  title       TEXT NOT NULL,
  url         TEXT NOT NULL DEFAULT '',
  host        TEXT NOT NULL DEFAULT '',
  kind        TEXT NOT NULL DEFAULT 'other'
              CHECK (kind IN ('repo', 'article', 'other')),
  core        TEXT NOT NULL DEFAULT '',
  innovation  TEXT NOT NULL DEFAULT '',
  audience    TEXT NOT NULL DEFAULT '',
  status      TEXT NOT NULL DEFAULT 'new'
              CHECK (status IN ('new', 'screened', 'workspace', 'analyzed',
                                'applied', 'skipped')),
  relevance   INTEGER,                        -- 1..5，相对本 skill
  verdict     TEXT CHECK (verdict IN ('adopt', 'adapt', 'skip') OR verdict IS NULL),
  reason      TEXT NOT NULL DEFAULT '',
  triage_score  INTEGER,                      -- 确定性打分（机制词加分/噪声词减分）
  triage_route  TEXT CHECK (triage_route IN ('deep', 'brief', 'skip') OR triage_route IS NULL),
  triage_reason TEXT NOT NULL DEFAULT '',
  triage_at     TEXT,
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL,
  UNIQUE (brief_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_candidates_status ON candidates(status, id);

CREATE TABLE IF NOT EXISTS analyses (
  id           INTEGER PRIMARY KEY,
  candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
  report_path  TEXT NOT NULL,                 -- 相对 skill 根
  verdict      TEXT NOT NULL CHECK (verdict IN ('adopt', 'adapt', 'skip')),
  mechanisms   TEXT NOT NULL DEFAULT '[]',    -- JSON 数组
  evidence     TEXT NOT NULL DEFAULT '[]',    -- JSON 数组，path:line 或 URL
  cost         TEXT NOT NULL DEFAULT '',
  risk         TEXT NOT NULL DEFAULT '',
  created_at   TEXT NOT NULL,
  UNIQUE (candidate_id)
);

CREATE TABLE IF NOT EXISTS changes (
  id           INTEGER PRIMARY KEY,
  candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
  files        TEXT NOT NULL DEFAULT '[]',    -- JSON 数组
  summary      TEXT NOT NULL,
  rationale    TEXT NOT NULL,
  diffstat     TEXT NOT NULL DEFAULT '',
  gate         TEXT NOT NULL DEFAULT '{}',    -- JSON: {pytest, doccheck, smoke}
  commit_sha   TEXT NOT NULL DEFAULT '',
  applied_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workspaces (
  id           INTEGER PRIMARY KEY,
  candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
  path         TEXT NOT NULL UNIQUE,
  commit_sha   TEXT NOT NULL DEFAULT '',
  bytes        INTEGER NOT NULL DEFAULT 0,
  cloned_at    TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  cleaned_at   TEXT
);

CREATE TABLE IF NOT EXISTS events (
  id         INTEGER PRIMARY KEY,
  ts         TEXT NOT NULL,
  kind       TEXT NOT NULL,
  detail     TEXT NOT NULL DEFAULT '{}'
);
