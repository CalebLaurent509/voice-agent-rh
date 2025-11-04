import os
import threading
import time
import datetime
import csv, json, requests
from datetime import datetime as dt
from dotenv import load_dotenv
from fastapi import FastAPI
import uvicorn

# === TES IMPORTS LOCAUX ===
from vapi import Vapi
from get_applicants_number import main as gmail_scan

# ================= CONFIG =================
load_dotenv()
client = Vapi(token=os.getenv("VAPI_API_KEY"))
AGENT_ID = os.getenv("VAPI_AGENT_ID")
PHONE_ID = os.getenv("PHONE_ID")
RECRUITER_EMAIL = os.getenv("RECRUITER_EMAIL")
URL = "https://voice-agent-rh-1-hgt5.onrender.com"

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
        time.sleep(30)  # toutes les 5 minutes (recommandé)

# ================= UTILS =================
def is_within_hours():
    """Renvoie True si on est entre 7h00 et 4h00 (du lendemain)."""
    now = datetime.datetime.now()
    start = now.replace(hour=7, minute=0, second=0, microsecond=0)
    end = now.replace(hour=11, minute=0, second=0, microsecond=0) + datetime.timedelta(days=1)
    return start <= now <= end

def send_email(to, subject, body):
    """Envoie un email via Mailgun."""
    api_key = os.getenv("MAILGUN_API_KEY")
    domain = os.getenv("MAILGUN_DOMAIN")
    if not api_key or not domain:
        print("MAILGUN_API_KEY ou MAILGUN_DOMAIN manquant")
        return
    try:
        r = requests.post(
            f"https://api.mailgun.net/v3/{domain}/messages",
            auth=("api", api_key),
            data={"from": f"Recruitment Bot <postmaster@{domain}>", "to": to, "subject": subject, "text": body},
        )
        print(f"📧 Mailgun status: {r.status_code}")
    except Exception as e:
        print("❌ Erreur Mailgun:", e)

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
    called = load_called_numbers()
    if not os.path.exists(CSV_FILE):
        return []
    with open(CSV_FILE, newline='') as f:
        reader = csv.DictReader(f)
        return [row["Number"].strip() for row in reader if row.get("Number") and row["Number"].strip() not in called]

def notify_if_qualified(entry):
    """Envoie un mail si candidat qualifié."""
    recruiter = RECRUITER_EMAIL
    data = entry.get("structured_data", {})
    if not data.get("qualified"):
        return
    candidate_name = data.get("candidate_name", "Candidate")
    interview_time = data.get("interview_time", "To be confirmed")
    summary = entry.get("summary", "")
    number = entry.get("number")

    body = f"""
    Hello Recruiter,

    A candidate has been qualified for an interview.

    Name: {candidate_name}
    Number: {number}
    Interview Time: {interview_time}

    Summary:
    {summary}

    ---
    Sent automatically by the Voice Agent System.
    """
    send_email(recruiter, f"Qualified Candidate: {candidate_name}", body)

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

def save_summary(call_obj, number):
    summary = getattr(call_obj.analysis, "summary", None)
    structured_data = getattr(call_obj.analysis, "structured_data", None)
    entry = {
        "number": number,
        "timestamp": dt.now().strftime("%Y-%m-%d %H:%M:%S"),
        "summary": summary or "",
        "structured_data": structured_data or {}
    }

    if not os.path.exists(SUMMARY_FILE):
        with open(SUMMARY_FILE, "w") as f:
            json.dump([entry], f, indent=2)
    else:
        with open(SUMMARY_FILE, "r+", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = []
            data.append(entry)
            f.seek(0)
            json.dump(data, f, indent=2, ensure_ascii=False)
    notify_if_qualified(entry)
    print("[INFO] Data saved for", number)

# ================= MAIN JOB LOOP =================
def job_loop():
    print("[INFO] Background worker started ✅")
    while True:
        try:
            if is_within_hours():
                print("[INFO] Valid time slot (7h-4h): scanning Gmail and making calls")
                gmail_scan()
                numbers = get_numbers_to_call()
                for num in numbers:
                    call_id = create_call(num)
                    if not call_id:
                        continue
                    call_obj = wait_for_completion(call_id)
                    if not call_obj:
                        continue
                    if call_obj.status in ("completed", "ended"):
                        log_call(num, call_obj.status)
                        save_summary(call_obj, num)
                        print("[SUCCESS] Call completed for", num)
                    time.sleep(10)
            else:
                print("[INFO] Outside hours (7h-4h). Sleeping 30min...")
                time.sleep(1800)
            
        except Exception as e:
            print("[ERROR] Loop error:", e)
            time.sleep(60)

# ================= FASTAPI SERVER =================
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
    # Lancer le mini-serveur FastAPI pour Render
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
