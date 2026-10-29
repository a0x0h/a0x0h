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
import math
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


def chips(x, y, tags, color, size=15, gap=10, pad=12, h=30):
    out, cx = [], x
    cw = size * 0.6
    for t in tags:
        w = len(t) * cw + pad * 2
        out.append(
            f'<rect x="{cx}" y="{y}" width="{w:.1f}" height="{h}" rx="3" fill="{color}" fill-opacity=".06" '
            f'stroke="{color}" stroke-opacity=".35"/>'
            f'<text class="m" x="{cx+pad}" y="{y+h/2+size*0.36:.1f}" font-size="{size}" fill="{INK}" '
            f'fill-opacity=".85">{esc(t)}</text>'
        )
        cx += w + gap
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
    W, H = 1200, 540
    b = [frame(W, H)]
    # top bar
    b.append(
        f'<rect x="48" y="38" width="24" height="24" fill="none" stroke="{PAL["quant"]}" stroke-width="2"/>'
        f'<rect x="57" y="47" width="6" height="6" fill="{PAL["quant"]}"/>'
        f'<text class="mb" x="86" y="56" font-size="17" fill="{INK}" letter-spacing="2">AH.SYS</text>'
    )
    nav = [("QNT", "quant"), ("CHN", "chain"), ("SEC", "sec"), ("AGT", "agent"), ("NFR", "infra")]
    nx = 640
    for code, key in nav:
        b.append(f'<rect x="{nx}" y="44" width="8" height="8" fill="{PAL[key]}"/>')
        b.append(f'<text class="mb" x="{nx+16}" y="54" font-size="15" fill="{MIST}" letter-spacing="2">{code}</text>')
        nx += 80
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

    # ticker
    b.append(f'<line x1="0" y1="{H-58}" x2="{W}" y2="{H-58}" stroke="{LINE}"/>')
    words = [("MARKETS", "quant"), ("CHAINS", "chain"), ("DEFENSES", "sec"), ("AGENTS", "agent"), ("INFRASTRUCTURE", "infra")]
    seg, x = [], 0
    for wd, k in words:
        seg.append(f'<rect x="{x}" y="-7" width="7" height="7" fill="{PAL[k]}" transform="rotate(45 {x+3.5} -3.5)"/>')
        seg.append(f'<text class="mb" x="{x+24}" y="0" font-size="15" fill="{MIST}" letter-spacing="4">{wd}</text>')
        x += 24 + len(wd) * 9 + len(wd) * 4 + 52
    seg_w = x
    reps = math.ceil(W / seg_w) + 1
    tick = "".join(f'<g transform="translate({i*seg_w} 0)">{"".join(seg)}</g>' for i in range(reps))
    b.append(
        f'<g clip-path="url(#card)"><g transform="translate(0 {H-24})"><g class="ticker">{tick}</g></g></g>'
    )

    # scan line
    b.append(
        f'<defs><linearGradient id="scan" x1="0" x2="0" y1="0" y2="1">'
        f'<stop offset="0" stop-color="{PAL["quant"]}" stop-opacity="0"/>'
        f'<stop offset="1" stop-color="{PAL["quant"]}" stop-opacity=".07"/></linearGradient></defs>'
        f'<g clip-path="url(#card)"><rect class="scan" x="0" y="-120" width="{W}" height="120" fill="url(#scan)"/></g>'
    )

    css = ANIM + f"""
.boot{{opacity:0;animation:fadein .25s ease forwards}}
.name{{animation:rise 1s cubic-bezier(.16,1,.3,1) both}}
.role{{animation:fadein 1s .5s ease both}}
.desc{{animation:fadein 1s .8s ease both}}
.ticker{{animation:tick {seg_w/40:.1f}s linear infinite}}
@keyframes tick{{to{{transform:translateX(-{seg_w}px)}}}}
.scan{{animation:scan 7s cubic-bezier(.4,0,.2,1) infinite}}
@keyframes scan{{0%{{transform:translateY(0)}}60%,100%{{transform:translateY({H+140}px)}}}}
"""
    svg("header.svg", W, H, "".join(b), css,
        "Abolfazl Hosseini — Systems Engineer & Technical Founder. Booting modules: quant, chain, sec, agent, infra.")


# ------------------------------------------------------------------------ modules

def glyph_quant(cx, cy, c):
    # order book: bids grow left of mid, asks right; widths breathe
    out = []
    rnd = random.Random(7)
    for i in range(7):
        y = cy - 84 + i * 24
        bw = 40 + rnd.random() * 90
        aw = 40 + rnd.random() * 90
        dur = 2.2 + rnd.random() * 2
        out.append(
            f'<rect x="{cx-6-bw:.1f}" y="{y}" width="{bw:.1f}" height="16" fill="{c}" fill-opacity="{.85 - i*0.09:.2f}" '
            f'style="transform-origin:{cx-6}px {y}px;animation:breathe {dur:.1f}s ease-in-out {i*0.2:.1f}s infinite"/>'
            f'<rect x="{cx+6}" y="{y}" width="{aw:.1f}" height="16" fill="none" stroke="{c}" stroke-opacity="{.75 - i*0.08:.2f}" '
            f'style="transform-origin:{cx+6}px {y}px;animation:breathe {dur+.7:.1f}s ease-in-out {i*0.15:.1f}s infinite"/>'
        )
    out.append(f'<line x1="{cx}" y1="{cy-96}" x2="{cx}" y2="{cy+86}" stroke="{INK}" stroke-opacity=".5" stroke-dasharray="2 4"/>')
    out.append(f'<text class="m" x="{cx-10}" y="{cy+108}" font-size="15" fill="{FAINT}" text-anchor="end">BID</text>')
    out.append(f'<text class="m" x="{cx+10}" y="{cy+108}" font-size="15" fill="{FAINT}">ASK</text>')
    return "".join(out)


def glyph_chain(cx, cy, c):
    nodes = [(-110, -60), (-40, -86), (30, -40), (110, -76), (-90, 30), (0, 40), (90, 20), (-30, 86), (60, 90)]
    edges = [(0, 1), (1, 2), (2, 3), (0, 4), (4, 5), (2, 5), (5, 6), (3, 6), (4, 7), (5, 8), (7, 8), (6, 8)]
    out = []
    for a, bb in edges:
        x1, y1 = cx + nodes[a][0], cy + nodes[a][1]
        x2, y2 = cx + nodes[bb][0], cy + nodes[bb][1]
        out.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{c}" stroke-opacity=".3"/>')
    for i, (a, bb) in enumerate(edges[::2]):
        x1, y1 = cx + nodes[a][0], cy + nodes[a][1]
        x2, y2 = cx + nodes[bb][0], cy + nodes[bb][1]
        out.append(
            f'<circle r="3" fill="{c}"><animateMotion dur="{2.4 + i*0.35:.2f}s" repeatCount="indefinite" '
            f'path="M{x1} {y1}L{x2} {y2}"/></circle>'
        )
    cluster = {2, 5, 6}
    for i, (x, y) in enumerate(nodes):
        r = 9 if i in cluster else 6
        fill = c if i in cluster else BG
        out.append(f'<circle cx="{cx+x}" cy="{cy+y}" r="{r}" fill="{fill}" stroke="{c}" stroke-width="1.5"/>')
    out.append(
        f'<ellipse cx="{cx+40}" cy="{cy+6}" rx="88" ry="66" fill="none" stroke="{c}" stroke-opacity=".5" '
        f'stroke-dasharray="3 5" class="pulse"/>'
    )
    return "".join(out)


def glyph_sec(cx, cy, c):
    out = [f'<defs><linearGradient id="sweep" x1="0" x2="1"><stop offset="0" stop-color="{c}" stop-opacity="0"/>'
           f'<stop offset="1" stop-color="{c}" stop-opacity=".35"/></linearGradient></defs>']
    for r in (40, 75, 110):
        out.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{c}" stroke-opacity=".22"/>')
    out.append(f'<line x1="{cx-118}" y1="{cy}" x2="{cx+118}" y2="{cy}" stroke="{c}" stroke-opacity=".15"/>')
    out.append(f'<line x1="{cx}" y1="{cy-118}" x2="{cx}" y2="{cy+118}" stroke="{c}" stroke-opacity=".15"/>')
    out.append(
        f'<g style="transform-origin:{cx}px {cy}px;animation:spin 4s linear infinite">'
        f'<path d="M{cx} {cy}L{cx+110} {cy}A110 110 0 0 0 {cx+110*math.cos(math.radians(-40)):.1f} '
        f'{cy+110*math.sin(math.radians(-40)):.1f}Z" fill="url(#sweep)"/></g>'
    )
    bx, by = cx + 52, cy - 46
    out.append(
        f'<g class="found"><circle cx="{bx}" cy="{by}" r="6" fill="{c}"/>'
        f'<circle cx="{bx}" cy="{by}" r="14" fill="none" stroke="{c}" stroke-opacity=".6"/></g>'
        f'<g class="closed"><rect x="{bx-11}" y="{by-11}" width="22" height="22" fill="{BG}" stroke="{INK}" stroke-width="1.5"/>'
        f'<path d="M{bx-6} {by}l4 4 8-8" fill="none" stroke="{INK}" stroke-width="2"/></g>'
    )
    out.append(f'<text class="m" x="{cx}" y="{cy+142}" font-size="15" fill="{FAINT}" text-anchor="middle">FOUND → CLOSED</text>')
    return "".join(out)


def glyph_agent(cx, cy, c):
    pts = {"PLAN": (cx - 100, cy - 60), "TOOLS": (cx + 100, cy - 60), "EVAL": (cx + 100, cy + 50), "ACT": (cx - 100, cy + 50)}
    out = []
    order = ["PLAN", "TOOLS", "EVAL", "ACT", "PLAN"]
    d = "M" + "L".join(f"{pts[k][0]} {pts[k][1]}" for k in order)
    out.append(f'<path d="{d}" fill="none" stroke="{c}" stroke-opacity=".25" stroke-width="1.5"/>')
    out.append(f'<path d="{d}" fill="none" stroke="{c}" stroke-width="2" stroke-dasharray="14 186" class="flow"/>')
    out.append(f'<path d="M{cx-100} {cy-60}L{cx+100} {cy+50}" stroke="{c}" stroke-opacity=".18" stroke-dasharray="3 5"/>')
    for k, (x, y) in pts.items():
        w = 84
        out.append(
            f'<rect x="{x-w/2}" y="{y-16}" width="{w}" height="32" rx="4" fill="{BG}" stroke="{c}" stroke-opacity=".8"/>'
            f'<text class="mb" x="{x}" y="{y+5.5}" font-size="15" fill="{INK}" text-anchor="middle" letter-spacing="1.5">{k}</text>'
        )
    out.append(
        f'<rect x="{cx-34}" y="{cy-12}" width="68" height="24" rx="12" fill="{c}" fill-opacity=".12" stroke="{c}" stroke-opacity=".5"/>'
        f'<text class="m" x="{cx}" y="{cy+5}" font-size="15" fill="{c}" text-anchor="middle">guard</text>'
    )
    out.append(f'<text class="m" x="{cx}" y="{cy+102}" font-size="15" fill="{FAINT}" text-anchor="middle">AUDIT LOG ▸ ON</text>'.replace("▸", "→"))
    return "".join(out)


def glyph_infra(cx, cy, c):
    layers = ["services   go · py", "containers docker", "cluster    k8s · aws", "state      pg · redis"]
    out = []
    for i, name in enumerate(layers):
        y = cy - 92 + i * 42
        out.append(
            f'<rect x="{cx-130}" y="{y}" width="260" height="32" rx="3" fill="{c}" fill-opacity="{.04 + i*0.03:.2f}" '
            f'stroke="{c}" stroke-opacity="{.3 + i*0.12:.2f}"/>'
            f'<text class="m" x="{cx-116}" y="{y+21}" font-size="15" fill="{INK}" fill-opacity=".85" xml:space="preserve">{esc(name)}</text>'
            f'<circle cx="{cx+114}" cy="{y+16}" r="4" fill="{c}" class="pulse" style="animation-delay:{i*0.4:.1f}s"/>'
        )
    hb = f"M{cx-130} {cy+98}h70l10-20 12 34 10-24 8 10h150"
    out.append(f'<path d="{hb}" fill="none" stroke="{c}" stroke-opacity=".25" stroke-width="1.5"/>')
    out.append(f'<path d="{hb}" fill="none" stroke="{c}" stroke-width="2" stroke-dasharray="40 320" class="beat"/>')
    return "".join(out)


MODULES = [
    dict(idx="01", code="QUANT.ENGINE", key="quant", glyph=glyph_quant,
         title="Markets at the latency edge.",
         lead=["High-frequency microstructure — queue position, order-book imbalance,",
               "adverse selection — turned into engines that price, size and fire",
               "without a human in the loop. Derivatives and risk underneath."],
         tags=["HFT Research", "Microstructure", "Order Books", "Derivatives", "Risk", "MQL5"]),
    dict(idx="02", code="CHAIN.SCAN", key="chain", glyph=glyph_chain,
         title="Chains, read statistically.",
         lead=["On-chain data treated as a market feed — clustering, asset scoring",
               "and signal selection. Every call judged in distributions, not point",
               "estimates: confidence intervals, tail risk, VaR."],
         tags=["On-chain Analytics", "Probability", "FRM", "Tail Risk / VaR", "Portfolio Metrics"]),
    dict(idx="03", code="SEC.KERNEL", key="sec", glyph=glyph_sec,
         title="Found it. Then closed it.",
         lead=["Bug bounty and vulnerability research on one side, threat modeling",
               "and hardened infrastructure on the other. Auth bypass, SSRF, IDOR,",
               "deserialization → RCE — closed at the architecture level."],
         tags=["Bug Bounty", "Vuln Research", "OWASP", "Threat Modeling", "Hardening"]),
    dict(idx="04", code="AGENT.MESH", key="agent", glyph=glyph_agent,
         title="Software with agency.",
         lead=["From one configurable agent to full agentic systems: graph-based",
               "orchestration, retrieval grounded in real data, tool use, eval loops",
               "and the guardrails that make autonomy safe — every decision auditable."],
         tags=["Orchestration", "LangGraph", "RAG", "Eval Loops", "LLM Safety", "React"]),
    dict(idx="05", code="INFRA.BASE", key="infra", glyph=glyph_infra,
         title="The substrate it all runs on.",
         lead=["Go and Python services, containers, Kubernetes, pipelines.",
               "The unglamorous layer that decides whether everything",
               "above it lives."],
         tags=["Go", "Python", "Kubernetes", "AWS", "Docker", "Postgres", "Redis"]),
]


def module(m):
    W, H = 1200, 330
    c = PAL[m["key"]]
    b = [frame(W, H, c)]
    b.append(f'<rect x="0" y="40" width="4" height="{H-80}" fill="{c}"/>')
    b.append(
        f'<text class="mb" x="48" y="62" font-size="16" fill="{c}" letter-spacing="3.5">'
        f'{m["idx"]} <tspan fill="{FAINT}">—</tspan> {m["code"]}</text>'
    )
    b.append(f'<text class="d" x="46" y="118" font-size="38" fill="{INK}" letter-spacing="-.5">{esc(m["title"])}</text>')
    b.append(lines(48, 164, m["lead"], size=17, lh=28))
    b.append(chips(48, 260, m["tags"], c))
    b.append(f'<line x1="790" y1="40" x2="790" y2="{H-40}" stroke="{LINE}"/>')
    b.append(m["glyph"](990, 160, c))
    css = ANIM + """
@keyframes breathe{0%,100%{transform:scaleX(1)}50%{transform:scaleX(.62)}}
@keyframes spin{to{transform:rotate(360deg)}}
.found{animation:found 4s steps(1) infinite}.closed{animation:closed 4s steps(1) infinite}
@keyframes found{0%,45%{opacity:0}46%,79%{opacity:1}80%,100%{opacity:0}}
@keyframes closed{0%,79%{opacity:0}80%,100%{opacity:1}}
.flow{animation:flow 3s linear infinite}@keyframes flow{to{stroke-dashoffset:-200}}
.beat{animation:beat 2.6s linear infinite}@keyframes beat{from{stroke-dashoffset:360}to{stroke-dashoffset:0}}
"""
    svg(f"modules/{m['idx']}-{m['key']}.svg", W, H, "".join(b), css,
        f"{m['idx']} {m['code']} — {m['title']} " + " ".join(m["lead"]))


# ------------------------------------------------------------------------ founder

def founder():
    W, H = 1200, 170
    b = [frame(W, H)]
    b.append(f'<text class="mb" x="600" y="62" font-size="15" fill="{FAINT}" text-anchor="middle" letter-spacing="5">FOUNDER.MODE</text>')
    b.append(
        f'<text class="d" x="600" y="118" font-size="34" fill="{INK}" text-anchor="middle" letter-spacing="-.5">'
        f'I don’t ship modules. <tspan fill="{MIST}">I ship the system.</tspan></text>'
    )
    x0 = 600 - 5 * 26 / 2
    for i, k in enumerate(PAL):
        b.append(f'<rect x="{x0 + i*26:.0f}" y="138" width="16" height="3" fill="{PAL[k]}"/>')
    svg("founder.svg", W, H, "".join(b), "", "FOUNDER.MODE — I don't ship modules. I ship the system.")


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
    b.append(lines(48, 210, [
        "A complete execution terminal rendered natively",
        "inside the MT5 chart. Arm multiple price triggers,",
        "size them against one portfolio-wide risk cap,",
        "split every fill across three take-profits, and let",
        "a retry-safe order pipeline absorb requotes.",
    ], size=17, lh=27))
    b.append(chips(48, 356, ["MQL5", "NATIVE PANEL", "MULTI-TRIGGER", "RISK ENGINE"], c, size=14, h=28))
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


# --------------------------------------------------------------------------- vault

VAULT = [
    ("B/02", "Signal Bridge", "Hardened pipeline carrying signals to execution — retries, resilience, protected processing.", "quant"),
    ("B/03", "On-Chain Signal Engine", "ML-driven selection over on-chain analytics and portfolio metrics, with dynamic allocation.", "chain"),
    ("B/04", "LLM Trade Agent", "Reads natural-language commands, validates intent, executes behind rule-based guards.", "agent"),
    ("B/05", "Venture Intelligence", "Multi-workspace platform scoring ventures through automated evaluation pipelines.", "agent"),
    ("B/06", "Infrastructure Work", "Go and Python services, clusters, pipelines, hardening.", "infra"),
]


def vault():
    W, H = 1200, 440
    b = [frame(W, H)]
    b.append(
        f'<text class="mb" x="48" y="62" font-size="16" fill="{MIST}" letter-spacing="3.5">BUILDS <tspan fill="{FAINT}">—</tspan> SHIPPED &amp; RUNNING</text>'
        f'<text class="m" x="1152" y="62" font-size="15" fill="{FAINT}" text-anchor="end" letter-spacing="2">PRIVATE · SOURCE ON REQUEST</text>'
    )
    cw, ch, gx, gy = 357, 160, 16, 16
    for i in range(6):
        col, row = i % 3, i // 3
        x, y = 48 + col * (cw + gx), 92 + row * (ch + gy)
        if i < len(VAULT):
            code, name, desc, k = VAULT[i]
            c = PAL[k]
            b.append(f'<rect x="{x}" y="{y}" width="{cw}" height="{ch}" rx="6" fill="#080b10" stroke="{LINE}"/>')
            b.append(f'<rect x="{x}" y="{y+18}" width="3" height="26" fill="{c}"/>')
            b.append(f'<text class="mb" x="{x+20}" y="{y+30}" font-size="13" fill="{c}" letter-spacing="2">{code}</text>')
            b.append(f'<text class="d" x="{x+20}" y="{y+60}" font-size="20" fill="{INK}">{esc(name)}</text>')
            b.append(lines(x + 20, y + 92, wrap(desc, 35), size=15, lh=22))
        else:
            b.append(
                f'<rect x="{x}" y="{y}" width="{cw}" height="{ch}" rx="6" fill="none" stroke="{INK}" stroke-opacity=".2" stroke-dasharray="4 5"/>'
                f'<text class="d" x="{x+20}" y="{y+62}" font-size="40" fill="{INK}">+05</text>'
                f'<text class="mb" x="{x+20}" y="{y+94}" font-size="13" fill="{MIST}" letter-spacing="2">FURTHER BUILDS — NOT PUBLIC</text>'
                + lines(x + 20, y + 122, ["Signal infra, on-chain engines,", "agent systems. NDA on request."], size=15, lh=22, fill=FAINT)
            )
    svg("builds/vault.svg", W, H, "".join(b), "",
        "Builds shipped and running: Signal Bridge, On-Chain Signal Engine, LLM Trade Agent, Venture Intelligence, Infrastructure Work, and five more under NDA.")


# --------------------------------------------------------------------------- repos

REPOS = [
    ("airport-twin", "3D digital twin of Mashhad International Airport, driven by a seeded discrete-event simulation.",
     "TypeScript", "#3178c6", ["three.js", "React", "DES"]),
    ("Clueless", "Invisible AI copilot for interviews and meetings on Windows. Offline speech, Claude answers, hidden from screen share.",
     "C#", "#178600", ["Windows", "Speech", "LLM"]),
    ("Iranian_Messenger_Chat_Export", "Privacy-first Chrome extension: exports Bale, Eitaa or Rubika chats as Telegram-style ZIPs. Nothing leaves the browser.",
     "JavaScript", "#f1e05a", ["Chrome", "Privacy"]),
]


def repo(name, desc, lang, lc, tags):
    W, H = 390, 290
    b = [frame(W, H, rx=12)]
    b.append(f'<text class="mb" x="28" y="44" font-size="13" fill="{FAINT}" letter-spacing="2.5">PUBLIC.REPO</text>')
    b.append(f'<text class="m" x="{W-28}" y="44" font-size="15" fill="{MIST}" text-anchor="end">↗</text>')
    size = min(22, (W - 56) / (len(name) * 0.6))
    b.append(f'<text class="mb" x="28" y="84" font-size="{size:.1f}" fill="{INK}">{esc(name)}</text>')
    b.append(lines(28, 120, wrap(desc, 36), size=15, lh=23))
    b.append(f'<line x1="28" y1="{H-62}" x2="{W-28}" y2="{H-62}" stroke="{LINE}"/>')
    b.append(f'<circle cx="34" cy="{H-34}" r="6" fill="{lc}"/>')
    b.append(f'<text class="m" x="48" y="{H-29}" font-size="15" fill="{MIST}">{esc(lang)}</text>')
    b.append(
        f'<text class="m" x="{W-28}" y="{H-29}" font-size="13" fill="{FAINT}" text-anchor="end">{esc(" · ".join(tags))}</text>'
    )
    svg(f"repos/{name.lower()}.svg", W, H, "".join(b), "", f"{name} — {desc}")


# --------------------------------------------------------------------------- stack

def stack():
    W, H = 1200, 470
    b = [frame(W, H)]
    b.append(
        f'<rect x="1" y="1" width="{W-2}" height="48" rx="13" fill="#080b10"/>'
        f'<rect x="1" y="30" width="{W-2}" height="20" fill="#080b10"/>'
        f'<line x1="0" y1="50" x2="{W}" y2="50" stroke="{LINE}"/>'
        f'<rect x="28" y="12" width="210" height="38" fill="{BG}"/>'
        f'<rect x="28" y="12" width="210" height="2" fill="{PAL["infra"]}"/>'
        f'<text class="m" x="46" y="37" font-size="15" fill="{INK}">ah.sys/stack.toml</text>'
        f'<text class="m" x="{W-28}" y="35" font-size="15" fill="{FAINT}" text-anchor="end">UTF-8 · TOML</text>'
    )
    K, S, P, C = PAL["chain"], PAL["quant"], MIST, FAINT  # key, string, punct, comment

    def s(v):
        return f'<tspan fill="{S}">"{esc(v)}"</tspan>'

    def arr(vs):
        return f'<tspan fill="{P}">[</tspan>' + f'<tspan fill="{P}">, </tspan>'.join(s(v) for v in vs) + f'<tspan fill="{P}">]</tspan>'

    def kv(k, v, pad=14):
        return f'<tspan fill="{K}">{k}</tspan><tspan fill="{P}">{" " * (pad - len(k))}= </tspan>{v}'

    def sec(n):
        return f'<tspan fill="{PAL["agent"]}">[{n}]</tspan>'

    src = [
        f'<tspan fill="{C}"># the substrate. what everything above it runs on.</tspan>',
        sec("runtime"),
        kv("languages", arr(["Go", "Python", "TypeScript", "C#", "MQL5"])),
        kv("infra", arr(["Kubernetes", "Docker", "AWS"])),
        kv("state", arr(["Postgres", "Redis"])),
        "",
        sec("agents"),
        kv("orchestration", s("LangGraph")),
        kv("grounding", s("RAG")),
        kv("guards", arr(["eval-loops", "llm-safety", "audit-trail"])),
        "",
        sec("interface"),
        kv("web", arr(["React", "three.js"])) + f'<tspan fill="{C}">   # dashboards that keep decisions auditable</tspan>',
    ]
    for i, row in enumerate(src):
        y = 92 + i * 27
        b.append(f'<text class="m" x="64" y="{y}" font-size="15" fill="{FAINT}" text-anchor="end">{i+1}</text>')
        if row:
            b.append(f'<text class="m" x="88" y="{y}" font-size="16" xml:space="preserve">{row}</text>')
    y = 92 + len(src) * 27
    b.append(f'<text class="m" x="64" y="{y}" font-size="15" fill="{FAINT}" text-anchor="end">{len(src)+1}</text>')
    b.append(f'<rect x="88" y="{y-15}" width="9" height="19" fill="{INK}" class="blink"/>')
    svg("stack.svg", W, H, "".join(b), ANIM,
        "stack.toml — languages: Go, Python, TypeScript, C#, MQL5; infra: Kubernetes, Docker, AWS; state: Postgres, Redis; agents: LangGraph, RAG, eval loops, LLM safety; interface: React, three.js.")


# -------------------------------------------------------------------------- footer

def footer():
    W, H = 1200, 300
    c = PAL["quant"]
    b = [frame(W, H, c)]
    b.append(dot(56, 62, c, 4))
    b.append(f'<circle cx="56" cy="62" r="4" fill="none" stroke="{c}" class="ping"/>')
    b.append(f'<text class="mb" x="74" y="68" font-size="16" fill="{MIST}" letter-spacing="3.5">I/O PORT :: <tspan fill="{c}">LISTENING</tspan></text>')
    b.append(f'<text class="d" x="46" y="150" font-size="64" fill="{INK}" letter-spacing="-1.5">Open a socket.</text>')
    b.append(lines(48, 202, [
        "Building something that needs markets, chains or agents —",
        "or all three at once? The system accepts new connections.",
    ], size=18, lh=29))
    b.append(
        f'<text class="m" x="1152" y="68" font-size="15" fill="{FAINT}" text-anchor="end" letter-spacing="2">ACCEPTING CONNECTIONS</text>'
    )
    svg("io/socket.svg", W, H, "".join(b), ANIM + f"""
.ping{{transform-origin:56px 62px;animation:ping 2s cubic-bezier(0,0,.2,1) infinite}}
@keyframes ping{{from{{transform:scale(1);opacity:1}}to{{transform:scale(4.5);opacity:0}}}}
""", "I/O PORT :: LISTENING — Open a socket. Building something that needs markets, chains or agents?")


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


def statusbar():
    W, H = 1200, 56
    b = [
        f'<line x1="0" y1="1" x2="{W}" y2="1" stroke="{INK}" stroke-opacity=".12"/>'
        f'<text class="m" x="4" y="36" font-size="14" fill="{FAINT}" letter-spacing="2.5">© 2026 ABOLFAZL HOSSEINI · CANADA</text>'
    ]
    x = W - 4
    b.append(f'<text class="mb" x="{x}" y="36" font-size="14" fill="{MIST}" text-anchor="end" letter-spacing="2.5">ALL MODULES NOMINAL</text>')
    for i, k in enumerate(reversed(list(PAL))):
        b.append(f'<rect x="{x - 300 - i*16}" y="26" width="8" height="8" fill="{PAL[k]}" class="pulse" style="animation-delay:{i*.3:.1f}s"/>')
    svg("io/status.svg", W, H, "".join(b), ANIM, "© 2026 Abolfazl Hosseini — all modules nominal.")


# ---------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fonts", required=True, type=Path)
    a = ap.parse_args()
    FONTS.update(d=a.fonts / "unb800.ttf", m=a.fonts / "plex400.ttf", mb=a.fonts / "plex600.ttf")
    print("ah.sys :: compiling assets")
    header()
    for m in MODULES:
        module(m)
    founder()
    tradevision()
    vault()
    for r in REPOS:
        repo(*r)
    stack()
    footer()
    for l in LINKS:
        link_button(*l)
    statusbar()


if __name__ == "__main__":
    main()
