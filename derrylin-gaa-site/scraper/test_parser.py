"""Checks the team-page parser against a mock page shaped like fermanagh.gaa.ie.

Run:  python scraper/test_parser.py
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import scrape  # noqa: E402

COMP = "https://fermanagh.gaa.ie/fixtures-results/football/club/{grade}/{slug}/6ebd6106-f1d1-430b-b0d7-27a78d469151/"
TEAM = "https://fermanagh.gaa.ie/fixtures-results/team/{slug}/a78482ce-7649-6fcf-4908-5f2190e62840/"
VENUE = "https://fermanagh.gaa.ie/fixtures-results/venue/{slug}/35ed67b1-6ab2-419f-8ba9-a004011db461/"


def block(comp, grade, home, hs, time, as_, away, venue=None, ref="TBC", live=False, split_scores=False):
    def score(s):
        if split_scores and "-" in s:
            g, p = s.split("-")
            return f'<span class="g">{g}</span><span class="sep">-</span><span class="p">{p}</span>'
        return f"<span>{s}</span>"
    venue_html = (f'<a href="{VENUE.format(slug="v")}">{venue}</a>' if venue else '<a href="#">TBC</a>')
    extra = ('<p><strong>Live via:</strong> Monaghan Bros Fermanagh GAA TV <strong>Tickets:</strong> '
             '<a href="https://www.fermanagh.gaa.ie/tickets">Buy Tickets</a></p>') if live else ""
    return f"""
    <div class="fixture">
      <a class="comp" href="{COMP.format(grade=grade, slug='x')}">{comp}</a>
      <div class="row">
        <a href="{TEAM.format(slug='h')}">{home}</a>
        <div class="score">{score(hs)}</div><div class="time">{time}</div><div class="score">{score(as_)}</div>
        <a href="{TEAM.format(slug='a')}">{away}</a>
      </div>
      <p><strong>Venue:</strong> {venue_html} <strong>Referee:</strong> {ref}</p>
      {extra}
    </div>"""


PAGE = f"""<!doctype html><html><head><title>t</title><script>var x = "Saturday 1st Jan 2026";</script></head><body>
<nav>
  <a href="https://fermanagh.gaa.ie/fixtures-results/football/club/senior/">SENIOR</a>
  <a href="https://fermanagh.gaa.ie/fixtures-results/football/club/senior/mannok-senior-football-championship/d4343792-5afa-4bbc-970b-3091881ca10f/">Senior Football Championship</a>
</nav>
<h1>Team: Derrylin O'Connells</h1>
<ul><li><a href="#fixtures">Fix</a></li><li><a href="#results">Res</a></li></ul>
<section id="fixtures">
  <h3>Saturday 10th Oct 2026</h3>
  {block("U16 Football League 2026 - League Division 1 - Round 8", "juvenile", "Derrylin O'Connells", "0-0", "11:00", "0-0", "Kinawley Brian Borus", "O'Connell Park, Derrylin", "Aaron Quigley")}
  {block("Cadco Intermediate Football Championship - Semi Final", "intermediate", "Derrylin O'Connells", "0-0", "18:00", "0-0", "Kinawley Brian Borus", "St Molaise's Park, Irvinestown", "Niall McCann", live=True)}
  <h3><span>Saturday</span> <span>24th Oct 2026</span></h3>
  {block("U16 Football League 2026 - League Division 1 - Round 10", "juvenile", "Newtownbutler First Fermanaghs", "0-0", "TBC", "0-0", "Derrylin O'Connells", None)}
  <button>Load more Fixtures</button>
</section>
<section id="results">
  <h3>Saturday 3rd Oct 2026</h3>
  {block("Cadco Intermediate Football Championship - Quarter Final", "intermediate", "Derrylin O'Connells", "0-25", "16:30", "2-10", "St Patrick's Donagh", "O'Connell Park, Derrylin", "James Carey", split_scores=True)}
  <h3>Sunday 5th Jul 2026</h3>
  {block("U18 Minor Football League 2026 - League Division 1 - Round 4", "minor", "Derrylin O'Connells", "0-0", "Conceded", "CONC", "Coa O`Dwyer's (C)", "O'Connell Park, Derrylin")}
  <h3>Saturday 23rd May 2026</h3>
  {block("B McCaffrey &amp; Sons Erne Cup Division 2 - Round 6", "junior", "Belnaleck Art MacMurroughs GAC (C)", "CONC", "Conceded", "0-0", "Derrylin O'Connells", "Belnaleck GAA Grounds")}
  <h3>Saturday 22nd Aug 2026</h3>
  {block("Senior Football League Division 2/3 Play-Off -", "senior", "Belcoo O'Rahilly's", "1-23", "18:00", "0-24", "Derrylin O'Connells", "Belnaleck GAA Grounds", "Michael Keown")}
  <a href="#" class="more">Load more Results</a>
</section>
<section id="tables">
  <h2>Intermediate Football Championship</h2>
  <table><tr><td><a href="#">Derrylin O'Connells</a></td><td>2</td></tr></table>
</section>
</body></html>"""


def main():
    raw = scrape.parse_team_page(PAGE)
    got = [scrape.normalise(r, date(2026, 10, 9)) for r in raw]
    for m in got:
        print(m["date"], m["time"], m["grade"], "|", m["round"], "|", m["home"], m["homeScore"], "v",
              m["away"], m["awayScore"], "|", m["venue"], "|", m["referee"], "|", m["status"], m["concededBy"], m["stream"])
    assert len(got) == 7, len(got)
    by = {(m["date"], m["grade"]): m for m in got}
    assert by[("2026-10-10", "Seniors")]["stream"] == "Monaghan Bros Fermanagh GAA TV"
    assert by[("2026-10-10", "Seniors")]["venue"] == "St Molaise's Park, Irvinestown"
    assert by[("2026-10-10", "U16")]["referee"] == "Aaron Quigley"
    assert by[("2026-10-24", "U16")]["venue"] == "TBC" and by[("2026-10-24", "U16")]["time"] is None
    assert by[("2026-10-03", "Seniors")]["homeScore"] == "0-25" and by[("2026-10-03", "Seniors")]["awayScore"] == "2-10"
    assert by[("2026-07-05", "U18")]["status"] == "conceded" and by[("2026-07-05", "U18")]["concededBy"] == "away"
    assert by[("2026-07-05", "U18")]["away"] == "Coa O`Dwyer's"
    assert by[("2026-05-23", "Reserves")]["concededBy"] == "home"
    assert by[("2026-08-22", "Seniors")]["round"] == "" and by[("2026-08-22", "Seniors")]["status"] == "result"
    assert all(m["status"] == "fixture" for m in got if m["date"] >= "2026-10-10")
    print("parser OK")


if __name__ == "__main__":
    main()
