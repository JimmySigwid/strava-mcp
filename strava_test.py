import os
import http.server
import urllib.parse
import webbrowser
import requests
import json
import threading

CLIENT_ID = "202589"
CLIENT_SECRET = os.environ["STRAVA_CLIENT_SECRET"]
REDIRECT_URI = "http://localhost:8080"
AUTH_URL = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/oauth/token"

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
            self.wfile.write(b"<h2>No code received.</h2>")

    def log_message(self, format, *args):
        pass  # suppress server logs


def get_access_token():
    url = (
        f"{AUTH_URL}?client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=activity:read_all"
    )
    print("Opening browser for Strava authorization...")
    webbrowser.open(url)

    server = http.server.HTTPServer(("localhost", 8080), CallbackHandler)
    server.handle_request()

    resp = requests.post(TOKEN_URL, data={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": auth_code,
        "grant_type": "authorization_code",
    })
    resp.raise_for_status()
    return resp.json()["access_token"]


def fetch_recent_activities(token):
    resp = requests.get(
        "https://www.strava.com/api/v3/athlete/activities",
        headers={"Authorization": f"Bearer {token}"},
        params={"per_page": 5},
    )
    resp.raise_for_status()
    return resp.json()


if __name__ == "__main__":
    token = get_access_token()
    print("\nAccess token obtained.\n")

    activities = fetch_recent_activities(token)
    print(f"Last {len(activities)} activities:\n")
    for a in activities:
        dist_km = a["distance"] / 1000
        duration = a["moving_time"] // 60
        print(f"  {a['start_date_local'][:10]}  {a['name']}")
        print(f"    {dist_km:.2f} km  |  {duration} min  |  type: {a['type']}\n")
