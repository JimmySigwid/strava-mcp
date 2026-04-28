"""
Capture a fresh Hailey HR Bearer token from Chrome.
Reads the OIDC token stored in sessionStorage after SSO login.
Can be run manually or called by hailey_mcp.py when the token expires.
"""
import os
import json
import time
from playwright.sync_api import sync_playwright

TOKENS_FILE = os.path.join(os.path.dirname(__file__), "hailey_token.json")
PROFILE_DIR = os.path.join(os.path.dirname(__file__), "hailey_browser_profile")
CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
HAILEY_URL = "https://haileyhr.app"
OIDC_KEY_PREFIX = "oidc.user:https://signin.haileyhr.app"


def extract_token_from_page(page) -> dict | None:
    """Extract the OIDC token from the page's sessionStorage."""
    try:
        result = page.evaluate("""
            () => {
                const key = Object.keys(sessionStorage).find(k => k.startsWith('oidc.user:https://signin.haileyhr.app'));
                if (!key) return null;
                const data = JSON.parse(sessionStorage.getItem(key));
                return { access_token: data.access_token, expires_at: data.expires_at };
            }
        """)
        return result
    except Exception:
        return None


def capture(timeout_seconds: int = 60) -> bool:
    """
    Launch Chrome with the Hailey profile, navigate to haileyhr.app,
    extract the OIDC token from sessionStorage, and save to file.
    Returns True if successful, False if timed out.
    """
    os.makedirs(PROFILE_DIR, exist_ok=True)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            PROFILE_DIR,
            headless=False,
            executable_path=CHROME_PATH,
            args=["--no-sandbox"],
            viewport={"width": 1400, "height": 900},
        )

        page = context.pages[0] if context.pages else context.new_page()
        print("Opening Hailey HR to capture token...")
        page.goto(HAILEY_URL)

        start = time.time()
        while time.time() - start < timeout_seconds:
            # Wait for the app shell to load
            if "haileyhr.app" in page.url and "/callback" not in page.url:
                token_data = extract_token_from_page(page)
                if token_data and token_data.get("access_token"):
                    print("Token captured successfully!")
                    with open(TOKENS_FILE, "w") as f:
                        json.dump(token_data, f)
                    context.close()
                    return True
            page.wait_for_timeout(500)

        context.close()
        print(f"Timed out after {timeout_seconds}s — no token found in sessionStorage.")
        return False


if __name__ == "__main__":
    success = capture()
    if not success:
        print("Failed to capture token. Make sure you are logged in to Hailey HR in Chrome.")
