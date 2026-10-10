# The Weekly and The Daily: the FinanceHubW magazine

Two editions, built to look different at a glance:

| | The Weekly | The Daily |
|---|---|---|
| When | Every Saturday, covering Monday to Friday | Tuesday to Friday mornings (IST), covering the previous market day |
| Length | 20 slides | 6 slides |
| Look | Dark and colourful, one colour per chapter, tinted photos, Bodoni Moda serif headlines | White pages, black sans-serif (Schibsted Grotesk) headlines, one coral band across the top of every slide, no photos |
| Cover | Full-bleed photo with the issue title | Giant coral date numeral |
| Name on slide | "The Weekly" box on the cover | "The Daily" plus the date in the coral band on every slide |
| Job | One story that ties the week together | What happened today, in a minute |

Saturday has no Daily: Friday's session is covered by The Weekly.

The sections below describe The Weekly. The Daily follows the same steps with these paths:
slides in `magazine/daily/YYYY-MM-DD/slides/01.html` ... `06.html` (the date is the market day
covered), `python magazine/render.py daily YYYY-MM-DD`, an entry in `site/daily.json`
(date, label, title, summary, `"slides": 6`) and an entry in `social/daily_queue.json`
(date, title, caption). Daily slide order: cover, the story, the scoreboard, mover of the day,
also today, up next. Never restyle one edition to look like the other.

## How an issue goes out

1. Write the slides as `magazine/issues/issue-NN/slides/01.html` ... `20.html`. Each is a plain
   1080x1350 page that links `../../../fonts/fonts.css` and uses photos from `../../../photos/`.
   Copy the previous issue's slides as the starting point.
2. Render them: `python magazine/render.py NN`. This writes `site/media/magazine/issue-NN/01.jpg`
   and so on, and fails if any slide's content overflows its frame.
3. Add the issue to `site/magazine.json` (title, week, summary, sections, `"slides": 20`).
4. Add the issue to `social/magazine_queue.json` with its Instagram caption (sources, photo
   credits, "Information only, not investment advice.") and a `short` list of ten slide numbers
   that still tell the story if Instagram only accepts ten.
5. Commit and push to `main`. Vercel redeploys the site, and the "Post magazine" workflow waits
   for the slides to be live and posts the carousel to Instagram.

Posting needs the `META_TOKEN` and `IG_USER_ID` secrets (the same ones the Shorts workflow uses).
Without them the workflow does nothing. Set the repo variable `SOCIAL_DRY_RUN=1` to pause posting.

## Rules

- Global finance only. Every figure comes from a named source; if sources disagree, leave it out.
- Information only: no recommendations to buy or sell anything.
- Look: Bodoni Moda headlines, Schibsted Grotesk body, near-black `#141311`, white, coral
  `#FA5B3C`, and one colour per chapter (blue `#2F5BFF`, violet `#7C3AED`, green `#00C48C`,
  pink `#FF3D8B`, gold `#FABC4D`). Plus and minus signs next to big Bodoni numbers are set in
  Schibsted Grotesk, because Bodoni's own signs are too thin to see.
- Every slide but the cover ends with a teaser for the next slide and a progress bar.
- Copyright: the cover and the last slide carry "© <year> FinanceHubW", and the caption ends with
  "© <year> FinanceHubW. All rights reserved. Share with credit to @financehubw." The terms are in
  `CONTENT_LICENSE.md`.
- Photo credits: `magazine/photos/CREDITS.md`. Fonts are under the SIL Open Font License.
