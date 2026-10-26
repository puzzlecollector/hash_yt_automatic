"""Google Trends (KR) realtime keywords + a 'is it still rising?' score."""
import email.utils, html, json, math, re, time
from datetime import datetime, timezone
import requests
from . import config

RSS = "https://trends.google.com/trending/rss?geo=KR"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"}


def _traffic(s):
    m = re.search(r"([\d,]+)", s or "")
    return int(m.group(1).replace(",", "")) if m else 0


def fetch_rss():
    x = requests.get(RSS, headers=UA, timeout=30).text
    now = datetime.now(timezone.utc); out = []
    for it in re.findall(r"<item>(.*?)</item>", x, re.S):
        g = lambda tag: (re.search(rf"<{tag}>(.*?)</{tag}>", it, re.S) or [None, ""])[1]
        news = []
        for n in re.findall(r"<ht:news_item>(.*?)</ht:news_item>", it, re.S):
            ng = lambda tag: html.unescape((re.search(rf"<ht:{tag}>(.*?)</ht:{tag}>", n, re.S) or [None, ""])[1])
            news.append({"title": ng("news_item_title"), "url": ng("news_item_url"), "source": ng("news_item_source")})
        pub = email.utils.parsedate_to_datetime(g("pubDate")) if g("pubDate") else now
        out.append({"keyword": html.unescape(g("title")), "traffic": _traffic(g("ht:approx_traffic")),
                    "age_h": round((now - pub).total_seconds() / 3600, 2), "news": news})
    return out


def rising_curves(keywords):
    """Per keyword: ratio of the last 45 min vs the 45 min before (pytrends, 'now 4-H'). None if unavailable."""
    res = {}
    try:
        from pytrends.request import TrendReq
        py = TrendReq(hl="ko-KR", tz=-540, timeout=(10, 25))
        for i in range(0, len(keywords), 5):
            chunk = keywords[i:i + 5]
            try:
                py.build_payload(chunk, timeframe="now 4-H", geo="KR")
                df = py.interest_over_time()
                for k in chunk:
                    if k not in df: continue
                    s = df[k].astype(float).values
                    if len(s) < 20: continue
                    n = max(3, len(s) // 6)          # ~40 min windows on the 4h series
                    recent, prev = s[-n:].mean(), s[-2 * n:-n].mean()
                    res[k] = {"recent": round(float(recent), 1), "prev": round(float(prev), 1),
                              "ratio": round(float((recent + 1) / (prev + 1)), 2), "peak": float(s.max())}
            except Exception:
                pass
            time.sleep(2)
    except Exception:
        pass
    return res


def _history():
    p = config.STATE / "trend_snapshots.json"
    return (json.loads(p.read_text()) if p.exists() else []), p


def candidates():
    """Trending keywords ranked by rising momentum (traffic, recency, curve slope, change since last poll)."""
    items = fetch_rss()
    snaps, p = _history()
    last = {s["keyword"]: s["traffic"] for s in (snaps[-1]["items"] if snaps else [])}
    curves = rising_curves([i["keyword"] for i in items])
    for it in items:
        c = curves.get(it["keyword"])
        it["curve"] = c
        score = math.log10(max(it["traffic"], 50))                      # 2000+ -> 3.3
        score += max(0, 3 - it["age_h"]) * 0.4                          # freshly trending
        if c: score += min(2.0, max(-1.5, (c["ratio"] - 1) * 2))        # still going up?
        prev = last.get(it["keyword"])
        if prev is not None: score += 0.5 if it["traffic"] > prev else (-0.5 if it["traffic"] < prev else 0)
        it["prev_traffic"] = prev
        it["score"] = round(score, 2)
    items.sort(key=lambda i: -i["score"])
    snaps.append({"ts": datetime.now(timezone.utc).isoformat(), "items": [{"keyword": i["keyword"], "traffic": i["traffic"]} for i in items]})
    config.STATE.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(snaps[-60:], ensure_ascii=False, indent=1))
    return items


def recently_used(hours=None):
    hours = hours or config.TOPIC_COOLDOWN_H
    p = config.STATE / "made.json"
    made = json.loads(p.read_text()) if p.exists() else []
    now = time.time()   # skipped/failed topics may be retried after 4h (e.g. match results come in later)
    return [m for m in made if m["ts"] > now - (hours if m["status"] in ("ready", "needs_review") else 4) * 3600]


def mark_used(keyword, slug, status):
    p = config.STATE / "made.json"
    made = json.loads(p.read_text()) if p.exists() else []
    made.append({"keyword": keyword, "slug": slug, "status": status, "ts": time.time()})
    p.write_text(json.dumps(made[-500:], ensure_ascii=False, indent=1))
