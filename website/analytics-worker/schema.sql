CREATE TABLE IF NOT EXISTS pageviews (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  time INTEGER NOT NULL,
  page TEXT NOT NULL,
  referrer TEXT DEFAULT '',
  ua TEXT DEFAULT '',
  country TEXT DEFAULT 'unknown',
  city TEXT DEFAULT '',
  region TEXT DEFAULT '',
  tz TEXT DEFAULT '',
  session TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_pageviews_time ON pageviews(time);
CREATE INDEX IF NOT EXISTS idx_pageviews_page ON pageviews(page);
CREATE INDEX IF NOT EXISTS idx_pageviews_country ON pageviews(country);
CREATE INDEX IF NOT EXISTS idx_pageviews_referrer ON pageviews(referrer);
