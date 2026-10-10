"""
Newsroom behaviours that make the account feel alive, all fully automatic:

- rhythm:      how many posts this run, based on the hour (IST), with randomness,
               quiet nights and bursts when big news breaks
- updates:     a new report on a story already posted becomes a "🔄 UPDATE"
               quote-post of the original instead of a duplicate
- corrections: recent posts are re-checked against newer reporting; if a
               checker finds an error, a "⚠️ CORRECTION" reply goes out
- polls:       a neutral weekly poll on Sundays
- variety:     rotating titles/sign-offs so posts don't look stamped
"""
from __future__ import annotations

import random
import time

# ------------------------------------------------------------------ rhythm
QUIET_HOURS = range(1, 6)          # 1:00-5:59 AM IST: only breaking news
PEAK_HOURS = set(range(8, 17)) | set(range(19, 24))  # India session + US open
BREAKING_SCORE = 14                # score needed to post during quiet hours


def ist_now() -> time.struct_time:
    return time.gmtime(time.time() + 5.5 * 3600)


def posts_this_run(base: int, top_score: float) -> int:
    h = ist_now().tm_hour
    if h in QUIET_HOURS:
        return 1 if top_score >= BREAKING_SCORE else 0
    if top_score >= BREAKING_SCORE:           # big news day: burst
        return base + 1
    if h in PEAK_HOURS:
        return random.choice([base - 1, base, base, base + 1]) if base > 1 else base
    return random.choice([0, 1, 1, base]) if base > 0 else 0


# ------------------------------------------------------------------ updates
def match_recent(kw: set[str], recent: list[dict], within_h: float = 24) -> dict | None:
    cutoff = time.time() - within_h * 3600
    for r in reversed(recent):
        if r.get("ts", 0) < cutoff or not r.get("kw") or not r.get("tweet_id"):
            continue
        prev = set(r["kw"])
        shared = kw & prev
        if len(shared) >= 3 and len(shared) / min(len(kw), len(prev)) >= 0.5:
            return r
    return None


# ------------------------------------------------------------------ polls
POLLS = [
    ("Where are you putting most of your savings this month?", ["Stocks / MFs", "Gold", "FD / Savings", "Crypto"]),
    ("Which will matter most for markets this week?", ["Interest rates", "Inflation data", "Company results", "Global news"]),
    ("How do you mostly invest?", ["SIP every month", "Lump sum", "Trading", "Not investing yet"]),
    ("What's your biggest money goal right now?", ["Emergency fund", "Buy a home", "Retirement", "Pay off loans"]),
    ("Which asset do you understand the least?", ["Stocks", "Bonds", "Crypto", "Mutual funds"]),
    ("Where do you get your finance news first?", ["X", "YouTube", "News apps", "Friends / family"]),
    ("How often do you check your investments?", ["Daily", "Weekly", "Monthly", "Rarely"]),
    ("Which topic should we explain more?", ["Taxes", "Stock market", "Crypto", "Economy"]),
]


def poll_due(state: dict) -> tuple[str, list[str]] | None:
    t = ist_now()
    week = time.strftime("%Y-%W", t)
    if t.tm_wday == 6 and t.tm_hour == 11 and state.get("last_poll") != week:  # Sunday 11 AM IST
        state["last_poll"] = week
        i = state.get("poll_index", 0) % len(POLLS)
        state["poll_index"] = i + 1
        q, opts = POLLS[i]
        return f"🗳️ SUNDAY POLL\n\n{q}\n\nVote below 👇", opts
    return None


# ------------------------------------------------------------------ variety
BRIEF_TITLES = [
    "🌅 MORNING BRIEF | 3 things to know today",
    "☕ Before markets open: today's 3 big stories",
    "🌅 Good morning! Here's what moved overnight",
    "📰 Your 30-second morning catch-up",
]
WRAP_TITLES = [
    "🌆 MARKET WRAP | Today's top stories",
    "🔔 Closing bell: what mattered today",
    "🌆 Day in 30 seconds: the stories that moved money",
    "📊 End-of-day recap",
]
SIGNOFFS = [
    "Verified finance news, explained simply. Follow @{h}",
    "Confirmed by multiple sources, explained for everyone. @{h}",
    "No hype, no tips. Just the facts, simply. @{h}",
    "Follow @{h} to understand money, every day",
]


def pick(options: list[str], state: dict, key: str) -> str:
    """Rotates through options without repeating the last one."""
    last = state.get(key)
    choices = [o for o in options if o != last] or options
    choice = random.choice(choices)
    state[key] = choice
    return choice
