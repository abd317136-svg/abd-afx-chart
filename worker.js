// Cloudflare Worker: شموع XAU/USD الفوري من Twelve Data
// الإعداد: Settings > Variables and Secrets > أضف Secret باسم TD_KEY (مفتاح Twelve Data)
const IV = {"1m":"1min","5m":"5min","15m":"15min","1h":"1h","4h":"4h","1d":"1day"};
const CORS = {"Access-Control-Allow-Origin":"*","Access-Control-Allow-Methods":"GET,OPTIONS","Access-Control-Allow-Headers":"*"};
const J = (body, status=200, extra={}) => new Response(JSON.stringify(body), {status, headers:{"Content-Type":"application/json",...CORS,...extra}});
const fmt = ms => new Date(ms).toISOString().slice(0,19).replace("T"," ");

export default {
  async fetch(req, env, ctx) {
    if (req.method === "OPTIONS") return new Response(null, {headers: CORS});
    const u = new URL(req.url);
    if (u.pathname !== "/klines") return J({ok:true, source:"twelvedata XAU/USD"});
    const tf = u.searchParams.get("tf") || "1h";
    const iv = IV[tf];
    if (!iv) return J({error:"bad tf"}, 400);
    const limit = Math.max(1, Math.min(+u.searchParams.get("limit") || 500, 1000));
    const end = +u.searchParams.get("end") || 0;      // ملي ثانية

    const cache = caches.default;
    const ck = new Request(u.toString());
    const hit = await cache.match(ck);
    if (hit) return new Response(hit.body, {headers: hit.headers});

    let api = `https://api.twelvedata.com/time_series?symbol=XAU/USD&interval=${iv}&outputsize=${limit}&timezone=UTC&order=ASC&apikey=${env.TD_KEY}`;
    if (end) api += `&end_date=${encodeURIComponent(fmt(Math.floor(end/1000)*1000))}`;
    let j;
    try { j = await (await fetch(api)).json(); } catch (e) { return J({error:"upstream"}, 502); }
    if (!j.values) return J({error: j.message || "no data"}, 502);

    const seen = new Set();
    const rows = j.values.map(v => [
      Math.floor(Date.parse(v.datetime.replace(" ","T") + (v.datetime.length > 10 ? "Z" : "T00:00:00Z")) / 1000),
      +v.open, +v.high, +v.low, +v.close
    ]).filter(r => r[0] && !seen.has(r[0]) && seen.add(r[0])).sort((a,b) => a[0]-b[0]);

    const ttl = end ? 3600 : 100;
    const res = J(rows, 200, {"Cache-Control": `public, max-age=${ttl}`});
    ctx.waitUntil(cache.put(ck, res.clone()));
    return res;
  }
};
