import subprocess
import time
import datetime
import logging
import csv, os, json, smtplib
from dotenv import load_dotenv
from vapi import Vapi
from datetime import datetime as dt
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
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

def start_server():
    """Demarre le serveur FastAPI dans un sous-processus"""
    print("[INFO] Launching FastAPI server...")
    return subprocess.Popen(
        ["uvicorn", "get_calendly_data:app", "--host", "0.0.0.0", "--port", "10000"]
    )

# EMAIL UTILS
def send_email(to, subject, body):
    sender = os.getenv("SENDER_EMAIL_SMTP")
    password = os.getenv("SENDER_PASS_SMTP")

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, password)
            server.send_message(msg)
        print("[SUCCESS] Email sent to: " + to)
    except Exception as e:
        print("[WARNING] Error sending email to " + to + ": " + str(e))

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
    """Envoie les emails au recruteur et au candidat quand un appel est qualifie."""
    data = entry.get("structured_data", {})
    if not data.get("qualified"):
        return

    candidate_name = data.get("candidate_name", "Candidate")
    interview_time = data.get("interview_time", "To be confirmed")
    summary = entry.get("summary", "")
    number = entry.get("number")
    candidate_email = get_sender_email_by_number(number)

    # Email au recruteur
    recruiter_body = f"""
    A candidate has been qualified for interview.

    Name: {candidate_name}
    Number: {number}
    Email: {candidate_email or 'N/A'}
    Interview Time: {interview_time}

    Summary: {summary}
    """
    send_email(RECRUITER_EMAIL, f"Qualified Candidate: {candidate_name}", recruiter_body)

    # Email au candidat
    if candidate_email:
        candidate_body = f"""
        Hello {candidate_name},

        Congratulations! You've been qualified for the next interview step at Starlight PR.
        Your interview is scheduled for: {interview_time}
        Our recruiter will contact you at this number: {number}.

        Best regards,
        Starlight PR Team
        """
        send_email(candidate_email, f"Interview Confirmation – {candidate_name}", candidate_body)

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
    server_process = start_server()
    
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
        server_process.terminate()