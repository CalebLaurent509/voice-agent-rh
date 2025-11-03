import csv, os, time, json
from dotenv import load_dotenv
from vapi import Vapi
from datetime import datetime
import requests
# ---------------------------
# CONFIG
# ---------------------------
load_dotenv()
client = Vapi(token=os.getenv("VAPI_API_KEY"))
AGENT_ID = os.getenv("VAPI_AGENT_ID")
PHONE_ID = os.getenv("PHONE_ID")

CSV_FILE = "phone_numbers.csv"
CALLED_LOG = "called_numbers.csv"
SUMMARY_FILE = "call_summaries.json"

# ---------------------------
# UTILS
# ---------------------------

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


def load_called_numbers():
    """Charge les numéros déjà appelés"""
    if not os.path.exists(CALLED_LOG):
        return set()
    with open(CALLED_LOG, newline='') as f:
        reader = csv.reader(f)
        next(reader, None)
        return {row[0] for row in reader if row}

def log_call(number, status):
    """Journalise les appels"""
    file_exists = os.path.exists(CALLED_LOG)
    with open(CALLED_LOG, "a", newline='') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Number", "Status", "Timestamp"])
        writer.writerow([number, status, datetime.now().strftime("%Y-%m-%d %H:%M:%S")])

def get_numbers_to_call():
    """Récupère les numéros à appeler"""
    called = load_called_numbers()
    numbers = []
    with open(CSV_FILE, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            num = row.get("Numéro") or row.get("Number")
            if num and num not in called:
                numbers.append(num.strip())
    return numbers

def get_sender_email_by_number(number):
    """Récupère l'email de l'expéditeur correspondant à un numéro dans le CSV"""
    with open(CSV_FILE, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            num = (row.get("Number") or row.get("Numéro") or "").strip()
            if num == number:
                return row.get("SenderEmail")
    return None

# ---------------------------
# VAPI CALLS
# ---------------------------
def create_call(number):
    """Crée un appel via Vapi"""
    try:
        call = client.calls.create(
            assistant_id=AGENT_ID,
            phone_number_id=PHONE_ID,
            customer={"number": number}
        )
        print(f"==> [INFO] [*] Appel lancé vers {number} (ID: {call.id})")
        return call.id
    except Exception as e:
        print(f"==> [ERROR] [!] Erreur lors de l'appel à {number}: {e}")
        return None

def wait_for_in_progress(call_id, max_wait=30):
    """Attend que l'appel passe à 'in-progress'"""
    for _ in range(max_wait):
        call = client.calls.get(call_id)
        status = call.status
        print(f"- Statut: {status}")
        if status == "in-progress":
            return True
        elif status in ("failed", "no-answer", "ended", "completed"):
            return False
        time.sleep(2)
    return False

def wait_for_completion(call_id):
    """Attend la fin de l'appel et renvoie l'objet complet"""
    for _ in range(120):  # 120 * 5s = 10min max
        call = client.calls.get(call_id)
        status = call.status
        if status in ("completed", "failed", "no-answer", "ended"):
            return call
        time.sleep(5)
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



def save_summary(call_obj, number):
    """Sauvegarde le résumé (summary) et les données structurées (structuredData)"""
    summary = None
    structured_data = None

    if hasattr(call_obj, "analysis") and call_obj.analysis:
        # Récupère le résumé textuel
        summary = getattr(call_obj.analysis, "summary", None)

        # Récupère les données structurées si disponibles
        structured_data = getattr(call_obj.analysis, "structured_data", None) or \
                        getattr(call_obj.analysis, "structuredData", None)

    if not summary and not structured_data:
        print(f"==> [WARNING] [!] Aucun résumé ni donnée structurée pour {number}")
        return

    entry = {
        "number": number,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "summary": summary or "",
        "structured_data": structured_data or {}
    }

    # Crée le fichier s’il n’existe pas encore
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

    print(f"==> [INFO] [*] Données sauvegardées pour {number} → résumé + structuredData")

# ---------------------------
# MAIN LOOP
# ---------------------------

if __name__ == "__main__":
    numbers = get_numbers_to_call()
    print(f"==> [INFO] [*] {len(numbers)} numéros à appeler")

    for num in numbers:
        print(f"\n==> [INFO] [*] Appel de {num} ...")
        call_id = create_call(num)
        if not call_id:
            continue

        # Attente de l’état "in-progress"
        print("==> [INFO] [*] En attente de passage à 'in-progress'...")
        started = wait_for_in_progress(call_id)
        if not started:
            print(f"==> [WARNING] [!] L'appel vers {num} n’a jamais atteint 'in-progress'")
            continue

        print(f"==> [INFO] [*] L'appel vers {num} est maintenant 'in-progress'")

        # Attente de la fin complète de l’appel
        call_obj = wait_for_completion(call_id)
        if not call_obj:
            print(f"==> [WARNING] [!] Pas de réponse finale pour {num}")
            continue

        status = call_obj.status
        print(f"==> [INFO] [*] Appel terminé ({num}) → {status}")

        # Si l’appel s’est bien déroulé, on le marque comme “consommé”
        if status in ("completed", "ended"):
            log_call(num, status)
            save_summary(call_obj, num)
            print(f"==> [SUCCESS] [+] Appel {num} considéré comme 'consommé'")
        else:
            print(f"==> [INFO] [*] Appel {num} ignoré (statut final: {status})")

        # Pause entre les appels
        time.sleep(10)

    print("\n==> [SUCCESS] [+] Campagne terminée.")
