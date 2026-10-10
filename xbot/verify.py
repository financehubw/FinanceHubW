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


def _parse(text: str) -> tuple[bool | None, str]:
    """(True, reason) for PASS, (False, reason) for FAIL, (None, snippet) if the reply
    can't be read. An unreadable reply is not an objection, so it never blocks a post."""
    text = text or ""
    # reasoning models sometimes think out loud first; only the final answer matters
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    for m in reversed(list(re.finditer(r"\{[^{}]*\}", text, re.S))):
        try:
            d = json.loads(m.group(0))
        except json.JSONDecodeError:
            continue
        verdict = str(d.get("verdict", "")).strip().upper()
        if verdict in ("PASS", "FAIL"):
            return verdict == "PASS", str(d.get("reason", ""))[:200]
    words = re.findall(r"\b(PASS|FAIL)\b", text.upper())
    if words:
        return words[-1] == "PASS", "(plain-text verdict)"
    return None, "unreadable reply: " + re.sub(r"\s+", " ", text)[:80]


_working: dict[str, str] = {}   # provider -> model that answered, reused for the rest of the run


def _detail(e: Exception) -> str:
    """Short, key-free reason for a failed call (HTTP status + start of the error body)."""
    r = getattr(e, "response", None)
    if r is not None:
        body = re.sub(r"\s+", " ", (r.text or ""))[:140]
        return f"HTTP {r.status_code}: {body}"
    return type(e).__name__


def _models(env: str, defaults: list[str]) -> list[str]:
    chosen = os.environ.get(env, "").strip()
    return [chosen] if chosen else defaults


_exhausted: set[str] = set()


def _try_models(provider: str, models: list[str], call) -> str:
    """Tries each model in order. A busy model (429) gets one retry after a pause;
    a missing/blocked model or an empty reply moves on to the next model."""
    if provider in _exhausted:
        raise RuntimeError(f"{provider}: daily free limit reached")
    if provider in _working:
        models = [_working[provider]] + [m for m in models if m != _working[provider]]
    last: Exception | None = None
    for model in models:
        for attempt in range(2):
            try:
                text = call(model)
            except requests.HTTPError as e:
                last = e
                code = e.response.status_code if e.response is not None else 0
                if code == 429 and "per-day" in (e.response.text if e.response is not None else ""):
                    _exhausted.add(provider)   # daily allowance used up: stop asking this provider today
                    raise
                if code == 429 and attempt == 0:
                    time.sleep(20)      # free tiers limit requests per minute; wait and retry once
                    continue
                if code in (400, 403, 404, 429, 500, 502, 503):
                    break               # this model is unavailable: try the next one
                raise
            if text and text.strip():
                _working[provider] = model
                return text
            last = RuntimeError(f"{model} returned an empty reply")
            break                       # empty reply: try the next model
    raise last or RuntimeError(f"{provider}: no model configured")


def _openai_style(url: str, key: str, model: str, prompt: str, extra: dict | None = None,
                  max_tokens: int = 200) -> str:
    r = requests.post(
        url,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", **(extra or {})},
        json={"model": model, "temperature": 0, "max_tokens": max_tokens,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"] or ""


GEMINI_MODELS = ["gemini-3.5-flash-lite", "gemini-3.6-flash", "gemini-3.1-flash-lite", "gemini-2.5-flash"]
GROQ_MODELS = ["llama-3.3-70b-versatile"]
GROQ_OSS_MODELS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]
OPENROUTER_PREFER = ("llama-3.3-70b", "gpt-oss-120b", "deepseek", "qwen", "gemma", "mistral", "llama")


def _gemini(prompt: str, max_tokens: int = 200) -> str:
    def call(model):
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},   # header, so the key never appears in logs
            json={"contents": [{"parts": [{"text": prompt}]}],
                  "generationConfig": {"temperature": 0, "maxOutputTokens": max_tokens}},
            timeout=60,
        )
        r.raise_for_status()
        parts = r.json()["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts)
    return _try_models("Gemini", _models("GEMINI_MODEL", GEMINI_MODELS), call)


def _groq(prompt: str, max_tokens: int = 200) -> str:
    return _try_models("Groq", _models("GROQ_MODEL", GROQ_MODELS), lambda m: _openai_style(
        "https://api.groq.com/openai/v1/chat/completions", os.environ["GROQ_API_KEY"], m, prompt,
        max_tokens=max_tokens))


def _groq_oss(prompt: str, max_tokens: int = 200) -> str:
    """A second, independent checker on the same free Groq key (a different model family).
    It reasons before answering, so it gets extra room."""
    return _try_models("Groq OSS", _models("GROQ_OSS_MODEL", GROQ_OSS_MODELS), lambda m: _openai_style(
        "https://api.groq.com/openai/v1/chat/completions", os.environ["GROQ_API_KEY"], m, prompt,
        max_tokens=max(max_tokens, 1200)))


def _openrouter_free_models() -> list[str]:
    """Free models change often, so ask OpenRouter which ones exist right now."""
    try:
        r = requests.get("https://openrouter.ai/api/v1/models", timeout=30)
        r.raise_for_status()
        ids = [m["id"] for m in r.json().get("data", []) if str(m.get("id", "")).endswith(":free")]
    except Exception:  # noqa: BLE001
        return []
    ranked = sorted(ids, key=lambda i: next((n for n, k in enumerate(OPENROUTER_PREFER) if k in i),
                                            len(OPENROUTER_PREFER)))
    return ranked[:5]


def _openrouter(prompt: str, max_tokens: int = 200) -> str:
    models = _models("OPENROUTER_MODEL", []) or _openrouter_free_models()
    return _try_models("OpenRouter", models, lambda m: _openai_style(
        "https://openrouter.ai/api/v1/chat/completions", os.environ["OPENROUTER_API_KEY"], m, prompt,
        {"HTTP-Referer": "https://financehubw-site.vercel.app", "X-Title": "FinanceHubW"},
        max_tokens=max(max_tokens, 1200)))


def _grok(prompt: str) -> str:
    return _openai_style("https://api.x.ai/v1/chat/completions", os.environ["XAI_API_KEY"],
                         os.environ.get("XAI_MODEL", "grok-3-mini"), prompt)


def _claude(prompt: str, max_tokens: int = 200, model: str = "") -> str:
    import anthropic  # only needed when the paid key is set
    msg = anthropic.Anthropic().messages.create(
        model=model or os.environ.get("CLAUDE_CHECK_MODEL", "claude-sonnet-5"), max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}])
    return msg.content[0].text


def _oa(provider: str, url: str, key_env: str, models: list[str], min_tokens: int = 0):
    """Makes a checker for any OpenAI-style free endpoint. Each one has its own free allowance."""
    def fn(prompt: str, max_tokens: int = 200) -> str:
        return _try_models(provider, _models(provider.upper().replace(" ", "_").replace("-", "_") + "_MODEL", models),
                           lambda m: _openai_style(url, os.environ[key_env], m, prompt,
                                                   max_tokens=max(max_tokens, min_tokens)))
    return fn


GROQ = "https://api.groq.com/openai/v1/chat/completions"
GITHUB = "https://models.github.ai/inference/chat/completions"     # free with the Actions GITHUB_TOKEN
_groq_alt = _oa("Groq Qwen", GROQ, "GROQ_API_KEY", ["qwen/qwen3-32b"], 1200)

# Every free checker. Each has its own separate free limits, so one running out never blocks posting.
# The ones without a key set are skipped automatically.
CHECKERS = [
    ("Gemini", "GEMINI_API_KEY", _gemini),
    ("Groq GPT-OSS", "GROQ_API_KEY", _groq_oss),
    ("Groq Qwen", "GROQ_API_KEY", _groq_alt),
    ("Groq Kimi", "GROQ_API_KEY", _oa("Groq Kimi", GROQ, "GROQ_API_KEY", ["moonshotai/kimi-k2-instruct-0905", "moonshotai/kimi-k2-instruct"])),
    ("Groq Llama", "GROQ_API_KEY", _oa("Groq Llama", GROQ, "GROQ_API_KEY", ["meta-llama/llama-4-maverick-17b-128e-instruct", "meta-llama/llama-4-scout-17b-16e-instruct", "llama-3.3-70b-versatile"])),
    ("GitHub GPT", "GITHUB_TOKEN", _oa("GitHub GPT", GITHUB, "GITHUB_TOKEN", ["openai/gpt-4.1-mini", "openai/gpt-4o-mini", "openai/gpt-4.1-nano"])),
    ("GitHub Llama", "GITHUB_TOKEN", _oa("GitHub Llama", GITHUB, "GITHUB_TOKEN", ["meta/Llama-3.3-70B-Instruct", "meta/Meta-Llama-3.1-405B-Instruct"])),
    ("GitHub Mistral", "GITHUB_TOKEN", _oa("GitHub Mistral", GITHUB, "GITHUB_TOKEN", ["mistral-ai/mistral-medium-2505", "mistral-ai/mistral-small-2503"])),
    ("Cerebras", "CEREBRAS_API_KEY", _oa("Cerebras", "https://api.cerebras.ai/v1/chat/completions", "CEREBRAS_API_KEY", ["gpt-oss-120b", "llama-3.3-70b", "qwen-3-32b"], 1200)),
    ("Mistral", "MISTRAL_API_KEY", _oa("Mistral", "https://api.mistral.ai/v1/chat/completions", "MISTRAL_API_KEY", ["mistral-small-latest", "open-mistral-nemo"])),
    ("OpenRouter", "OPENROUTER_API_KEY", _openrouter),
    ("Grok", "XAI_API_KEY", _grok),
    ("Claude", "ANTHROPIC_API_KEY", _claude),
]


def active_checkers() -> list[str]:
    return [name for name, env, _ in CHECKERS if os.environ.get(env)]


WRITERS = ["Claude", "Gemini", "Groq GPT-OSS", "OpenRouter"]


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
                errors.append(f"{name}: {_detail(e)}")
    raise RuntimeError("no writer model available (" + "; ".join(errors or ["no keys set"]) + ")")


def fact_check(post: str, sources: list[dict], skip: str = "", limit: int = 6, template: str = "") -> tuple[bool, list[str]]:
    """Returns (approved, log lines). Approved only if no checker says FAIL
    and at least MIN_PASSES checkers say PASS. A checker that errors is ignored."""
    min_passes = int(os.environ.get("MIN_PASSES") or 2)
    src_text = "\n\n".join(
        f"[{s['publisher']}] {s['title']}\n{s['summary']}" for s in sources[:limit])
    prompt = (template or PROMPT).format(post=post, sources=src_text)

    passes, log = 0, []
    for name, env, fn in CHECKERS:
        if not os.environ.get(env) or name == skip:
            continue
        for attempt in range(2):
            try:
                ok, reason = _parse(fn(prompt, 400))
                break
            except Exception as e:  # noqa: BLE001  network, quota, bad model name
                if attempt == 0:
                    time.sleep(3)
                    continue
                ok, reason = None, f"unavailable ({_detail(e)})"
        log.append(f"{name}: {'PASS' if ok else 'FAIL' if ok is False else 'SKIP'} - {reason}")
        if ok is False:
            return False, log  # one objection is enough
        if ok:
            passes += 1
            if passes >= min_passes + 1:
                break

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
            ok, reason = _parse(fn(prompt, 400))
        except Exception:  # noqa: BLE001
            continue
        if ok is None:
            continue
        if ok:
            passes += 1
        else:
            fails += 1
            reasons.append(reason or "details differ")
    return fails, passes, reasons
