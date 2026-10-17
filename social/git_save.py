"""Push the bot's commit without ever losing another run's records.

Several workflows save JSON logs at the same time (what was posted, which comments were answered...).
A plain "keep my version" rebase can silently erase the other run's entries, and an erased entry means
something gets posted twice. Here, when two runs touched the same JSON file, the lists inside are
MERGED (union, de-duplicated), so no record is ever dropped. Text logs keep the newest version.

    python3 social/git_save.py --sync     pull, merge safely, push (exit 0 on success)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys


def git(*a, check=False):
    return subprocess.run(["git", *a], capture_output=True, text=True, check=check)


def ident(x):
    if isinstance(x, dict):
        for k in ("key", "id", "file", "date", "issue"):
            if k in x:
                return f"{k}={x[k]}"
    return json.dumps(x, sort_keys=True)


def merge(a, b):
    """a = version already on GitHub, b = this run's version. Lists are unioned; b wins on scalars."""
    if isinstance(a, list) and isinstance(b, list):
        out, seen = [], {}
        for x in a + b:
            k = ident(x)
            if k in seen:
                out[seen[k]] = x if isinstance(x, dict) else out[seen[k]]   # newer copy of the same record
            else:
                seen[k] = len(out); out.append(x)
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        return {k: merge(a[k], b[k]) if k in a and k in b else (b[k] if k in b else a[k]) for k in {**a, **b}}
    return b


def resolve() -> bool:
    files = [f for f in git("diff", "--name-only", "--diff-filter=U").stdout.split() if f]
    for f in files:
        upstream, mine = git("show", f":2:{f}").stdout, git("show", f":3:{f}").stdout
        if f.endswith(".json"):
            try:
                up, me = json.loads(upstream or "null"), json.loads(mine or "null")
                if "queue" in os.path.basename(f) and isinstance(up, list) and isinstance(me, list):
                    # queues shrink when something posts: keep this run's queue, add only NEW upstream items
                    # that were never posted (so a posted item can't come back and post twice)
                    done = "".join(open(x).read() for x in ("social/posted.json", "social/magazine_posted.json")
                                   if os.path.exists(x))
                    mine_ids = {ident(x) for x in me}
                    merged = me + [x for x in up if ident(x) not in mine_ids
                                   and not (isinstance(x, dict) and str(x.get("id", "\0")) in done)]
                else:
                    merged = merge(up, me)
                with open(f, "w", encoding="utf-8") as fh:
                    json.dump(merged, fh, indent=1, ensure_ascii=False)
            except json.JSONDecodeError:
                git("checkout", "--theirs", f)
        else:
            git("checkout", "--theirs", f)           # this run's copy of a log or generated file
        git("add", f)
    env = {**os.environ, "GIT_EDITOR": "true"}
    r = subprocess.run(["git", "rebase", "--continue"], capture_output=True, text=True, env=env)
    return r.returncode == 0 or "No rebase in progress" in r.stderr


def sync(branch: str) -> bool:
    for _ in range(6):
        r = git("pull", "--rebase", "origin", branch)
        guard = 0
        while r.returncode != 0 and guard < 20 and git("diff", "--name-only", "--diff-filter=U").stdout.strip():
            guard += 1
            if not resolve():
                r = git("status")
                break
            r = git("status")
            if "rebase in progress" not in r.stdout:
                break
        if "rebase in progress" in git("status").stdout:
            git("rebase", "--abort")
            continue
        if git("push", "origin", f"HEAD:{branch}").returncode == 0:
            return True
    return False


if __name__ == "__main__":
    branch = os.environ.get("GITHUB_REF_NAME") or "main"
    sys.exit(0 if sync(branch) else 1)
