"""Delete one Instagram post by media id (python social/ig_delete.py <id>)."""
import os, sys, requests
r = requests.delete(f"https://graph.facebook.com/v21.0/{sys.argv[1]}", timeout=30,
                    params={"access_token": os.environ["META_TOKEN"]})
print(r.status_code, r.text[:300])
