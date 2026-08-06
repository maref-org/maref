#!/usr/bin/env bash
# Analytics query tool for maref.cc
# Usage: ./scripts/analytics.sh [top-pages|countries|referrers|realtime|daily]
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CMD="${1:-daily}"

case "$CMD" in
  realtime)
    echo "=== Last 10 pageviews ==="
    pnpm --dir "$PROJECT_DIR" wrangler d1 execute maref-analytics --remote \
      --command "SELECT datetime(time/1000, 'unixepoch') as ts, page, country, referrer FROM pageviews ORDER BY time DESC LIMIT 10"
    ;;
  countries)
    echo "=== Pageviews by Country ==="
    pnpm --dir "$PROJECT_DIR" wrangler d1 execute maref-analytics --remote \
      --command "SELECT country, COUNT(*) as visits FROM pageviews GROUP BY country ORDER BY visits DESC"
    ;;
  referrers)
    echo "=== Top Referrers ==="
    pnpm --dir "$PROJECT_DIR" wrangler d1 execute maref-analytics --remote \
      --command "SELECT referrer, COUNT(*) as visits FROM pageviews WHERE referrer != '' GROUP BY referrer ORDER BY visits DESC LIMIT 15"
    ;;
  top-pages)
    echo "=== Top Pages ==="
    pnpm --dir "$PROJECT_DIR" wrangler d1 execute maref-analytics --remote \
      --command "SELECT page, COUNT(*) as visits FROM pageviews GROUP BY page ORDER BY visits DESC LIMIT 15"
    ;;
  daily)
    echo "=== Daily Visitors (last 14 days) ==="
    pnpm --dir "$PROJECT_DIR" wrangler d1 execute maref-analytics --remote \
      --command "SELECT datetime(time/1000, 'unixepoch', 'start of day') as day, COUNT(*) as visits, COUNT(DISTINCT substr(ua,1,40)||country) as uniq FROM pageviews WHERE time > unixepoch('now','-14 days')*1000 GROUP BY day ORDER BY day DESC"
    ;;
  summary)
    echo "=== MAREF Analytics Summary ==="
    pnpm --dir "$PROJECT_DIR" wrangler d1 execute maref-analytics --remote \
      --command "SELECT COUNT(*) as total_views, COUNT(DISTINCT substr(ua,1,40)||country) as estimated_visitors FROM pageviews"
    echo "---"
    $0 countries
    echo "---"
    $0 referrers
    echo "---"
    $0 top-pages
    ;;
  *)
    echo "Usage: $0 [top-pages|countries|referrers|realtime|daily|summary]"
    exit 1
    ;;
esac
