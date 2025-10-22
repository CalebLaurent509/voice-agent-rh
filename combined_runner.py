import subprocess
import time
import datetime
from get_applicants_number import main
import logging

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
    logging.info("[INFO] Lancement du serveur FastAPI...")
    return subprocess.Popen(
        ["uvicorn", "get_calendly_data:app", "--host", "0.0.0.0", "--port", "10000"]
    )

if __name__ == "__main__":
    logging.info("[INFO] Lancement du serveur et du Gmail watcher...")

    # Lancer le serveur
    server_process = start_server()

    try:
        while True:
            if is_within_hours():
                logging.info("[INFO] Dans la plage horaire (7h → 4h) : scan Gmail...")
                try:
                    main()
                    logging.info("[INFO] Scan Gmail terminé. En attente avant le prochain scan...")
                except Exception as e:
                    logging.error(f"[ERROR] Gmail watcher: {e}")
                time.sleep(30)  # 10 minutes
            else:
                logging.info("[INFO] En dehors des heures d’appel. Attente 30 min...")
                time.sleep(1800)
    except KeyboardInterrupt:
        logging.info("[INFO] Arrêt manuel détecté. Fermeture du serveur...")
        server_process.terminate()
