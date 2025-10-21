from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import requests, os, pytz
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from collections import defaultdict

load_dotenv()

app = FastAPI(title="Vapi Calendly Tool", version="2.0")

# 🔐 Credentials
TOKEN = f"Bearer {os.getenv('CALENDLY_TOKEN')}"
EVENT_TYPE_ID = os.getenv("EVENT_TYPE_ID")
HEADERS = {"Authorization": TOKEN, "Content-Type": "application/json"}

utc = pytz.utc
eastern = pytz.timezone("America/New_York")


def get_event_types():
    url = "https://api.calendly.com/event_types"
    params = {"user": f"https://api.calendly.com/users/{EVENT_TYPE_ID}"}
    res = requests.get(url, headers=HEADERS, params=params)
    res.raise_for_status()
    return res.json()["collection"]

def get_available_times(event_type_uri, start_date, end_date):
    url = "https://api.calendly.com/event_type_available_times"
    params = {
        "event_type": event_type_uri,
        "start_time": start_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end_time": end_date.strftime("%Y-%m-%dT%H:%M:%SZ")
    }
    res = requests.get(url, headers=HEADERS, params=params)
    res.raise_for_status()
    return res.json().get("collection", [])

def get_event_hosts(event_type_uri):
    url = "https://api.calendly.com/event_type_memberships"
    params = {"event_type": event_type_uri}
    res = requests.get(url, headers=HEADERS, params=params)
    res.raise_for_status()
    data = res.json().get("collection", [])
    return [m["member"]["email"] for m in data]

def get_availability(threshold: int = 3):
    now = datetime.now(timezone.utc)
    start = now + timedelta(minutes=10)
    end = start + timedelta(days=7)
    event_types = get_event_types()
    all_availability = []

    for evt in event_types:
        uri = evt["uri"]
        name = evt["name"]
        available = get_available_times(uri, start, end)
        count = len(available)
        slots_by_day = defaultdict(list)
        for slot in available:
            dt_utc = datetime.strptime(slot["start_time"], "%Y-%m-%dT%H:%M:%SZ")
            dt_local = utc.localize(dt_utc).astimezone(eastern)
            day_label = dt_local.strftime("%A, %B %d")
            slots_by_day[day_label].append(dt_local)

        daily_slots = []
        for day in sorted(slots_by_day):
            times = sorted(slots_by_day[day])
            if times:
                start_time = times[0].strftime("%I:%M %p")
                end_time = times[-1].strftime("%I:%M %p")
                daily_slots.append({
                    "day": day,
                    "start_time": start_time,
                    "end_time": end_time
                })

        all_availability.append({
            "event_name": name,
            "total_slots": count,
            "available_days": daily_slots
        })

        if count < threshold:
            hosts = get_event_hosts(uri)
            print(f"[!] Low availability ({count}) for {name}. Notify: {hosts}")

    return all_availability


# -----------------------------
# 🧠 Vapi-Compatible Endpoint
# -----------------------------
@app.post("/availability")
async def availability_tool(request: Request):
    """Vapi will call this endpoint when the assistant uses the tool."""
    try:
        _ = await request.json()  # Vapi sends tool call info here
    except:
        pass

    data = get_availability()
    if not data or not data[0]["available_days"]:
        phrase = "There are no open interview slots right now."
        slots = []
    else:
        days = data[0]["available_days"]
        slots = days[:5]
        readable = " or ".join(
            f"{d['day']} from {d['start_time']} to {d['end_time']}" for d in slots
        )
        phrase = f"Available slots are: {readable}."

    print("==> [INFO] [*]:", phrase)

    return JSONResponse(content={
        "speech": phrase,
        "messages": [{"role": "assistant", "content": phrase}],
        "data": {"slots": slots} 
    })

# Pour lancer : uvicorn get_calendly_data:app --reload
# curl -X POST http://localhost:8000/availability