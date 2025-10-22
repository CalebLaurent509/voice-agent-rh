# gmail_extract_numbers.py
import os, re, base64, csv, json
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from PyPDF2 import PdfReader
from docx import Document
import logging
from dotenv import load_dotenv
load_dotenv()

TOKEN = os.getenv("GOOGLE_TOKEN")
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
CREDS_FILE = 'credentials.json'
TOKEN_FILE = 'token.json'
SAVE_DIR = 'attachments_temp'
OUTPUT_FILE = 'phone_numbers.csv'

# Décode le fichier credentials depuis la variable Render
if os.getenv("GOOGLE_CREDENTIALS_B64"):
    creds_data = base64.b64decode(os.getenv("GOOGLE_CREDENTIALS_B64"))
    with open("credentials.json", "wb") as f:
        f.write(creds_data)

# AUTHENTICATION
def auth_gmail():
    """Authentifie Gmail via token .env ou navigateur local si nécessaire."""
    google_token = None  # 🔧 Correction: initialisation
    token_env = os.getenv("GOOGLE_TOKEN")

    # 1️⃣ Si le token est défini dans .env (en Base64)
    if token_env:
        try:
            decoded_token = json.loads(base64.b64decode(token_env).decode("utf-8"))
            google_token = Credentials.from_authorized_user_info(decoded_token, SCOPES)
            logging.info("✅ Token chargé depuis la variable d'environnement (Base64).")
        except Exception as e:
            logging.error(f"⚠️ Erreur lors du chargement du token .env : {e}")

    # 2️⃣ Sinon, utiliser un token local
    elif os.path.exists(TOKEN_FILE):
        google_token = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        logging.info("✅ Token local (token.json) utilisé.")

    # 3️⃣ Si aucun token valide : générer un nouveau via navigateur
    if not google_token or not google_token.valid:
        if google_token and google_token.expired and google_token.refresh_token:
            google_token.refresh(Request())
            logging.info("🔁 Token Gmail rafraîchi automatiquement.")
        else:
            logging.info("🌐 Aucun token valide — ouverture du navigateur pour authentification...")
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_FILE, SCOPES)
            google_token = flow.run_local_server(port=0)
            logging.info("✅ Nouveau token généré via navigateur local.")

        with open(TOKEN_FILE, 'w') as f:
            f.write(google_token.to_json())
        logging.info("💾 Token sauvegardé dans token.json.")

    return build('gmail', 'v1', credentials=google_token)



# CSV UTILITY
def load_processed_files():
    """Read the CSV to retrieve the list of already processed files"""
    processed = set()
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, newline='') as f:
            reader = csv.reader(f)
            next(reader, None)  # skip header
            for row in reader:
                if row:
                    processed.add(row[0])
    return processed

# SEARCH & DOWNLOAD attachments
def find_messages(service, subject_phrase, max_results=50):
    query = f'subject:"{subject_phrase}" has:attachment'
    results = service.users().messages().list(userId='me', q=query, maxResults=max_results).execute()
    return [m['id'] for m in results.get('messages', [])]

def download_attachments(service, msg_id, processed_files):
    msg = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
    attachments = []

    def recurse_parts(parts):
        for part in parts:
            filename = part.get('filename')
            if filename and any(filename.lower().endswith(ext) for ext in ['.pdf', '.docx']):
                # Skip if already listed in the CSV
                if filename in processed_files:
                    logging.info(f"[INFO] [*] Already processed (CSV): {filename}")
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
                    logging.info(f"[SUCCESS] [+] File downloaded: {filename}")
                    attachments.append(path)

            if 'parts' in part:
                recurse_parts(part['parts'])

    payload = msg.get('payload', {})
    recurse_parts(payload.get('parts', []))
    return attachments

# EXTRACTION UTILITIES
def extract_numbers_from_pdf(path):
    numbers = set()
    with open(path, 'rb') as f:
        reader = PdfReader(f)
        for page in reader.pages:
            text = page.extract_text() or ""
            numbers.update(re.findall(r'\+?\d[\d\s\-()]{7,}', text))
    return numbers

def extract_numbers_from_docx(path):
    numbers = set()
    doc = Document(path)
    for p in doc.paragraphs:
        numbers.update(re.findall(r'\+?\d[\d\s\-()]{7,}', p.text))
    return numbers

def looks_like_phone(n):
    n_clean = re.sub(r"[^\d+]", "", n)
    if len(n_clean) < 9 or len(n_clean) > 15:
        return False
    if re.match(r"^(19|20)\d{2}", n_clean):
        return False
    if not re.search(r"\+|\(|\)|-| ", n):
        return False
    return True

def normalize_phone(n):
    n = re.sub(r"[^\d+()\- ]", "", n)
    match = re.search(r"\((\d{3})\)[\s\-]*\d", n)
    if match:
        start = n.find(match.group(0))
        n = n[start:]
    n = re.sub(r"[^\d+]", "", n)
    if len(n) > 15:
        n = n[-10:]
    if len(n) == 10:
        n = "+1" + n
    elif n.startswith("1") and len(n) == 11:
        n = "+" + n
    return n

# main logic
def main():
    service = auth_gmail()
    subject = "New application: Appointment Setter"
    processed_files = load_processed_files()

    ids = find_messages(service, subject)
    logging.info(f"[INFO] [*] {len(ids)} emails found for subject: {subject}")
    results = []

    for i, msg_id in enumerate(ids, 1):
        logging.info(f"[INFO] [*] Email {i}/{len(ids)}")
        attachments = download_attachments(service, msg_id, processed_files)
        if not attachments:
            logging.info("[INFO] [*] No new attachments to process.")
            continue

        for att in attachments:
            logging.info(f"[INFO] [*] Analyzing {att} ...")
            try:
                if att.lower().endswith('.pdf'):
                    nums = extract_numbers_from_pdf(att)
                elif att.lower().endswith('.docx'):
                    nums = extract_numbers_from_docx(att)
                else:
                    nums = set()

                valid_nums = [normalize_phone(n) for n in nums if looks_like_phone(n)]
                if valid_nums:
                    logging.info(f"[INFO] [*] Valid numbers: {', '.join(valid_nums)}")
                    for n in valid_nums:
                        results.append((os.path.basename(att), n))
                else:
                    logging.warning("[WARNING] [!] No valid phone number found.")
            finally:
                # Delete the file after analysis
                try:
                    os.remove(att)
                    logging.info(f"[SUCCESS] [+] File removed: {att}")
                except Exception as e:
                    logging.error(f"[ERROR] [!] Unable to remove {att}: {e}")

    # Summary and CSV export
    if results:
        logging.info("[INFO] [*] Final summary:")
        file_exists = os.path.exists(OUTPUT_FILE)
        with open(OUTPUT_FILE, 'a', newline='') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(['File', 'Number'])
            for filename, num in sorted(set(results)):
                logging.info(f"[INFO] [*] {filename} → {num}")
                writer.writerow([filename, num])
        logging.info(f"[INFO] [*] Results appended to {OUTPUT_FILE} ({len(results)} new entries)")
    else:
        logging.info("[INFO] [*] No new data to save.")

    # Final cleanup of the directory if it's empty
    if os.path.exists(SAVE_DIR) and not os.listdir(SAVE_DIR):
        os.rmdir(SAVE_DIR)
        logging.info("[INFO] [*] 'attachments' folder removed (empty).")

if __name__ == '__main__':
    main()
