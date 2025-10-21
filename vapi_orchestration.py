import csv, os, time, json
from dotenv import load_dotenv
from vapi import Vapi
from datetime import datetime

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
        print(f"📞 Appel lancé vers {number} (ID: {call.id})")
        return call.id
    except Exception as e:
        print(f"❌ Erreur lors de l'appel à {number}: {e}")
        return None

def wait_for_in_progress(call_id, max_wait=30):
    """Attend que l'appel passe à 'in-progress'"""
    for _ in range(max_wait):
        call = client.calls.get(call_id)
        status = call.status
        print(f"⏳ Statut: {status}")
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

def save_summary(call_obj, number):
    """Sauvegarde le résumé Vapi (analysis.summary)"""
    summary = None

    # ✅ Corrigé : accès direct à l'attribut .summary
    if hasattr(call_obj, "analysis") and call_obj.analysis:
        try:
            summary = call_obj.analysis.summary
        except AttributeError:
            summary = None

    if not summary:
        print(f"⚠️ Aucun résumé disponible pour {number}")
        return

    entry = {
        "number": number,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "summary": summary
    }

    # Écriture dans le fichier JSON
    if not os.path.exists(SUMMARY_FILE):
        with open(SUMMARY_FILE, "w") as f:
            json.dump([entry], f, indent=2)
    else:
        with open(SUMMARY_FILE, "r+") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = []
            data.append(entry)
            f.seek(0)
            json.dump(data, f, indent=2)

    print(f"✅ Résumé sauvegardé pour {number}")


# ---------------------------
# MAIN LOOP
# ---------------------------
if __name__ == "__main__":
    numbers = get_numbers_to_call()
    print(f"📋 {len(numbers)} numéros à appeler")

    for num in numbers:
        print(f"\n🚀 Appel de {num} ...")
        call_id = create_call(num)
        if not call_id:
            continue

        # Attente de l'état "in-progress"
        print("🕓 En attente de passage à 'in-progress'...")
        started = wait_for_in_progress(call_id)
        if started:
            print(f"✅ L'appel vers {num} est maintenant 'in-progress'")
            log_call(num, "in-progress")
        else:
            print(f"⚠️ L'appel vers {num} n’a jamais atteint 'in-progress'")
            continue

        # Attente de la fin de l'appel
        call_obj = wait_for_completion(call_id)
        if not call_obj:
            print(f"⚠️ Pas de réponse finale pour {num}")
            continue

        print(f"📞 Appel terminé ({num}) → {call_obj.status}")
        log_call(num, call_obj.status)

        # Récupération du résumé
        save_summary(call_obj, num)

        # Pause entre les appels
        time.sleep(10)

    print("\n🎉 Campagne terminée.")
