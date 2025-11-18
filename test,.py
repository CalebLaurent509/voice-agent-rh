from dateutil import parser
import pytz

def parse_interview_time(text, default_tz="America/New_York"):
    """
    Convertit un datetime en texte vers ISO 8601.
    Retourne None si impossible à parser.
    """
    if not text or not isinstance(text, str):
        return None

    try:
        # parser.parse gère "Thursday, November 20th at 10 AM"
        dt = parser.parse(text, fuzzy=True)
    except Exception:
        return None

    # Si pas de timezone → on applique ton fuseau
    if dt.tzinfo is None:
        tz = pytz.timezone(default_tz)
        dt = tz.localize(dt)

    return dt.isoformat()

print(parse_interview_time("Thursday, November 20th at 10 AM"))