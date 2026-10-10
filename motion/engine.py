"""FinanceHub in Motion: brand motion-graphics engine.

Renders 1080x1920 30fps Shorts from a JSON-like scene list.
Each frame is an SVG -> PNG (cairosvg) piped into ffmpeg.
"""
import json, math, subprocess, sys
import cairosvg
from PIL import ImageFont
_FC={}
def tw(text,size,path='/root/.fonts/fraunces-latin-900-normal.ttf'):
    k=(path,size)
    if k not in _FC: _FC[k]=ImageFont.truetype(path,size)
    return _FC[k].getlength(text)

W, H, FPS = 1080, 1920, 30
INK, PAPER, RED, MUTE = "#0F0E0C", "#F3ECDD", "#E0482B", "#8C857A"
SERIF, SANS = "Fraunces", "Archivo SemiBold"


# ---------- easing ----------
def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def ease_out(t): t = clamp(t); return 1 - (1 - t) ** 3
def ease_in_out(t): t = clamp(t); return 4*t*t*t if t < .5 else 1 - (-2*t + 2) ** 3 / 2
def back_out(t):
    t = clamp(t); c1 = 1.70158; c3 = c1 + 1
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2
def seg(t, a, b): return clamp((t - a) / (b - a)) if b > a else 1.0


def esc(s): return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def money(v, dec=0):
    if dec: return f"${v:,.{dec}f}"
    return f"${v:,.0f}"


# ---------- mark ----------
def mark(x, y, s, bg=INK):
    return f'''<g transform="translate({x},{y}) scale({s})">
<path d="M116 440 V236 A140 140 0 0 1 396 236 V440 Z" fill="{PAPER}"/>
<clipPath id="mk"><path d="M156 440 V240 A100 100 0 0 1 356 240 V440 Z"/></clipPath>
<g clip-path="url(#mk)"><rect x="100" y="100" width="320" height="400" fill="{bg}"/>
<circle cx="256" cy="360" r="78" fill="{RED}"/>
<g stroke="{bg}" stroke-width="7"><line x1="160" y1="340" x2="360" y2="340"/><line x1="160" y1="376" x2="360" y2="376"/><line x1="160" y1="412" x2="360" y2="412"/></g></g>
<rect x="84" y="440" width="344" height="22" fill="{PAPER}"/></g>'''


def chrome(t_global, total):
    """Persistent brand chrome: top wordmark + bottom progress bar."""
    p = clamp(t_global / total)
    return (f'<text x="72" y="130" font-family="{SERIF}" font-weight="900" font-size="44" fill="{PAPER}">'
            f'Finance<tspan fill="{RED}">Hub</tspan></text>'
            f'<rect x="72" y="{H-90}" width="{W-144}" height="6" fill="{PAPER}" opacity=".15"/>'
            f'<rect x="72" y="{H-90}" width="{(W-144)*p:.1f}" height="6" fill="{RED}"/>')


def words_reveal(text, x, y, size, t, color=PAPER, weight=900, family=SERIF, anchor="middle",
                 per=0.07, dur=0.35, highlight=(), line_h=1.12, max_chars=16):
    """Kinetic word-by-word reveal with rise + fade; wraps lines."""
    words = text.split()
    lines, cur = [], []
    for w in words:
        if len(" ".join(cur + [w])) > max_chars and cur: lines.append(cur); cur = [w]
        else: cur.append(w)
    if cur: lines.append(cur)
    out, i = [], 0
    y0 = y - (len(lines) - 1) * size * line_h / 2
    sp = tw(" ", size)
    for li, line in enumerate(lines):
        widths = [tw(w, size) for w in line]
        total = sum(widths) + sp * (len(line) - 1)
        cx = x - total / 2 if anchor == "middle" else x
        ly = y0 + li * size * line_h
        for w, wd in zip(line, widths):
            k = ease_out(seg(t, i * per, i * per + dur))
            col = RED if w.strip(".,!?") in [h.strip(".,!?") for h in highlight] else color
            out.append(f'<text x="{cx:.1f}" y="{ly + (1-k)*size*0.4:.1f}" font-family="{family}" font-weight="{weight}" '
                       f'font-size="{size}" fill="{col}" fill-opacity="{k:.3f}">{esc(w)}</text>')
            cx += wd + sp
            i += 1
    return "".join(out)


def label(text, x, y, size, t, color=MUTE, anchor="middle", delay=0.0):
    k = ease_out(seg(t, delay, delay + 0.4))
    return (f'<text x="{x}" y="{y + (1-k)*20:.1f}" text-anchor="{anchor}" font-family="{SANS}" font-weight="800" '
            f'font-size="{size}" letter-spacing="{size/4:.1f}" fill="{color}" fill-opacity="{k:.3f}">{esc(text.upper())}</text>')


# ---------- scenes ----------
def sc_kicker(s, t, d):
    body = words_reveal(s["text"], W/2, H/2 - 40, s.get("size", 118), t, highlight=s.get("hl", []),
                        max_chars=s.get("wrap", 14))
    if s.get("sub"): body += label(s["sub"], W/2, H/2 + 260, 34, t, delay=0.6)
    return body


def sc_counter(s, t, d):
    k = ease_in_out(seg(t, 0.25, d - 0.6))
    v = s["from"] + (s["to"] - s["from"]) * k
    txt = s.get("prefix", "$") + f"{v:,.{s.get('dec',0)}f}" + s.get("suffix", "")
    pop = back_out(seg(t, d - 0.6, d - 0.3)) if k >= 1 else 1
    size = s.get("size", 170) * (1 + 0.06 * (1 - abs(pop - 1)) * (1 if k >= 1 else 0))
    col = RED if k >= 1 and s.get("land_red", True) else PAPER
    out = label(s.get("top", ""), W/2, H/2 - 230, 38, t)
    out += (f'<text x="{W/2}" y="{H/2 + 50}" text-anchor="middle" font-family="{SERIF}" font-weight="900" '
            f'font-size="{size:.0f}" fill="{col}" letter-spacing="-4">{esc(txt)}</text>')
    out += label(s.get("bottom", ""), W/2, H/2 + 200, 34, t, delay=0.3)
    return out


def sc_chart(s, t, d):
    """Growth curves drawing themselves, with end-value tags."""
    x0, x1, y0, y1 = 110, W - 110, 1380, 520
    ymax = s["ymax"]
    out = label(s.get("title", ""), W/2, 420, 36, t)
    # axis
    out += f'<line x1="{x0}" y1="{y0}" x2="{x1}" y2="{y0}" stroke="{PAPER}" stroke-opacity=".25" stroke-width="3"/>'
    for i, xl in enumerate(s.get("xlabels", [])):
        xx = x0 + (x1 - x0) * i / (len(s["xlabels"]) - 1)
        out += f'<text x="{xx}" y="{y0+60}" text-anchor="middle" font-family="{SANS}" font-weight="800" font-size="30" fill="{MUTE}">{esc(xl)}</text>'
    for si, ser in enumerate(s["series"]):
        start, stop = ser.get("start", 0.2 + si * 0.9), ser.get("stop", d - 1.2)
        k = ease_in_out(seg(t, start, stop))
        pts = ser["points"]  # list of (xfrac, value)
        n = max(2, int(len(pts) * k))
        path = []
        for j, (xf, val) in enumerate(pts[:n]):
            px = x0 + (x1 - x0) * xf; py = y0 - (y0 - y1) * (val / ymax)
            path.append(f'{"M" if j == 0 else "L"}{px:.1f} {py:.1f}')
        col = ser.get("color", RED)
        out += f'<path d="{" ".join(path)}" fill="none" stroke="{col}" stroke-width="12" stroke-linecap="round" stroke-linejoin="round"/>'
        if n:
            xf, val = pts[n - 1]; px = x0 + (x1 - x0) * xf; py = y0 - (y0 - y1) * (val / ymax)
            out += f'<circle cx="{px:.1f}" cy="{py:.1f}" r="16" fill="{col}"/>'
            tag = f'{ser["name"]}  {money(val)}'
            ty = 560 + si * 64
            out += (f'<text x="{x0}" y="{ty:.1f}" text-anchor="start" font-family="{SANS}" font-weight="800" '
                    f'font-size="38" fill="{col}">{esc(tag)}</text>')
    if s.get("note"):
        out += words_reveal(s["note"], W/2, 1620, 64, max(0, t - (d - 2.2)), highlight=s.get("hl", []), max_chars=22)
    return out


def sc_tiles(s, t, d):
    """Money doubling: tile count doubles each step."""
    steps = s["steps"]  # list of (label_years, amount)
    per = (d - 0.8) / len(steps)
    i = min(len(steps) - 1, int(t / per))
    k = back_out(seg(t - i * per, 0, 0.45))
    tiles = 2 ** i
    cols = 1 if tiles == 1 else min(8, int(math.ceil(math.sqrt(tiles * 2))))
    rows = math.ceil(tiles / cols)
    size = min(760 / cols, 640 / rows) * 0.82
    gap = size * 0.18
    gw, gh = cols * size + (cols - 1) * gap, rows * size + (rows - 1) * gap
    ox, oy = (W - gw) / 2, 1080 - gh / 2
    out = ""
    for n in range(tiles):
        r_, c_ = divmod(n, cols)
        new = n >= tiles // 2 and i > 0
        sc = k if new else 1
        cx, cy = ox + c_ * (size + gap) + size / 2, oy + r_ * (size + gap) + size / 2
        s2 = size * sc
        out += f'<rect x="{cx-s2/2:.1f}" y="{cy-s2/2:.1f}" width="{s2:.1f}" height="{s2:.1f}" rx="{s2*0.14:.1f}" fill="{RED if new else PAPER}"/>'
    yrs, amt = steps[i]
    out += label(s.get("title", ""), W/2, 420, 36, t)
    out += (f'<text x="{W/2}" y="{620}" text-anchor="middle" font-family="{SERIF}" font-weight="900" font-size="150" '
            f'fill="{PAPER}" letter-spacing="-4">{esc(money(amt))}</text>')
    out += label(yrs, W/2, 1560, 40, t - i * per, color=RED)
    return out


def sc_shrink(s, t, d):
    """A bill shrinking while a year counter runs."""
    k = ease_in_out(seg(t, 0.4, d - 0.8))
    yr_f = s["y0"] + (s["y1"] - s["y0"]) * k
    yr = int(yr_f)
    if s.get("table"):
        # real data points [[year, value], ...]: every on-screen pair (year, value) is true,
        # not a straight line between the two ends
        tab = s["table"]
        val = tab[-1][1]
        for (ya, va), (yb, vb) in zip(tab, tab[1:]):
            if ya <= yr <= yb:                       # value for the year actually shown
                val = va + (vb - va) * ((yr - ya) / (yb - ya) if yb > ya else 1)
                break
    else:
        val = s["v0"] + (s["v1"] - s["v0"]) * k
    scale = math.sqrt(val / s["v0"])
    bw, bh = 700 * scale, 320 * scale
    cx, cy = W / 2, 1020
    out = label(s.get("title", ""), W/2, 420, 36, t)
    out += (f'<text x="{W/2}" y="600" text-anchor="middle" font-family="{SERIF}" font-weight="900" font-size="120" '
            f'fill="{MUTE}">{yr}</text>')
    out += (f'<rect x="{cx-bw/2:.1f}" y="{cy-bh/2:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="{18*scale:.1f}" '
            f'fill="none" stroke="{PAPER}" stroke-width="{max(3, 8*scale):.1f}"/>'
            f'<rect x="{cx-bw/2+24*scale:.1f}" y="{cy-bh/2+24*scale:.1f}" width="{bw-48*scale:.1f}" height="{bh-48*scale:.1f}" '
            f'rx="{10*scale:.1f}" fill="none" stroke="{PAPER}" stroke-opacity=".35" stroke-width="{max(2,3*scale):.1f}"/>'
            f'<text x="{cx}" y="{cy + 50*scale:.1f}" text-anchor="middle" font-family="{SERIF}" font-weight="900" '
            f'font-size="{150*scale:.0f}" fill="{PAPER}">{esc(s.get("face","$1"))}</text>')
    col = RED if k > 0.98 else PAPER
    out += (f'<text x="{W/2}" y="1420" text-anchor="middle" font-family="{SERIF}" font-weight="900" font-size="130" '
            f'fill="{col}" letter-spacing="-3">{esc(s.get("fmt","{}").format(money(val, s.get("dec",2))))}</text>')
    out += label(s.get("bottom", ""), W/2, 1530, 32, t, delay=0.5)
    return out


def sc_end(s, t, d):
    k = back_out(seg(t, 0, 0.6))
    out = mark(W/2 - 180 * k, 560, 0.7 * k) if k > 0.01 else ""
    out += words_reveal(s.get("text", "Where money makes sense."), W/2, 1140, 72, t - 0.3, max_chars=26)
    out += label(s.get("cta", "Follow for more"), W/2, 1300, 36, t, color=RED, delay=0.8)
    out += label("Education, not financial advice", W/2, 1700, 24, t, delay=1.0)
    return out


SCENES = dict(kicker=sc_kicker, counter=sc_counter, chart=sc_chart, tiles=sc_tiles, shrink=sc_shrink, end=sc_end)


def frame_svg(scenes, fi, total):
    tg = fi / FPS
    acc = 0.0
    for s in scenes:
        d = s["dur"]
        if tg < acc + d or s is scenes[-1]:
            t = tg - acc
            # scene transition: quick wipe-in from red bar
            wipe = 1 - ease_out(seg(t, 0, 0.25))
            body = SCENES[s["t"]](s, t, d)
            op = 1 - ease_out(seg(t, d - 0.2, d)) if s is not scenes[-1] else 1
            svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}">'
                   f'<rect width="{W}" height="{H}" fill="{INK}"/>'
                   f'<g opacity="{op:.3f}">{body}</g>{chrome(tg, total)}'
                   f'<rect x="0" y="0" width="{W*wipe:.1f}" height="{H}" fill="{RED}"/></svg>')
            return svg
        acc += d


def render(spec_path, out_path):
    spec = json.load(open(spec_path))
    scenes = spec["scenes"]
    total = sum(s["dur"] for s in scenes)
    nframes = int(total * FPS)
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(FPS), "-i", "-",
         "-f", "lavfi", "-t", f"{total}", "-i", "anullsrc=r=48000:cl=stereo",
         "-vf", "noise=alls=5:allf=t,vignette=PI/6,format=yuv420p",
         "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-c:a", "aac", "-shortest",
         "-movflags", "+faststart", out_path], stdin=subprocess.PIPE)
    for fi in range(nframes):
        ff.stdin.write(cairosvg.svg2png(bytestring=frame_svg(scenes, fi, total).encode(), output_width=W, output_height=H))
    ff.stdin.close(); ff.wait()
    return total


def still(spec_path, sec, out_png):
    spec = json.load(open(spec_path)); scenes = spec["scenes"]; total = sum(s["dur"] for s in scenes)
    cairosvg.svg2png(bytestring=frame_svg(scenes, int(sec * FPS), total).encode(), write_to=out_png, output_width=540)


if __name__ == "__main__":
    if sys.argv[1] == "still":
        still(sys.argv[2], float(sys.argv[3]), sys.argv[4])
    else:
        print(render(sys.argv[1], sys.argv[2]))
