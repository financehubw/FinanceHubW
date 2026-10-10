"""
Renders the slides of one Weekly issue or one Daily edition to JPEGs for Instagram.

    python magazine/render.py 1                   # The Weekly, issue number
    python magazine/render.py daily 2026-10-09    # The Daily, the market day it covers

Weekly  reads magazine/issues/issue-01/slides/01.html ...   writes site/media/magazine/issue-01/01.jpg ...
Daily   reads magazine/daily/2026-10-09/slides/01.html ...  writes site/media/daily/2026-10-09/01.jpg ...
Each slide is a 1080x1350 page. The website serves the JPEGs, which gives Instagram a public
URL to fetch them from.
Fails if any slide's content overflows its 1080x1350 frame, so a clipped slide never ships.

Needs: pip install playwright && playwright install chromium
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
W, H = 1080, 1350

# An element overflows when its content is wider/taller than its own box, or it sticks out
# of the slide. Absolutely positioned full-bleed photos are skipped.
CHECK = """
() => {
  const out = [];
  const root = document.body.firstElementChild;
  for (const el of root.querySelectorAll('*')) {
    if (el.tagName === 'IMG' || el.getAttribute('aria-hidden') === 'true') continue;
    const r = el.getBoundingClientRect();
    const text = (el.textContent || '').trim().slice(0, 40);
    if (r.right > %d + 1 || r.bottom > %d + 1 || r.left < -1) out.push('outside frame: ' + text);
    else if (el.children.length === 0 && el.scrollWidth > el.clientWidth + 2) out.push('too wide: ' + text);
  }
  if (root.scrollHeight > %d + 1) out.push('content taller than the slide by ' + (root.scrollHeight - %d) + 'px');
  return out;
}
""" % (W, H, H, H)


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    if sys.argv[1] == "daily":
        if len(sys.argv) < 3 or not re.fullmatch(r"\d{4}-\d{2}-\d{2}(-sample)?", sys.argv[2]):
            sys.exit("usage: python magazine/render.py daily YYYY-MM-DD")
        src = ROOT / "magazine" / "daily" / sys.argv[2] / "slides"
        dst = ROOT / "site" / "media" / "daily" / sys.argv[2]
    else:
        n = int(sys.argv[1])
        src = ROOT / "magazine" / "issues" / f"issue-{n:02d}" / "slides"
        dst = ROOT / "site" / "media" / "magazine" / f"issue-{n:02d}"
    slides = sorted(src.glob("[0-9][0-9].html"))
    if not slides:
        sys.exit(f"no slides in {src}")
    if len(slides) > 20:
        sys.exit("Instagram allows at most 20 slides in one post")
    dst.mkdir(parents=True, exist_ok=True)
    problems = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        for s in slides:
            page.goto(s.as_uri())
            page.evaluate("document.fonts.ready")
            page.wait_for_load_state("networkidle")
            for issue in page.evaluate(CHECK):
                problems.append(f"{s.name}: {issue}")
            page.screenshot(path=str(dst / f"{s.stem}.jpg"), type="jpeg", quality=90,
                            clip={"x": 0, "y": 0, "width": W, "height": H})
            print(f"rendered {s.name}")
        browser.close()
    if problems:
        print("\nLAYOUT PROBLEMS (fix the slide HTML and render again):", file=sys.stderr)
        for line in problems:
            print("  " + line, file=sys.stderr)
        sys.exit(1)
    print(f"{len(slides)} slides -> {dst.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
