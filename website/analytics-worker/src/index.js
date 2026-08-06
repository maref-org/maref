// maref-analytics — lightweight self-hosted analytics for maref.cc
// Routed at https://maref.cc/api/* (via Cloudflare Worker)

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;
    const corsHeaders = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    };

    // CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders });
    }

    // POST /api/collect — receive pageview beacon
    if (request.method === "POST" && path === "/api/collect") {
      try {
        const data = await request.json();
        await savePageview(env.DB, data, request);
        return new Response(null, { status: 204, headers: corsHeaders });
      } catch (e) {
        return new Response("error", { status: 400 });
      }
    }

    // GET /api/health — health check
    if (request.method === "GET" && path === "/api/health") {
      return new Response("OK", { status: 200 });
    }

    return new Response("Not found", { status: 404 });
  },
};

async function savePageview(db, data, request) {
  const cf = request.cf || {};
  const { page = "/", referrer = "", ua = "" } = data;
  const uaHeader = request.headers.get("User-Agent") || ua;

  const pageview = {
    time: Date.now(),
    page,
    referrer,
    ua: uaHeader,
    country: cf.country || "unknown",
    city: cf.city || "",
    region: cf.region || "",
    tz: cf.timezone || "",
  };

  if (!db) return;

  try {
    await db.prepare(
      "INSERT INTO pageviews (time, page, referrer, ua, country, city, region, tz) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
    ).bind(
      pageview.time, pageview.page, pageview.referrer, pageview.ua,
      pageview.country, pageview.city, pageview.region, pageview.tz
    ).run();
  } catch (e) {
    // Analytics errors never break the page
  }
}
