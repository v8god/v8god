#!/usr/bin/env python3
"""Regenerates stats.svg, langs.svg, trophies.svg, contributions.svg (+ -light variants)
from LIVE GitHub data. Run manually (needs a GITHUB_TOKEN env var) or via the
update-stats.yml workflow, which runs it on a schedule and commits the result.

Usage:
    GITHUB_TOKEN=xxxx GITHUB_USERNAME=v8god python3 generate_stat_cards.py
"""
import os, sys, json, math, urllib.request, urllib.error

TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
USERNAME = os.environ.get("GITHUB_USERNAME", "v8god")
OUT_DIR = os.environ.get("OUT_DIR", ".")

if not TOKEN:
    sys.exit("ERROR: set GITHUB_TOKEN (a token with public read access is enough).")

API = "https://api.github.com"

def api_get(path):
    req = urllib.request.Request(f"{API}{path}", headers={
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)

def graphql(query, variables):
    req = urllib.request.Request(
        f"{API}/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)

# ---------------- fetch live data ----------------
user = api_get(f"/users/{USERNAME}")
repos = api_get(f"/users/{USERNAME}/repos?per_page=100&type=owner")

lang_counts = {}
stars_received = 0
for repo in repos:
    if repo.get("fork"):
        continue
    lang = repo.get("language")
    if lang:
        lang_counts[lang] = lang_counts.get(lang, 0) + 1
    stars_received += repo.get("stargazers_count", 0)

gql = graphql(
    """query($login:String!){ user(login:$login){
        contributionsCollection { contributionCalendar { totalContributions
          weeks { contributionDays { date contributionCount weekday color } } } } } }""",
    {"login": USERNAME},
)
cal = gql["data"]["user"]["contributionsCollection"]["contributionCalendar"]
total_contributions = cal["totalContributions"]

# GitHub buckets each day's shade RELATIVE to this user's own distribution (not
# fixed count thresholds) — so derive levels from GitHub's own per-day `color`
# field, ranked by the average count each color represents, rather than
# guessing absolute cutoffs. This reproduces the real profile's shading exactly.
raw_days = [(day["date"], day["contributionCount"], day["weekday"], col, day["color"])
            for col, week in enumerate(cal["weeks"]) for day in week["contributionDays"]]

color_counts = {}
for _, cnt, _, _, color in raw_days:
    color_counts.setdefault(color, []).append(cnt)
zero_colors = {c for c, counts in color_counts.items() if max(counts) == 0}
nonzero_sorted = sorted((c for c in color_counts if c not in zero_colors),
                         key=lambda c: sum(color_counts[c]) / len(color_counts[c]))
color_level = {c: 0 for c in zero_colors}
color_level.update({c: min(i + 1, 4) for i, c in enumerate(nonzero_sorted)})

grid = []
for date, cnt, weekday, col, color in raw_days:
    grid.append({"date": date, "count": cnt, "level": color_level.get(color, 0),
                 "row": weekday, "col": col})

days_sorted = sorted(grid, key=lambda d: d["date"])
best_streak = cur = 0
for d in days_sorted:
    cur = cur + 1 if d["count"] > 0 else 0
    best_streak = max(best_streak, cur)

from collections import defaultdict
monthly = defaultdict(int)
for d in days_sorted:
    monthly[d["date"][:7]] += d["count"]
best_month = max(monthly.items(), key=lambda kv: kv[1]) if monthly else ("", 0)

summary = {
    "total_repos": user.get("public_repos", len(repos)),
    "followers": user.get("followers", 0),
    "following": user.get("following", 0),
    "stars_received": stars_received,
    "contributions_year": total_contributions,
    "longest_streak": best_streak,
    "best_month": {"ym": best_month[0], "count": best_month[1]},
    "languages": lang_counts or {"—": 1},
}
print("Live summary:", json.dumps(summary, indent=2))

# ---------------- design tokens (kept in sync with the original asset set) ----------------
FONT_SANS = "'Segoe UI', ui-sans-serif, system-ui, -apple-system, 'Helvetica Neue', Arial, sans-serif"
FONT_MONO = "'Cascadia Code','Fira Code', ui-monospace, 'SFMono-Regular', Consolas, 'Courier New', monospace"

DARK = dict(mode="dark", bg0="#05060B", bg1="#0A0D16", bg2="#10131F", panel="#12162A",
    graphite="#1B2033", violet="#8B5CF6", violet_soft="#A78BFA", violet_dim="#4C3BA8",
    cyan="#22D3EE", cyan_soft="#67E8F9", emerald="#34D399", text0="#EEF0FA", text1="#9AA1BE",
    text2="#5D6484", card_fill_soft="#12162A80", card_stroke="#8B5CF64D")
LIGHT = dict(mode="light", bg0="#F3F4FB", bg1="#FAFBFF", bg2="#FFFFFF", panel="#FFFFFF",
    graphite="#E6E8F5", violet="#6D28D9", violet_soft="#7C3AED", violet_dim="#C4B5FD",
    cyan="#0891B2", cyan_soft="#0E7C90", emerald="#059669", text0="#12131F", text1="#4B5170",
    text2="#7B819C", card_fill_soft="#FFFFFFB8", card_stroke="#6D28D93D")
LANG_COLORS = {"JavaScript": "#F1C40F", "TypeScript": "#3B82F6", "Python": "#22D3EE",
               "HTML": "#EF6B6B", "CSS": "#8B5CF6", "Java": "#EF6B6B", "C++": "#A78BFA"}

def esc(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

def anim(attr, vals, kts, dur, begin="0s", extra=""):
    v = ";".join(str(x) for x in vals); k = ";".join(str(x) for x in kts)
    return f'<animate attributeName="{attr}" values="{v}" keyTimes="{k}" dur="{dur}s" begin="{begin}" repeatCount="indefinite" {extra}/>'

def card_shell(T, p, W, H, title, body):
    glow_op = "0.22" if T["mode"] == "dark" else "0.12"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="{esc(title)}">
<title>{esc(title)}</title>
<defs>
<linearGradient id="{p}bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="{T['bg1']}"/><stop offset="100%" stop-color="{T['bg0']}"/></linearGradient>
<filter id="{p}bl" x="-150%" y="-150%" width="400%" height="400%"><feGaussianBlur stdDeviation="34"/></filter>
<clipPath id="{p}cl"><rect width="{W}" height="{H}" rx="20"/></clipPath>
</defs>
<g clip-path="url(#{p}cl)">
<rect width="{W}" height="{H}" fill="url(#{p}bg)"/>
<rect width="{W}" height="{H}" fill="none" stroke="{T['card_stroke']}"/>
<circle cx="{W-40}" cy="20" r="120" filter="url(#{p}bl)" fill="{T['violet']}" opacity="{glow_op}"/>
<text x="24" y="34" font-family="{FONT_SANS}" font-size="15.5" font-weight="700" fill="{T['text0']}">{esc(title)}</text>
<circle cx="{W-22}" cy="30" r="3.4" fill="{T['emerald']}">{anim("opacity",[0.4,1,0.4],[0,0.5,1],2.4)}</circle>
{body}
</g></svg>'''

def build_stats(T, uid):
    p = f"st{uid}_"; W, H = 480, 260
    metrics = [("Repositories", summary["total_repos"], 20, T["violet"]),
               ("Contributions / yr", summary["contributions_year"], 600, T["cyan"]),
               ("Longest Streak", summary["longest_streak"], 20, T["emerald"]),
               ("Following", summary["following"], 10, T["violet_soft"])]
    body = []
    cell_w = (W - 48) / 4
    for i, (label, val, maxv, color) in enumerate(metrics):
        cx = 24 + cell_w * i + cell_w / 2; cy = 118; r = 40
        pct = min(100, val / maxv * 100) if maxv else 0
        circ = 2 * math.pi * r; dash = circ * pct / 100
        body.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{T["graphite"]}" stroke-width="10"/>')
        body.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" stroke-width="10" stroke-linecap="round" '
                     f'transform="rotate(-90 {cx} {cy})" stroke-dasharray="{circ:.1f}" stroke-dashoffset="{circ-dash:.1f}"/>')
        body.append(f'<text x="{cx}" y="{cy+6}" text-anchor="middle" font-family="{FONT_SANS}" font-size="19" font-weight="700" fill="{T["text0"]}">{val}</text>')
        body.append(f'<text x="{cx}" y="{cy+64}" text-anchor="middle" font-family="{FONT_SANS}" font-size="10.5" fill="{T["text1"]}">{esc(label)}</text>')
    weeks = {}
    for d in grid:
        weeks[d["col"]] = weeks.get(d["col"], 0) + d["count"]
    last_cols = sorted(weeks)[-26:]
    vals = [weeks[c] for c in last_cols]; vmax = max(vals) or 1
    sx0, sy0, sw, sh = 24, 210, W - 48, 34; bw = sw / len(vals)
    body.append(f'<text x="24" y="196" font-family="{FONT_SANS}" font-size="10.5" fill="{T["text2"]}">LAST 26 WEEKS</text>')
    for i, v in enumerate(vals):
        h = 3 + (v / vmax) * (sh - 3)
        body.append(f'<rect x="{sx0+i*bw:.1f}" y="{sy0+sh-h:.1f}" width="{bw-1.4:.1f}" height="{h:.1f}" rx="1" fill="{T["cyan"]}"/>')
    return card_shell(T, p, W, H, f"GitHub Statistics — {USERNAME}", "".join(body))

def build_langs(T, uid):
    p = f"lg{uid}_"; W, H = 480, 230
    langs = summary["languages"]; total = sum(langs.values()) or 1
    body = []; y = 56
    for i, (name, count) in enumerate(sorted(langs.items(), key=lambda kv: -kv[1])):
        pct = count / total * 100; color = LANG_COLORS.get(name, T["cyan"])
        body.append(f'<text x="24" y="{y}" font-family="{FONT_SANS}" font-size="12.5" fill="{T["text0"]}" font-weight="600">{esc(name)}</text>')
        body.append(f'<text x="{W-24}" y="{y}" text-anchor="end" font-family="{FONT_MONO}" font-size="12" fill="{T["text1"]}">{pct:.1f}%</text>')
        bx, by, bw_full = 24, y+10, W-48
        body.append(f'<rect x="{bx}" y="{by}" width="{bw_full}" height="8" rx="4" fill="{T["graphite"]}"/>')
        body.append(f'<rect x="{bx}" y="{by}" width="{bw_full*pct/100:.1f}" height="8" rx="4" fill="{color}"/>')
        y += 40
    body.append(f'<text x="24" y="{y-8}" font-family="{FONT_SANS}" font-size="10.5" fill="{T["text2"]}">ACROSS {len(langs)} LANGUAGES</text>')
    return card_shell(T, p, W, H, "Most Used Languages", "".join(body))

def build_trophies(T, uid):
    p = f"tr{uid}_"; W, H = 480, 170
    trophies = [("Repositories", summary["total_repos"], "\u25c8"),
                ("Contributions", summary["contributions_year"], "\u2726"),
                ("Longest Streak", f'{summary["longest_streak"]}d', "\u25b2"),
                ("Best Month", summary["best_month"]["count"], "\u2605")]
    body = []; cell_w = (W - 48 - 42) / 4
    for i, (label, val, icon) in enumerate(trophies):
        cx = 24 + i * (cell_w + 14); cy = 46
        body.append(f'<g transform="translate({cx},{cy})">')
        body.append(f'<rect width="{cell_w}" height="96" rx="14" fill="{T["card_fill_soft"]}" stroke="{T["card_stroke"]}"/>')
        body.append(f'<text x="{cell_w/2}" y="34" text-anchor="middle" font-size="22" fill="{T["cyan"]}">{icon}</text>')
        body.append(f'<text x="{cell_w/2}" y="62" text-anchor="middle" font-family="{FONT_SANS}" font-size="18" font-weight="700" fill="{T["text0"]}">{val}</text>')
        body.append(f'<text x="{cell_w/2}" y="82" text-anchor="middle" font-family="{FONT_SANS}" font-size="9.5" fill="{T["text1"]}">{esc(label.upper())}</text>')
        body.append('</g>')
    body.append(f'<text x="24" y="150" font-family="{FONT_SANS}" font-size="10" fill="{T["text2"]}">Live snapshot from github.com/{USERNAME}</text>')
    return card_shell(T, p, W, H, "Trophy Case", "".join(body))

MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

def build_contrib(T, uid):
    p = f"cg{uid}_"; cell, gap = 10, 3
    ncols = max(d["col"] for d in grid) + 1
    left_pad, top_pad = 26, 34
    W = left_pad + ncols * (cell + gap) + 16
    H = top_pad + 7 * (cell + gap) + 26
    levels = [T["graphite"], "#2d235940", T["violet_dim"], T["violet"], T["cyan"]] if T["mode"]=="dark" \
        else [T["graphite"], "#DCD3FA", T["violet_dim"], T["violet"], T["cyan"]]
    body = []
    seen = {}
    for d in days_sorted:
        ym = d["date"][:7]
        if ym not in seen: seen[ym] = d["col"]
    for ym, col in seen.items():
        body.append(f'<text x="{left_pad+col*(cell+gap)}" y="16" font-family="{FONT_SANS}" font-size="9.5" fill="{T["text2"]}">{MONTH_NAMES[int(ym[5:7])-1]}</text>')
    for row, lbl in {1:"Mon",3:"Wed",5:"Fri"}.items():
        body.append(f'<text x="0" y="{top_pad+row*(cell+gap)+8}" font-family="{FONT_SANS}" font-size="9" fill="{T["text2"]}">{lbl}</text>')
    for d in grid:
        x = left_pad + d["col"]*(cell+gap); y = top_pad + d["row"]*(cell+gap)
        body.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2.5" fill="{levels[min(d["level"],4)]}"/>')
    body.append(f'<text x="{left_pad}" y="{H-6}" font-family="{FONT_SANS}" font-size="10" fill="{T["text2"]}">{summary["contributions_year"]} contributions in the last year</text>')
    lx = W - 120
    body.append(f'<text x="{lx-30}" y="{H-6}" font-family="{FONT_SANS}" font-size="9.5" fill="{T["text2"]}">Less</text>')
    for i, c in enumerate(levels):
        body.append(f'<rect x="{lx+i*13}" y="{H-14}" width="10" height="10" rx="2.5" fill="{c}"/>')
    body.append(f'<text x="{lx+5*13+4}" y="{H-6}" font-family="{FONT_SANS}" font-size="9.5" fill="{T["text2"]}">More</text>')
    return card_shell(T, p, W, H, "Contribution Activity — real daily data", "".join(body))

# ---------------- write files ----------------
files = {
    "stats.svg": build_stats(DARK, "a"), "stats-light.svg": build_stats(LIGHT, "d"),
    "langs.svg": build_langs(DARK, "b"), "langs-light.svg": build_langs(LIGHT, "e"),
    "trophies.svg": build_trophies(DARK, "c"), "trophies-light.svg": build_trophies(LIGHT, "f"),
    "contributions.svg": build_contrib(DARK, "g"), "contributions-light.svg": build_contrib(LIGHT, "h"),
}
os.makedirs(OUT_DIR, exist_ok=True)
for name, svg in files.items():
    path = os.path.join(OUT_DIR, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)
    print("wrote", path)
