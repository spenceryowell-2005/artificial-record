# Artificial Record

The AI industry, on the record. A daily briefing published at
[artificialrecord.com](https://artificialrecord.com).

## How this repository works

Editions are markdown files in `content/editions/`, one per day, named by date.
`build.py` turns them into a complete static site in `site/`, which GitHub
Actions deploys to GitHub Pages on every push to `main`.

There is no framework and one dependency. The daily publish is the one thing
that must not break, so the build has as few moving parts as possible.

```
content/editions/YYYY-MM-DD.md   the editions
audio/YYYY-MM-DD.mp3             optional audio, matched to an edition by date
static/style.css                 the whole stylesheet
build.py                         the whole build
site/                            output, not committed
```

## Building locally

```bash
pip install markdown
python3 build.py
python3 -m http.server -d site 8000
```

## Edition format

Front matter, then markdown:

```markdown
---
title: AI Industry Daily Briefing — September 3, 2026
date: 2026-09-03
edition: 4
slug: ai-industry-daily-briefing-2026-09-03
summary: One sentence for the archive, the feed and the link preview.
---

## The Executive Read
...
```

`date` sets the URL, the feed order and the audio pairing. `slug` is the
permanent URL and must never change once an edition is published.

## Audio

If `audio/<date>.mp3` exists, the edition page renders a player and the RSS
item gains an `<enclosure>`. If it does not, neither appears and nothing else
changes. Audio is generated in the GitHub Action, which has network access the
publishing environment does not.

## Editorial standards

Every claim traces to a source that was actually fetched. Items that are
reported rather than confirmed are labelled in the text. Nothing is hyped, and
no edition is padded to reach a length. A shorter edition beats a padded one.
