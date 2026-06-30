"""
Daily-post agent. Runs from the .github/workflows/daily-post.yml cron.

Flow:
  1. Decide a topic for today's post.
     - If TOPIC_OVERRIDE env var is set (manual workflow run), use that.
     - Otherwise: pull fresh items from PSL/Pakistan cricket RSS feeds,
       filter for Hyderabad Kingsmen mentions or PSL/Pakistan news,
       dedupe against .seen_urls.json so we don't write the same story twice.
     - If no fresh news on a given day, fall back to a rotating off-season
       topic from data/offseason_topics.txt (e.g. "Profile a Kingsmen player",
       "Niaz Stadium retrospective", "PSL 2027 fixture preview").
  2. Generate original analysis via the Anthropic Claude API in Pakistani-
     English editorial voice. Return JSON: title, slug, excerpt, body_md, tags.
  3. Render a Pillow banner with the headline, save to static/banners/.
  4. Write the post Markdown to content/posts/SLUG.md with Hugo front-matter.
  5. Update .seen_urls.json with anything used.

The workflow file commits anything new and pushes.

Required env:
  ANTHROPIC_API_KEY   - the Claude API key (set as repo secret)

Optional env:
  TOPIC_OVERRIDE      - manual topic for the day
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import feedparser
from bs4 import BeautifulSoup
from slugify import slugify

ROOT = Path(__file__).resolve().parent.parent
SEEN_CACHE = ROOT / "data" / ".seen_urls.json"
OFFSEASON_TOPICS = ROOT / "data" / "offseason_topics.txt"
POSTS_DIR = ROOT / "content" / "posts"
BANNERS_DIR = ROOT / "static" / "banners"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("daily-post")


# Reasonable, free, English-language Pakistan cricket sources.
# You can add more by appending dicts here.
RSS_SOURCES = [
    {"name": "Dawn cricket",      "url": "https://www.dawn.com/feeds/sports"},
    {"name": "Geo Super",         "url": "https://www.geosuper.tv/rss"},
    {"name": "ESPNcricinfo PAK",  "url": "https://www.espncricinfo.com/rss/content/story/feeds/2.xml"},
]

# Keyword priority. Higher = more likely to be picked.
# Independent Pakistan cricket publication — broad scope, Kingsmen as one focus.
PRIORITY_KEYWORDS = [
    ("hyderabad kingsmen",     8),
    ("kingsmen",               6),
    ("psl",                    7),
    ("pakistan super league",  7),
    ("babar azam",             6),
    ("mohammad rizwan",        6),
    ("shaheen afridi",         6),
    ("naseem shah",            5),
    ("saim ayub",              5),
    ("pakistan cricket",       5),
    ("pakistan vs",            6),
    ("test cricket pakistan",  4),
    ("champions trophy",       4),
    ("t20 world cup",          4),
    ("marnus labuschagne",     4),
    ("sharjeel khan",          3),
    ("riley meredith",         3),
    ("jason gillespie",        3),
    ("niaz stadium",           3),
    ("gaddafi stadium",        3),
    ("national stadium",       3),
    ("pcb",                    3),
    ("quaid-e-azam",           2),
    ("sindh cricket",          3),
]


@dataclass
class NewsItem:
    title: str
    summary: str
    link: str
    source: str

    @property
    def fingerprint(self) -> str:
        return hashlib.sha1(self.link.encode()).hexdigest()

    def score(self) -> int:
        text = (self.title + " " + self.summary).lower()
        return sum(weight for kw, weight in PRIORITY_KEYWORDS if kw in text)


def load_seen() -> set[str]:
    if SEEN_CACHE.exists():
        return set(json.loads(SEEN_CACHE.read_text()))
    return set()


def save_seen(seen: set[str]) -> None:
    SEEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
    SEEN_CACHE.write_text(json.dumps(sorted(seen)))


def fetch_news() -> list[NewsItem]:
    items: list[NewsItem] = []
    for src in RSS_SOURCES:
        try:
            parsed = feedparser.parse(src["url"])
            if parsed.bozo:
                log.warning("Feed %s parse warning: %s", src["name"], parsed.bozo_exception)
            for entry in parsed.entries[:25]:
                summary_html = entry.get("summary", "")
                summary_text = BeautifulSoup(summary_html, "html.parser").get_text(" ", strip=True)
                items.append(
                    NewsItem(
                        title=entry.get("title", "").strip(),
                        summary=summary_text[:1200],
                        link=entry.get("link", "").strip(),
                        source=src["name"],
                    )
                )
        except Exception as exc:  # noqa: BLE001
            log.warning("Failed source %s: %s", src["name"], exc)
    return items


def pick_topic(seen: set[str]) -> tuple[str, str | None]:
    """Return (topic_description, source_url). source_url may be None for off-season."""
    override = os.environ.get("TOPIC_OVERRIDE", "").strip()
    if override:
        log.info("Using TOPIC_OVERRIDE: %s", override)
        return override, None

    items = fetch_news()
    fresh = [it for it in items if it.fingerprint not in seen]
    if fresh:
        fresh.sort(key=lambda x: x.score(), reverse=True)
        best = fresh[0]
        if best.score() >= 1:
            log.info("Picked news topic (score %d): %s", best.score(), best.title)
            return f"{best.title}\n\nSource summary: {best.summary}", best.link

    # Fallback: off-season topic
    if OFFSEASON_TOPICS.exists():
        topics = [t.strip() for t in OFFSEASON_TOPICS.read_text().splitlines() if t.strip() and not t.startswith("#")]
        if topics:
            # rotate by day-of-year so the same topic doesn't repeat in a week
            doy = datetime.now(timezone.utc).timetuple().tm_yday
            topic = topics[doy % len(topics)]
            log.info("No fresh news. Using off-season topic: %s", topic)
            return topic, None

    # Absolute fallback
    return "Write a 700-word off-season analysis piece about the Hyderabad Kingsmen's PSL 2026 debut season and what to watch for in PSL 2027.", None


def claude_write_post(topic: str, source_url: str | None) -> dict[str, Any]:
    """Call Anthropic and return {title, slug, excerpt, body_md, tags}."""
    from anthropic import Anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        sys.exit("ANTHROPIC_API_KEY not set. Add it as a repo secret.")

    client = Anthropic(api_key=api_key)

    system = (
        "You are a senior cricket writer for an INDEPENDENT Pakistan cricket publication "
        "(domain: hyderabadkingsmen.com). This site covers the Pakistan Super League (all "
        "eight franchises, with a slightly heavier focus on the Hyderabad Kingsmen because "
        "of the domain), the Pakistan national cricket teams (Test, ODI, T20I), Sindh and "
        "Hyderabad domestic cricket, and ICC events.\n\n"
        "IMPORTANT: This publication is NOT the official Hyderabad Kingsmen PSL franchise. "
        "It is not affiliated with the PCB or the PSL. It is an independent fan publication. "
        "Cover the Kingsmen as a journalistic subject, not as the publication's team. "
        "Cover the whole Pakistan cricket scene — Babar Azam's national team, the wider PSL, "
        "Pakistan tours abroad — at least as seriously as you cover the Kingsmen.\n\n"
        "VOICE\n"
        "- Crisp, knowledgeable, slightly opinionated. Pakistani-English idiom.\n"
        "- Active voice. Short paragraphs.\n"
        "- Never use em dashes (--). Use commas or sentence breaks.\n"
        "- Refer to teams in third person. Never say 'we' or 'our' about any cricket team.\n"
        "RULES\n"
        "- Produce ORIGINAL analysis. Do not paraphrase any source sentence-by-sentence.\n"
        "- If a fact is not in the source, do not invent it. Hedge or omit.\n"
        "- Where you cite a source, do so at the bottom of the post.\n"
        "STRUCTURE (700-900 words)\n"
        "1. Lede (2-3 sentences) — what happened, why it matters for Pakistan cricket.\n"
        "2. The angle: what this story is really about.\n"
        "3. What it means going forward (for the team or player involved).\n"
        "4. What to watch next.\n"
        "5. If a source URL was provided, include `Source: <link>` line at the end.\n"
        "OUTPUT FORMAT (strict)\n"
        "Return ONLY a JSON object with keys: title, slug, excerpt, body_md, tags.\n"
        "- title: SEO-friendly headline 50-70 chars.\n"
        "- slug: kebab-case slug, max 60 chars, no dates.\n"
        "- excerpt: 1-2 sentence summary for meta description, 150-200 chars.\n"
        "- body_md: full Markdown body (no front-matter, no title H1).\n"
        "- tags: list of 4-7 lowercase tags (include 'pakistan-cricket' or 'psl' as one tag).\n"
        "Do NOT wrap the JSON in code fences."
    )

    user = f"TOPIC TODAY:\n{topic}\n"
    if source_url:
        user += f"\nSOURCE URL TO CITE: {source_url}\n"

    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    raw = resp.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.lstrip().startswith("json"):
            raw = raw.split("\n", 1)[1]
        raw = raw.rstrip("`").strip()
    return json.loads(raw)


def render_banner(slug: str, headline: str) -> Path:
    """Render a 1200x630 banner using Pillow. Brand: gold + black."""
    from PIL import Image, ImageDraw, ImageFont

    BANNERS_DIR.mkdir(parents=True, exist_ok=True)
    width, height = 1200, 630
    img = Image.new("RGB", (width, height), "#000000")
    draw = ImageDraw.Draw(img)

    # Top gold stripe
    draw.rectangle([(0, 0), (width, 12)], fill="#D4AF37")

    # Find a font
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "/Library/Fonts/Arial Bold.ttf",
    ]
    kicker_font, headline_font, brand_font = None, None, None
    for p in font_paths:
        try:
            kicker_font = ImageFont.truetype(p, 28)
            headline_font = ImageFont.truetype(p, 64)
            brand_font = ImageFont.truetype(p, 26)
            break
        except (OSError, IOError):
            continue
    if not headline_font:
        kicker_font = headline_font = brand_font = ImageFont.load_default()

    draw.text((60, 60), "DAILY", fill="#D4AF37", font=kicker_font)

    # word-wrap headline
    lines: list[str] = []
    line = ""
    for word in headline.split():
        cand = (line + " " + word).strip()
        if draw.textlength(cand, font=headline_font) <= width - 120:
            line = cand
        else:
            if line:
                lines.append(line)
            line = word
        if len(lines) == 5:
            break
    if line and len(lines) < 5:
        lines.append(line)
    if len(lines) == 5 and lines[-1]:
        while draw.textlength(lines[-1] + "...", font=headline_font) > width - 120 and " " in lines[-1]:
            lines[-1] = lines[-1].rsplit(" ", 1)[0]
        lines[-1] = lines[-1] + "..."

    y = 130
    for line in lines:
        draw.text((60, y), line, fill="#FFFFFF", font=headline_font)
        y += 80

    # Bottom gold bar
    draw.rectangle([(0, height - 70), (width, height)], fill="#D4AF37")
    draw.text((60, height - 52), "HYDERABAD KINGSMEN", fill="#000000", font=brand_font)

    out = BANNERS_DIR / f"{slug}.png"
    img.save(out, "PNG", optimize=True)
    return out


def write_post(post: dict[str, Any], banner_path: Path, source_url: str | None) -> Path:
    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    slug = post["slug"]
    title = post["title"]
    body = post["body_md"]

    # If there's a source and the body doesn't already cite it, append a Source line.
    if source_url and source_url not in body:
        body = body.rstrip() + f"\n\n*Source: <{source_url}>*\n"

    front = {
        "title": title.replace('"', "'"),
        "slug": slug,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+05:00"),
        "draft": False,
        "description": post.get("excerpt", "").replace('"', "'"),
        "banner": f"/banners/{banner_path.name}",
        "kicker": "ANALYSIS",
        "author": "Hyderabad Kingsmen",
        "translationKey": slug,
        "tags": post.get("tags", []),
        "categories": ["Analysis"],
    }

    def yaml_val(v: Any) -> str:
        if isinstance(v, list):
            return "[" + ", ".join('"' + str(x).replace('"', '\\"') + '"' for x in v) + "]"
        if isinstance(v, bool):
            return "true" if v else "false"
        return '"' + str(v).replace('"', '\\"') + '"'

    fm_lines = ["---"]
    for k, v in front.items():
        fm_lines.append(f"{k}: {yaml_val(v)}")
    fm_lines.append("---\n")
    full = "\n".join(fm_lines) + "\n" + body.strip() + "\n"

    dest = POSTS_DIR / f"{slug}.md"
    dest.write_text(full, encoding="utf-8")
    log.info("Wrote post -> %s", dest)
    return dest


def main() -> None:
    seen = load_seen()
    topic, source_url = pick_topic(seen)
    post = claude_write_post(topic, source_url)
    banner = render_banner(post["slug"], post["title"])
    write_post(post, banner, source_url)
    if source_url:
        seen.add(hashlib.sha1(source_url.encode()).hexdigest())
        save_seen(seen)


if __name__ == "__main__":
    main()
