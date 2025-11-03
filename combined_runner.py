import subprocess
import time
import datetime
import logging
import csv, os, json, requests
from dotenv import load_dotenv
from vapi import Vapi
from datetime import datetime as dt
from get_applicants_number import main as gmail_scan

# CONFIG
load_dotenv()
client = Vapi(token=os.getenv("VAPI_API_KEY"))
AGENT_ID = os.getenv("VAPI_AGENT_ID")
PHONE_ID = os.getenv("PHONE_ID")

CSV_FILE = "phone_numbers.csv"
CALLED_LOG = "called_numbers.csv"
SUMMARY_FILE = "call_summaries.json"
RECRUITER_EMAIL = os.getenv("RECRUITER_EMAIL")

# SERVER + TIME CHECK
def is_within_hours():
    """Renvoie True si on est entre 7h00 et 4h00 (du lendemain)."""
    now = datetime.datetime.now()
    start = now.replace(hour=7, minute=0, second=0, microsecond=0)
    end = now.replace(hour=4, minute=0, second=0, microsecond=0) + datetime.timedelta(days=1)
    return start <= now <= end

# EMAIL UTILS
def send_email(to, subject, body):
    """Envoie un email via l’API Mailgun"""
    api_key = os.getenv("MAILGUN_API_KEY")
    domain = os.getenv("MAILGUN_DOMAIN")

    if not api_key or not domain:
        print("⚠️ MAILGUN_API_KEY ou MAILGUN_DOMAIN manquant dans .env")
        return

    try:
        response = requests.post(
            f"https://api.mailgun.net/v3/{domain}/messages",
            auth=("api", api_key),
            data={
                "from": f"Recruitment Bot <postmaster@{domain}>",
                "to": to,
                "subject": subject,
                "text": body,
            },
        )

        if response.status_code == 200:
            print(f"✅ Email envoyé à {to}")
        else:
            print(f"⚠️ Erreur Mailgun ({response.status_code}): {response.text}")

    except Exception as e:
        print(f"❌ Erreur d’envoi via Mailgun: {e}")


# APPLICANTS & CALL LOGIC
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
    numbers = []
    with open(CSV_FILE, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            num = row.get("Number") or row.get("Numéro")
            if num and num not in called:
                numbers.append(num.strip())
    return numbers

def get_sender_email_by_number(number):
    with open(CSV_FILE, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (row.get("Number") or "").strip() == number:
                return row.get("SenderEmail")
    return None


def notify_if_qualified(entry):
    """Envoie uniquement un email au recruteur si un candidat est qualifié."""
    recruiter = os.getenv("RECRUITER_EMAIL")
    data = entry.get("structured_data", {})

    if not data.get("qualified"):
        return  # Ne rien faire si non qualifié

    candidate_name = data.get("candidate_name", "Candidate")
    interview_time = data.get("interview_time", "To be confirmed")
    summary = entry.get("summary", "")
    number = entry.get("number")

    recruiter_body = f"""
    Hello Recruiter,

    A candidate has been qualified for an interview.

    Name: {candidate_name}
    Number: {number}
    Interview Time: {interview_time}

    Summary:
    {summary}

    ---
    Message sent automatically by the Voice Agent System.
    """

    send_email(recruiter, f"Qualified Candidate: {candidate_name}", recruiter_body)


def create_call(number):
    try:
        call = client.calls.create(
            assistant_id=AGENT_ID,
            phone_number_id=PHONE_ID,
            customer={"number": number}
        )
        print("[INFO] Call started to " + number + " (ID: " + call.id + ")")
        return call.id
    except Exception as e:
        print("[ERROR] Error calling " + number + ": " + str(e))
        return None

def wait_for_completion(call_id):
    for _ in range(120):
        call = client.calls.get(call_id)
        if call.status in ("completed", "failed", "no-answer", "ended"):
            return call
        time.sleep(5)
    return None

def save_summary(call_obj, number):
    summary = getattr(call_obj.analysis, "summary", None) if hasattr(call_obj, "analysis") else None
    structured_data = getattr(call_obj.analysis, "structured_data", None) if hasattr(call_obj, "analysis") else None

    if not summary and not structured_data:
        print("[WARNING] No summary for " + number)
        return

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
    print("[INFO] Data saved for " + number)

# MAIN SCHEDULER LOOP
if __name__ == "__main__":
    print("[INFO] Starting server and Gmail watcher...")    
    try:
        while True:
            if is_within_hours():
                print("[INFO] Valid time slot (7h-4h): scanning Gmail and making calls")
                try:
                    gmail_scan()
                    numbers = get_numbers_to_call()
                    for num in numbers:
                        print("[INFO] Calling " + num)
                        call_id = create_call(num)
                        if not call_id:
                            continue
                        call_obj = wait_for_completion(call_id)
                        if not call_obj:
                            continue
                        if call_obj.status in ("completed", "ended"):
                            log_call(num, call_obj.status)
                            save_summary(call_obj, num)
                            print("[SUCCESS] Call completed for " + num)
                        time.sleep(10)
                except Exception as e:
                    print("[ERROR] Gmail watcher or call error: " + str(e))
                time.sleep(30)
            else:
                print("[INFO] Outside hours (7h-4h). Waiting 30 min...")
                time.sleep(1800)
    except KeyboardInterrupt:
        print("[INFO] Manual stop detected. Closing server...")