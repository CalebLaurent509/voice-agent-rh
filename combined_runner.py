import threading
import time, os
import datetime, pytz
import csv, json, requests
from dateutil import parser
from datetime import datetime as dt
from dotenv import load_dotenv
from fastapi import FastAPI
import uvicorn

load_dotenv()

from vapi import Vapi
from get_applicants_number import main as gmail_scan

# === TIDYCAL CONFIG ===
BOOKING_TYPE_ID = os.getenv("BOOKING_TYPE_ID")
TOKEN = f"Bearer {os.getenv('TIDYCAL_TOKEN')}"
BASE_URL = "https://tidycal.com/api"
HEADERS = {"Authorization": TOKEN, "Content-Type": "application/json"}

# ================= CONFIG VAPI / FICHIERS =================
client = Vapi(token=os.getenv("VAPI_API_KEY"))
AGENT_ID = os.getenv("VAPI_AGENT_ID")
PHONE_ID = os.getenv("PHONE_ID")
URL = "https://get-tidycal-data.onrender.com"

CSV_FILE = "phone_numbers.csv"
CALLED_LOG = "called_numbers.csv"
SUMMARY_FILE = "call_summaries.json"


def keep_alive():
    """Ping régulier du endpoint /wake-up pour éviter la mise en veille Render."""
    while True:
        try:
            r = requests.get(f"{URL}/wake-up", timeout=10)
            print(f"[KEEP-ALIVE] Ping -> {r.status_code}")
        except Exception as e:
            print("[KEEP-ALIVE ERROR]", e)
        time.sleep(300)


def is_within_hours():
    """
    Renvoie True si on est entre 7h du matin (07:00 AM)
    et 16h (4:00 PM) aujourd’hui — fuseau US/Eastern.
    """
    tz = pytz.timezone("America/New_York")
    now = datetime.datetime.now(tz)

    start = now.replace(hour=7, minute=0, second=0, microsecond=0)   # 07:00
    end   = now.replace(hour=16, minute=0, second=0, microsecond=0)  # 16:00 (4 PM)

    return start <= now <= end



def load_called_numbers():
    if not os.path.exists(CALLED_LOG):
        return set()
    with open(CALLED_LOG, newline='') as f:
        reader = csv.reader(f)
        next(reader, None)
        return {row[0] for row in reader if row}


def log_call(number, status):
    file_exists = os.path.exists(CALLED_LOG)
    with open(CALLED_LOG, "a", newline='') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Number", "Status", "Timestamp"])
        writer.writerow([number, status, dt.now().strftime("%Y-%m-%d %H:%M:%S")])


def get_numbers_to_call():
    """
    Lit le CSV et renvoie une liste de dicts:
    [
      {"number": "+1...", "email": "candidate@example.com"},
      ...
    ]
    en excluant les numéros déjà appelés.
    """
    called = load_called_numbers()
    if not os.path.exists(CSV_FILE):
        return []

    leads = []
    with open(CSV_FILE, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            num = (row.get("Number") or "").strip()
            email = (row.get("SenderEmail") or "").strip()
            if num and num not in called:
                leads.append({"number": num, "email": email})
    return leads


def create_call(number):
    try:
        call = client.calls.create(
            assistant_id=AGENT_ID,
            phone_number_id=PHONE_ID,
            customer={"number": number}
        )
        print(f"[INFO] Call started to {number} (ID: {call.id})")
        return call.id
    except Exception as e:
        print(f"[ERROR] Call error {number}: {e}")
        return None


def wait_for_completion(call_id):
    for _ in range(120):
        call = client.calls.get(call_id)
        if call.status in ("completed", "failed", "no-answer", "ended"):
            return call
        time.sleep(5)
    return None

def parse_interview_time(text, default_tz="America/New_York"):
    """
    Convertit un datetime en texte vers ISO 8601.
    Retourne None si impossible à parser.
    """
    if not text or not isinstance(text, str):
        return None

    try:
        # parser.parse gère "Thursday, November 20th at 10 AM"
        dt = parser.parse(text, fuzzy=True)
    except Exception:
        return None

    # Si pas de timezone → on applique ton fuseau
    if dt.tzinfo is None:
        tz = pytz.timezone(default_tz)
        dt = tz.localize(dt)

    return dt.isoformat()


def book_meeting_local(starts_at, name, email, phone, role, timezone="America/New_York"):

    if not all([starts_at, name, email, phone, role]):
        print("[BOOKING] Champs manquants pour la réservation:", {
            "starts_at": starts_at, "name": name, "email": email,
            "phone": phone, "role": role
        })
        return {"error": "Missing required fields"}

    # FIX : retirer le timezone (-05:00) pour éviter décalage double
    starts_at_clean = starts_at.split("-")[0]   # => "2025-11-21T09:15:00"

    payload = {
        "starts_at": starts_at_clean,
        "name": name,
        "email": email,
        "timezone": timezone,  # on laisse cette ligne
        "booking_questions": [
            {"booking_type_question_id": 1, "answer": phone},
            {"booking_type_question_id": 2, "answer": role}
        ]
    }

    url = f"{BASE_URL}/booking-types/{BOOKING_TYPE_ID}/bookings"
    res = requests.post(url, headers=HEADERS, json=payload)

    if res.status_code not in (200, 201):
        print("[BOOKING] Booking failed:", res.status_code, res.text)
        return {"error": res.text}

    data = res.json().get("data", {})
    phrase = f"Booked {data.get('booking_type', {}).get('title', 'meeting')} for {name} on {starts_at}."
    print("[BOOKING]", phrase)

    return {
        "speech": phrase,
        "data": data
    }


def save_summary(call_obj, number, email):
    """
    Sauvegarde le résumé dans un JSON
    + déclenche le booking TidyCal en utilisant structured_data renvoyé par l'agent.
    """
    summary = getattr(call_obj.analysis, "summary", None)
    structured_data = getattr(call_obj.analysis, "structured_data", None) or {}

    entry = {
        "number": number,
        "timestamp": dt.now().strftime("%Y-%m-%d %H:%M:%S"),
        "summary": summary or "",
        "structured_data": structured_data
    }

    # Sauvegarde le JSON
    if not os.path.exists(SUMMARY_FILE):
        with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
            json.dump([entry], f, indent=2, ensure_ascii=False)
    else:
        with open(SUMMARY_FILE, "r+", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = []
            data.append(entry)
            f.seek(0)
            json.dump(data, f, indent=2, ensure_ascii=False)

    print("[INFO] Data saved for", number)

    # ========= ICI ON UTILISE LES DONNÉES DE L'AGENT POUR BOOKER =========
    # Adapte les clés suivant ce que tu mets dans structured_data depuis Vapi.
    qualified = structured_data.get("qualified")  # bool ou "yes"/"no"
    raw_time = structured_data.get("interview_time")
    interview_time = parse_interview_time(raw_time)

    if not interview_time:
        print("[ERROR] Impossible de parser la date :", raw_time)
        print("[INFO] Booking skipped.")
        return

    candidate_name = (
        structured_data.get("candidate_name")
        or structured_data.get("name")
        or number
    )
    candidate_role = (
        structured_data.get("candidate_role")
        or structured_data.get("role")
        or "Candidate"
    )
    timezone = structured_data.get("timezone") or "America/New_York"

    # Si le candidat est qualifié ET qu'on a un créneau → on book
    if qualified and interview_time:
        print("[INFO] Candidate qualified, booking meeting via TidyCal...")
        result = book_meeting_local(
            starts_at=interview_time,
            name=candidate_name,
            email=email or structured_data.get("email") or "no-email@example.com",
            phone=number,
            role=candidate_role,
            timezone=timezone
        )
        print("[INFO] Booking result:", result)
    else:
        print("[INFO] Pas de booking (qualified/interview_time manquant)",
              "qualified=", qualified, "interview_time=", interview_time)


# ================= MAIN JOB LOOP =================
def job_loop():
    print("[INFO] Background worker started ✅")
    while True:
        try:
            if not is_within_hours():
                print("[INFO] Outside hours (7 AM - 4 PM). Sleeping 30min...")
                time.sleep(1800)
                continue

            print("[INFO] Scanning Gmail and making calls...")
            gmail_scan()

            leads = get_numbers_to_call()
            if not leads:
                print("[INFO] No numbers to call. Sleeping 30min...")
                time.sleep(1800)
                continue

            for lead in leads:
                num = lead["number"]
                email = lead.get("email") or ""

                call_id = create_call(num)
                if not call_id:
                    continue

                call_obj = wait_for_completion(call_id)
                if not call_obj:
                    continue

                if call_obj.status in ("completed", "ended"):
                    log_call(num, call_obj.status)
                    save_summary(call_obj, num, email)
                    print("[SUCCESS] Call completed for", num)

                time.sleep(10)

            # VERY IMPORTANT — prevents double calls
            print("[INFO] Sleeping 30min before next cycle...")
            time.sleep(1800)

        except Exception as e:
            print("[ERROR] Loop error:", e)
            time.sleep(60)


# ================= FASTAPI SERVER (juste pour healthcheck Render) =================
app = FastAPI()

@app.get("/")
def root():
    return {"status": "running", "time": str(datetime.datetime.now())}

@app.get("/health")
def health():
    return {"ok": True}


if __name__ == "__main__":
    # Lancer ton worker dans un thread de fond
    threading.Thread(target=job_loop, daemon=True).start()
    threading.Thread(target=keep_alive, daemon=True).start()

    # Lancer le mini-serveur FastAPI
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)