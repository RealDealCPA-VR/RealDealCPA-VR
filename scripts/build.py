"""Builds every animated panel on the RealDealCPA-VR profile.

Run:  python scripts/build.py          (uses $GITHUB_TOKEN, else `gh auth token`)
      python scripts/build.py --offline (reuses data/live.json)

Live numbers (contributions, stars, releases, versions, languages) come from the
GitHub GraphQL API; curated copy lives in PROFILE below. Every panel is a plain
SVG animated with SMIL, so it renders inside GitHub's <img> sandbox with no
scripts, fonts or third-party services. Static values are the panel's base state,
so a viewer that ignores animation still sees the finished picture.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os
import subprocess
import sys
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
CACHE = ROOT / "data" / "live.json"
LOGIN = "RealDealCPA-VR"

INK, CARD, LINE = "#050605", "#0b0d0b", "#1c221b"
PAPER, MUTED, DIM = "#eef0ea", "#9aa196", "#5d6459"
LIME, ARC, COPPER, MINT, AMBER = "#c8f560", "#5fe3ff", "#ff8a3d", "#8ff0b8", "#ffb547"
SANS = "'Inter','Segoe UI',system-ui,-apple-system,'Helvetica Neue',Arial,sans-serif"
MONO = "ui-monospace,'SF Mono','Cascadia Code',Consolas,'DejaVu Sans Mono',monospace"

# ─────────────────────────────── curated copy ───────────────────────────────
# Numbers here were read from each project (README, tests, git) on 2026-10-03.
FLAGSHIPS = [
    {
        "file": "card-iron-jarvis", "repo": "Iron-Jarvis", "name": "Iron Jarvis", "accent": ARC,
        "kind": "AI OPERATING SYSTEM", "pill": "{release} · SHIPPING",
        "tagline": "Your own local-first AI operating system.",
        "blurb": "One chat box that hands big jobs to a team of agents. They plan, build and review in sandboxed worktrees, and nothing merges without your approval.",
        "metrics": [("{stars}★", "stars"), ("{tags}", "releases"), ("10.8K+", "tests"), ("{commits}", "commits")],
        "stack": "Python · FastAPI · Next.js · Electron · MCP",
    },
    {
        "file": "card-raster-studio", "repo": "Raster-studio", "name": "Raster Studio", "accent": COPPER,
        "kind": "CREATIVE SOFTWARE · RUST", "pill": "PRE-RELEASE",
        "tagline": "A Photoshop-class image editor. Your files stay local.",
        "blurb": "Opens and saves PSD/PSB with layers, masks and smart objects. 69 tools, 71 filters, 60+ formats. No account, no cloud, no network calls.",
        "metrics": [("558K", "lines of rust"), ("6,534", "tests"), ("69", "tools"), ("71", "filters")],
        "stack": "Rust · wgpu · custom UI · ICC colour · PSD codec",
    },
    {
        "file": "card-ironcore", "repo": "IronCore", "name": "IronCore", "accent": "#ff6b4a",
        "kind": "CODING AGENT · LOCAL MODELS", "pill": "{release} · ON PYPI",
        "tagline": "The coding agent that molds itself to local models.",
        "blurb": "Measures what your model can really do (honest context, tool-call reliability), then moves the jobs small models fumble into reliable code.",
        "metrics": [("2,740", "offline tests"), ("90%", "coverage gate"), ("30.8K", "lines of python")],
        "stack": "Python · Textual · Ollama · llama.cpp · vLLM · MCP",
    },
    {
        "file": "card-quickbooks-mcp", "repo": "Quickbooks-MCP-Desktop", "name": "QuickBooks MCP", "accent": "#4ade80",
        "kind": "MCP SERVER · ACCOUNTING", "pill": "{release} · SHIPPED",
        "tagline": "Let AI agents keep QuickBooks Desktop books, safely.",
        "blurb": "150 accounting tools over QBXML with dry-run previews, read-only sessions and rollback-safe batch posting. Real books, no wreckage.",
        "metrics": [("150", "mcp tools"), ("1,725", "tests"), ("65K", "lines of ts")],
        "stack": "TypeScript · MCP SDK · QBXML 16.0 · COM",
    },
    {
        "file": "card-iron-proxy", "repo": "Iron-Proxy", "name": "Iron-Proxy", "accent": "#7aa2ff",
        "kind": "DEVELOPER TOOL · MIT", "pill": "OPEN SOURCE",
        "tagline": "All your AI subscriptions. Never hit a limit.",
        "blurb": "Ordered failover across your own accounts: it switches mid-conversation when one runs out and switches back the moment it resets.",
        "metrics": [("364", "test cases"), ("5", "packages"), ("0", "core deps")],
        "stack": "TypeScript · Electron · React · pnpm workspaces",
    },
    {
        "file": "card-karboncopy", "repo": "KarbonCopy", "name": "KarbonCopy", "accent": "#b79cff",
        "kind": "PRACTICE MANAGEMENT · SELF-HOSTED", "pill": "PROTOTYPE",
        "tagline": "The whole accounting practice, on your own network.",
        "blurb": "Work tracking, billing, client portal and e-signatures on one office machine, with a 33-tool MCP server so Claude can run the practice.",
        "metrics": [("43", "db tables"), ("33", "mcp tools"), ("34", "app pages")],
        "stack": "Next.js 15 · SQLite · Drizzle · Socket.IO · Stripe",
    },
]

TOTAL_TESTS = "23,600+"   # 10,800 + 6,534 + 2,740 + 1,725 + 1,443 + 364 across the flagships
TOTAL_LINES = "990K+"     # 558K Rust + 282K Iron Jarvis + 65K + 41.5K + 30.8K + 15.4K

PHRASES = [
    "a local-first AI operating system",
    "MCP servers that keep real books",
    "a Photoshop-class editor in Rust",
    "private AI on two DGX Sparks",
    "agents that ask before they act",
]

TOOLS = [
    ("Python", "#3572A5"), ("TypeScript", "#3178c6"), ("Rust", "#dea584"), ("C#", "#7355dd"),
    ("FastAPI", MINT), ("Next.js", PAPER), ("React", ARC), ("Electron", "#9feaf9"),
    ("SQLite", "#7fb2d8"), ("Postgres", "#6b9bd1"), ("Drizzle", LIME), ("Tailwind", "#38bdf8"),
    ("wgpu", COPPER), ("MCP", LIME), ("Claude", "#e8a27c"), ("Ollama", PAPER),
    ("vLLM", AMBER), ("llama.cpp", "#c9a26b"), ("DGX Spark", "#76b900"), ("GitHub Actions", "#8fb3ff"),
    ("Playwright", "#7bc47f"), ("Vitest", "#b8d86b"), ("pytest", "#7fc6e8"), ("QuickBooks", "#4ade80"),
]


# ─────────────────────────────── live data ───────────────────────────────
QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar { totalContributions weeks { contributionDays { date contributionCount } } }
    }
    repositories(ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC, first: 100) {
      totalCount
      nodes { name stargazerCount languages(first: 10, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name color } } } }
    }
  }
  %s
}
"""
REPO_FRAGMENT = """
  r%d: repository(owner: "%s", name: "%s") {
    latestRelease { tagName }
    refs(refPrefix: "refs/tags/", first: 0) { totalCount }
    defaultBranchRef { target { ... on Commit { history { totalCount } } } }
  }"""


def token() -> str:
    if os.environ.get("GITHUB_TOKEN"):
        return os.environ["GITHUB_TOKEN"]
    return subprocess.check_output(["gh", "auth", "token"], text=True).strip()


def fetch() -> dict:
    frags = "".join(REPO_FRAGMENT % (i, LOGIN, f["repo"]) for i, f in enumerate(FLAGSHIPS))
    body = json.dumps({"query": QUERY % frags, "variables": {"login": LOGIN}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql", data=body,
        headers={"Authorization": f"bearer {token()}", "Content-Type": "application/json", "User-Agent": "realdealcpa-profile"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.load(resp)
    if payload.get("errors"):
        raise RuntimeError(payload["errors"])
    d = payload["data"]
    cal = d["user"]["contributionsCollection"]["contributionCalendar"]
    repos = d["user"]["repositories"]["nodes"]
    langs: dict[str, list] = {}
    for r in repos:
        for e in r["languages"]["edges"]:
            n = e["node"]["name"]
            langs.setdefault(n, [0, e["node"]["color"] or DIM])[0] += e["size"]
    flag = {}
    for i, f in enumerate(FLAGSHIPS):
        r = d.get(f"r{i}") or {}
        hist = ((r.get("defaultBranchRef") or {}).get("target") or {}).get("history") or {}
        star = next((x["stargazerCount"] for x in repos if x["name"] == f["repo"]), 0)
        flag[f["repo"]] = {
            "release": (r.get("latestRelease") or {}).get("tagName"),
            "tags": (r.get("refs") or {}).get("totalCount", 0),
            "commits": hist.get("totalCount", 0),
            "stars": star,
        }
    return {
        "fetchedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "contributions": cal["totalContributions"],
        "days": [[day["date"], day["contributionCount"]] for w in cal["weeks"] for day in w["contributionDays"]],
        "stars": sum(r["stargazerCount"] for r in repos),
        "publicRepos": d["user"]["repositories"]["totalCount"],
        "languages": {k: {"bytes": v[0], "color": v[1]} for k, v in langs.items()},
        "flagships": flag,
    }


def load(offline: bool) -> dict:
    if not offline:
        try:
            data = fetch()
            CACHE.parent.mkdir(exist_ok=True)
            CACHE.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
            return data
        except Exception as exc:  # keep the last good snapshot rather than publish zeros
            print(f"live fetch failed ({exc}); using {CACHE.name}", file=sys.stderr)
    return json.loads(CACHE.read_text(encoding="utf-8"))


# ─────────────────────────────── helpers ───────────────────────────────
def x(s) -> str:
    return escape(str(s), {'"': "&quot;"})


def num(n: int) -> str:
    return f"{n:,}"


def svg(w: int, h: int, body: str, title: str, extra_style: str = "") -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{x(title)}">\n'
        f"<title>{x(title)}</title>\n"
        f"<style>.s{{font-family:{SANS}}}.m{{font-family:{MONO}}}{extra_style}</style>\n"
        f"{body}\n</svg>\n"
    )


def frame(w: int, h: int, glow: str = LIME, gid: str = "fg") -> str:
    return (
        f'<defs><radialGradient id="{gid}" cx="85%" cy="0%" r="70%"><stop offset="0" stop-color="{glow}" stop-opacity=".16"/>'
        f'<stop offset="1" stop-color="{glow}" stop-opacity="0"/></radialGradient></defs>'
        f'<rect x=".5" y=".5" width="{w-1}" height="{h-1}" rx="18" fill="{INK}" stroke="{LINE}"/>'
        f'<rect x=".5" y=".5" width="{w-1}" height="{h-1}" rx="18" fill="url(#{gid})"/>'
    )


def fade_in(at: float, total: float, dur: float = 0.35) -> str:
    """Opacity 0 until `at`, then 1. Base opacity stays 1 for viewers without SMIL."""
    a, b = min(at / total, 0.98), min((at + dur) / total, 0.99)
    return (f'<animate attributeName="opacity" values="0;0;1;1" keyTimes="0;{a:.4f};{b:.4f};1" '
            f'dur="{total}s" fill="freeze"/>')


def wrap(text: str, limit: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        if cur and len(cur) + 1 + len(word) > limit:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    return lines + [cur] if cur else lines


def write(name: str, content: str) -> None:
    (ASSETS / name).write_text(content, encoding="utf-8", newline="\n")
    print(f"  assets/{name}  {len(content)/1024:.1f} KB")


# ─────────────────────────────── hero ───────────────────────────────
def hero(live: dict) -> str:
    W, H = 1000, 340
    ij = live["flagships"]["Iron-Jarvis"]
    cx, cy = 165, 170
    parts = [frame(W, H, LIME, "hg")]
    parts.append(
        '<defs>'
        f'<pattern id="grid" width="32" height="32" patternUnits="userSpaceOnUse"><path d="M32 0H0V32" fill="none" stroke="{LIME}" stroke-opacity=".07"/></pattern>'
        '<linearGradient id="gm" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity=".9"/><stop offset=".55" stop-color="#fff" stop-opacity=".25"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>'
        '<mask id="gridmask"><rect width="1000" height="340" fill="url(#gm)"/></mask>'
        f'<radialGradient id="core"><stop offset="0" stop-color="#ffffff"/><stop offset=".35" stop-color="{ARC}"/><stop offset="1" stop-color="{ARC}" stop-opacity="0"/></radialGradient>'
        f'<radialGradient id="halo"><stop offset="0" stop-color="{ARC}" stop-opacity=".35"/><stop offset="1" stop-color="{ARC}" stop-opacity="0"/></radialGradient>'
        f'<linearGradient id="word" x1="0" x2="1"><stop offset="0" stop-color="{PAPER}"/><stop offset=".55" stop-color="{PAPER}"/><stop offset="1" stop-color="{LIME}"/></linearGradient>'
        '<clipPath id="heroclip"><rect x="1" y="1" width="998" height="338" rx="17"/></clipPath>'
        '</defs>'
    )
    g = ['<g clip-path="url(#heroclip)">', '<rect width="1000" height="340" fill="url(#grid)" mask="url(#gridmask)"/>']
    # scan line
    g.append(f'<rect x="0" y="-60" width="1000" height="60" fill="{LIME}" opacity=".035">'
             '<animate attributeName="y" values="-60;340" dur="6s" repeatCount="indefinite"/></rect>')
    # arc reactor
    g.append(f'<circle cx="{cx}" cy="{cy}" r="150" fill="url(#halo)"><animate attributeName="r" values="140;160;140" dur="4s" repeatCount="indefinite"/></circle>')
    rings = [
        (112, 1, "2 10", 60, 1, .45),
        (98, 1.5, "60 14 6 14", 40, -1, .55),
        (80, 2, "1 5", 90, 1, .5),
    ]
    for r, sw, dash, dur, d, op in rings:
        g.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{ARC}" stroke-width="{sw}" stroke-dasharray="{dash}" opacity="{op}">'
            f'<animateTransform attributeName="transform" type="rotate" from="0 {cx} {cy}" to="{360*d} {cx} {cy}" dur="{dur}s" repeatCount="indefinite"/></circle>'
        )
    circ = 2 * math.pi * 62
    seg = circ / 10
    g.append(
        f'<circle cx="{cx}" cy="{cy}" r="62" fill="none" stroke="{ARC}" stroke-width="13" stroke-dasharray="{seg*0.72:.2f} {seg*0.28:.2f}" opacity=".85">'
        f'<animate attributeName="opacity" values=".55;.95;.55" dur="3s" repeatCount="indefinite"/>'
        f'<animateTransform attributeName="transform" type="rotate" from="0 {cx} {cy}" to="-360 {cx} {cy}" dur="30s" repeatCount="indefinite"/></circle>'
    )
    g.append(f'<circle cx="{cx}" cy="{cy}" r="44" fill="none" stroke="{ARC}" stroke-opacity=".6"/>')
    tri = " ".join(f"{cx + 34*math.cos(math.radians(a - 90)):.1f},{cy + 34*math.sin(math.radians(a - 90)):.1f}" for a in (0, 120, 240))
    g.append(f'<polygon points="{tri}" fill="none" stroke="{ARC}" stroke-width="2" opacity=".7">'
             f'<animateTransform attributeName="transform" type="rotate" from="0 {cx} {cy}" to="360 {cx} {cy}" dur="20s" repeatCount="indefinite"/></polygon>')
    g.append(f'<circle cx="{cx}" cy="{cy}" r="34" fill="url(#core)"><animate attributeName="r" values="30;38;30" dur="3s" repeatCount="indefinite"/></circle>')
    # orbiting satellites
    for r, dur, col, size in ((112, 9, LIME, 4), (98, 14, ARC, 3), (128, 22, COPPER, 3)):
        g.append(f'<g><circle cx="{cx + r}" cy="{cy}" r="{size}" fill="{col}"/>'
                 f'<animateTransform attributeName="transform" type="rotate" from="0 {cx} {cy}" to="360 {cx} {cy}" dur="{dur}s" repeatCount="indefinite"/></g>')

    # text block
    tx = 330
    g.append(f'<text x="{tx}" y="92" class="m" font-size="13" letter-spacing="3" fill="{ARC}">// HELLO, WORLD. I\'M VR.</text>')
    g.append(f'<text x="{tx}" y="168" class="s" font-size="78" font-weight="900" letter-spacing="-2" fill="url(#word)">RealDealCPA</text>')
    # shimmer sweep across the wordmark
    g.append(
        '<clipPath id="wordclip"><text x="%d" y="168" class="s" font-size="78" font-weight="900" letter-spacing="-2">RealDealCPA</text></clipPath>' % tx
        + f'<g clip-path="url(#wordclip)"><rect x="-200" y="90" width="160" height="100" fill="#fff" opacity=".35" transform="skewX(-20)">'
        '<animate attributeName="x" values="-200;-200;1200" keyTimes="0;.7;1" dur="7s" repeatCount="indefinite"/></rect></g>'
    )
    g.append(f'<text x="{tx+2}" y="208" class="s" font-size="24" fill="{PAPER}" opacity=".92">The CPA who ships real software.</text>')

    # typing line, each phrase revealed through its own clip with a shared cursor
    cw, fs, ty = 10.8, 18, 258
    px = tx + 2
    prefix = "> building"
    g.append(f'<text x="{px}" y="{ty}" class="m" font-size="{fs}" fill="{LIME}" textLength="{len(prefix)*cw:.1f}" lengthAdjust="spacingAndGlyphs">{x(prefix)}</text>')
    x0 = px + (len(prefix) + 1) * cw
    slot, char_t, erase_t = 4.4, 0.055, 0.018
    total = slot * len(PHRASES)
    events: list[tuple[float, int, int]] = []  # (time, phrase, chars shown)
    for i, p in enumerate(PHRASES):
        s = i * slot
        for k in range(len(p) + 1):
            events.append((s + 0.15 + k * char_t, i, k))
        hold = s + slot - 0.2 - len(p) * erase_t
        for k in range(len(p), -1, -1):
            events.append((hold + (len(p) - k) * erase_t, i, k))
    events.sort()
    times = [0.0] + [e[0] for e in events]
    kt = ";".join(f"{t/total:.5f}" for t in times)
    for i, p in enumerate(PHRASES):
        vals = ["0"] + [f"{e[2]*cw:.1f}" if e[1] == i else "0" for e in events]
        base = len(p) * cw if i == 0 else 0
        g.append(
            f'<clipPath id="ph{i}"><rect x="{x0:.1f}" y="{ty-20}" width="{base:.1f}" height="28">'
            f'<animate attributeName="width" calcMode="discrete" values="{";".join(vals)}" keyTimes="{kt}" dur="{total}s" repeatCount="indefinite"/></rect></clipPath>'
            f'<text x="{x0:.1f}" y="{ty}" class="m" font-size="{fs}" fill="{ARC}" clip-path="url(#ph{i})" textLength="{len(p)*cw:.1f}" lengthAdjust="spacingAndGlyphs">{x(p)}</text>'
        )
    cur_vals = [f"{x0 + len(PHRASES[0])*cw:.1f}"] + [f"{x0 + e[2]*cw:.1f}" for e in events]
    g.append(
        f'<rect x="{x0 + len(PHRASES[0])*cw:.1f}" y="{ty-16}" width="10" height="20" fill="{LIME}">'
        f'<animate attributeName="x" calcMode="discrete" values="{";".join(cur_vals)}" keyTimes="{kt}" dur="{total}s" repeatCount="indefinite"/>'
        '<animate attributeName="opacity" values="1;1;0;0" keyTimes="0;.5;.5;1" dur="1s" repeatCount="indefinite"/></rect>'
    )
    # status chip
    chip = f"SHIPPING · IRON JARVIS {ij['release'] or ''}".strip()
    cwid = len(chip) * 7.4 + 44
    g.append(
        f'<g transform="translate({W - 24 - cwid:.0f},24)"><rect width="{cwid:.0f}" height="28" rx="14" fill="{CARD}" stroke="{LINE}"/>'
        f'<circle cx="18" cy="14" r="4" fill="{LIME}"><animate attributeName="opacity" values="1;.25;1" dur="1.6s" repeatCount="indefinite"/></circle>'
        f'<circle cx="18" cy="14" r="4" fill="none" stroke="{LIME}"><animate attributeName="r" values="4;11" dur="1.6s" repeatCount="indefinite"/><animate attributeName="opacity" values=".8;0" dur="1.6s" repeatCount="indefinite"/></circle>'
        f'<text x="32" y="18.5" class="m" font-size="12" letter-spacing="1" fill="{PAPER}">{x(chip)}</text></g>'
    )
    g.append(f'<text x="{tx+2}" y="306" class="m" font-size="11.5" letter-spacing="3.2" fill="{MUTED}">LOCAL-FIRST  ·  FAIL-CLOSED  ·  TESTED  ·  SHIPPED</text>')
    g.append("</g>")
    return svg(W, H, "".join(parts + g), "RealDealCPA: the CPA who ships real software")


# ─────────────────────────────── stats (odometers) ───────────────────────────────
def stats(live: dict) -> str:
    W, H = 1000, 150
    ij = live["flagships"]["Iron-Jarvis"]
    tiles = [
        (num(live["contributions"]), "CONTRIBUTIONS", "in the last 12 months", LIME),
        (num(ij["tags"]), "RELEASES SHIPPED", "of Iron Jarvis alone", ARC),
        (TOTAL_TESTS, "AUTOMATED TESTS", "across the flagships", MINT),
        (TOTAL_LINES, "LINES OF CODE", "Rust · Python · TypeScript", COPPER),
        (f"{live['stars']}★", "GITHUB STARS", f"on {live['publicRepos']} public builds", AMBER),
    ]
    gap, tw = 12, (W - 4 * 12) / 5
    lh, fs, cw = 46, 38, 23
    out = []
    for t, (value, label, sub, col) in enumerate(tiles):
        tx = t * (tw + gap)
        out.append(f'<g transform="translate({tx:.1f},0)">')
        out.append(f'<rect x=".5" y=".5" width="{tw-1:.1f}" height="{H-1}" rx="16" fill="{INK}" stroke="{LINE}"/>')
        out.append(f'<rect x="20" y="0" width="{tw-40:.1f}" height="2" fill="{col}"><animate attributeName="width" values="0;{tw-40:.1f}" dur="1.2s" fill="freeze"/></rect>')
        out.append(f'<text x="{tw/2:.1f}" y="32" text-anchor="middle" class="m" font-size="11" letter-spacing="2" fill="{MUTED}">{label}</text>')
        base_y = 88
        out.append(f'<clipPath id="oc{t}"><rect x="0" y="{base_y - 36}" width="{tw:.1f}" height="46"/></clipPath><g clip-path="url(#oc{t})">')
        start = tw / 2 - len(value) * cw / 2
        digit_i = 0
        for ci, ch in enumerate(value):
            ccx = start + ci * cw + cw / 2
            if ch.isdigit():
                d = int(ch)
                strip = "".join(f'<text x="{ccx:.1f}" y="{base_y + k*lh}" text-anchor="middle">{k % 10}</text>' for k in range(20))
                final = -(10 + d) * lh
                dur = 1.4 + 0.18 * (len(value) - ci) + 0.1 * t
                out.append(
                    f'<g transform="translate(0 {final})" class="m" font-size="{fs}" font-weight="700" fill="{PAPER}">{strip}'
                    f'<animateTransform attributeName="transform" type="translate" values="0 0;0 {final}" dur="{dur:.2f}s" '
                    'calcMode="spline" keySplines="0.2 0.7 0.1 1" fill="freeze"/></g>'
                )
                digit_i += 1
            else:
                colr = col if ch in "★+K" else PAPER
                out.append(f'<text x="{ccx:.1f}" y="{base_y}" text-anchor="middle" class="m" font-size="{fs}" font-weight="700" fill="{colr}">{x(ch)}</text>')
        out.append("</g>")
        out.append(f'<text x="{tw/2:.1f}" y="124" text-anchor="middle" class="s" font-size="12.5" fill="{DIM}">{x(sub)}</text>')
        out.append("</g>")
    return svg(W, H, "".join(out), "Live stats: contributions, releases, tests, lines of code and stars")


# ─────────────────────────────── terminal ───────────────────────────────
def terminal(live: dict) -> str:
    W = 1000
    fl = live["flagships"]
    ij, ic, qb = fl["Iron-Jarvis"], fl["IronCore"], fl["Quickbooks-MCP-Desktop"]

    def fleet(name, ver, detail, state, col):
        return ("out", [("● ", col), (f"{name:<17}", PAPER), (f"{(ver or ''):<11}", ARC), (f"{detail:<34}", MUTED), (state, col)])

    # (kind, segments) where segments are (text, colour); kind "cmd" types out, "out" fades in
    script = [
        ("cmd", "whoami"),
        ("out", [("VR", PAPER), (" · CPA, builder, and the human in the loop behind ", MUTED), ("RealDealCPA", LIME), (".", MUTED)]),
        ("out", [("I build the software accounting firms wish existed, then make AI run it safely.", MUTED)]),
        ("gap", None),
        ("cmd", "cat ~/principles.md"),
        ("out", [("▸ ", LIME), ("Local-first.  ", PAPER), ("Your data stays on your machine unless you say otherwise.", MUTED)]),
        ("out", [("▸ ", LIME), ("Fail-closed.  ", PAPER), ("An agent only gets the tools it was armed with.", MUTED)]),
        ("out", [("▸ ", LIME), ("Ask first.    ", PAPER), ("Risky steps wait for a human; code waits for an approved diff.", MUTED)]),
        ("out", [("▸ ", LIME), ("Prove it.     ", PAPER), ("A green suite is not proof. Drive the real app.", MUTED)]),
        ("gap", None),
        ("cmd", "jarvis status --fleet"),
        fleet("Iron Jarvis", ij["release"], f"{num(ij['tags'])} releases · 10,800+ tests", "shipping", LIME),
        fleet("Raster Studio", "rust", "558K lines · 6,534 tests", "building", COPPER),
        fleet("IronCore", ic["release"], "on PyPI · 2,740 offline tests", "shipped", LIME),
        fleet("QuickBooks MCP", qb["release"], "150 tools · 1,725 tests", "shipped", LIME),
        ("prompt", None),
    ]
    lh, fs, cw, left, top = 25, 15, 9.0, 32, 76
    H = top + lh * len(script) + 10
    out = [
        f'<rect x=".5" y=".5" width="{W-1}" height="{H-1}" rx="16" fill="{CARD}" stroke="{LINE}"/>',
        f'<path d="M.5 40.5H{W-.5}" stroke="{LINE}"/>',
        '<circle cx="24" cy="21" r="6" fill="#ff5f57"/><circle cx="44" cy="21" r="6" fill="#febc2e"/><circle cx="64" cy="21" r="6" fill="#28c840"/>',
        f'<text x="{W/2}" y="25" text-anchor="middle" class="m" font-size="12" fill="{DIM}">vr@realdealcpa: ~</text>',
    ]
    t, events = 0.6, []
    for i, (kind, seg) in enumerate(script):
        y = top + i * lh
        if kind == "gap":
            continue
        if kind == "cmd":
            events.append(("cmd", i, y, seg, t))
            t += 0.35 + len(seg) * 0.045 + 0.25
        elif kind == "out":
            events.append(("out", i, y, seg, t))
            t += 0.12
        else:
            events.append(("prompt", i, y, None, t))
    total = round(t + 0.5, 2)
    for kind, i, y, seg, at in events:
        if kind == "cmd":
            n = len(seg)
            out.append(f'<g opacity="1">{fade_in(at, total, 0.01)}<text x="{left}" y="{y}" class="m" font-size="{fs}" fill="{LIME}">$</text></g>')
            x0 = left + 2 * cw
            vals = ["0"] + [f"{k*cw:.1f}" for k in range(n + 1)]
            kts = ["0"] + [f"{min((at + 0.3 + k*0.045)/total, 0.999):.4f}" for k in range(n + 1)]
            out.append(
                f'<clipPath id="tc{i}"><rect x="{x0}" y="{y-16}" width="{n*cw:.1f}" height="22">'
                f'<animate attributeName="width" calcMode="discrete" values="{";".join(vals)}" keyTimes="{";".join(kts)}" dur="{total}s" fill="freeze"/></rect></clipPath>'
                f'<text x="{x0}" y="{y}" class="m" font-size="{fs}" fill="{PAPER}" clip-path="url(#tc{i})" textLength="{n*cw:.1f}" lengthAdjust="spacingAndGlyphs">{x(seg)}</text>'
            )
        elif kind == "out":
            spans, length = [], 0
            for text, col in seg:
                spans.append(f'<tspan fill="{col}">{x(text)}</tspan>')
                length += len(text)
            out.append(f'<g opacity="1">{fade_in(at, total, 0.2)}<text x="{left}" y="{y}" class="m" font-size="{fs}" xml:space="preserve" '
                       f'textLength="{length*cw:.1f}" lengthAdjust="spacingAndGlyphs">{"".join(spans)}</text></g>')
        else:
            out.append(
                f'<g opacity="1">{fade_in(at, total, 0.01)}<text x="{left}" y="{y}" class="m" font-size="{fs}" fill="{LIME}">$</text>'
                f'<rect x="{left + 2*cw}" y="{y-14}" width="9" height="18" fill="{LIME}">'
                '<animate attributeName="opacity" values="1;1;0;0" keyTimes="0;.5;.5;1" dur="1s" repeatCount="indefinite"/></rect></g>'
            )
    return svg(W, H, "".join(out), "Terminal: whoami, principles and the status of the flagship builds")


# ─────────────────────────────── project cards ───────────────────────────────
def card(f: dict, live: dict) -> str:
    W, H = 600, 330
    d = live["flagships"][f["repo"]]
    fill = lambda s: s.format(release=d.get("release") or "", tags=num(d.get("tags", 0)),
                              stars=d.get("stars", 0), commits=num(d.get("commits", 0)))
    acc = f["accent"]
    out = [
        '<defs>'
        f'<radialGradient id="cg" cx="100%" cy="0%" r="85%"><stop offset="0" stop-color="{acc}" stop-opacity=".28"/><stop offset="1" stop-color="{acc}" stop-opacity="0"/></radialGradient>'
        f'<linearGradient id="cb" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="{W}" y2="{H}">'
        f'<stop offset="0" stop-color="{acc}" stop-opacity=".9"/><stop offset=".3" stop-color="{acc}" stop-opacity="0"/>'
        f'<stop offset=".7" stop-color="{acc}" stop-opacity="0"/><stop offset="1" stop-color="{acc}" stop-opacity=".9"/>'
        f'<animateTransform attributeName="gradientTransform" type="rotate" from="0 {W/2} {H/2}" to="360 {W/2} {H/2}" dur="8s" repeatCount="indefinite"/></linearGradient>'
        f'<pattern id="cd" width="18" height="18" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="1" fill="{acc}" fill-opacity=".10"/></pattern>'
        f'<clipPath id="cc"><rect x="1" y="1" width="{W-2}" height="{H-2}" rx="19"/></clipPath>'
        '</defs>',
        f'<rect x=".75" y=".75" width="{W-1.5}" height="{H-1.5}" rx="20" fill="{CARD}"/>',
        f'<g clip-path="url(#cc)"><rect width="{W}" height="{H}" fill="url(#cd)"/><rect width="{W}" height="{H}" fill="url(#cg)"/>',
    ]
    # rotating rings motif in the corner
    rx_, ry_ = W - 70, 64
    for r, dash, dur, dirn in ((70, "3 7", 30, 1), (52, "40 10", 20, -1), (34, "2 4", 14, 1)):
        out.append(f'<circle cx="{rx_}" cy="{ry_}" r="{r}" fill="none" stroke="{acc}" stroke-opacity=".35" stroke-dasharray="{dash}">'
                   f'<animateTransform attributeName="transform" type="rotate" from="0 {rx_} {ry_}" to="{360*dirn} {rx_} {ry_}" dur="{dur}s" repeatCount="indefinite"/></circle>')
    out.append(f'<circle cx="{rx_}" cy="{ry_}" r="7" fill="{acc}"><animate attributeName="opacity" values=".4;1;.4" dur="2.4s" repeatCount="indefinite"/></circle>')
    out.append("</g>")
    out.append(f'<rect x=".75" y=".75" width="{W-1.5}" height="{H-1.5}" rx="20" fill="none" stroke="{LINE}"/>')
    out.append(f'<rect x=".75" y=".75" width="{W-1.5}" height="{H-1.5}" rx="20" fill="none" stroke="url(#cb)" stroke-width="1.5"/>')

    out.append(f'<text x="30" y="44" class="m" font-size="11" letter-spacing="2" fill="{acc}">{x(f["kind"])}</text>')
    pill = fill(f["pill"]).strip(" ·")
    pw = len(pill) * 7 + 24
    out.append(f'<g transform="translate(30,58)"><rect width="{pw}" height="22" rx="11" fill="{acc}" fill-opacity=".12" stroke="{acc}" stroke-opacity=".5"/>'
               f'<text x="{pw/2}" y="15" text-anchor="middle" class="m" font-size="11" letter-spacing=".5" fill="{acc}">{x(pill)}</text></g>')
    out.append(f'<text x="30" y="122" class="s" font-size="36" font-weight="800" letter-spacing="-1" fill="{PAPER}">{x(f["name"])}</text>')
    out.append(f'<text x="30" y="151" class="s" font-size="17.5" font-weight="600" fill="{PAPER}" opacity=".9">{x(f["tagline"])}</text>')
    for li, line in enumerate(wrap(f["blurb"], 64)[:3]):
        out.append(f'<text x="30" y="{177 + li*21}" class="s" font-size="15" fill="{MUTED}">{x(line)}</text>')

    mets = f["metrics"]
    mw = (W - 60) / len(mets)
    out.append(f'<path d="M30 238.5H{W-30}" stroke="{LINE}"/>')
    for mi, (val, label) in enumerate(mets):
        mx = 30 + mi * mw
        out.append(f'<g opacity="1">{fade_in(0.2 + mi*0.15, 1.6, 0.4)}'
                   f'<text x="{mx}" y="272" class="s" font-size="28" font-weight="800" fill="{PAPER}">{x(fill(val))}</text>'
                   f'<text x="{mx}" y="292" class="m" font-size="11.5" letter-spacing="1" fill="{MUTED}">{x(label.upper())}</text></g>')
    out.append(f'<text x="30" y="{H-13}" class="m" font-size="12" fill="{DIM}">{x(f["stack"])}</text>')
    out.append(f'<text x="{W-30}" y="{H-13}" text-anchor="end" class="m" font-size="12" letter-spacing="1" fill="{acc}">REPO →</text>')
    return svg(W, H, "".join(out), f"{f['name']}: {f['tagline']}")


# ─────────────────────────────── contribution skyline ───────────────────────────────
def streaks(days: list[list]) -> tuple[int, int, tuple[str, int]]:
    longest = run = 0
    for _, c in days:
        run = run + 1 if c else 0
        longest = max(longest, run)
    cur = 0
    seq = [c for _, c in days]
    if seq and seq[-1] == 0:
        seq = seq[:-1]  # today isn't over yet
    for c in reversed(seq):
        if not c:
            break
        cur += 1
    best = max(days, key=lambda d: d[1]) if days else ("", 0)
    return longest, cur, (best[0], best[1])


def skyline(live: dict) -> str:
    W, H = 1000, 500
    days = live["days"]
    first = dt.date.fromisoformat(days[0][0])
    pad = (first.weekday() + 1) % 7  # GitHub weeks start on Sunday
    cells = [((i + pad) // 7, (i + pad) % 7, c, date) for i, (date, c) in enumerate(days)]
    weeks = cells[-1][0] + 1
    peak = max((c for _, _, c, _ in cells), default=1) or 1
    longest, current, (best_date, best_n) = streaks(days)

    # Oblique projection: weeks run right and up (a year that climbs), days run right and down.
    u, v = (12.6, -3.3), (8.0, 5.6)
    ox, oy = 190.0, 420.0
    maxh = 120.0
    k = 0.84  # cell footprint, leaves a gutter between blocks

    def P(w, d):
        return ox + w * u[0] + d * v[0], oy + w * u[1] + d * v[1]

    def height(c):
        return max(4.0, (c / peak) ** 0.6 * maxh) if c else 0.0

    levels = ["#2c4214", "#5b8a22", "#94c83c", LIME]

    def shade(hexc, f):
        r, g, b = (int(hexc[i:i + 2], 16) for i in (1, 3, 5))
        return f"#{int(r*f):02x}{int(g*f):02x}{int(b*f):02x}"

    total_anim, grow = 3.4, 0.9
    out = [frame(W, H, LIME, "sg")]
    ua, ub = u[0] * k, u[1] * k
    va, vb = v[0] * k, v[1] * k
    blocks = []
    # back rows first; within a row, right to left (the left faces are the visible ones)
    for w, d, c, date in sorted(cells, key=lambda t: (t[1], -t[0])):
        X, Y = P(w + (1 - k) / 2, d + (1 - k) / 2)
        base = f"M{X:.1f} {Y:.1f}l{ua:.1f} {ub:.1f}l{va:.1f} {vb:.1f}l{-ua:.1f} {-ub:.1f}z"
        if not c:
            blocks.append(f'<path d="{base}" fill="#151b14"/>')
            continue
        h = height(c)
        lvl = min(3, int((c / peak) ** 0.6 * 4))
        top = ARC if date == best_date else levels[lvl]
        # geometry relative to the near-left base corner; the block scales up from the floor
        bx, by = X + va, Y + vb
        top_face = f"M{-va:.1f} {-vb-h:.1f}l{ua:.1f} {ub:.1f}l{va:.1f} {vb:.1f}l{-ua:.1f} {-ub:.1f}z"
        front = f"M0 {-h:.1f}l{ua:.1f} {ub:.1f}v{h:.1f}l{-ua:.1f} {-ub:.1f}z"
        left = f"M{-va:.1f} {-vb-h:.1f}l{va:.1f} {vb:.1f}v{h:.1f}l{-va:.1f} {-vb:.1f}z"
        delay = 0.2 + w / weeks * (total_anim - grow - 0.3)
        a1, a2 = delay / total_anim, (delay + grow) / total_anim
        blocks.append(
            f'<path d="{base}" fill="#151b14"/>'
            f'<g transform="translate({bx:.1f} {by:.1f})"><g>'
            f'<animateTransform attributeName="transform" type="scale" values="1 0;1 0;1 1;1 1" keyTimes="0;{a1:.4f};{a2:.4f};1" '
            f'calcMode="spline" keySplines="0 0 1 1;0.2 0.8 0.2 1;0 0 1 1" dur="{total_anim}s" fill="freeze"/>'
            f'<path d="{left}" fill="{shade(top, .5)}"/><path d="{front}" fill="{shade(top, .72)}"/><path d="{top_face}" fill="{top}"/>'
            "</g></g>"
        )
    out.append(f'<g>{"".join(blocks)}</g>')
    # month labels along the front edge
    seen = set()
    for w, d, c, date in cells:
        if date[:7] not in seen and date[8:10] <= "07" and d == 0:
            seen.add(date[:7])
            X, Y = P(w + 0.2, 7.5)
            out.append(f'<text x="{X:.1f}" y="{Y+10:.1f}" class="m" font-size="10" fill="{DIM}">{dt.date.fromisoformat(date).strftime("%b").upper()}</text>')
    # best-day beacon
    for w, d, c, date in cells:
        if date == best_date and c:
            X, Y = P(w + .5, d + .5)
            ty = Y - height(c) - 34
            out.append(
                f'<g opacity="1">{fade_in(total_anim, total_anim + 0.6, 0.4)}'
                f'<path d="M{X:.1f} {Y-height(c)-4:.1f}V{ty+5:.1f}" stroke="{ARC}" stroke-dasharray="2 3"/>'
                f'<circle cx="{X:.1f}" cy="{ty:.1f}" r="4" fill="{ARC}"><animate attributeName="r" values="3;6;3" dur="2s" repeatCount="indefinite"/></circle>'
                f'<text x="{X-10:.1f}" y="{ty-4:.1f}" text-anchor="end" class="m" font-size="11" fill="{ARC}">best day · {c}</text></g>'
            )
    # headline + facts, top-left where the year starts low
    span = f"{first.strftime('%b %Y')} – {dt.date.fromisoformat(days[-1][0]).strftime('%b %Y')}"
    out.append(f'<text x="40" y="58" class="m" font-size="12" letter-spacing="3" fill="{LIME}">CONTRIBUTIONS · LAST 12 MONTHS</text>')
    out.append(f'<text x="40" y="112" class="s" font-size="56" font-weight="900" letter-spacing="-2" fill="{PAPER}">{num(live["contributions"])}</text>')
    out.append(f'<text x="40" y="140" class="s" font-size="15" fill="{MUTED}">{x(span)}</text>')
    best_label = dt.date.fromisoformat(best_date).strftime("%b %d").replace(" 0", " ") if best_date else "-"
    facts = [("LONGEST STREAK", f"{longest} days"), ("CURRENT STREAK", f"{current} days"), ("BEST DAY", f"{best_n} on {best_label}")]
    for fi, (lab, val) in enumerate(facts):
        fx = 40 + fi * 150
        out.append(f'<g opacity="1">{fade_in(0.4 + fi*0.25, 2.0, 0.4)}<text x="{fx}" y="184" class="m" font-size="10.5" letter-spacing="2" fill="{DIM}">{lab}</text>'
                   f'<text x="{fx}" y="210" class="s" font-size="20" font-weight="800" fill="{PAPER}">{x(val)}</text></g>')
    lx, ly = W - 210, H - 32
    out.append(f'<text x="{lx}" y="{ly+10}" class="m" font-size="10" fill="{DIM}">LESS</text>')
    for i, col in enumerate(["#151b14"] + levels):
        out.append(f'<rect x="{lx + 38 + i*16}" y="{ly}" width="12" height="12" rx="2" fill="{col}"/>')
    out.append(f'<text x="{lx + 38 + 5*16 + 4}" y="{ly+10}" class="m" font-size="10" fill="{DIM}">MORE</text>')
    return svg(W, H, "".join(out), f"Contribution skyline: {num(live['contributions'])} contributions in the last year")


# ─────────────────────────────── stack ───────────────────────────────
def stack(live: dict) -> str:
    W = 1000
    langs = sorted(live["languages"].items(), key=lambda kv: -kv[1]["bytes"])
    total = sum(v["bytes"] for _, v in langs) or 1
    top = [(k, v["bytes"] / total, v["color"]) for k, v in langs[:6]]
    rest = 1 - sum(p for _, p, _ in top)
    if rest > 0.001:
        top.append(("Other", rest, DIM))
    out = []
    bx, by, bw, bh = 40, 60, W - 80, 14
    out.append(f'<text x="40" y="40" class="m" font-size="12" letter-spacing="3" fill="{LIME}">LANGUAGES · PUBLIC REPOS</text>')
    out.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="7" fill="#141a13"/>')
    out.append(f'<clipPath id="lb"><rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="7"/></clipPath><g clip-path="url(#lb)">')
    cur, t = bx, 0.0
    for name, p, col in top:
        w = p * bw
        out.append(f'<rect x="{cur:.1f}" y="{by}" width="{w:.1f}" height="{bh}" fill="{col}">'
                   f'<animate attributeName="width" values="0;0;{w:.1f}" keyTimes="0;{t/2.4:.3f};{min((t+0.45)/2.4, 1):.3f}" dur="2.4s" fill="freeze"/></rect>')
        cur += w
        t += 0.3
    out.append("</g>")
    lx = 40
    for name, p, col in top:
        label = f"{name} {p*100:.1f}%"
        out.append(f'<circle cx="{lx+5}" cy="{by+38}" r="5" fill="{col}"/><text x="{lx+16}" y="{by+42}" class="s" font-size="13" fill="{PAPER}">{x(name)} '
                   f'<tspan fill="{MUTED}">{p*100:.1f}%</tspan></text>')
        lx += len(label) * 7.6 + 40
    # tool chips
    out.append(f'<text x="40" y="160" class="m" font-size="12" letter-spacing="3" fill="{LIME}">TOOLBOX</text>')
    cxp, cyp, rowh = 40, 178, 40
    for i, (name, col) in enumerate(TOOLS):
        w = len(name) * 7.8 + 38
        if cxp + w > W - 40:
            cxp, cyp = 40, cyp + rowh
        out.append(f'<g opacity="1">{fade_in(0.15 + i*0.05, 2.0, 0.3)}'
                   f'<rect x="{cxp:.1f}" y="{cyp}" width="{w:.1f}" height="30" rx="15" fill="{CARD}" stroke="{LINE}"/>'
                   f'<circle cx="{cxp+16:.1f}" cy="{cyp+15}" r="4.5" fill="{col}"/>'
                   f'<text x="{cxp+28:.1f}" y="{cyp+19.5}" class="m" font-size="13" fill="{PAPER}">{x(name)}</text></g>')
        cxp += w + 10
    H = cyp + 30 + 34
    body = f'<rect x=".5" y=".5" width="{W-1}" height="{H-1}" rx="18" fill="{INK}" stroke="{LINE}"/>' + "".join(out)
    return svg(W, H, body, "Languages and toolbox")


# ─────────────────────────────── section titles + footer ───────────────────────────────
def section(n: int, title: str, col: str = LIME) -> str:
    W, H = 1000, 60
    tw = len(title) * 17.5 + 78
    body = (
        f'<defs><linearGradient id="sl" x1="0" x2="1"><stop offset="0" stop-color="{col}" stop-opacity=".8"/><stop offset="1" stop-color="{col}" stop-opacity="0"/></linearGradient></defs>'
        f'<rect x=".5" y=".5" width="{W-1}" height="{H-1}" rx="14" fill="{INK}" stroke="{LINE}"/>'
        f'<text x="24" y="37" class="m" font-size="14" font-weight="700" fill="{col}">{n:02d}</text>'
        f'<text x="58" y="38" class="s" font-size="21" font-weight="800" letter-spacing="2.5" fill="{PAPER}">{x(title)}</text>'
        f'<rect x="{tw:.0f}" y="30" width="{W-tw-24:.0f}" height="1.5" fill="url(#sl)"/>'
        f'<rect x="{tw:.0f}" y="28.5" width="40" height="4.5" rx="2" fill="{col}"><animate attributeName="x" values="{tw:.0f};{W-84}" dur="3.5s" repeatCount="indefinite"/>'
        '<animate attributeName="opacity" values="1;0" dur="3.5s" repeatCount="indefinite"/></rect>'
    )
    return svg(W, H, body, f"{n:02d} {title.title()}")


def footer() -> str:
    W, H = 1000, 140
    waves = []
    for i, (col, amp, op, dur) in enumerate(((LIME, 14, .5, 7), (ARC, 10, .35, 10), (COPPER, 7, .25, 13))):
        pts = " ".join(f"{px},{40 + amp*math.sin(px/60 + i):.1f}" for px in range(0, 2501, 20))
        waves.append(f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-opacity="{op}" stroke-width="1.5">'
                     f'<animateTransform attributeName="transform" type="translate" values="0 0;-{int(2*math.pi*60*3)} 0" dur="{dur}s" repeatCount="indefinite"/></polyline>')
    body = (
        '<defs><linearGradient id="ff" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".2" stop-color="#fff"/>'
        '<stop offset=".8" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient><mask id="fm"><rect width="1000" height="84" fill="url(#ff)"/></mask></defs>'
        f'<rect x=".5" y=".5" width="{W-1}" height="{H-1}" rx="18" fill="{INK}" stroke="{LINE}"/>'
        f'<g mask="url(#fm)">{"".join(waves)}</g>'
        f'<text x="500" y="102" text-anchor="middle" class="m" font-size="14" letter-spacing="4" fill="{LIME}">REALDEALCPA.AI</text>'
        f'<text x="500" y="124" text-anchor="middle" class="s" font-size="12.5" fill="{MUTED}">Built local-first. Shipped with tests. Reviewed by a human.</text>'
    )
    return svg(W, H, body, "realdealcpa.ai")


def main() -> None:
    live = load("--offline" in sys.argv)
    ASSETS.mkdir(exist_ok=True)
    write("hero.svg", hero(live))
    write("stats.svg", stats(live))
    write("terminal.svg", terminal(live))
    for f in FLAGSHIPS:
        write(f"{f['file']}.svg", card(f, live))
    write("skyline.svg", skyline(live))
    write("stack.svg", stack(live))
    for n, (name, title) in enumerate((("flagships", "FLAGSHIP BUILDS"), ("screens", "ON SCREEN"),
                                        ("year", "A YEAR OF SHIPPING"), ("stack", "STACK"), ("more", "MORE BUILDS")), 1):
        write(f"section-{name}.svg", section(n, title))
    write("footer.svg", footer())
    print(f"data fetched {live['fetchedAt']}")


if __name__ == "__main__":
    main()
