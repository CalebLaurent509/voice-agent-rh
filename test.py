import os, requests
from dotenv import load_dotenv
load_dotenv()

def send_simple_message():
    return requests.post(
        "https://api.mailgun.net/v3/sandboxad4079eb78e14fcea4a4571752b7777f.mailgun.org/messages",
        auth=("api", os.getenv("MAILGUN_API_KEY")),
        data={
            "from": "Mailgun Sandbox <postmaster@sandboxad4079eb78e14fcea4a4571752b7777f.mailgun.org>",
            "to": "laurentcaleb99@gmail.com",
            "subject": "Hello Daniel",
            "text": "Congratulations Daniel, you just sent an email with Mailgun! You are truly awesome!"
        }
    )

print(send_simple_message().text)
