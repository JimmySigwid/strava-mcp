"""
Hailey HR MCP Server
Provides tools to read and create 1:1s (one-to-ones) in Hailey HR.

Discovered endpoints (2026-04-27):
  Read:   GET  https://one-to-one-projection.hhr.app/OneToOnesForOverview
          GET  https://one-to-one-projection.hhr.app/OneToOne?oneToOneId=...
  Write:  POST https://simple-process-manager.hhr.app/StartOneToOne
          POST https://simple-process-manager.hhr.app/UpdateOneToOne
  Search: GET  https://employee-list-projection.hhr.app/Employees?searchQuery=...
  Auth:   OIDC JWT stored in sessionStorage['oidc.user:https://signin.haileyhr.app:front-end-client']
          JWT contains 'employee_id' claim (current user's Hailey employee ID)
"""
import base64
import json
import os
import sys
import time
import uuid

import requests
from mcp.server.fastmcp import FastMCP

TOKENS_FILE = os.path.join(os.path.dirname(__file__), "hailey_token.json")

PROJECTION_BASE = "https://one-to-one-projection.hhr.app"
SPM_BASE = "https://simple-process-manager.hhr.app"
EMPLOYEE_LIST_BASE = "https://employee-list-projection.hhr.app"

# Default 1:1 type ("One-to-one") — from ManageableOneToOneTypesForEmployee
DEFAULT_OTO_TYPE_ID = "9c9bc1a4-9420-4a7e-acf3-75610210cc4e"

mcp = FastMCP("Hailey HR")


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _decode_jwt_payload(token: str) -> dict:
    payload = token.split(".")[1]
    payload += "=" * (4 - len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


def _token_expires_at(token: str) -> int:
    try:
        return _decode_jwt_payload(token).get("exp", 0)
    except Exception:
        return 0


def _refresh_token() -> str:
    print("Token expired or missing — capturing fresh token via browser...", flush=True)
    sys.path.insert(0, os.path.dirname(__file__))
    from hailey_extract_token import capture
    success = capture(timeout_seconds=60)
    if not success:
        raise RuntimeError(
            "Token refresh failed. Open https://haileyhr.app in Chrome and try again."
        )
    with open(TOKENS_FILE) as f:
        return json.load(f)["access_token"]


def _load_token() -> str:
    if not os.path.exists(TOKENS_FILE):
        return _refresh_token()

    with open(TOKENS_FILE) as f:
        data = json.load(f)
    token = data["access_token"]

    exp = _token_expires_at(token)
    if exp and time.time() > exp - 300:
        token = _refresh_token()

    return token


def _my_employee_id(token: str) -> str:
    """Extract the current user's employee ID from the JWT."""
    return _decode_jwt_payload(token).get("employee_id", "")


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _api_get(url: str, params: dict = None) -> dict:
    token = _load_token()
    resp = requests.get(url, params=params, headers=_headers(token), timeout=15)
    if resp.status_code == 401:
        token = _refresh_token()
        resp = requests.get(url, params=params, headers=_headers(token), timeout=15)
    resp.raise_for_status()
    return resp.json()


def _api_post(url: str, payload: dict) -> requests.Response:
    token = _load_token()
    resp = requests.post(url, json=payload, headers=_headers(token), timeout=15)
    if resp.status_code == 401:
        token = _refresh_token()
        resp = requests.post(url, json=payload, headers=_headers(token), timeout=15)
    resp.raise_for_status()
    return resp


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------

@mcp.tool()
def list_one_to_ones(page: int = 1, page_size: int = 30) -> str:
    """
    List your one-to-ones (most recent first).

    Returns id, title, status, meetingDate, employeeId, colleagueEmployeeId
    for each entry. Use get_one_to_one(id) to fetch notes for a specific entry.
    """
    data = _api_get(
        f"{PROJECTION_BASE}/OneToOnesForOverview",
        params={"pageNumber": page, "pageSize": page_size},
    )
    items = data.get("oneToOnes", [])
    result = [
        {
            "id": i["oneToOneId"],
            "title": i["title"],
            "status": i["status"],
            "meetingDate": i.get("meetingDate"),
            "employeeId": i.get("employeeId"),
            "colleagueEmployeeId": i.get("colleagueEmployeeId"),
            "typeName": i.get("oneToOneTypeName"),
        }
        for i in items
    ]
    return json.dumps(result, indent=2)


@mcp.tool()
def get_one_to_one(one_to_one_id: str) -> str:
    """
    Get the full details of a one-to-one, including notes and template sections.

    Args:
        one_to_one_id: The UUID of the one-to-one (from list_one_to_ones)
    """
    data = _api_get(
        f"{PROJECTION_BASE}/OneToOne",
        params={"oneToOneId": one_to_one_id},
    )
    return json.dumps(data, indent=2)


@mcp.tool()
def search_employees(query: str, page_size: int = 10) -> str:
    """
    Search for employees by name (to find their employee ID for create_one_to_one).

    Args:
        query: Name or partial name to search for
        page_size: Max results (default 10)
    """
    data = _api_get(
        f"{EMPLOYEE_LIST_BASE}/Employees",
        params={"searchQuery": query, "pageSize": page_size, "pageNumber": 1},
    )
    employees = data.get("employees", data.get("items", []))
    result = [
        {
            "id": e.get("employeeId") or e.get("id"),
            "name": e.get("name") or f"{e.get('firstName', '')} {e.get('lastName', '')}".strip(),
            "email": e.get("email") or e.get("workEmail"),
            "department": e.get("departmentName") or e.get("department"),
            "title": e.get("title") or e.get("jobTitle"),
        }
        for e in employees
    ]
    return json.dumps(result, indent=2)


@mcp.tool()
def create_one_to_one(
    employee_id: str,
    title: str,
    meeting_date: str,
    notes: str = "",
    one_to_one_type_id: str = DEFAULT_OTO_TYPE_ID,
) -> str:
    """
    Create a new one-to-one meeting, optionally with notes.

    Args:
        employee_id: ID of your direct report (use search_employees to look up)
        title: Title for the one-to-one
        meeting_date: Date in YYYY-MM-DD format
        notes: Meeting notes (optional, plain text or basic HTML)
        one_to_one_type_id: Type UUID (defaults to standard "One-to-one" type)

    Returns the new one-to-one's ID and details.
    """
    token = _load_token()
    my_id = _my_employee_id(token)
    if not my_id:
        raise ValueError("Could not determine current user's employee ID from token.")

    new_id = str(uuid.uuid4())
    hdrs = _headers(token)

    # Step 1 — create the 1:1 skeleton
    start_payload = {
        "oneToOneId": new_id,
        "title": title,
        "meetingDate": meeting_date,
        "oneToOneTypeId": one_to_one_type_id,
        "employeeId": employee_id,
        "colleagueEmployeeId": my_id,
    }
    resp = requests.post(f"{SPM_BASE}/StartOneToOne", json=start_payload, headers=hdrs, timeout=15)
    if resp.status_code == 401:
        token = _refresh_token()
        hdrs = _headers(token)
        resp = requests.post(f"{SPM_BASE}/StartOneToOne", json=start_payload, headers=hdrs, timeout=15)
    resp.raise_for_status()

    # Step 2 — add notes if provided
    if notes:
        update_payload = {
            "oneToOneId": new_id,
            "title": title,
            "meetingDate": meeting_date,
            "notes": notes,
            "sections": [],
        }
        resp = requests.post(f"{SPM_BASE}/UpdateOneToOne", json=update_payload, headers=hdrs, timeout=15)
        resp.raise_for_status()

    return json.dumps({
        "success": True,
        "oneToOneId": new_id,
        "title": title,
        "meetingDate": meeting_date,
        "employeeId": employee_id,
        "colleagueEmployeeId": my_id,
        "notes": notes,
        "next_step": "Call request_sign_off(one_to_one_id) to request sign-off after user confirms.",
    }, indent=2)


@mcp.tool()
def update_one_to_one_notes(
    one_to_one_id: str,
    notes: str,
    title: str | None = None,
    meeting_date: str | None = None,
) -> str:
    """
    Update the notes (and optionally title/date) of an existing one-to-one.

    Args:
        one_to_one_id: UUID of the one-to-one to update
        notes: New notes content (replaces existing notes)
        title: New title (if None, keeps the existing title)
        meeting_date: New date in YYYY-MM-DD format (if None, keeps existing)
    """
    # Fetch current data if we need to fill in missing fields
    if title is None or meeting_date is None:
        current = _api_get(
            f"{PROJECTION_BASE}/OneToOne",
            params={"oneToOneId": one_to_one_id},
        )
        title = title or current.get("title")
        meeting_date = meeting_date or current.get("meetingDate")

    _api_post(
        f"{SPM_BASE}/UpdateOneToOne",
        {
            "oneToOneId": one_to_one_id,
            "title": title,
            "meetingDate": meeting_date,
            "notes": notes,
            "sections": [],
        },
    )
    return json.dumps({
        "success": True,
        "oneToOneId": one_to_one_id,
        "title": title,
        "meetingDate": meeting_date,
        "notes": notes,
    }, indent=2)


@mcp.tool()
def request_sign_off(one_to_one_id: str) -> str:
    """
    Request sign-off for an existing one-to-one meeting.

    This sends a sign-off request to the other participant. Use after creating
    or reviewing a one-to-one to formally close it out.

    Args:
        one_to_one_id: UUID of the one-to-one to request sign-off for
    """
    _api_post(
        f"{SPM_BASE}/RequestSignOffOneToOne",
        {"oneToOneId": one_to_one_id},
    )
    return json.dumps({
        "success": True,
        "oneToOneId": one_to_one_id,
        "message": "Sign-off requested.",
    }, indent=2)


if __name__ == "__main__":
    mcp.run()
