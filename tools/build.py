"""
ah.sys :: profile asset compiler

Renders every SVG in ../assets from the definitions below. Fonts (Unbounded 800,
IBM Plex Mono 400/600) are subset per file to the glyphs actually used and
embedded as WOFF2, so the cards render identically inside GitHub's <img> sandbox.

    pip install fonttools brotli
    python tools/build.py --fonts <dir containing unb800.ttf, plex400.ttf, plex600.ttf>
"""

import argparse
import base64
import html
import io
import random
import re
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets"

BG = "#05070a"
INK = "#e8ecef"
MIST = "#949ea8"
FAINT = "#58626b"
LINE = "rgba(232,236,239,0.08)"

PAL = {
    "quant": "#00e08a",
    "chain": "#3fc4ff",
    "sec": "#ff4054",
    "agent": "#9e7bff",
    "infra": "#ffb224",
}

FONTS = {}  # class -> (family, ttf path)


def esc(s):
    return html.escape(s, quote=False)


# --------------------------------------------------------------------------- fonts

def font_face(family, ttf, chars):
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["kern", "liga"]
    opts.name_IDs = []
    opts.notdef_outline = False
    font = TTFont(ttf)
    sub = subset.Subsetter(opts)
    sub.populate(text="".join(sorted(chars)) + " ")
    sub.subset(font)
    buf = io.BytesIO()
    font.flavor = "woff2"
    font.save(buf)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"@font-face{{font-family:'{family}';src:url(data:font/woff2;base64,{b64}) format('woff2');}}"


def text_by_class(body):
    """Collect the characters rendered by each font class (d / m / mb)."""
    used = {"d": set(), "m": set(), "mb": set()}
    for m in re.finditer(r'<(text|tspan)\b([^>]*)>(.*?)</\1>', body, re.S):
        attrs, inner = m.group(2), m.group(3)
        cls = re.search(r'class="([^"]*)"', attrs)
        names = cls.group(1).split() if cls else []
        txt = html.unescape(re.sub(r"<[^>]+>", "", inner))
        for k in used:
            if k in names:
                used[k] |= set(txt)
        # tspans inherit from their parent <text>; gather nested tspans too
        for t in re.finditer(r'<tspan\b([^>]*)>(.*?)</tspan>', inner, re.S):
            c2 = re.search(r'class="([^"]*)"', t.group(1))
            for k in used:
                if c2 and k in c2.group(1).split():
                    used[k] |= set(html.unescape(t.group(2)))
    return used


BASE_CSS = f"""
.d{{font-family:'AHD','Unbounded','Arial Black',sans-serif;font-weight:800}}
.m{{font-family:'AHM','IBM Plex Mono',ui-monospace,Menlo,Consolas,monospace;font-weight:400}}
.mb{{font-family:'AHMB','IBM Plex Mono',ui-monospace,Menlo,Consolas,monospace;font-weight:600}}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}}}
"""


def svg(name, w, h, body, css="", title=""):
    used = text_by_class(body)
    faces = []
    for cls, fam in (("d", "AHD"), ("m", "AHM"), ("mb", "AHMB")):
        if used[cls]:
            faces.append(font_face(fam, FONTS[cls], used[cls]))
    doc = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'role="img" aria-label="{html.escape(title)}">'
        f"<title>{esc(title)}</title>"
        f"<style>{''.join(faces)}{BASE_CSS}{css}</style>"
        f"{body}</svg>"
    )
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(doc, encoding="utf-8")
    print(f"  {name:28s} {len(doc)/1024:6.1f} KB")


# ------------------------------------------------------------------------ helpers

def frame(w, h, accent=None, rx=14):
    """Card background: panel, hairline border, faint grid, corner ticks."""
    out = [
        f'<defs><clipPath id="card"><rect width="{w}" height="{h}" rx="{rx}"/></clipPath>'
        f'<pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">'
        f'<path d="M40 0H0V40" fill="none" stroke="{INK}" stroke-opacity=".028"/></pattern></defs>',
        f'<rect width="{w}" height="{h}" rx="{rx}" fill="{BG}"/>',
        f'<rect width="{w}" height="{h}" rx="{rx}" fill="url(#grid)"/>',
        f'<rect x=".5" y=".5" width="{w-1}" height="{h-1}" rx="{rx}" fill="none" stroke="{LINE}"/>',
    ]
    c = accent or INK
    t = 14
    for x, y, dx, dy in ((12, 12, 1, 1), (w - 12, 12, -1, 1), (12, h - 12, 1, -1), (w - 12, h - 12, -1, -1)):
        out.append(
            f'<path d="M{x} {y+dy*t}V{y}H{x+dx*t}" fill="none" stroke="{c}" stroke-opacity=".45" stroke-width="1.5"/>'
        )
    return "".join(out)




def lines(x, y, rows, cls="m", size=17, lh=27, fill=MIST, extra=""):
    return "".join(
        f'<text class="{cls}" x="{x}" y="{y+i*lh}" font-size="{size}" fill="{fill}" {extra}>{esc(r)}</text>'
        for i, r in enumerate(rows)
    )


def wrap(s, n):
    words, rows, cur = s.split(), [], ""
    for w in words:
        if len(cur) + len(w) + (1 if cur else 0) > n:
            rows.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}" if cur else w
    if cur:
        rows.append(cur)
    return rows


def dot(x, y, color, r=4, blink=False):
    cls = ' class="blink"' if blink else ""
    return (
        f'<circle cx="{x}" cy="{y}" r="{r*2.4}" fill="{color}" fill-opacity=".15"{cls}/>'
        f'<circle cx="{x}" cy="{y}" r="{r}" fill="{color}"/>'
    )


ANIM = """
@keyframes blink{0%,49%{opacity:1}50%,100%{opacity:0}}
@keyframes pulse{0%,100%{opacity:.25}50%{opacity:1}}
@keyframes rise{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
@keyframes fadein{from{opacity:0}to{opacity:1}}
.blink{animation:blink 1.1s steps(1) infinite}
.pulse{animation:pulse 2.4s ease-in-out infinite}
"""


# ------------------------------------------------------------------------- header

def header():
    W, H = 1200, 490
    b = [frame(W, H)]
    # top bar
    b.append(
        f'<rect x="48" y="38" width="24" height="24" fill="none" stroke="{PAL["quant"]}" stroke-width="2"/>'
        f'<rect x="57" y="47" width="6" height="6" fill="{PAL["quant"]}"/>'
        f'<text class="mb" x="86" y="56" font-size="17" fill="{INK}" letter-spacing="2">AH.SYS</text>'
    )
    b.append(f'<text class="m" x="1152" y="54" font-size="15" fill="{FAINT}" text-anchor="end" letter-spacing="2">LOC: CANADA</text>')
    b.append(f'<line x1="48" y1="84" x2="1152" y2="84" stroke="{LINE}"/>')

    # status
    b.append(dot(56, 124, PAL["quant"], 4, blink=False))
    b.append(
        f'<text class="m" x="72" y="130" font-size="15" fill="{MIST}" letter-spacing="2.5">'
        f'MOD.00 :: SYS.CORE — <tspan class="mb" fill="{PAL["quant"]}">ONLINE</tspan></text>'
    )

    # name
    b.append(
        f'<defs><linearGradient id="fade" x1="0" x2="1"><stop offset="0" stop-color="{MIST}"/>'
        f'<stop offset="1" stop-color="{FAINT}" stop-opacity=".55"/></linearGradient></defs>'
    )
    b.append(
        '<g class="name">'
        f'<text class="d" x="44" y="236" font-size="92" fill="{INK}" letter-spacing="-1">ABOLFAZL</text>'
        f'<text class="d" x="44" y="334" font-size="92" fill="url(#fade)" letter-spacing="-1">HOSSEINI</text>'
        "</g>"
    )
    b.append(
        f'<text class="mb role" x="48" y="384" font-size="18" fill="{INK}" letter-spacing="3.2">'
        "SYSTEMS ENGINEER &amp; TECHNICAL FOUNDER</text>"
    )
    b.append(
        '<g class="desc">'
        + lines(48, 424, [
            "I build systems that have to survive contact with the",
            "real world — live markets, open chains, hostile networks.",
        ], size=17, lh=27)
        + "</g>"
    )

    # boot console
    px, py, pw, ph = 770, 150, 382, 290
    b.append(
        f'<rect x="{px}" y="{py}" width="{pw}" height="{ph}" rx="8" fill="#080b10" stroke="{LINE}"/>'
        f'<line x1="{px}" y1="{py+36}" x2="{px+pw}" y2="{py+36}" stroke="{LINE}"/>'
    )
    for i, k in enumerate(("sec", "infra", "quant")):
        b.append(f'<circle cx="{px+20+i*16}" cy="{py+18}" r="4.5" fill="{PAL[k]}" fill-opacity=".7"/>')
    b.append(f'<text class="m" x="{px+pw-16}" y="{py+23}" font-size="15" fill="{FAINT}" text-anchor="end">tty0</text>')
    rows = [
        ("cmd", "$ ah.sys --boot --user a0x0h"),
        ("quant", "quant.engine"),
        ("chain", "chain.scan"),
        ("sec", "sec.kernel"),
        ("agent", "agent.mesh"),
        ("infra", "infra.base"),
    ]
    ly = py + 72
    for i, (k, label) in enumerate(rows):
        delay = 0.35 + i * 0.32
        if k == "cmd":
            b.append(
                f'<text class="m boot" style="animation-delay:{delay:.2f}s" x="{px+20}" y="{ly}" font-size="16" '
                f'fill="{INK}">{esc(label)}</text>'
            )
        else:
            b.append(
                f'<text class="m boot" style="animation-delay:{delay:.2f}s" x="{px+20}" y="{ly}" font-size="16" fill="{MIST}">'
                f'[ <tspan class="mb" fill="{PAL[k]}">OK</tspan> ] {esc(label)}'
                f'<tspan fill="{FAINT}">{"." * (16 - len(label))}</tspan><tspan fill="{FAINT}"> loaded</tspan></text>'
            )
        ly += 31
    d = 0.35 + len(rows) * 0.32
    b.append(
        f'<text class="mb boot" style="animation-delay:{d:.2f}s" x="{px+20}" y="{ly+4}" font-size="16" fill="{PAL["quant"]}">'
        f'» all modules nominal</text>'
        f'<rect class="boot" style="animation-delay:{d:.2f}s" x="{px+228}" y="{ly-11}" width="10" height="19" fill="{PAL["quant"]}">'
        f'<animate attributeName="opacity" values="1;1;0;0" keyTimes="0;.5;.5;1" dur="1.1s" repeatCount="indefinite"/></rect>'
    )

    css = ANIM + f"""
.boot{{opacity:0;animation:fadein .25s ease forwards}}
.name{{animation:rise 1s cubic-bezier(.16,1,.3,1) both}}
.role{{animation:fadein 1s .5s ease both}}
.desc{{animation:fadein 1s .8s ease both}}
"""
    svg("header.svg", W, H, "".join(b), css,
        "Abolfazl Hosseini — Systems Engineer & Technical Founder. Booting modules: quant, chain, sec, agent, infra.")


# -------------------------------------------------------------------------- focus

FOCUS = [
    ("01", "QUANT.ENGINE", "quant", "Markets at the latency edge.", "HFT · microstructure · MQL5"),
    ("02", "CHAIN.SCAN", "chain", "Chains, read statistically.", "on-chain · VaR · FRM"),
    ("03", "SEC.KERNEL", "sec", "Found it. Then closed it.", "bug bounty · hardening"),
    ("04", "AGENT.MESH", "agent", "Software with agency.", "LangGraph · RAG · evals"),
    ("05", "INFRA.BASE", "infra", "The substrate it all runs on.", "Go · Python · Kubernetes"),
]


def focus():
    W, H = 1200, 380
    b = [frame(W, H)]
    for i, (idx, code, k, title, hint) in enumerate(FOCUS):
        y = 40 + i * 60
        c = PAL[k]
        if i:
            b.append(f'<line x1="48" y1="{y}" x2="1152" y2="{y}" stroke="{LINE}"/>')
        b.append(
            f'<rect x="48" y="{y+24}" width="10" height="10" fill="{c}"/>'
            f'<text class="mb" x="76" y="{y+35}" font-size="15" fill="{c}" letter-spacing="3">{code}</text>'
            f'<text class="d" x="320" y="{y+38}" font-size="24" fill="{INK}">{esc(title)}</text>'
            f'<text class="m" x="1152" y="{y+35}" font-size="15" fill="{FAINT}" text-anchor="end">{esc(hint)}</text>'
        )
    svg("focus.svg", W, H, "".join(b), "",
        "Focus: " + "; ".join(f"{code} — {title}" for _, code, _, title, _ in FOCUS))


# --------------------------------------------------------------------- tradevision

def tradevision():
    W, H = 1200, 470
    c = PAL["quant"]
    b = [frame(W, H, c)]
    b.append(
        f'<text class="mb" x="48" y="62" font-size="16" fill="{c}" letter-spacing="3.5">B/01 <tspan fill="{FAINT}">—</tspan> FLAGSHIP</text>'
        f'<text class="d" x="46" y="128" font-size="54" fill="{INK}" letter-spacing="-1">TradeVision</text>'
        f'<text class="mb" x="48" y="164" font-size="16" fill="{MIST}" letter-spacing="1.5">TRADING EXPERT FOR METATRADER 5 — v3.00</text>'
    )
    b.append(lines(48, 222, [
        "An execution terminal rendered natively inside",
        "the MT5 chart: multi-trigger entries, one",
        "portfolio-wide risk cap, split take-profits.",
    ], size=17, lh=28))
    b.append(dot(56, 420, c, 4))
    b.append(
        f'<text class="mb" x="72" y="425" font-size="15" fill="{c}" letter-spacing="2.5">RUNNING IN LIVE MARKETS</text>'
        f'<text class="mb" x="684" y="425" font-size="15" fill="{INK}" letter-spacing="2.5" text-anchor="end">OPEN TERMINAL ↗</text>'
    )

    # chart panel
    px, py, pw, ph = 720, 40, 440, 390
    b.append(f'<rect x="{px}" y="{py}" width="{pw}" height="{ph}" rx="8" fill="#080b10" stroke="{LINE}"/>')
    b.append(
        f'<text class="mb" x="{px+18}" y="{py+28}" font-size="15" fill="{INK}">XAUUSD · M15</text>'
        f'<text class="m" x="{px+pw-18}" y="{py+28}" font-size="15" fill="{FAINT}" text-anchor="end">TV v3.00</text>'
        f'<line x1="{px}" y1="{py+44}" x2="{px+pw}" y2="{py+44}" stroke="{LINE}"/>'
    )
    # candles
    rnd = random.Random(42)
    price = 0.0
    xs, top, bot = px + 20, py + 64, py + 300
    series = []
    for i in range(26):
        o = price
        price += rnd.gauss(0.25, 1.0)
        cl = price
        hi = max(o, cl) + abs(rnd.gauss(0, .5))
        lo = min(o, cl) - abs(rnd.gauss(0, .5))
        series.append((o, hi, lo, cl))
    lo_all = min(s[2] for s in series) - 1.5
    hi_all = max(s[1] for s in series) + 4.5

    def Y(v):
        return bot - (v - lo_all) / (hi_all - lo_all) * (bot - top)

    for i, (o, hi, lo, cl) in enumerate(series):
        x = xs + i * 11.5
        up = cl >= o
        col = c if up else INK
        b.append(f'<line x1="{x+3.5}" y1="{Y(hi):.1f}" x2="{x+3.5}" y2="{Y(lo):.1f}" stroke="{col}" stroke-opacity=".6"/>')
        y1, y2 = sorted((Y(o), Y(cl)))
        fill = col if up else BG
        b.append(f'<rect x="{x}" y="{y1:.1f}" width="7" height="{max(1.5, y2-y1):.1f}" fill="{fill}" stroke="{col}" stroke-opacity=".8"/>')
    last = series[-1][3]
    levels = [
        ("TP3", last + 4.0, c, 1.0), ("TP2", last + 2.7, c, .75), ("TP1", last + 1.4, c, .5),
        ("ENTRY", last, INK, .9), ("SL", last - 1.6, PAL["sec"], .9),
    ]
    lx2 = px + pw - 70
    for name, v, col, op in levels:
        y = Y(v)
        dash = "" if name == "ENTRY" else ' stroke-dasharray="5 4"'
        b.append(f'<line x1="{xs}" y1="{y:.1f}" x2="{lx2}" y2="{y:.1f}" stroke="{col}" stroke-opacity="{op}"{dash}/>')
        b.append(
            f'<rect x="{lx2+4}" y="{y-10:.1f}" width="50" height="20" rx="2" fill="{col}" fill-opacity=".14" stroke="{col}" stroke-opacity="{op}"/>'
            f'<text class="mb" x="{lx2+29}" y="{y+5:.1f}" font-size="12" fill="{col}" text-anchor="middle">{name}</text>'
        )
    # armed triggers
    for k, v in enumerate((last - 0.6, last + 0.7)):
        y = Y(v)
        b.append(
            f'<line x1="{xs+150}" y1="{y:.1f}" x2="{lx2}" y2="{y:.1f}" stroke="{PAL["infra"]}" stroke-opacity=".8" '
            f'stroke-dasharray="1 4" class="pulse" style="animation-delay:{k*0.6}s"/>'
        )
    # footer stats
    fy = py + 322
    b.append(f'<line x1="{px}" y1="{fy}" x2="{px+pw}" y2="{fy}" stroke="{LINE}"/>')
    stats = [("RISK CAP", "2.00%"), ("TRIGGERS", "3 ARMED"), ("SPLIT", "3 × TP"), ("RETRY", "SAFE")]
    for i, (k, v) in enumerate(stats):
        x = px + 18 + i * 106
        b.append(
            f'<text class="m" x="{x}" y="{fy+26}" font-size="12" fill="{FAINT}" letter-spacing="1">{k}</text>'
            f'<text class="mb" x="{x}" y="{fy+50}" font-size="15" fill="{INK}">{esc(v)}</text>'
        )
    svg("builds/tradevision.svg", W, H, "".join(b), ANIM,
        "B/01 Flagship — TradeVision, a trading expert for MetaTrader 5 (v3.00), running in live markets.")


# --------------------------------------------------------------------------- repos

REPOS = [
    ("Sullis", "Operating system for venture building: AI agents for research, validation and portfolio scoring.",
     "sullis.ai · Next.js · FastAPI", PAL["agent"]),
    ("airport-twin", "3D digital twin of Mashhad airport, driven by a seeded discrete-event simulation.",
     "TypeScript", "#3178c6"),
    ("Clueless", "Invisible AI copilot for interviews and meetings. Offline speech, hidden from screen share.",
     "C#", "#178600"),
]


def repo(name, desc, lang, lc):
    W, H = 390, 220
    b = [frame(W, H, rx=12)]
    size = min(20, (W - 80) / (len(name) * 0.6))
    b.append(f'<text class="mb" x="28" y="58" font-size="{size:.1f}" fill="{INK}">{esc(name)}</text>')
    b.append(f'<text class="m" x="{W-28}" y="58" font-size="15" fill="{FAINT}" text-anchor="end">↗</text>')
    b.append(lines(28, 94, wrap(desc, 36), size=15, lh=23))
    b.append(f'<line x1="28" y1="{H-62}" x2="{W-28}" y2="{H-62}" stroke="{LINE}"/>')
    b.append(f'<circle cx="34" cy="{H-34}" r="6" fill="{lc}"/>')
    b.append(f'<text class="m" x="48" y="{H-29}" font-size="15" fill="{MIST}">{esc(lang)}</text>')
    svg(f"repos/{name.lower()}.svg", W, H, "".join(b), "", f"{name} — {desc}")


# ------------------------------------------------------------------------ contact

LINKS = [
    ("email", "EMAIL", "hosseini.systems@gmail.com", "quant"),
    ("linkedin", "LINKEDIN", "in/abhs", "chain"),
    ("portfolio", "PORTFOLIO", "lhosseini.ir", "agent"),
]


def link_button(slug, label, value, k):
    W, H = 390, 84
    c = PAL[k]
    b = [
        f'<rect width="{W}" height="{H}" rx="10" fill="{BG}"/>'
        f'<rect x=".5" y=".5" width="{W-1}" height="{H-1}" rx="10" fill="none" stroke="{LINE}"/>'
        f'<rect x="0" y="22" width="3" height="40" fill="{c}"/>'
        f'<text class="mb" x="26" y="36" font-size="13" fill="{c}" letter-spacing="2.5">→ {label}</text>'
        f'<text class="m" x="26" y="62" font-size="{min(17, 300 / (len(value) * .6)):.1f}" fill="{INK}">{esc(value)}</text>'
        f'<text class="m" x="{W-26}" y="52" font-size="20" fill="{MIST}" text-anchor="end">↗</text>'
    ]
    svg(f"io/{slug}.svg", W, H, "".join(b), "", f"{label}: {value}")


# ---------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fonts", required=True, type=Path)
    a = ap.parse_args()
    FONTS.update(d=a.fonts / "unb800.ttf", m=a.fonts / "plex400.ttf", mb=a.fonts / "plex600.ttf")
    print("ah.sys :: compiling assets")
    header()
    focus()
    tradevision()
    for r in REPOS:
        repo(*r)
    for l in LINKS:
        link_button(*l)

if __name__ == "__main__":
    main()
