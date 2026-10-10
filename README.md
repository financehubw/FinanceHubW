# FinanceHubW

Automated finance news account for X, plus the FinanceHubW brand kit.

## What the bot does
Every 30 minutes GitHub Actions runs `bot.py`:

1. **Reads 170+ sources covering 49 countries and regions** (`sources.py`): 82 direct feeds from newsrooms, exchanges,
   central banks and regulators (RBI, SEBI, Fed, SEC, ECB, BoE, BoJ, MAS, RBA, Bank of Canada, IMF,
   World Bank, BIS…) plus 51 Google News searches covering India, US, UK, Europe, Japan, China,
   Hong Kong, Singapore, Australia, Canada, Korea, Middle East, Africa, Latin America, crypto,
   commodities and forex. Google News pulls in hundreds of big and small outlets.
2. **Groups the same story** across outlets and ranks by importance, how widely it's covered, and freshness.
3. **Trust filter:** a story is only considered if 2+ independent outlets report it, or it comes
   from an official body, or from a top-tier newsroom. Single-source rumours are dropped.
4. **Claude writes the post** from the combined reporting and picks the region.
5. **AI fact-check (`verify.py`):** Gemini, Groq (Llama), OpenRouter and Grok (whichever keys you add)
   plus Claude each check every number, name and region against the source reports.
   **One FAIL blocks the post**, and at least 2 checkers must PASS (`MIN_PASSES`).
6. **Posts to X** (default 2 per run = up to 96/day, set `POSTS_PER_RUN`, max 6) in one fixed
   layout written so anyone understands it, with jargon explained in brackets:
   ```
   🇮🇳 RBI KEEPS KEY INTEREST RATE AT 6.5%

   📌 India's central bank left its repo rate (the rate banks borrow at) unchanged
   📊 Repo rate: 6.5% (no change)
   💡 Home and car loan EMIs usually stay the same when this rate holds

   📍 India · 📰 Economic Times · ✅ 3 sources
   <link to the original article>
   ```
   Lines are dropped in order of importance if a post would exceed X's limit.
   With X Premium, set repo variable `LONG_POSTS=1` to always keep every line.
7. Skips anything already posted, sponsored content, "stocks to buy" and price-prediction pieces.

It recovers on its own from dead feeds, X duplicate rejections, X rate limits, AI outages and overlapping runs.

## Fact-check keys (free)
| Secret | Where | Cost |
|---|---|---|
| `GEMINI_API_KEY` | aistudio.google.com → Get API key | Free tier |
| `GROQ_API_KEY` | console.groq.com → API Keys | Free tier |
| `OPENROUTER_API_KEY` | openrouter.ai → Keys | Free models |
| `XAI_API_KEY` (Grok) | console.x.ai | Paid, optional |

Add at least two of the free ones. Model names can be changed with repo variables
`GEMINI_MODEL`, `GROQ_MODEL`, `OPENROUTER_MODEL`, `XAI_MODEL` if a provider renames them.

## What makes FinanceHubW different
| Most finance accounts | FinanceHubW |
|---|---|
| Trader shorthand only pros understand | Plain words, jargon explained in brackets |
| Opinions, tips, hype | Facts only, never advice or predictions |
| Rumours from one source | Posted only when confirmed, with a ✅ source count |
| No idea where it came from | 📍 place and 📰 publisher on every post |
| Headlines only | 💡 what it means for ordinary people |
| Never teaches | 📚 Daily finance word, a free course over time |

## Daily schedule (IST)
| Time | Post |
|---|---|
| 8:30 AM | 🌅 Morning brief: top 3 verified stories |
| 9:00 AM | 📺 YouTube promo |
| 1:00 PM | 📚 Finance word of the day (hand-written, `glossary.json`) |
| 7:00 AM | 🌐 Global markets overnight (live prices) |
| 4:00 PM | 📈 India markets at close (live prices) |
| 4:30 PM | 🌆 Market wrap after Indian close |
| Sunday 6:00 PM | 🧾 Weekly transparency report |
| 8:00 PM | 📺 YouTube promo |
| Every 30 min | Verified news posts |

| Sunday 11:00 AM | 🗳️ Weekly poll |

## Runs itself like a newsroom (`newsroom.py`)
- **Natural rhythm:** post count varies by hour with randomness; busier in Indian market hours and
  the US open, silent 1-6 AM IST unless there's breaking news, bursts on big news days.
- **🔄 Updates:** new reporting on a story already posted becomes an UPDATE that quotes the original.
- **⚠️ Corrections:** each run re-checks one recent post against newer, wider reporting. If most
  fact-checkers say it was wrong, a CORRECTION reply goes out automatically.
- **Variety:** rotating brief titles and sign-offs so posts never look stamped.

The account stays labelled "Automated" on X (required by X's rules).

## Trust features
- **📈 Market snapshots** from live price data (`markets.py`): India at close (4:00 PM IST) and
  global overnight (7:00 AM IST). Numbers come from market data, never from AI.
- **🏛️ Official** label when a story comes straight from a central bank, regulator or exchange.
- **🧾 Weekly transparency report** (Sunday 6 PM IST): stories scanned, confirmed, blocked by
  fact-check, posted, and corrections issued.
- **Public Standards & Corrections page** (`docs/`): explains the process and lists every
  correction automatically. Turn it on at Settings → Pages → Branch `main`, folder `/docs`
  (needs a public repo). Move the repo to the FinanceHubW organization first (see Privacy) so the link
  is `https://financehubw.github.io/financehubw/` and never shows a personal username.

## Profile setup (once)
**Bio:** `Verified finance news from 49 countries, explained so anyone gets it. Confirmed by multiple sources, fact-checked, corrected in public. Automated. Not financial advice.`
**Website:** the Standards page link above. **Location:** `🌐 Worldwide`.
**Pinned post:**
```
👋 Welcome to FinanceHubW

📌 Finance news from 49 countries, in plain words
✅ Posted only when confirmed by 2+ sources or official
🔍 Fact-checked before every post
⚠️ Mistakes corrected in public

How we work 👇
<standards page link>
```

## Keep it free
Private repos get 2,000 GitHub Actions minutes/month, which this bot can exceed. Make the repo
public (Settings → General → Change visibility) for unlimited free minutes. Keys stay safe in Secrets.

Briefs only use stories that already passed fact-checking. Add terms to `glossary.json` any time.
YouTube link: set repo variable `YOUTUBE_URL` to change it. Profile tip: put `youtube.com/@FinanceHubW` in the X bio and your X link on YouTube.

## One-time setup
1. **X keys** at developer.x.com → your Project → App → *User authentication settings*: set **Read and Write**. Then *Keys and tokens*: copy API Key, API Secret, and generate Access Token + Secret (generate them *after* setting Read and Write).
2. **Claude key** at console.anthropic.com → API Keys.
3. In this repo: **Settings → Secrets and variables → Actions → New repository secret**, add:
   `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_SECRET`, plus the free `GEMINI_API_KEY`, `GROQ_API_KEY` and `OPENROUTER_API_KEY` (one writes, the other two check). `ANTHROPIC_API_KEY` is optional: when set, Claude writes the posts instead
4. **Test**: Actions → *Post finance update* → Run workflow → tick *Preview only*. Check the log for the post it would have made.
5. Run it once without *Preview only*. From then on it posts every 30 minutes by itself.
6. On X: Settings → Your account → Account information → **Automation** → mark the account as automated (required by X rules).

## Costs
- **X API:** up to 96 posts/day at the default (~2,900/month). Check your tier's monthly post limit on developer.x.com. For fewer posts, set repo variable `POSTS_PER_RUN` to 1, or change the cron in `.github/workflows/post.yml`.
- **Claude API (Haiku):** roughly $3-8/month (writer + one checker call per post).
- **GitHub Actions:** free.

## Controls
- Pause: Actions → *Post finance update* → ⋯ → Disable workflow.
- Sources: `sources.py` (add any RSS feed or Google News search). Topic weighting: `PRIORITY_WORDS` in `bot.py`.
- Failures: GitHub emails you when a run fails.

## Brand kit (`brand/`)
| File | Use |
|---|---|
| `financehubw-profile.png` | Profile picture for X, YouTube and Instagram (1000×1000, safe for the circle crop) |
| `financehubw-x-header.png` | X header (1500×500) |
| `financehubw-youtube-banner.png` | YouTube banner (2560×1440, logo inside the TV/desktop/mobile safe area) |
| `financehubw-logo-horizontal.png` | Transparent logo for thumbnails, videos, watermarks |
| `financehubw-icon.png` | Transparent mark only |

Colours: Navy `#0A1A33` / `#0F2B55` · Growth green `#18C98B` · Gold `#F2B233`. Typeface: Poppins Bold.
`brand/mark.py` regenerates every asset.

## Privacy of the owner
- All commits are authored as "FinanceHubW"; no personal name or email appears in the code or history.
- **Move the repo to a FinanceHubW organization** before making it public: github.com → + → New organization
  (free) named `financehubw`, then this repo → Settings → Transfer ownership. Otherwise the URL shows your username.
- On X: use an email and phone number used nowhere else, don't follow or interact from personal accounts,
  and keep "Verified ID" off. X never shows your API developer details publicly.
- Pay for paid APIs with a card whose name isn't shown publicly (it isn't, on any of these services).

## License
Code: MIT (see `LICENSE`). Posts and the FinanceHubW name, logo and brand assets © FinanceHubW, all rights reserved; see `CONTENT_LICENSE.md`.

## Website (`site/`)

The public site lives in `site/` and is deployed by Vercel (project root directory: `site`).

- `site/tweets.json` is written by `bot.py` every time a post is published. The site's
  "Live from X" calendar reads it, so the archive fills itself.
- `site/magazine.json` holds the weekly magazine. Add a new object to `issues` each week
  (highest `issue` number shows first) and set `"sample": false` once the first real issue is in.

## Weekly magazine

The Weekly is a 20-slide Instagram carousel and website issue published every Saturday. The Daily is a 6-slide carousel for each market day, with its own look. The slides live in `magazine/`, the rendered images in `site/media/magazine/`, and the `Post magazine` workflow posts each new issue to Instagram. See [`magazine/README.md`](magazine/README.md).
