import subprocess
import time
import datetime
from get_applicants_number import main

def is_within_hours():
    """Renvoie True si on est entre 7h00 et 4h00 (du lendemain)."""
    now = datetime.datetime.now()
    start = now.replace(hour=7, minute=0, second=0, microsecond=0)
    end = now.replace(hour=4, minute=0, second=0, microsecond=0) + datetime.timedelta(days=1)
    if start <= now <= end:
        return True
    return False

def start_server():
    """Démarre le serveur FastAPI dans un sous-processus"""
    print("🚀 [INFO] Lancement du serveur FastAPI...")
    return subprocess.Popen(
        ["uvicorn", "get_calendly_data:app", "--host", "0.0.0.0", "--port", "10000"]
    )

if __name__ == "__main__":
    print("📬 [Render] Gmail watcher + Server started")

    # Lancer le serveur
    server_process = start_server()

    try:
        while True:
            if is_within_hours():
                print("🕓 [INFO] Dans la plage horaire (7h → 4h) : scan Gmail...")
                try:
                    main()
                    print("✅ [INFO] Scan terminé. Attente 10 min...")
                except Exception as e:
                    print(f"❌ [ERROR] Gmail watcher: {e}")
                time.sleep(600)  # 10 minutes
            else:
                print("🌙 [INFO] En dehors des heures d’appel. Attente 30 min...")
                time.sleep(1800)
    except KeyboardInterrupt:
        print("🛑 [INFO] Arrêt manuel détecté. Fermeture du serveur...")
        server_process.terminate()
