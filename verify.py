"""
Independent fact-check of every post before it goes out.

Each configured AI model gets the draft post plus the original reporting from
every outlet that covered the story, and must answer PASS only if every fact
in the post is supported by those sources. One FAIL blocks the post.

Free models used when their key is set:
  GEMINI_API_KEY      Google Gemini (free tier at aistudio.google.com)
  GROQ_API_KEY        Llama on Groq (free tier at console.groq.com)
  OPENROUTER_API_KEY  free models on OpenRouter (openrouter.ai)
Optional paid:
  XAI_API_KEY         Grok (console.x.ai)
  ANTHROPIC_API_KEY   Claude (paid). Optional: when set it writes the posts and also checks.

The writer is chosen by write(): Claude if its key is set, otherwise the first free
model that answers (Gemini, then Groq, then OpenRouter). The model that wrote a post
never checks that same post.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time

import requests

PROMPT = """You are a strict financial fact-checker. Below is a draft social media post and
the source reporting it is based on.

Answer PASS only if EVERY factual claim in the post (numbers, percentages, names,
countries, directions like rise/fall, dates, who said/did what) is directly
supported by the sources. Answer FAIL if anything is unsupported, exaggerated,
contradicted, attributed to the wrong region/entity, or phrased as advice/prediction.
The place (📍) and source name (📰) must match the sources.
A 💡 line may give a general, widely accepted explanation of what this kind of event
usually means for ordinary people (e.g. higher rates usually make loans costlier);
FAIL it only if that explanation is wrong or predicts a specific outcome.

Reply with JSON only: {{"verdict": "PASS" or "FAIL", "reason": "<one short sentence>"}}

DRAFT POST:
{post}

SOURCES:
{sources}"""


def _parse(text: str) -> tuple[bool, str]:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return False, "unreadable reply"
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        return False, "unreadable reply"
    return str(d.get("verdict", "")).upper() == "PASS", str(d.get("reason", ""))[:200]


def _openai_style(url: str, key: str, model: str, prompt: str, extra: dict | None = None,
                  max_tokens: int = 200) -> str:
    r = requests.post(
        url,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", **(extra or {})},
        json={"model": model, "temperature": 0, "max_tokens": max_tokens,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=45,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _gemini(prompt: str, max_tokens: int = 200) -> str:
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        params={"key": os.environ["GEMINI_API_KEY"]},
        json={"contents": [{"parts": [{"text": prompt}]}],
              "generationConfig": {"temperature": 0, "maxOutputTokens": max_tokens}},
        timeout=45,
    )
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def _groq(prompt: str, max_tokens: int = 200) -> str:
    return _openai_style("https://api.groq.com/openai/v1/chat/completions", os.environ["GROQ_API_KEY"],
                         os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"), prompt,
                         max_tokens=max_tokens)


def _openrouter(prompt: str, max_tokens: int = 200) -> str:
    return _openai_style("https://openrouter.ai/api/v1/chat/completions", os.environ["OPENROUTER_API_KEY"],
                         os.environ.get("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free"), prompt,
                         {"HTTP-Referer": "https://x.com/FinanceHubW", "X-Title": "FinanceHubW"},
                         max_tokens=max_tokens)


def _grok(prompt: str) -> str:
    return _openai_style("https://api.x.ai/v1/chat/completions", os.environ["XAI_API_KEY"],
                         os.environ.get("XAI_MODEL", "grok-3-mini"), prompt)


def _claude(prompt: str, max_tokens: int = 200, model: str = "") -> str:
    import anthropic  # only needed when the paid key is set
    msg = anthropic.Anthropic().messages.create(
        model=model or os.environ.get("CLAUDE_CHECK_MODEL", "claude-sonnet-5"), max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}])
    return msg.content[0].text


CHECKERS = [
    ("Gemini", "GEMINI_API_KEY", _gemini),
    ("Groq Llama", "GROQ_API_KEY", _groq),
    ("OpenRouter", "OPENROUTER_API_KEY", _openrouter),
    ("Grok", "XAI_API_KEY", _grok),
    ("Claude", "ANTHROPIC_API_KEY", _claude),
]


def active_checkers() -> list[str]:
    return [name for name, env, _ in CHECKERS if os.environ.get(env)]


WRITERS = ["Claude", "Gemini", "Groq Llama", "OpenRouter"]


def write(prompt: str) -> tuple[str, str]:
    """Returns (reply text, model name) from the first writer that answers.
    Raises RuntimeError if none is configured or all fail."""
    errors = []
    for name in WRITERS:
        env, fn = next((e, f) for n, e, f in CHECKERS if n == name)
        if not os.environ.get(env):
            continue
        for attempt in range(3):
            try:
                if name == "Claude":
                    text = fn(prompt, 500, os.environ.get("WRITER_MODEL", "claude-haiku-4-5-20251001"))
                else:
                    text = fn(prompt, 500)
                return text, name
            except Exception as e:  # noqa: BLE001  quota, network, bad model name
                if attempt < 2:
                    time.sleep(10 * (attempt + 1))
                    continue
                errors.append(f"{name}: {type(e).__name__}")
    raise RuntimeError("no writer model available (" + "; ".join(errors or ["no keys set"]) + ")")


def fact_check(post: str, sources: list[dict], skip: str = "") -> tuple[bool, list[str]]:
    """Returns (approved, log lines). Approved only if no checker says FAIL
    and at least MIN_PASSES checkers say PASS. A checker that errors is ignored."""
    min_passes = int(os.environ.get("MIN_PASSES", "2"))
    src_text = "\n\n".join(
        f"[{s['publisher']}] {s['title']}\n{s['summary']}" for s in sources[:6])
    prompt = PROMPT.format(post=post, sources=src_text)

    passes, log = 0, []
    for name, env, fn in CHECKERS:
        if not os.environ.get(env) or name == skip:
            continue
        for attempt in range(2):
            try:
                ok, reason = _parse(fn(prompt))
                break
            except Exception as e:  # noqa: BLE001  network, quota, bad model name
                if attempt == 0:
                    time.sleep(3)
                    continue
                ok, reason = None, f"unavailable ({type(e).__name__})"
        log.append(f"{name}: {'PASS' if ok else 'FAIL' if ok is False else 'SKIP'} - {reason}")
        if ok is False:
            return False, log  # one objection is enough
        if ok:
            passes += 1

    if passes < min_passes:
        log.append(f"only {passes} checker(s) passed, need {min_passes}")
        return False, log
    return True, log


if __name__ == "__main__":
    print("active checkers:", ", ".join(active_checkers()) or "none", file=sys.stderr)


def recheck(post: str, sources: list[dict]) -> tuple[int, int, list[str]]:
    """Runs every checker (no early stop). Returns (fails, passes, fail reasons)."""
    src_text = "\n\n".join(f"[{s['publisher']}] {s['title']}\n{s['summary']}" for s in sources[:6])
    prompt = PROMPT.format(post=post, sources=src_text)
    fails, passes, reasons = 0, 0, []
    for name, env, fn in CHECKERS:
        if not os.environ.get(env):
            continue
        try:
            ok, reason = _parse(fn(prompt))
        except Exception:  # noqa: BLE001
            continue
        if ok:
            passes += 1
        else:
            fails += 1
            reasons.append(reason or "details differ")
    return fails, passes, reasons
