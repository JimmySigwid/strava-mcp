import json
import time
import os
import requests
from mcp.server.fastmcp import FastMCP

CLIENT_ID = "202589"
CLIENT_SECRET = "71dd5aff6fcd6a58baa016574da89625a112e9fe"
TOKENS_FILE = os.path.join(os.path.dirname(__file__), "tokens.json")

mcp = FastMCP("Strava")


def load_tokens():
    with open(TOKENS_FILE) as f:
        return json.load(f)


def save_tokens(tokens):
    with open(TOKENS_FILE, "w") as f:
        json.dump(tokens, f, indent=2)


def get_access_token():
    tokens = load_tokens()
    if time.time() > tokens["expires_at"] - 60:
        resp = requests.post("https://www.strava.com/oauth/token", data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "refresh_token": tokens["refresh_token"],
            "grant_type": "refresh_token",
        })
        resp.raise_for_status()
        new = resp.json()
        tokens = {
            "access_token": new["access_token"],
            "refresh_token": new["refresh_token"],
            "expires_at": new["expires_at"],
        }
        save_tokens(tokens)
    return tokens["access_token"]


@mcp.tool()
def get_recent_activities(count: int = 10) -> str:
    """Fetch the most recent Strava activities."""
    token = get_access_token()
    resp = requests.get(
        "https://www.strava.com/api/v3/athlete/activities",
        headers={"Authorization": f"Bearer {token}"},
        params={"per_page": count},
    )
    resp.raise_for_status()
    activities = resp.json()

    lines = []
    for a in activities:
        dist_km = a["distance"] / 1000
        duration = a["moving_time"] // 60
        pace_per_km = (a["moving_time"] / 60) / dist_km if dist_km > 0 else 0
        pace_min = int(pace_per_km)
        pace_sec = int((pace_per_km - pace_min) * 60)
        hr = f"  avg HR: {a['average_heartrate']:.0f}" if a.get("average_heartrate") else ""
        elev = f"  elev: {a['total_elevation_gain']:.0f} m" if a.get("total_elevation_gain") else ""
        lines.append(
            f"{a['start_date_local'][:10]}  {a['name']}  [id: {a['id']}]\n"
            f"  {dist_km:.2f} km | {duration} min | pace {pace_min}:{pace_sec:02d}/km{hr}{elev}"
        )
    return "\n\n".join(lines)


@mcp.tool()
def get_activity_detail(activity_id: int) -> str:
    """Fetch full details for a specific Strava activity by ID."""
    token = get_access_token()
    resp = requests.get(
        f"https://www.strava.com/api/v3/activities/{activity_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()
    a = resp.json()

    dist_km = a["distance"] / 1000
    duration_min = a["moving_time"] // 60
    elapsed_min = a.get("elapsed_time", 0) // 60
    pace_per_km = (a["moving_time"] / 60) / dist_km if dist_km > 0 else 0
    pace_min = int(pace_per_km)
    pace_sec = int((pace_per_km - pace_min) * 60)

    lines = [
        f"Name: {a['name']}",
        f"ID: {a['id']}",
        f"Date: {a['start_date_local'][:10]}",
        f"Sport type: {a.get('sport_type', a.get('type', 'Unknown'))}",
        f"Distance: {dist_km:.2f} km",
        f"Moving time: {duration_min} min",
        f"Elapsed time: {elapsed_min} min",
        f"Pace: {pace_min}:{pace_sec:02d} /km",
        f"Elevation gain: {a.get('total_elevation_gain', 0):.0f} m",
        f"Elevation high: {a.get('elev_high', 0):.0f} m",
        f"Elevation low: {a.get('elev_low', 0):.0f} m",
    ]

    if a.get("average_speed"):
        lines.append(f"Avg speed: {a['average_speed'] * 3.6:.1f} km/h")
    if a.get("max_speed"):
        lines.append(f"Max speed: {a['max_speed'] * 3.6:.1f} km/h")
    if a.get("average_heartrate"):
        lines.append(f"Avg HR: {a['average_heartrate']:.0f} bpm")
    if a.get("max_heartrate"):
        lines.append(f"Max HR: {a['max_heartrate']:.0f} bpm")
    if a.get("average_cadence"):
        lines.append(f"Avg cadence: {a['average_cadence']:.0f} spm")
    if a.get("average_watts"):
        lines.append(f"Avg power: {a['average_watts']:.0f} W")
    if a.get("max_watts"):
        lines.append(f"Max power: {a['max_watts']:.0f} W")
    if a.get("weighted_average_watts"):
        lines.append(f"Normalized power: {a['weighted_average_watts']:.0f} W")
    if a.get("calories"):
        lines.append(f"Calories: {a['calories']:.0f} kcal")
    if a.get("suffer_score"):
        lines.append(f"Suffer score: {a['suffer_score']}")
    if a.get("achievement_count"):
        lines.append(f"Achievements: {a['achievement_count']}")
    if a.get("kudos_count") is not None:
        lines.append(f"Kudos: {a['kudos_count']}")
    if a.get("gear") and a["gear"].get("name"):
        lines.append(f"Gear: {a['gear']['name']}")
    if a.get("device_name"):
        lines.append(f"Device: {a['device_name']}")
    if a.get("workout_type") is not None:
        workout_types = {0: "Default", 1: "Race", 2: "Long run", 3: "Workout"}
        lines.append(f"Workout type: {workout_types.get(a['workout_type'], a['workout_type'])}")
    if a.get("description"):
        lines.append(f"Notes: {a['description']}")

    if a.get("splits_metric"):
        lines.append("\nSplits (per km):")
        for s in a["splits_metric"]:
            s_dist = s["distance"] / 1000
            if s_dist < 0.1:
                continue
            s_pace = (s["moving_time"] / 60) / s_dist if s_dist > 0 else 0
            s_min = int(s_pace)
            s_sec = int((s_pace - s_min) * 60)
            s_hr = f"  HR: {s['average_heartrate']:.0f}" if s.get("average_heartrate") else ""
            s_elev = f"  elev: {s.get('elevation_difference', 0):+.0f} m" if s.get("elevation_difference") else ""
            lines.append(f"  km {s['split']}: {s_min}:{s_sec:02d}/km  {s_dist:.2f} km{s_hr}{s_elev}")

    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
