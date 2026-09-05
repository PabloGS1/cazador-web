-- Cazador API - Cloudflare D1 schema
-- Aplica con: wrangler d1 execute cazador --remote --file=./schema.sql

CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  github_id INTEGER UNIQUE NOT NULL,
  login TEXT NOT NULL,
  name TEXT DEFAULT '',
  avatar_url TEXT DEFAULT '',
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS profiles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL DEFAULT 'default',
  role_taxonomy TEXT NOT NULL DEFAULT '{}',
  anti_identity TEXT NOT NULL DEFAULT '{}',
  hard_reject TEXT NOT NULL DEFAULT '{}',
  domain_keywords TEXT NOT NULL DEFAULT '[]',
  skills_keywords TEXT NOT NULL DEFAULT '[]',
  geography TEXT NOT NULL DEFAULT '{}',
  seniority TEXT NOT NULL DEFAULT '{}',
  spoken_languages TEXT NOT NULL DEFAULT '["english"]',
  min_match INTEGER NOT NULL DEFAULT 40,
  max_match INTEGER NOT NULL DEFAULT 200,
  is_default INTEGER NOT NULL DEFAULT 0,
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS saved_searches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  filters TEXT NOT NULL DEFAULT '{}',
  created_at TEXT DEFAULT (datetime('now'))
);

-- Ofertas (features extraidas por matcher.py). text_lower/title_lower se usan
-- para puntuar por perfil en caliente.
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL DEFAULT '',
  company TEXT DEFAULT '',
  location TEXT DEFAULT '',
  source TEXT DEFAULT '',
  url TEXT DEFAULT '',
  posted TEXT DEFAULT '',
  salary_min_eur INTEGER,
  salary_max_eur INTEGER,
  salary_raw TEXT DEFAULT '',
  lang TEXT DEFAULT 'en',
  lang_req TEXT DEFAULT '',
  years_min INTEGER DEFAULT 0,
  eng_title INTEGER DEFAULT 0,
  hard_block INTEGER DEFAULT 0,
  hard_tech INTEGER DEFAULT 0,
  title_lower TEXT DEFAULT '',
  text_lower TEXT DEFAULT '',
  -- Score precalculado para el perfil por defecto (generado en el seed).
  -- /api/jobs usa estos campos (ORDER BY match) para responder en ms sin
  -- rescore en caliente; los perfiles custom se puntuan con scoreJob().
  match INTEGER DEFAULT 0,
  role_family TEXT DEFAULT '',
  why TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_jobs_hard ON jobs(hard_block, hard_tech);
CREATE INDEX IF NOT EXISTS idx_jobs_match ON jobs(hard_block, hard_tech, match);
