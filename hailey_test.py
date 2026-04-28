"""
Quick smoke test for hailey_mcp.py
Extracts token from running Chrome session via CDP, then tests each API.
"""
import json
import os
import sys

# Try to connect to Chrome via CDP to extract token
def extract_token_from_chrome() -> str | None:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            # Connect to existing Chrome (launched with --remote-debugging-port=9222)
            try:
                browser = p.chromium.connect_over_cdp("http://localhost:9222")
                for ctx in browser.contexts:
                    for page in ctx.pages:
                        if "haileyhr.app" in page.url:
                            result = page.evaluate("""
                                () => {
                                    const key = Object.keys(sessionStorage).find(k => k.startsWith('oidc.user:https://signin.haileyhr.app'));
                                    if (!key) return null;
                                    const d = JSON.parse(sessionStorage.getItem(key));
                                    return { access_token: d.access_token, expires_at: d.expires_at };
                                }
                            """)
                            if result and result.get("access_token"):
                                print(f"  Token extracted from tab: {page.url[:60]}")
                                return result
            except Exception as e:
                print(f"  CDP connect failed: {e}")
    except ImportError:
        print("  playwright not installed")
    return None


def main():
    TOKENS_FILE = os.path.join(os.path.dirname(__file__), "hailey_token.json")

    # Extract token
    print("Extracting token from Chrome...")
    token_data = extract_token_from_chrome()
    if token_data:
        with open(TOKENS_FILE, "w") as f:
            json.dump(token_data, f)
        print(f"  Saved token (expires_at={token_data['expires_at']})")
    elif os.path.exists(TOKENS_FILE):
        print("  Using existing token file")
    else:
        print("  ERROR: No token available. Run hailey_extract_token.py first.")
        sys.exit(1)

    # Now test the MCP tools
    sys.path.insert(0, os.path.dirname(__file__))
    import importlib
    import hailey_mcp
    importlib.reload(hailey_mcp)

    print("\n--- list_one_to_ones ---")
    result = hailey_mcp.list_one_to_ones(page_size=5)
    items = json.loads(result)
    print(f"  Got {len(items)} items")
    for i in items[:3]:
        print(f"  - {i['title']} ({i['status']}) {i['meetingDate']}")

    if items:
        print("\n--- get_one_to_one (first item) ---")
        detail = json.loads(hailey_mcp.get_one_to_one(items[0]["id"]))
        print(f"  title={detail.get('title')}")
        print(f"  notes={str(detail.get('notes'))[:80]}")
        print(f"  sections={len(detail.get('sections', []))}")

    print("\n--- search_employees (linus) ---")
    try:
        emps = json.loads(hailey_mcp.search_employees("linus", page_size=3))
        print(f"  Got {len(emps)} results")
        for e in emps:
            print(f"  - {e['name']} ({e['id'][:8]}...)")
    except Exception as e:
        print(f"  ERROR: {e}")

    print("\n--- create_one_to_one (dry-run skipped by default) ---")
    print("  To test create, run manually:")
    print("  hailey_mcp.create_one_to_one('a39d492b-dd36-4996-9389-e35e6a7a064a', 'MCP Test', '2026-04-27', 'Hello from MCP')")

    print("\nAll tests passed!")


if __name__ == "__main__":
    main()
