import threading
from datetime import datetime, timedelta

from . import outil
from ..plateforme import alerte

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


@outil
def date_heure():
    """Donne la date et l'heure actuelles."""
    n = datetime.now()
    return f"{JOURS[n.weekday()]} {n:%d/%m/%Y %H:%M:%S}"


def _alerte(msg):
    try:
        alerte(msg, "Jarvis - Rappel")
    except Exception:
        pass


@outil
def rappel(minutes: float, message: str):
    """Programme un rappel (fenêtre d'alerte) dans X minutes.
    minutes: délai en minutes
    message: texte du rappel"""
    t = threading.Timer(minutes * 60, _alerte, args=(message,))
    t.daemon = True
    t.start()
    return f"Rappel à {(datetime.now()+timedelta(minutes=minutes)):%H:%M} : {message}"


@outil
def notifier(message: str):
    """Affiche une fenêtre de notification à l'utilisateur.
    message: texte"""
    threading.Thread(target=_alerte, args=(message,), daemon=True).start()
    return "Notifié."


@outil
def calculer(expression: str):
    """Calcule une expression mathématique (ex: '2**10 / 3', 'sqrt(2)*pi').
    expression: expression Python"""
    import math
    return str(eval(expression, {"__builtins__": {}}, vars(math)))
