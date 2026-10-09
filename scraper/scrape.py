#!/usr/bin/env python3
"""
Refresh Derrylin O'Connells fixtures & results from fermanagh.gaa.ie.

Writes (only when the match data has actually changed):
  docs/data/fixtures.json      machine-readable copy
  docs/data/fixtures.js        the same data, loaded by the website
  docs/fixtures.ics            calendar feed, every grade
  docs/fixtures-<grade>.ics    calendar feed per grade (seniors, u16 ...)

Usage:
  python scraper/scrape.py                 # fetch the live team page (GitHub Action does this)
  python scraper/scrape.py --html page.html   # parse a saved copy of the page
  python scraper/scrape.py --seed scraper/seed.json   # build from a hand-made list

If nothing can be parsed the script exits with an error and leaves the
existing data untouched, so the site never goes blank.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

TEAM_URL = (
    "https://fermanagh.gaa.ie/fixtures-results/team/derrylin-oconnells/"
    "a78482ce-7649-6fcf-4908-5f2190e62840/"
)
CLUB_KEY = "derrylin"          # any team name containing this is "us"
CLUB_NAME = "Derrylin O'Connells"

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
DATA_DIR = DOCS / "data"
LONDON = ZoneInfo("Europe/London")

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
DATE_RE = re.compile(
    r"^(?:mon|tues|wednes|thurs|fri|satur|sun)day\s+(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]{3})[a-z]*\.?\s+(\d{4})$",
    re.I)
SCORE_RE = re.compile(r"^\d{1,2}-\d{1,3}$")
TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")
UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
COMP_HREF_RE = re.compile(r"/fixtures-results/[a-z_]+/[a-z_]+/[a-z0-9_]+/[^/]+/" + UUID + r"/?$", re.I)
LABEL_RE = re.compile(r"^(venue|referee|live via|tickets)\s*:\s*(.*)$", re.I)


# --------------------------------------------------------------------------
# Parsing the team page
# --------------------------------------------------------------------------

def _clean(s: str) -> str:
    return " ".join((s or "").split())


def _date_iso(text: str) -> str | None:
    m = DATE_RE.match(_clean(text))
    if not m:
        return None
    day, mon, year = int(m.group(1)), MONTHS.get(m.group(2).lower()[:3]), int(m.group(3))
    if not mon:
        return None
    return date(year, mon, day).isoformat()


def tokens(html: str):
    """Flatten the page into the sequence a reader sees: dates, links, text."""
    from bs4 import BeautifulSoup, Comment, NavigableString, Tag

    soup = BeautifulSoup(html, "html.parser")
    skip = {"script", "style", "noscript", "svg", "template", "head"}

    def walk(node):
        for child in node.children:
            if isinstance(child, Comment):
                continue
            if isinstance(child, NavigableString):
                t = _clean(str(child))
                if not t:
                    continue
                iso = _date_iso(t)
                yield ("date", iso) if iso else ("text", t)
            elif isinstance(child, Tag):
                if child.name in skip:
                    continue
                if child.name == "a":
                    yield ("link", _clean(child.get_text(" ")), child.get("href") or "")
                    continue
                if child.name in ("h1", "h2", "h3", "h4", "h5", "h6", "time") or "date" in " ".join(child.get("class") or []):
                    iso = _date_iso(child.get_text(" "))
                    if iso and not child.find("a"):
                        yield ("date", iso)
                        continue
                yield from walk(child)

    yield from walk(soup.body or soup)


def _join_score_bits(bits: list[str]) -> list[str]:
    """'0' '-' '25' rendered as separate spans -> '0-25'."""
    out, buf = [], ""
    for b in bits:
        if re.fullmatch(r"[\d\-–]+", b):
            buf += b.replace("–", "-")
        else:
            if buf:
                out.append(buf)
                buf = ""
            out.append(b)
    if buf:
        out.append(buf)
    return out


def parse_team_page(html: str) -> list[dict]:
    """Return raw match dicts in the same shape as seed.json."""
    raw: list[dict] = []
    cur_date = None
    m = None
    state = None      # home -> mid -> after
    field = None      # venue / ref / live / tickets while state == after

    def finish():
        if m and m.get("home") and m.get("away"):
            raw.append(m)

    for tok in tokens(html):
        kind = tok[0]
        if kind == "date":
            finish(); m = None; cur_date = tok[1]
            continue
        if kind == "text" and tok[1].lower().startswith("load more results"):
            finish(); m = None
            break                              # league tables follow; we're done
        if kind == "text" and tok[1].lower().startswith("load more fixtures"):
            finish(); m = None
            continue
        if kind == "link" and cur_date and COMP_HREF_RE.search(tok[2].split("?")[0]):
            finish()
            m = {"date": cur_date, "comp": tok[1], "href": tok[2], "mid": []}
            state, field = "home", None
            continue
        if m is None:
            continue

        if state == "home":
            if kind == "link":
                m["home"] = tok[1]; state = "mid"
        elif state == "mid":
            if kind == "link":
                m["away"] = tok[1]; state = "after"
            else:
                m["mid"].append(tok[1])
        elif state == "after":
            if kind == "text":
                lab = LABEL_RE.match(tok[1])
                if lab:
                    field = {"venue": "venue", "referee": "ref", "live via": "live", "tickets": "tickets"}[lab.group(1).lower()]
                    if lab.group(2):
                        if field != "tickets":
                            m[field] = lab.group(2)
                        field = None
                    continue
            if field in ("venue", "ref", "live"):
                m[field] = tok[1]
                field = None
            elif field == "tickets":
                field = None
    finish()

    # Turn the in-between tokens into scores and a throw-in time.
    for r in raw:
        bits = _join_score_bits(r.pop("mid"))
        scores = [b for b in bits if SCORE_RE.match(b) or b.upper() == "CONC"]
        r["hs"] = scores[0] if len(scores) > 0 else "0-0"
        r["as"] = scores[1] if len(scores) > 1 else "0-0"
        t = next((b for b in bits if TIME_RE.match(b)), None)
        if t:
            r["time"] = t
        elif any(b.lower() == "conceded" for b in bits):
            r["time"] = "Conceded"
        else:
            r["time"] = "TBC"
    return [r for r in raw if CLUB_KEY in (r["home"] + r["away"]).lower()]


# --------------------------------------------------------------------------
# Normalising
# --------------------------------------------------------------------------

def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def grade_of(comp: str, href: str = "") -> str:
    c, h = comp.lower(), (href or "").lower()
    prefix = ""
    if "ladies_football" in h or "ladies" in c or "girls" in c:
        prefix = "Ladies"
    elif "/hurling/" in h or "hurling" in c:
        prefix = "Hurling"
    elif "camogie" in h or "camogie" in c:
        prefix = "Camogie"
    age = re.search(r"\bu-?(\d{1,2})s?\b", c)
    if age:
        g = "U" + age.group(1)
    elif "minor" in c:
        g = "U18"
    elif "feile" in c or "féile" in c:
        g = "U15"
    elif "erne cup" in c or "reserve" in c:
        g = "Reserves"
    else:
        g = "" if prefix else "Seniors"
    return (prefix + " " + g).strip()


def _strip_conceded(name: str) -> tuple[str, bool]:
    n = _clean(name)
    if re.search(r"\(c\)\s*$", n, re.I):
        return re.sub(r"\s*\(c\)\s*$", "", n, flags=re.I), True
    return n, False


def normalise(r: dict, today: date) -> dict:
    home, home_c = _strip_conceded(r["home"])
    away, away_c = _strip_conceded(r["away"])
    comp_full = _clean(r["comp"]).rstrip("-").strip()
    if " - " in comp_full:
        competition, rnd = comp_full.rsplit(" - ", 1)
    else:
        competition, rnd = comp_full, ""
    grade = grade_of(comp_full, r.get("href", ""))
    hs, as_ = (r.get("hs") or "0-0").strip(), (r.get("as") or "0-0").strip()
    time = r.get("time") if TIME_RE.match(r.get("time") or "") else None
    d = date.fromisoformat(r["date"])

    conceded_by = None
    if home_c or hs.upper() == "CONC":
        conceded_by = "home"
    elif away_c or as_.upper() == "CONC":
        conceded_by = "away"

    if conceded_by or (r.get("time") or "").lower() == "conceded":
        status = "conceded"
    elif hs == "0-0" and as_ == "0-0":
        status = "fixture" if d >= today else "awaiting"
    else:
        status = "result"

    venue = _clean(r.get("venue") or "") or "TBC"
    ref = _clean(r.get("ref") or "") or "TBC"
    us = "home" if CLUB_KEY in home.lower() else "away"
    return {
        "id": slug(f"{r['date']} {grade} {home} v {away}"),
        "date": r["date"],
        "time": time,
        "competition": competition,
        "round": rnd,
        "grade": grade,
        "home": home,
        "away": away,
        "homeScore": hs if status == "result" else None,
        "awayScore": as_ if status == "result" else None,
        "status": status,
        "concededBy": conceded_by,
        "us": us,
        "venue": venue,
        "referee": ref,
        "stream": _clean(r.get("live") or "") or None,
    }


def merge(old: list[dict], new: list[dict]) -> list[dict]:
    """The page only shows recent games; keep older results we saw before."""
    ids = {m["id"] for m in new}
    kept = [m for m in old if m["id"] not in ids and m.get("status") in ("result", "conceded")]
    return sorted(new + kept, key=lambda m: (m["date"], m["time"] or "99:99", m["id"]))


# --------------------------------------------------------------------------
# Calendar feeds
# --------------------------------------------------------------------------

VTIMEZONE = """BEGIN:VTIMEZONE
TZID:Europe/London
BEGIN:DAYLIGHT
TZOFFSETFROM:+0000
TZOFFSETTO:+0100
TZNAME:BST
DTSTART:19700329T010000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:+0100
TZOFFSETTO:+0000
TZNAME:GMT
DTSTART:19701025T020000
RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU
END:STANDARD
END:VTIMEZONE""".split("\n")


def _ics_text(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> list[str]:
    out, cur = [], ""
    for ch in line:
        if len((cur + ch).encode("utf-8")) > 74:
            out.append(cur)
            cur = " " + ch
        else:
            cur += ch
    out.append(cur)
    return out


def short(name: str) -> str:
    return "Derrylin" if CLUB_KEY in name.lower() else name


def build_ics(matches: list[dict], cal_name: str, stamp: str) -> str:
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Derrylin O'Connells GAC//Fixtures//EN",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        "X-WR-CALNAME:" + _ics_text(cal_name), "X-WR-TIMEZONE:Europe/London",
        "REFRESH-INTERVAL;VALUE=DURATION:PT2H", "X-PUBLISHED-TTL:PT2H",
        *VTIMEZONE,
    ]
    for m in matches:
        d = date.fromisoformat(m["date"])
        if m["status"] == "result":
            title = f"{m['grade']}: {short(m['home'])} {m['homeScore']} {short(m['away'])} {m['awayScore']}"
        else:
            title = f"{m['grade']}: {short(m['home'])} v {short(m['away'])}"
            if m["status"] == "conceded":
                title += " (conceded)"
        desc = [m["competition"] + (f" – {m['round']}" if m["round"] else "")]
        if m["referee"] and m["referee"] != "TBC":
            desc.append("Referee: " + m["referee"])
        if m["stream"]:
            desc.append("Live on " + m["stream"])
        ev = ["BEGIN:VEVENT", f"UID:{m['id']}@derrylin-oconnells", "DTSTAMP:" + stamp]
        if m["time"]:
            hh, mm = map(int, m["time"].split(":"))
            start = datetime(d.year, d.month, d.day, hh, mm)
            end = start + timedelta(minutes=105 if m["grade"] in ("Seniors", "Reserves") else 90)
            ev += [f"DTSTART;TZID=Europe/London:{start:%Y%m%dT%H%M%S}",
                   f"DTEND;TZID=Europe/London:{end:%Y%m%dT%H%M%S}"]
        else:
            ev += [f"DTSTART;VALUE=DATE:{d:%Y%m%d}", f"DTEND;VALUE=DATE:{d + timedelta(days=1):%Y%m%d}"]
        ev += ["SUMMARY:" + _ics_text(title), "LOCATION:" + _ics_text(m["venue"]),
               "DESCRIPTION:" + _ics_text("\n".join(desc)), "END:VEVENT"]
        lines += ev
    lines.append("END:VCALENDAR")
    folded = []
    for ln in lines:
        folded += _fold(ln)
    return "\r\n".join(folded) + "\r\n"


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def fetch(url: str) -> str:
    import requests
    resp = requests.get(url, timeout=30, headers={
        "User-Agent": "Mozilla/5.0 (compatible; DerrylinFixturesBot/1.0; club fixtures page)",
        "Accept-Language": "en-GB,en;q=0.9",
    })
    resp.raise_for_status()
    return resp.text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", help="parse a saved copy of the team page")
    ap.add_argument("--seed", help="build from a JSON list of raw matches")
    ap.add_argument("--out", default=str(DOCS), help="site folder (default: docs)")
    ap.add_argument("--today", help="override today's date (YYYY-MM-DD), for testing")
    args = ap.parse_args()

    out = Path(args.out)
    data_dir = out / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    today = date.fromisoformat(args.today) if args.today else datetime.now(LONDON).date()

    if args.seed:
        raw = json.loads(Path(args.seed).read_text(encoding="utf-8"))
    else:
        html = Path(args.html).read_text(encoding="utf-8") if args.html else fetch(TEAM_URL)
        raw = parse_team_page(html)
    if not raw:
        print("No Derrylin matches found on the page - leaving existing data alone.", file=sys.stderr)
        return 1

    new = [normalise(r, today) for r in raw]
    json_path = data_dir / "fixtures.json"
    old_doc = {}
    if json_path.exists():
        try:
            old_doc = json.loads(json_path.read_text(encoding="utf-8"))
        except ValueError:
            old_doc = {}
    matches = merge(old_doc.get("matches", []), new)

    # Statuses depend on today's date, so re-derive them for carried-over rows too.
    if old_doc.get("matches") == matches:
        print(f"No changes ({len(matches)} matches).")
        return 0

    updated = datetime.now(timezone.utc).replace(microsecond=0)
    grades = sorted({m["grade"] for m in matches})
    doc = {
        "club": CLUB_NAME,
        "source": TEAM_URL,
        "updated": updated.isoformat().replace("+00:00", "Z"),
        "calendars": [{"grade": g, "file": f"fixtures-{slug(g)}.ics"} for g in grades],
        "matches": matches,
    }
    body = json.dumps(doc, ensure_ascii=False, indent=1)
    json_path.write_text(body + "\n", encoding="utf-8")
    (data_dir / "fixtures.js").write_text("window.DERRYLIN_FIXTURES = " + body + ";\n", encoding="utf-8")

    stamp = updated.strftime("%Y%m%dT%H%M%SZ")
    (out / "fixtures.ics").write_text(build_ics(matches, "Derrylin O'Connells – all teams", stamp), encoding="utf-8")
    for g in grades:
        subset = [m for m in matches if m["grade"] == g]
        (out / f"fixtures-{slug(g)}.ics").write_text(
            build_ics(subset, f"Derrylin O'Connells – {g}", stamp), encoding="utf-8")

    n_fix = sum(m["status"] == "fixture" for m in matches)
    print(f"Wrote {len(matches)} matches ({n_fix} upcoming) across {len(grades)} grades.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
