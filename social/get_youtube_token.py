"""Run ONCE on your PC to let the bot upload to the @FinanceHubW channel.

1. Google Cloud Console (signed in as financehubw@gmail.com): create a project,
   enable "YouTube Data API v3", create an OAuth client of type "Desktop app",
   download it as client_secret.json into this folder.
2. pip install google-auth-oauthlib
3. python get_youtube_token.py   -> a browser opens; pick the FinanceHubW channel.
4. It saves youtube_token.json. Add it as a secret, then delete the file:
     gh secret set YT_TOKEN_JSON --repo financehubw/FinanceHubW < youtube_token.json
"""
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

flow = InstalledAppFlow.from_client_secrets_file(
    "client_secret.json", ["https://www.googleapis.com/auth/youtube.upload"])
creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
Path("youtube_token.json").write_text(creds.to_json())
print("Saved youtube_token.json. Add it to GitHub (see the top of this file), then delete it.")
