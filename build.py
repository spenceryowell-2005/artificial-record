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

# Social profiles. Leave a value empty to hide that link.
SOCIAL = [
    ("LinkedIn", "https://www.linkedin.com/company/artificialrecord/"),
    ("X", "https://x.com/artificialrnews"),
    ("Instagram", "https://www.instagram.com/artificialrecord/"),
    ("Facebook", "https://www.facebook.com/profile.php?id=61594052120219"),
]
SITE_DESC = (
    "A daily briefing on the AI industry. Every claim source-linked, "
    "unconfirmed items labelled as such, nothing hyped."
)
SITE_URL = "https://artificialrecord.com"

# --------------------------------------------------------------------------
# EMAIL CAPTURE
#
# This is beehiiv's v3 script embed. beehiiv > Grow > Subscribe Forms > Embed
# gives you a tag like:
#   <script src="https://subscribe-forms.beehiiv.com/v3/loader.js"
#           data-beehiiv-form="THE-ID"></script>
# Only the data-beehiiv-form ID goes below. Nothing else, no quotes, no tags.
#
# Left empty, the signup block renders nothing and the site builds exactly as
# it did before. Nothing breaks if this is blank.
# --------------------------------------------------------------------------
SUBSCRIBE_FORM_ID = "e6878f91-43b4-40b5-9127-83e55a1eea18"
AUTHOR = "Artificial Record"
# Shown in the masthead dateline as "VOLUME I · NO. 9 · TUESDAY, ...".
# Roman numeral for the publication year/series; bump it each year.
VOLUME = "I"
# Words per minute used for the "EST. n MIN READ" line. 185 matches the
# figure the previous site displayed.
WPM = 185
LANGUAGE = "en-us"

# One flag controls the difference between the preview and the real site.
#
#   CUSTOM_DOMAIN unset  -> building for the github.io preview. Internal links
#                           are prefixed with /<repo>, no CNAME is written, and
#                           every page is marked noindex so the preview cannot
#                           compete with the real domain in search.
#   CUSTOM_DOMAIN=1      -> building for artificialrecord.com. Links are rooted
#                           at /, the CNAME is written, pages are indexable.
#
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


def read_minutes(html_text):
    """Rough reading time from the rendered body, in whole minutes."""
    words = len(re.sub(r"<[^>]+>", " ", html_text or "").split())
    return max(1, round(words / WPM))


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


def sub_form():
    """The beehiiv embed itself. Empty string until the form ID is set."""
    if not SUBSCRIBE_FORM_ID:
        return ""
    return (f'<script src="https://subscribe-forms.beehiiv.com/v3/loader.js" '
            f'data-beehiiv-form="{e(SUBSCRIBE_FORM_ID)}"></script>'
            f'<noscript><a href="https://embeds.beehiiv.com/{e(SUBSCRIBE_FORM_ID)}">'
            f'Subscribe by email</a></noscript>')


def sub_bar():
    """Slim signup strip directly under the masthead."""
    if not SUBSCRIBE_FORM_ID:
        return ""
    return f"""<section class="subbar">
  <div class="inner">
    <span class="kicker">The Briefing</span>
    <p class="say">Get the daily edition in your inbox.</p>
    <a class="cta" href="#subscribe">Subscribe</a>
  </div>
</section>"""


def sub_box():
    """Framed signup block before the footer."""
    if not SUBSCRIBE_FORM_ID:
        return ""
    return f"""<section class="subscribe" id="subscribe">
  <div class="box">
    <p class="kicker">Subscribe to the Daily</p>
    <h2>The AI briefing on your doorstep.</h2>
    <p>One email each morning. Source-backed, hype-free, built for operators.</p>
    <div class="form">{sub_form()}</div>
    <p class="fine">Free. Unsubscribe in one click.</p>
  </div>
</section>"""


SOCIAL_ICONS = {
    "LinkedIn": "M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z",
    "X": "M18.901 1.153h3.68l-8.04 9.19L24 22.846h-7.406l-5.8-7.584-6.638 7.584H.474l8.6-9.83L0 1.154h7.594l5.243 6.932ZM17.61 20.644h2.039L6.486 3.24H4.298Z",
    "Instagram": "M7.0301.084c-1.2768.0602-2.1487.264-2.911.5634-.7888.3075-1.4575.72-2.1228 1.3877-.6652.6677-1.075 1.3368-1.3802 2.127-.2954.7638-.4956 1.6365-.552 2.914-.0564 1.2775-.0689 1.6882-.0626 4.947.0062 3.2586.0206 3.6671.0825 4.9473.061 1.2765.264 2.1482.5635 2.9107.308.7889.72 1.4573 1.388 2.1228.6679.6655 1.3365 1.0743 2.1285 1.38.7632.295 1.6361.4961 2.9134.552 1.2773.056 1.6884.069 4.9462.0627 3.2578-.0062 3.668-.0207 4.9478-.0814 1.28-.0607 2.147-.2652 2.9098-.5633.7889-.3086 1.4578-.72 2.1228-1.3881.665-.6682 1.0745-1.3378 1.3795-2.1284.2957-.7632.4966-1.636.552-2.9124.056-1.2809.0692-1.6898.063-4.948-.0063-3.2583-.021-3.6668-.0817-4.9465-.0607-1.2797-.264-2.1487-.5633-2.9117-.3084-.7889-.72-1.4568-1.3876-2.1228C21.2982 1.33 20.628.9208 19.8378.6165 19.074.321 18.2017.1197 16.9244.0645 15.6471.0093 15.236-.005 11.977.0014 8.718.0076 8.31.0215 7.0301.0839m.1402 21.6932c-1.17-.0509-1.8053-.2453-2.2287-.408-.5606-.216-.96-.4771-1.3819-.895-.422-.4178-.6811-.8186-.9-1.378-.1644-.4234-.3624-1.058-.4171-2.228-.0595-1.2645-.072-1.6442-.079-4.848-.007-3.2037.0053-3.583.0607-4.848.05-1.169.2456-1.805.408-2.2282.216-.5613.4762-.96.895-1.3816.4188-.4217.8184-.6814 1.3783-.9003.423-.1651 1.0575-.3614 2.227-.4171 1.2655-.06 1.6447-.072 4.848-.079 3.2033-.007 3.5835.005 4.8495.0608 1.169.0508 1.8053.2445 2.228.408.5608.216.96.4754 1.3816.895.4217.4194.6816.8176.9005 1.3787.1653.4217.3617 1.056.4169 2.2263.0602 1.2655.0739 1.645.0796 4.848.0058 3.203-.0055 3.5834-.061 4.848-.051 1.17-.245 1.8055-.408 2.2294-.216.5604-.4763.96-.8954 1.3814-.419.4215-.8181.6811-1.3783.9-.4224.1649-1.0577.3617-2.2262.4174-1.2656.0595-1.6448.072-4.8493.079-3.2045.007-3.5825-.006-4.848-.0608M16.953 5.5864A1.44 1.44 0 1 0 18.39 4.144a1.44 1.44 0 0 0-1.437 1.4424M5.8385 12.012c.0067 3.4032 2.7706 6.1557 6.173 6.1493 3.4026-.0065 6.157-2.7701 6.1506-6.1733-.0065-3.4032-2.771-6.1565-6.174-6.1498-3.403.0067-6.156 2.771-6.1496 6.1738M8 12.0077a4 4 0 1 1 4.008 3.9921A3.9996 3.9996 0 0 1 8 12.0077",
    "Facebook": "M9.101 23.691v-7.98H6.627v-3.667h2.474v-1.58c0-4.085 1.848-5.978 5.858-5.978.401 0 .955.042 1.468.103a8.68 8.68 0 0 1 1.141.195v3.325a8.623 8.623 0 0 0-.653-.036 26.805 26.805 0 0 0-.733-.009c-.707 0-1.259.096-1.675.309a1.686 1.686 0 0 0-.679.622c-.258.42-.374.995-.374 1.752v1.297h3.919l-.386 2.103-.287 1.564h-3.246v8.245C19.396 23.238 24 18.179 24 12.044c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.628 3.874 10.35 9.101 11.647Z",
}

def social_row():
    items = []
    for n, u in SOCIAL:
        if not u or n not in SOCIAL_ICONS:
            continue
        items.append(
            f'<a class="soc" href="{e(u)}" rel="me noopener" target="_blank" '
            f'aria-label="{e(n)}" title="{e(n)}">'
            f'<svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true">'
            f'<path fill="currentColor" d="{SOCIAL_ICONS[n]}"/></svg>'
            f'<span>{e(n)}</span></a>')
    if not items:
        return ""
    return ('<div class="social"><p class="social-h">Follow Artificial Record</p>'
            '<div class="social-row">' + "".join(items) + "</div></div>")


SOCIAL_CSS = ("<style>"
    "footer.site .social{margin-top:22px}"
    "footer.site .social-h{font-family:var(--label);font-size:11px;font-weight:600;"
    "letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3);margin:0 0 10px}"
    "footer.site .social-row{display:flex;flex-wrap:wrap;gap:12px}"
    "footer.site a.soc{display:inline-flex;align-items:center;gap:10px;"
    "padding:11px 18px;min-height:48px;border:1px solid var(--rule);border-radius:3px;"
    "color:var(--ink);text-decoration:none;font-family:var(--label);font-size:15px;"
    "font-weight:600;transition:background .15s,color .15s,border-color .15s}"
    "footer.site a.soc svg{width:24px;height:24px;flex:none}"
    "footer.site a.soc:hover,footer.site a.soc:focus-visible{background:var(--accent);"
    "border-color:var(--accent);color:#fff}"
    "@media (max-width:520px){footer.site .social-row{display:grid;grid-template-columns:1fr 1fr}"
    "footer.site a.soc{justify-content:center}}"
    "</style>")


def chrome(inner, title, desc, canonical, kind="website", published=None,
           jsonld="", dateline="", after_main=""):
    line = dateline or f"Volume {VOLUME}"
    return f"""<!doctype html>
<html lang="en">
<head>
{head(title, desc, canonical, kind, published)}
{jsonld}
{SOCIAL_CSS}
</head>
<body>
<header class="site">
  <div class="inner">
    <a class="wordmark" href="{BASE}/">{e(SITE_TITLE)}</a>
    <p class="tagline">{e(SITE_TAGLINE)}</p>
    <div class="rules"></div>
    <p class="dateline">{line}</p>
  </div>
</header>
{sub_bar()}
<nav class="site"><div class="inner">
  <a href="{BASE}/">Latest</a>
  <a href="{BASE}/archive/">Archive</a>
  <a href="{BASE}/about/">About</a>
  <a href="{BASE}/feed.xml">RSS</a>
  {'<a href="#subscribe">Subscribe</a>' if SUBSCRIBE_FORM_ID else ''}
</div></nav>
<main>
{inner}
</main>
{after_main}
{sub_box()}
<footer class="site">
  <p>{e(SITE_TITLE)} — {e(SITE_TAGLINE)}</p>
  {social_row()}
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
    jsonld = f"""<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"NewsArticle","headline":{_j(ed['title'])},
"datePublished":"{ed['date']}","dateModified":"{ed['date']}",
"description":{_j(ed['summary'])},"url":"{canonical}",
"publisher":{{"@type":"Organization","name":{_j(SITE_TITLE)}}},
"author":{{"@type":"Organization","name":{_j(AUTHOR)}}}}}
</script>"""
    inner = f"""<article class="edition">
  <div class="meta-row">
    <span class="eyebrow">Executive Read</span>
    <span class="readtime">Est. {read_minutes(ed['html'])} min read</span>
  </div>
  <h1>{e(ed['title'])}</h1>
  {f'<p class="standfirst">{e(ed["summary"])}</p>' if ed['summary'] else ''}
  {player(ed)}
  <div class="prose">
{ed['html']}
  </div>
</article>
<p class="backlink"><a href="{BASE}/archive/">← All editions</a></p>"""
    return chrome(inner, ed["title"], ed["summary"] or SITE_DESC, canonical,
                  kind="article", published=ed["date"], jsonld=jsonld,
                  dateline=masthead_line(ed))


def masthead_line(ed):
    num = f" · No. {e(ed['number'])}" if ed["number"] else ""
    return f"Volume {VOLUME}{num} · {ed['dt']:%A}, {ed['dt']:%B} {ed['dt'].day}, {ed['dt']:%Y}"


def _j(s):
    return '"' + (s or "").replace("\\", "\\\\").replace('"', '\\"') + '"'


def index_page(editions):
    if not editions:
        return chrome("<p>No editions yet.</p>", SITE_TITLE, SITE_DESC, SITE_URL + "/")
    latest = editions[0]
    cards = "".join(
        f"""<li><a href="{BASE}/editions/{e(x['slug'])}/">
        <span class="d">No. {e(x['number']) if x['number'] else '—'} · {x['dt']:%B} {x['dt'].day}, {x['dt']:%Y}</span>
        <span class="t">{e(x['title'])}</span>
        <span class="s">{e((x['summary'] or '')[:150] + ('…' if len(x['summary'] or '') > 150 else ''))}</span></a></li>"""
        for x in editions[1:4]
    )
    recent = f"""<section class="recent">
  <div class="head">
    <h2>Recent Editions</h2>
    <a class="all" href="{BASE}/archive/">Full archive →</a>
  </div>
  <ul>{cards}</ul>
</section>""" if cards else ""

    inner = f"""<article class="edition">
  <div class="meta-row">
    <span class="eyebrow">Executive Read</span>
    <span class="readtime">Est. {read_minutes(latest['html'])} min read</span>
  </div>
  <h1>{e(latest['title'])}</h1>
  {f'<p class="standfirst">{e(latest["summary"])}</p>' if latest['summary'] else ''}
  {player(latest)}
  <div class="prose">
{latest['html']}
  </div>
</article>"""
    return chrome(inner, f"{SITE_TITLE} — {SITE_TAGLINE}", SITE_DESC, SITE_URL + "/",
                  dateline=masthead_line(latest), after_main=recent)


def about_page():
    inner = """<h1 class="page-title">About</h1>
<p class="standfirst">What this is, who writes it, and the rules it follows.</p>
<div class="prose">
<p><em>Artificial Record</em> is a daily briefing on the artificial-intelligence
industry, published every morning. It is written for people who work in AI and
in the fields it is reshaping — finance, law, consulting, operations, marketing,
engineering management. It assumes intelligence, not specialist knowledge.</p>

<h2>The standards</h2>
<p>The AI newsletter category is crowded with summarised press releases written
excitedly. This publication is built on the opposite premise, and these rules are
not negotiable:</p>
<p><strong>Every claim traces to a source.</strong> Primary sources first — company
newsrooms, regulatory filings, court dockets, investor relations. We fetch the
announcement, not an aggregator's summary of it.</p>
<p><strong>Uncertainty is labelled in the text.</strong> "Reported by", "in talks",
"according to". Something reported is never presented as something confirmed.</p>
<p><strong>What cannot be verified is dropped.</strong> A shorter edition beats a
padded one. One fabricated item costs more trust than a hundred correct ones earn.</p>
<p><strong>Nothing is hyped.</strong> No game-changers, no revolutions, no engagement
bait. Where a vendor's benchmark is the vendor's own, we say so.</p>
<p><strong>Public-company coverage is informational only.</strong> Nothing here is
financial advice, and nothing here is legal advice.</p>

<h2>Corrections</h2>
<p>When we get something wrong we correct it in the text of the next edition and
say plainly what is being withdrawn. If you spot an error, write to
<a href="mailto:corrections@artificialrecord.com">corrections@artificialrecord.com</a>
and it will be read.</p>

<h2>Contact</h2>
<p>Editorial: <a href="mailto:editor@artificialrecord.com">editor@artificialrecord.com</a><br>
Everything else: <a href="mailto:hello@artificialrecord.com">hello@artificialrecord.com</a></p>
</div>"""
    return chrome(inner, f"About — {SITE_TITLE}", SITE_DESC, SITE_URL + "/about/")


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
    write("about/index.html", about_page())
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
