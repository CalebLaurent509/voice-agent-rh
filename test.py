import requests, time

URL = "https://voice-agent-rh-1-hgt5.onrender.com/wake-up"

while True:
    try:
        r = requests.get(URL)
        print(f"[PING] {r.status_code} {r.text}")
    except Exception as e:
        print("[ERROR]", e)
    time.sleep(10)  # toutes les 10 minutes
