"""Run once to authorize and save tokens to tokens.json."""
import http.server
import urllib.parse
import webbrowser
import requests
import json
import os

CLIENT_ID = "202589"
CLIENT_SECRET = os.environ["STRAVA_CLIENT_SECRET"]
REDIRECT_URI = "http://localhost:8080"
TOKENS_FILE = os.path.join(os.path.dirname(__file__), "tokens.json")

auth_code = None

class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if "code" in params:
            auth_code = params["code"][0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<h2>Authorization successful! You can close this tab.</h2>")
        else:
            self.send_response(400)
            self.end_headers()

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    url = (
        f"https://www.strava.com/oauth/authorize"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=activity:read_all"
    )
    print("Opening browser for Strava authorization...")
    webbrowser.open(url)

    server = http.server.HTTPServer(("localhost", 8080), CallbackHandler)
    server.handle_request()

    resp = requests.post("https://www.strava.com/oauth/token", data={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": auth_code,
        "grant_type": "authorization_code",
    })
    resp.raise_for_status()
    tokens = resp.json()

    with open(TOKENS_FILE, "w") as f:
        json.dump({
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "expires_at": tokens["expires_at"],
        }, f, indent=2)

    print(f"Tokens saved to {TOKENS_FILE}")
