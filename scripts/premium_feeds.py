"""Fetch free RSS headlines from FT, NYT, WSJ and The Economist.

Prints a JSON list of {publisher, title, url, publishedAt, summary} from the last
72 hours, newest first. Feeds that fail are listed on stderr and skipped.
"""
import email.utils, html, json, re, sys, urllib.request
from datetime import datetime, timedelta, timezone

FEEDS = {
    "Financial Times": ["https://www.ft.com/rss/home", "https://www.ft.com/markets?format=rss", "https://www.ft.com/companies?format=rss"],
    "The New York Times": ["https://rss.nytimes.com/services/xml/rss/nyt/Business.xml", "https://rss.nytimes.com/services/xml/rss/nyt/Economy.xml", "https://rss.nytimes.com/services/xml/rss/nyt/YourMoney.xml"],
    "The Wall Street Journal": ["https://feeds.content.dowjones.io/public/rss/RSSMarketsMain", "https://feeds.content.dowjones.io/public/rss/RSSWorldNews", "https://feeds.content.dowjones.io/public/rss/RSSUSnews", "https://feeds.a.dj.com/rss/RSSMarketsMain.xml"],
    "The Economist": ["https://www.economist.com/finance-and-economics/rss.xml", "https://www.economist.com/business/rss.xml", "https://www.economist.com/leaders/rss.xml"],
}

def text(block, tag):
    m = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", block, re.S | re.I)
    if not m:
        return ""
    v = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", m.group(1), flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(v))).strip()

def parse(xml, publisher, since):
    out = []
    for block in re.findall(r"<item\b[^>]*>(.*?)</item>", xml, re.S | re.I):
        title, link = text(block, "title"), text(block, "link") or text(block, "guid")
        if not title or not link.startswith("https://"):
            continue
        published = None
        raw = text(block, "pubDate") or text(block, "dc:date")
        if raw:
            try:
                d = email.utils.parsedate_to_datetime(raw)
            except (TypeError, ValueError):
                try:
                    d = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                except ValueError:
                    d = None
            if d is not None:
                d = d if d.tzinfo else d.replace(tzinfo=timezone.utc)
                if d < since:
                    continue
                published = d.astimezone(timezone.utc).isoformat(timespec="seconds")
        out.append({"publisher": publisher, "title": title, "url": link.split("?")[0] if "nytimes.com" in link else link,
                    "publishedAt": published, "summary": text(block, "description")[:300]})
    return out

def main():
    since = datetime.now(timezone.utc) - timedelta(hours=72)
    items, seen = [], set()
    for publisher, urls in FEEDS.items():
        for url in urls:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "EquityLedger/1.0 (RSS reader)", "Accept": "application/rss+xml, application/xml, text/xml"})
                with urllib.request.urlopen(req, timeout=15) as r:
                    xml = r.read().decode("utf-8", "replace")
            except Exception as e:  # network policy, 403, timeout
                print(f"skip {url}: {e}", file=sys.stderr)
                continue
            for it in parse(xml, publisher, since):
                key = it["title"].lower()
                if key not in seen:
                    seen.add(key)
                    items.append(it)
    items.sort(key=lambda i: i["publishedAt"] or "", reverse=True)
    json.dump(items, sys.stdout, ensure_ascii=False)

if __name__ == "__main__":
    main()
