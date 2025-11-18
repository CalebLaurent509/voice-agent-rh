from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import requests, os
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import pytz

load_dotenv()

app = FastAPI(title="Vapi TidyCal Tool", version="1.1")

# Config
TOKEN = f"Bearer {os.getenv('TIDYCAL_TOKEN')}"
BOOKING_TYPE_ID = os.getenv("BOOKING_TYPE_ID")
BASE_URL = "https://tidycal.com/api"
HEADERS = {"Authorization": TOKEN, "Content-Type": "application/json"}

utc = pytz.utc
eastern = pytz.timezone("America/New_York")


# ----------------------------
# API Helpers
# ----------------------------

def list_booking_types():
    url = f"{BASE_URL}/booking-types"
    res = requests.get(url, headers=HEADERS)
    res.raise_for_status()
    data = res.json()
    return data.get("data", [])

def get_booking_type_info(booking_type_id):
    """Récupère les détails du booking type"""
    types = list_booking_types()
    for t in types:
        if str(t["id"]) == str(booking_type_id):
            return t
    return types[0] if types else {}

def list_timeslots(booking_type_id, start_dt, end_dt):
    url = f"{BASE_URL}/booking-types/{booking_type_id}/timeslots"
    params = {
        "starts_at": start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ends_at": end_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    res = requests.get(url, headers=HEADERS, params=params)
    res.raise_for_status()
    return res.json().get("data", [])


# ----------------------------
# Availability Logic
# ----------------------------

def get_availability():
    now = datetime.now(timezone.utc)
    start = now + timedelta(minutes=10)
    end = start + timedelta(days=7)

    booking_type_id = BOOKING_TYPE_ID
    if not booking_type_id:
        types = list_booking_types()
        if not types:
            return {"event_name": "Unknown", "total_slots": 0, "available_days": []}
        booking_type_id = types[0]["id"]

    # infos event
    info = get_booking_type_info(booking_type_id)
    title = info.get("title", "TidyCal Meeting")
    desc = info.get("description", "")
    duration = info.get("duration_minutes", 0)

    # créneaux disponibles
    slots = list_timeslots(booking_type_id, start, end)
    count = len(slots)
    slots_by_day = defaultdict(list)

    for slot in slots:
        dt_utc = datetime.fromisoformat(slot["starts_at"].replace("Z", "+00:00"))
        dt_local = dt_utc.astimezone(eastern)
        day_label = dt_local.strftime("%A, %B %d")
        slots_by_day[day_label].append(dt_local)

    daily_slots = []
    for day, times in sorted(slots_by_day.items()):
        start_time = min(times).strftime("%I:%M %p")
        end_time = max(times).strftime("%I:%M %p")
        daily_slots.append({
            "day": day,
            "start_time": start_time,
            "end_time": end_time
        })

    return {
        "event_name": title,
        "description": desc,
        "duration": f"{duration} minutes",
        "total_slots": count,
        "available_days": daily_slots
    }


# ----------------------------
# Routes
# ----------------------------

@app.get("/wake-up")
async def wake_up():
    """Endpoint de wake-up pour Render.com"""
    return JSONResponse(content={"status": "awake"})

@app.post("/availability")
async def availability_tool(request: Request):
    try:
        _ = await request.json()
    except:
        pass

    data = get_availability()
    days = data.get("available_days", [])

    if not days:
        phrase = f"There are no open slots right now for {data.get('event_name','this meeting')}."
        slots = []
    else:
        slots = days[:5]
        readable = " or ".join(
            f"{d['day']} from {d['start_time']} to {d['end_time']}" for d in slots
        )
        phrase = (
            f"{data['event_name']} ({data['duration']}). "
            f"{data['description']} "
            f"Available slots are: {readable}."
        )

    print("==> [INFO] [*]:", phrase)
    return JSONResponse(content={
        "speech": phrase,
        "messages": [{"role": "assistant", "content": phrase}],
        "data": data
    })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

# To run the app: uvicorn get_tidycal_data:app --reload --port 8000
# Example request: curl -X POST http://localhost:8000/availability