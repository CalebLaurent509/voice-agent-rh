# gmail_extract_numbers.py
import os, re, base64, csv, json
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from PyPDF2 import PdfReader
from docx import Document
from dotenv import load_dotenv
import fitz
load_dotenv()

# ---------------------------
# CONFIGURATION
# ---------------------------
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
CREDS_FILE = 'credentials.json'
TOKEN_FILE = 'token.json'
SAVE_DIR = 'attachments_temp'
OUTPUT_FILE = 'phone_numbers.csv'

# Si les credentials sont encodés en Base64 (Render, etc.)
if os.getenv("GOOGLE_CREDENTIALS_B64"):
    creds_data = base64.b64decode(os.getenv("GOOGLE_CREDENTIALS_B64"))
    with open(CREDS_FILE, "wb") as f:
        f.write(creds_data)

# ---------------------------
# AUTHENTIFICATION GMAIL
# ---------------------------
def auth_gmail():
    creds = None
    token_env = os.getenv("GOOGLE_TOKEN")

    if token_env:
        try:
            decoded_token = json.loads(base64.b64decode(token_env).decode("utf-8"))
            creds = Credentials.from_authorized_user_info(decoded_token, SCOPES)
            print("✅ Token loaded from environment variable.")
        except Exception as e:
            print(f"⚠️ Error loading token from .env: {e}")
    elif os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        print("✅ Using local token.")

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            print("🌐 Authenticating via browser...")
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)

# ---------------------------
# UTILS
# ---------------------------
def load_processed_files():
    processed = set()
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, newline='') as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                if row:
                    processed.add(row[0])
    return processed

def find_messages(service, subject_phrase, max_results=50):
    query = f'subject:"{subject_phrase}" has:attachment'
    results = service.users().messages().list(userId='me', q=query, maxResults=max_results).execute()
    return [m['id'] for m in results.get('messages', [])]

# ---------------------------
# TÉLÉCHARGEMENT + MÉTADONNÉES
# ---------------------------
def download_attachments(service, msg_id, processed_files):
    msg = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
    attachments = []

    # 🔹 Récupère l’adresse email de l’expéditeur
    sender_email = None
    headers = msg.get("payload", {}).get("headers", [])
    for h in headers:
        if h["name"].lower() == "from":
            match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', h["value"])
            if match:
                sender_email = match.group(0)
                print(f"[INFO] [*] Sender detected: {sender_email}")
            break

    def recurse_parts(parts):
        for part in parts:
            filename = part.get('filename')
            if filename and any(filename.lower().endswith(ext) for ext in ['.pdf', '.docx']):
                if filename in processed_files:
                    print(f"[INFO] [*] Already processed: {filename}")
                    continue
                attach_id = part['body'].get('attachmentId')
                if attach_id:
                    att = service.users().messages().attachments().get(
                        userId='me', messageId=msg_id, id=attach_id
                    ).execute()
                    data = base64.urlsafe_b64decode(att['data'].encode('utf-8'))
                    os.makedirs(SAVE_DIR, exist_ok=True)
                    path = os.path.join(SAVE_DIR, filename)
                    with open(path, 'wb') as f:
                        f.write(data)
                    print(f"[SUCCESS] [+] Attachment downloaded: {filename}")
                    attachments.append(path)
            if 'parts' in part:
                recurse_parts(part['parts'])

    payload = msg.get('payload', {})
    recurse_parts(payload.get('parts', []))
    return attachments, sender_email

# ---------------------------
# EXTRACTION DE NUMÉROS
# ---------------------------
def extract_numbers_from_pdf(path):
    numbers = set()
    try:
        with open(path, 'rb') as f:
            reader = PdfReader(f)
            for page in reader.pages:
                text = page.extract_text() or ""
                numbers.update(re.findall(r'\+?\d[\d\s\-()]{7,}', text))
    except Exception as e:
        print(f"[WARNING] PyPDF2 failed ({e}). Retrying with PyMuPDF...")
        try:
            doc = fitz.open(path)
            for page in doc:
                text = page.get_text("text")
                numbers.update(re.findall(r'\+?\d[\d\s\-()]{7,}', text))
        except Exception as e2:
            print(f"[ERROR] Failed to extract text from {path} with PyMuPDF: {e2}")
    return numbers

def extract_numbers_from_docx(path):
    numbers = set()
    doc = Document(path)
    for p in doc.paragraphs:
        numbers.update(re.findall(r'\+?\d[\d\s\-()]{7,}', p.text))
    return numbers

def looks_like_phone(n):
    n_clean = re.sub(r"[^\d+]", "", n)
    return 9 <= len(n_clean) <= 15 and not re.match(r"^(19|20)\d{2}", n_clean)

def normalize_phone(n):
    n = re.sub(r"[^\d+]", "", n)
    if len(n) == 10:
        n = "+1" + n
    elif n.startswith("1") and len(n) == 11:
        n = "+" + n
    return n[-15:]

# ---------------------------
# MAIN LOGIC
# ---------------------------
def main():
    service = auth_gmail()
    subject = "New application: Appointment Setter"
    processed_files = load_processed_files()
    ids = find_messages(service, subject)
    print(f"[INFO] [*] {len(ids)} emails found with subject: {subject}")

    results = []
    for i, msg_id in enumerate(ids, 1):
        print(f"[INFO] [*] Processing email {i}/{len(ids)} ...")
        attachments, sender_email = download_attachments(service, msg_id, processed_files)
        if not attachments:
            print("[INFO] [*] No new attachments.")
            continue

        for att in attachments:
            print(f"[INFO] [*] Analyzing file {att} ...")
            try:
                nums = set()
                if att.lower().endswith('.pdf'):
                    nums = extract_numbers_from_pdf(att)
                elif att.lower().endswith('.docx'):
                    nums = extract_numbers_from_docx(att)

                valid_nums = [normalize_phone(n) for n in nums if looks_like_phone(n)]
                if valid_nums:
                    for n in valid_nums:
                        results.append((os.path.basename(att), n, sender_email or "N/A"))
                        print(f"[INFO] [*] {att} → {n} ({sender_email})")
                else:
                    print("[WARNING] [!] No valid number found.")
            finally:
                try:
                    os.remove(att)
                    print(f"[SUCCESS] [+] File removed: {att}")
                except Exception as e:
                    print(f"[ERROR] [!] Failed to remove {att}: {e}")

    # Sauvegarde des résultats
    if results:
        file_exists = os.path.exists(OUTPUT_FILE)

        # Vérifie si un en-tête est présent
        has_header = False
        if file_exists:
            with open(OUTPUT_FILE, 'r', newline='') as f_check:
                first_line = f_check.readline().strip()
                has_header = first_line.startswith("File,")

        # Écrit les nouvelles lignes
        with open(OUTPUT_FILE, 'a', newline='') as f:
            writer = csv.writer(f)
            if not file_exists or not has_header:
                writer.writerow(['File', 'Number', 'SenderEmail'])
            for r in sorted(set(results)):
                writer.writerow(r)

        print(f"[SUCCESS] [+] {len(results)} entries appended to {OUTPUT_FILE}")

    else:
        print("[INFO] [*] No new results to save.")

    if os.path.exists(SAVE_DIR) and not os.listdir(SAVE_DIR):
        os.rmdir(SAVE_DIR)

if __name__ == "__main__":
    main()
