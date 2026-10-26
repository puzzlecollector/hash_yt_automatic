"""Collect news articles for a trending keyword (direct links from the trends feed + Google News headlines)."""
import html, re, urllib.parse
import requests
from .trends import UA


def _article_text(url):
    try:
        import trafilatura
        r = requests.get(url, headers=UA, timeout=20)
        r.encoding = r.apparent_encoding or r.encoding
        t = trafilatura.extract(r.text, include_comments=False, include_tables=False) or ""
        return re.sub(r"\n{2,}", "\n", t).strip()
    except Exception:
        return ""


def google_news(keyword, n=10):
    q = urllib.parse.quote(f"{keyword} when:2d")
    x = requests.get(f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko", headers=UA, timeout=20).text
    out = []
    for it in re.findall(r"<item>(.*?)</item>", x, re.S)[:n]:
        g = lambda tag: html.unescape((re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", it, re.S) or [None, ""])[1])
        out.append({"title": g("title"), "source": g("source"), "date": g("pubDate"), "url": g("link")})
    return out


SKIP_DOM = ("naver.com", "pstatic.net", "w3.org", "naver.net", "youtube.com", "instagram.com", "facebook.com")


def naver_news(keyword, n=8):
    """Latest article URLs from Naver News search (press sites + n.news/m.sports.naver)."""
    r = requests.get("https://search.naver.com/search.naver", params={"where": "news", "query": keyword, "sort": "1"}, headers=UA, timeout=20)
    out, doms = [], set()
    for u in re.findall(r'href="(https?://[^"]+)"', r.text):
        u = html.unescape(u)
        dom = re.match(r"https?://([^/]+)", u).group(1)
        ok_naver = ("n.news.naver.com/mnews/article" in u) or ("m.sports.naver.com/" in u and "/article/" in u) or ("m.entertain.naver.com/" in u and "/article/" in u)
        if (any(d in dom for d in SKIP_DOM) and not ok_naver) or not re.search(r"\d{4,}", u): continue
        if dom in doms: continue
        doms.add(dom); out.append({"title": "", "url": u, "source": dom})
        if len(out) >= n: break
    return out


def collect(item, max_articles=5):
    arts = []
    pool = list(item.get("news", [])[:4])
    try: pool += naver_news(item["keyword"])
    except Exception: pass
    for n in pool:
        if not n.get("url"): continue
        txt = _article_text(n["url"])
        if len(txt) > 300 and item["keyword"].replace(" ", "").lower() in txt.replace(" ", "").lower():
            arts.append({**n, "text": txt[:3000]})
        if len(arts) >= max_articles: break
    heads = []
    try:
        heads = google_news(item["keyword"])
    except Exception:
        pass
    if item.get("notes"):   # extra facts supplied by the caller (e.g. market data)
        arts.insert(0, {"title": "제공된 데이터", "source": "data", "url": "", "text": item["notes"]})
    return {"articles": arts, "headlines": heads}
