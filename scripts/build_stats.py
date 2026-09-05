#!/usr/bin/env python3
"""Generate assets/stats.svg and assets/heatmap.svg from the GitHub API.

Runs in GitHub Actions with the default GITHUB_TOKEN, so the profile never
depends on a third-party card service being up.

    USERNAME=Piyush-Karn GITHUB_TOKEN=xxx python scripts/build_stats.py
"""

import datetime as dt
import json
import os
import urllib.request

USER = os.environ.get("USERNAME", "PiyushKumar-96")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")

BG = "#0B0714"
GRID = "#1A1230"
TRACK = "#241A3C"
TEXT = "#E8E4FF"
SUB = "#CFC7EE"
MUTED = "#8C82B6"
CYAN = "#A78BFA"
VIOLET = "#F472B6"

HEAT = ["#150E29", "#33215C", "#5B34A8", "#8B5CF6", "#C4A6FF"]


# --------------------------------------------------------------------- data

def _request(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


GRAPHQL = """
query($login: String!) {
  user(login: $login) {
    followers { totalCount }
    contributionsCollection {
      totalCommitContributions
      restrictedContributionsCount
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
    pullRequests(states: MERGED) { totalCount }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false,
                 orderBy: {field: STARGAZERS, direction: DESC}) {
      totalCount
      nodes {
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""


def fetch_graphql():
    body = json.dumps({"query": GRAPHQL, "variables": {"login": USER}}).encode()
    headers = {
        "Authorization": f"bearer {TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": "profile-stats",
    }
    payload = _request("https://api.github.com/graphql", body, headers)
    user = payload["data"]["user"]
    cc = user["contributionsCollection"]
    cal = cc["contributionCalendar"]

    langs = {}
    stars = 0
    for repo in user["repositories"]["nodes"]:
        stars += repo["stargazerCount"]
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            entry = langs.setdefault(name, {"size": 0, "color": edge["node"]["color"] or CYAN})
            entry["size"] += edge["size"]

    return {
        "contributions": cal["totalContributions"],
        "commits": cc["totalCommitContributions"] + cc["restrictedContributionsCount"],
        "stars": stars,
        "repos": user["repositories"]["totalCount"],
        "followers": user["followers"]["totalCount"],
        "merged_prs": user["pullRequests"]["totalCount"],
        "languages": langs,
        "weeks": [
            [d["contributionCount"] for d in w["contributionDays"]]
            for w in cal["weeks"]
        ],
    }


def fetch_rest():
    """Token-free fallback: fewer numbers, no contribution calendar."""
    headers = {"User-Agent": "profile-stats"}
    user = _request(f"https://api.github.com/users/{USER}", headers=headers)
    repos = _request(
        f"https://api.github.com/users/{USER}/repos?per_page=100&sort=pushed",
        headers=headers,
    )
    langs = {}
    stars = 0
    for repo in repos:
        if repo.get("fork"):
            continue
        stars += repo.get("stargazers_count", 0)
        name = repo.get("language")
        if name:
            entry = langs.setdefault(name, {"size": 0, "color": CYAN})
            entry["size"] += max(repo.get("size", 1), 1)
    return {
        "contributions": None,
        "commits": None,
        "stars": stars,
        "repos": user.get("public_repos", 0),
        "followers": user.get("followers", 0),
        "merged_prs": None,
        "languages": langs,
        "weeks": [],
    }


# ------------------------------------------------------------------ helpers

def esc(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def human(n):
    if n is None:
        return "—"
    if n >= 1000:
        return f"{n / 1000:.1f}K".replace(".0K", "K")
    return str(n)


def top_languages(langs, limit=5):
    ranked = sorted(langs.items(), key=lambda kv: kv[1]["size"], reverse=True)[:limit]
    total = sum(v["size"] for _, v in ranked) or 1
    return [(name, v["color"] or CYAN, v["size"] / total) for name, v in ranked]


SHELL = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 {h}" width="1000" height="{h}" role="img" aria-label="{label}">
<title>{label}</title>
<defs>
  <linearGradient id="edge" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="{cyan}"/><stop offset="1" stop-color="{violet}"/>
  </linearGradient>
  <linearGradient id="beam" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="#D8B4FE" stop-opacity="0"/>
    <stop offset="0.5" stop-color="#D8B4FE" stop-opacity="0.35"/>
    <stop offset="1" stop-color="#D8B4FE" stop-opacity="0"/>
  </linearGradient>
  <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
    <path d="M40 0H0V40" fill="none" stroke="{grid}" stroke-width="1"/>
  </pattern>
  <clipPath id="card"><rect x="1" y="1" width="998" height="{hi}" rx="18"/></clipPath>
</defs>
<g clip-path="url(#card)">
  <rect width="1000" height="{h}" fill="{bg}"/>
  <rect width="1000" height="{h}" fill="url(#grid)" opacity="0.6"/>
  <rect x="-190" y="0" width="190" height="{h}" fill="url(#beam)" opacity="0.5">
    <animate attributeName="x" values="-190;1000" dur="7s" repeatCount="indefinite"/>
  </rect>
{body}
</g>
<rect x="1" y="1" width="998" height="{hi}" rx="18" fill="none" stroke="url(#edge)" stroke-width="1.4" opacity="0.75"/>
</svg>
"""


def shell(height, label, body):
    return SHELL.format(h=height, hi=height - 2, label=label, body=body,
                        bg=BG, grid=GRID, cyan=CYAN, violet=VIOLET)


# ------------------------------------------------------------------- stats

def build_stats(d):
    blocks = [
        (human(d["contributions"] if d["contributions"] is not None else d["commits"]),
         "contributions, this turn of the sun"),
        (human(d["repos"]), "public repositories"),
        (human(d["stars"]), "stars collected"),
        (human(d["followers"]), "fellow travellers"),
    ]

    body = ['  <g font-family="Georgia,DejaVu Serif,serif">']
    positions = [(70, 118), (290, 118), (70, 216), (290, 216)]
    for i, ((value, label), (x, y)) in enumerate(zip(blocks, positions)):
        begin = 0.05 + i * 0.05
        body.append(f'''    <g opacity="0">
      <text x="{x}" y="{y}" font-size="36" font-weight="bold" fill="{CYAN}">{value}</text>
      <text x="{x}" y="{y + 22}" font-size="12" fill="{MUTED}">{label}</text>
      <animate attributeName="opacity" values="0;0;1;1;0" keyTimes="0;{begin:.2f};{begin + 0.08:.2f};0.95;1" dur="10s" repeatCount="indefinite"/>
      <animateTransform attributeName="transform" type="translate" values="0 14;0 14;0 0;0 0;0 14" keyTimes="0;{begin:.2f};{begin + 0.08:.2f};0.95;1" dur="10s" repeatCount="indefinite"/>
    </g>''')

    body.append(f'    <text x="70" y="66" font-size="13" letter-spacing="2.5" fill="{SUB}">the ledger</text>')
    body.append(f'    <line x1="520" y1="50" x2="520" y2="250" stroke="{TRACK}" stroke-width="1"/>')
    body.append(f'    <text x="570" y="66" font-size="13" letter-spacing="2.5" fill="{SUB}">tongues spoken</text>')

    langs = top_languages(d["languages"])
    for i, (name, color, share) in enumerate(langs):
        y = 104 + i * 34
        begin = 0.10 + i * 0.05
        body.append(f'''    <g>
      <text x="570" y="{y + 4}" font-size="12.5" fill="{SUB}">{esc(name)}</text>
      <rect x="700" y="{y - 8}" width="200" height="9" rx="4.5" fill="{TRACK}"/>
      <rect x="700" y="{y - 8}" width="0" height="9" rx="4.5" fill="{color}">
        <animate attributeName="width" values="0;0;{round(200 * share)};{round(200 * share)};0" keyTimes="0;{begin:.2f};{begin + 0.14:.2f};0.95;1" dur="10s" repeatCount="indefinite"/>
      </rect>
      <text x="916" y="{y + 4}" font-size="12" fill="{MUTED}">{share * 100:.1f}%</text>
    </g>''')

    body.append("  </g>")
    return shell(280, f"GitHub statistics for {USER}", "\n".join(body))


# ----------------------------------------------------------------- heatmap

def build_heatmap(d):
    weeks = d["weeks"][-53:]
    if not weeks:
        return None

    peak = max((c for w in weeks for c in w), default=0) or 1
    cell, pitch = 13, 17
    x0, y0 = 46, 74

    def level(count):
        if count == 0:
            return 0
        ratio = count / peak
        return 1 + min(3, int(ratio * 4))

    body = ['  <g font-family="Georgia,DejaVu Serif,serif">']
    body.append(f'    <text x="46" y="46" font-size="13" letter-spacing="2.5" fill="{SUB}">'
                f'{human(d["contributions"])} contributions in the last year</text>')

    for wi, week in enumerate(weeks):
        begin = 0.03 + wi * 0.008
        body.append(f'    <g opacity="0">')
        for di, count in enumerate(week):
            fill = HEAT[level(count)]
            body.append(f'      <rect x="{x0 + wi * pitch}" y="{y0 + di * pitch}" '
                        f'width="{cell}" height="{cell}" rx="3" fill="{fill}"/>')
        body.append(f'      <animate attributeName="opacity" values="0;0;1;1;0" '
                    f'keyTimes="0;{begin:.3f};{min(begin + 0.05, 0.94):.3f};0.95;1" '
                    f'dur="12s" repeatCount="indefinite"/>')
        body.append("    </g>")

    legend_x = 700
    body.append(f'    <text x="{legend_x - 44}" y="{y0 + 7 * pitch + 26}" font-size="11" fill="{MUTED}">less</text>')
    for i, color in enumerate(HEAT):
        body.append(f'    <rect x="{legend_x + i * 18}" y="{y0 + 7 * pitch + 14}" width="13" height="13" rx="3" fill="{color}"/>')
    body.append(f'    <text x="{legend_x + 5 * 18 + 4}" y="{y0 + 7 * pitch + 26}" font-size="11" fill="{MUTED}">more</text>')
    body.append("  </g>")

    height = y0 + 7 * pitch + 50
    return shell(height, f"Contribution calendar for {USER}", "\n".join(body))


# -------------------------------------------------------------------- main

def main():
    if TOKEN:
        try:
            data = fetch_graphql()
        except Exception as exc:  # noqa: BLE001 - fall back rather than fail the build
            print(f"GraphQL failed ({exc}); falling back to REST")
            data = fetch_rest()
    else:
        data = fetch_rest()

    os.makedirs(OUT, exist_ok=True)

    with open(os.path.join(OUT, "stats.svg"), "w") as fh:
        fh.write(build_stats(data))
    print("wrote assets/stats.svg")

    heatmap = build_heatmap(data)
    if heatmap:
        with open(os.path.join(OUT, "heatmap.svg"), "w") as fh:
            fh.write(heatmap)
        print("wrote assets/heatmap.svg")
    else:
        print("no calendar data (no token) — kept existing heatmap.svg")

    print(f"generated {dt.datetime.utcnow():%Y-%m-%d %H:%M} UTC")


if __name__ == "__main__":
    main()
