from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import requests, os, pytz
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from collections import defaultdict

load_dotenv()

app = FastAPI(title="Vapi Calendly Tool", version="2.1")

# Credentials
TOKEN = f"Bearer {os.getenv('CALENDLY_TOKEN')}"
USER_ID = os.getenv("CALENDLY_USER_ID")
EVENT_TYPE_ID = os.getenv("EVENT_TYPE_ID")
HEADERS = {"Authorization": TOKEN, "Content-Type": "application/json"}

utc = pytz.utc
eastern = pytz.timezone("America/New_York")


def get_event_types():
    """Récupère la liste des event types du user"""
    url = "https://api.calendly.com/event_types"
    params = {"user": f"https://api.calendly.com/users/{USER_ID}"}
    res = requests.get(url, headers=HEADERS, params=params)
    res.raise_for_status()
    return res.json().get("collection", [])


def get_available_times(event_type_uri, start_date, end_date):
    """Récupère les créneaux disponibles"""
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
    """Récupère les hosts de l'événement"""
    url = "https://api.calendly.com/event_type_memberships"
    params = {"event_type": event_type_uri}
    res = requests.get(url, headers=HEADERS, params=params)
    res.raise_for_status()
    data = res.json().get("collection", [])
    return [m["member"]["email"] for m in data]


def get_availability(threshold: int = 3):
    """Retourne les slots disponibles pour l’event type sélectionné"""
    now = datetime.now(timezone.utc)
    start = now + timedelta(minutes=10)
    end = start + timedelta(days=7)
    event_uri = f"https://api.calendly.com/event_types/{EVENT_TYPE_ID}"

    available = get_available_times(event_uri, start, end)
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

    return {
        "event_name": "Starlight PR Interview",
        "total_slots": count,
        "available_days": daily_slots
    }

@app.get("/wake-up")
async def wake_up():
    """Endpoint de wake-up pour Render.com"""
    return JSONResponse(content={"status": "awake"})

@app.post("/availability")
async def availability_tool(request: Request):
    """Endpoint compatible avec Vapi"""
    try:
        _ = await request.json()
    except:
        pass

    data = get_availability()
    days = data.get("available_days", [])
    if not days:
        phrase = "There are no open interview slots right now."
        slots = []
    else:
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
# curl -X POST https://voice-agent-rh.onrender.com/availability