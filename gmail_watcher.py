import time
from get_applicants_number import main

if __name__ == "__main__":
    start_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    print(f"==> [INFO] [*] Gmail watcher started at {start_time}")
    while True:
        try:
            main()
            end_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            print(f"==> [INFO] [*] Gmail watcher completed a scan at {end_time}")
        except Exception as e:
            print(f"==> [ERROR] [!] {e}")
        print(f"==> [INFO] [*] Waiting 30 seconds before next scan...")
        time.sleep(30)  # 30 seconds for testing, change to 300 for 5 minutes
