# The Weekly: the FinanceHubW magazine

One issue a week, covering global finance for the Monday to Friday just ended. Each issue is a
20-slide Instagram carousel plus an entry in the website's magazine section.

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
- Photo credits: `magazine/photos/CREDITS.md`. Fonts are under the SIL Open Font License.
