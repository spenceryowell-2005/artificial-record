#!/usr/bin/env python3
"""
Artificial Record — static site builder.

Reads markdown editions from content/editions/*.md and writes a complete
server-rendered site to site/. No framework, no plugins: the daily publish
must not break because a dependency updated overnight.

Usage:  python3 build.py
Output: site/
"""

import html
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path

import markdown

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

SITE_TITLE = "Artificial Record"
SITE_TAGLINE = "The AI industry, on the record."
SITE_DESC = (
    "A daily briefing on the AI industry. Every claim source-linked, "
    "unconfirmed items labelled as such, nothing hyped."
)
SITE_URL = "https://artificialrecord.com"
AUTHOR = "Artificial Record"
LANGUAGE = "en-us"

# One flag controls the difference between the preview and the real site.
#
#   CUSTOM_DOMAIN unset  -> building for the github.io preview. Internal links
#                           are prefixed with /<repo>, no CNAME is written, and
#                           every page is marked noindex so the preview cannot
#                           compete with the real domain in search.
#   CUSTOM_DOMAIN=1      -> building for artificialrecord.com. Links are rooted
#                           at /, the CNAME is written, pages are indexable.
SUBSCRIBE_EMBED_URL = "#https://subscribe-forms.beehiiv.com/v3/loader.js" data-beehiiv-form="e6878f91-43b4-40b5-9127-83e55a1eea18"></script>"
# Set it in the workflow at DNS cutover (checklist item 12). Nothing else changes.
CUSTOM_DOMAIN = os.environ.get("CUSTOM_DOMAIN") == "1"
_REPO = os.environ.get("GITHUB_REPOSITORY", "")
BASE = "" if CUSTOM_DOMAIN or not _REPO else "/" + _REPO.split("/")[-1]

ROOT = Path(__file__).parent.resolve()
CONTENT = ROOT / "content" / "editions"
AUDIO = ROOT / "audio"
STATIC = ROOT / "static"
OUT = ROOT / "site"

# Phase 2 hook. Audio is optional everywhere: a missing MP3 must never
# break a page, a feed, or the build.
AUDIO_EXT = ".mp3"
AUDIO_MIME = "audio/mpeg"

MD = markdown.Markdown(extensions=["extra", "sane_lists", "smarty"])


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------

def parse_front_matter(text):
    """Return (meta dict, body). Front matter is `key: value` between --- fences."""
    meta, body = {}, text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            block = text[3:end].strip()
            body = text[end + 4:].lstrip("\n")
            for line in block.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip().lower()] = v.strip()
    return meta, body


def strip_leading_title(body):
    """Drop the H1 and an immediately following italic standfirst; the
    template renders both from metadata so they must not appear twice."""
    lines = body.splitlines()
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i < len(lines) and lines[i].startswith("# "):
        i += 1
        while i < len(lines) and not lines[i].strip():
            i += 1
        if i < len(lines) and re.match(r"^\*[^*].*\*$", lines[i].strip()):
            i += 1
        while i < len(lines) and lines[i].strip() in ("", "---"):
            i += 1
    return "\n".join(lines[i:])


def audio_for(date_str):
    """Return (relative_url, byte_size) if an MP3 exists for this date, else None."""
    p = AUDIO / f"{date_str}{AUDIO_EXT}"
    if p.exists() and p.stat().st_size > 0:
        return (f"/audio/{date_str}{AUDIO_EXT}", p.stat().st_size)
    return None


def load_editions():
    editions = []
    if not CONTENT.exists():
        return editions
    for path in sorted(CONTENT.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        meta, body = parse_front_matter(raw)
        date_str = meta.get("date") or path.stem
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            print(f"  ! skipping {path.name}: unreadable date {date_str!r}", file=sys.stderr)
            continue
        num = meta.get("edition", "")
        slug = meta.get("slug") or f"ai-industry-daily-briefing-{date_str}"
        MD.reset()
        editions.append({
            "path": path,
            "date": date_str,
            "dt": dt,
            "number": num,
            "slug": slug,
            "title": meta.get("title") or f"AI Industry Daily Briefing — {dt:%B %-d, %Y}",
            "summary": meta.get("summary", ""),
            "html": MD.convert(strip_leading_title(body)),
            "audio": audio_for(date_str),
        })
    editions.sort(key=lambda e: e["date"], reverse=True)
    return editions


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

def e(s):
    return html.escape(s or "", quote=True)


def head(title, desc, canonical, kind="website", published=None):
    tags = [
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{e(title)}</title>",
        f'<meta name="description" content="{e(desc)}">',
        f'<link rel="canonical" href="{e(canonical)}">',
        f'<link rel="stylesheet" href="{BASE}/style.css">',
        f'<link rel="alternate" type="application/rss+xml" title="{e(SITE_TITLE)}" href="{BASE}/feed.xml">',
        f'<meta property="og:type" content="{e(kind)}">',
        f'<meta property="og:title" content="{e(title)}">',
        f'<meta property="og:description" content="{e(desc)}">',
        f'<meta property="og:url" content="{e(canonical)}">',
        f'<meta property="og:site_name" content="{e(SITE_TITLE)}">',
        '<meta name="twitter:card" content="summary">',
        f'<meta name="twitter:title" content="{e(title)}">',
        f'<meta name="twitter:description" content="{e(desc)}">',
    ]
    if published:
        tags.append(f'<meta property="article:published_time" content="{published}">')
    if not CUSTOM_DOMAIN:
        tags.append('<meta name="robots" content="noindex, nofollow">')
    return "\n".join(tags)


def chrome(inner, title, desc, canonical, kind="website", published=None, jsonld=""):
    return f"""<!doctype html>
<html lang="en">
<head>
{head(title, desc, canonical, kind, published)}
{jsonld}
</head>
<body>
<header class="site">
  <a class="wordmark" href="{BASE}/">{e(SITE_TITLE)}</a>
  <p class="tagline">{e(SITE_TAGLINE)}</p>
  <nav><a href="{BASE}/">Latest</a><a href="{BASE}/archive/">Archive</a><a href="{BASE}/feed.xml">RSS</a></nav>
</header>
<main>
{inner}
</main>
<footer class="site">
  <p>{e(SITE_TITLE)} — {e(SITE_TAGLINE)}</p>
  <p class="fine">Every claim traces to a source we fetched. Items that are reported rather than confirmed are labelled as such. Informational only; nothing here is financial advice.</p>
</footer>
</body>
</html>
"""


def player(ed):
    """Phase 2 hook: renders nothing at all when no MP3 exists for the date."""
    if not ed["audio"]:
        return ""
    url, _size = ed["audio"]
    url = BASE + url
    return f"""<div class="listen">
  <p class="listen-label">Listen to this edition</p>
  <audio controls preload="none" src="{e(url)}"></audio>
</div>"""


def edition_page(ed):
    canonical = f"{SITE_URL}/editions/{ed['slug']}/"
    num = f"No. {e(ed['number'])} · " if ed["number"] else ""
    jsonld = f"""<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"NewsArticle","headline":{_j(ed['title'])},
"datePublished":"{ed['date']}","dateModified":"{ed['date']}",
"description":{_j(ed['summary'])},"url":"{canonical}",
"publisher":{{"@type":"Organization","name":{_j(SITE_TITLE)}}},
"author":{{"@type":"Organization","name":{_j(AUTHOR)}}}}}
</script>"""
    inner = f"""<article class="edition">
  <p class="eyebrow">{num}{ed['dt']:%B} {ed['dt'].day}, {ed['dt']:%Y}</p>
  <h1>{e(ed['title'])}</h1>
  {f'<p class="standfirst">{e(ed["summary"])}</p>' if ed['summary'] else ''}
  {player(ed)}
  <div class="prose">
{ed['html']}
  </div>
</article>
<p class="backlink"><a href="{BASE}/archive/">← All editions</a></p>"""
    return chrome(inner, ed["title"], ed["summary"] or SITE_DESC, canonical,
                  kind="article", published=ed["date"], jsonld=jsonld)


def _j(s):
    return '"' + (s or "").replace("\\", "\\\\").replace('"', '\\"') + '"'


def index_page(editions):
    if not editions:
        return chrome("<p>No editions yet.</p>", SITE_TITLE, SITE_DESC, SITE_URL + "/")
    latest = editions[0]
    num = f"No. {e(latest['number'])} · " if latest["number"] else ""
    recent = "".join(
        f"""<li><a href="{BASE}/editions/{e(x['slug'])}/">
        <span class="d">{x['dt']:%b} {x['dt'].day}</span>
        <span class="t">{e(x['summary'] or x['title'])}</span></a></li>"""
        for x in editions[1:11]
    )
    inner = f"""<article class="edition">
  <p class="eyebrow">Today · {num}{latest['dt']:%B} {latest['dt'].day}, {latest['dt']:%Y}</p>
  <h1>{e(latest['title'])}</h1>
  {f'<p class="standfirst">{e(latest["summary"])}</p>' if latest['summary'] else ''}
  {player(latest)}
  <div class="prose">
{latest['html']}
  </div>
</article>
{f'<section class="recent"><h2>Recent editions</h2><ul>{recent}</ul></section>' if recent else ''}"""
    return chrome(inner, f"{SITE_TITLE} — {SITE_TAGLINE}", SITE_DESC, SITE_URL + "/")


def archive_page(editions):
    rows = "".join(
        f"""<li><a href="{BASE}/editions/{e(x['slug'])}/">
        <span class="d">{x['dt']:%b} {x['dt'].day}, {x['dt']:%Y}</span>
        <span class="n">{('No. ' + e(x['number'])) if x['number'] else ''}</span>
        <span class="t">{e(x['summary'] or x['title'])}</span>
        {'<span class="a">audio</span>' if x['audio'] else ''}</a></li>"""
        for x in editions
    )
    inner = f"""<h1 class="page-title">Archive</h1>
<p class="standfirst">Every edition published, most recent first.</p>
<ul class="archive">{rows}</ul>"""
    return chrome(inner, f"Archive — {SITE_TITLE}",
                  f"Every edition of {SITE_TITLE}, most recent first.",
                  SITE_URL + "/archive/")


def feed_xml(editions):
    now = format_datetime(datetime.now(timezone.utc))
    items = []
    for x in editions[:50]:
        link = f"{SITE_URL}/editions/{x['slug']}/"
        enclosure = ""
        if x["audio"]:
            url, size = x["audio"]
            enclosure = f'<enclosure url="{e(SITE_URL + url)}" length="{size}" type="{AUDIO_MIME}"/>'
        items.append(f"""    <item>
      <title>{e(x['title'])}</title>
      <link>{e(link)}</link>
      <guid isPermaLink="true">{e(link)}</guid>
      <pubDate>{format_datetime(x['dt'])}</pubDate>
      <description>{e(x['summary'])}</description>
      {enclosure}
    </item>""")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{e(SITE_TITLE)}</title>
    <link>{e(SITE_URL)}</link>
    <description>{e(SITE_DESC)}</description>
    <language>{LANGUAGE}</language>
    <lastBuildDate>{now}</lastBuildDate>
    <atom:link href="{e(SITE_URL)}/feed.xml" rel="self" type="application/rss+xml"/>
{chr(10).join(items)}
  </channel>
</rss>
"""


def sitemap_xml(editions):
    urls = [f"{SITE_URL}/", f"{SITE_URL}/archive/"]
    urls += [f"{SITE_URL}/editions/{x['slug']}/" for x in editions]
    body = "".join(f"  <url><loc>{e(u)}</loc></url>\n" for u in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{body}</urlset>\n")


# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------

def write(rel, text):
    p = OUT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def main():
    editions = load_editions()
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    write("index.html", index_page(editions))
    write("archive/index.html", archive_page(editions))
    for ed in editions:
        write(f"editions/{ed['slug']}/index.html", edition_page(ed))
    write("feed.xml", feed_xml(editions))
    write("sitemap.xml", sitemap_xml(editions))
    write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n")
    if CUSTOM_DOMAIN:
        write("CNAME", SITE_URL.replace("https://", "").replace("http://", "") + "\n")

    css = STATIC / "style.css"
    if css.exists():
        shutil.copy(css, OUT / "style.css")

    if AUDIO.exists():
        for mp3 in AUDIO.glob(f"*{AUDIO_EXT}"):
            (OUT / "audio").mkdir(exist_ok=True)
            shutil.copy(mp3, OUT / "audio" / mp3.name)

    with_audio = sum(1 for x in editions if x["audio"])
    print(f"Built {len(editions)} edition(s) -> {OUT}")
    if editions:
        print(f"  latest: {editions[0]['date']}  ({editions[0]['slug']})")
    print(f"  audio attached: {with_audio}")


if __name__ == "__main__":
    main()
