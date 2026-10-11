"""Diagnose the Facebook Page connection. Writes docs/fb_check.json (no secrets)."""
import json, os, requests
G = "https://graph.facebook.com/v21.0"
page, tok = os.environ.get("FB_PAGE_ID", ""), os.environ.get("FB_PAGE_TOKEN", "")
out = {"page_id_set": bool(page), "token_set": bool(tok)}
def g(path, **p):
    try:
        return requests.get(f"{G}/{path}", params={"access_token": tok, **p}, timeout=30).json()
    except Exception as e:
        return {"exception": str(e)}
out["me"] = g("me", fields="id,name")
out["page"] = g(page, fields="id,name,tasks")
out["debug"] = g("debug_token", input_token=tok)
d = out["debug"].get("data", {})
out["debug"] = {k: d.get(k) for k in ("type", "is_valid", "expires_at", "scopes", "profile_id", "error")}
os.makedirs("docs", exist_ok=True)
json.dump(out, open("docs/fb_check.json", "w"), indent=1)
print(json.dumps(out, indent=1))
