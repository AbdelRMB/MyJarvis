"""Le proxy Apache du serveur de comptes ne laisse passer que GET, POST et PUT : toute autre méthode reçoit un
404 HTML (« Erreur du serveur (404) » dans Wesley). C'est ce qui empêchait traiter_ticket / resoudre_ticket de
clore un ticket (requête PATCH). Ce test vérifie que ni l'appli de bureau ni l'appli mobile n'en envoient.

Lancer : python -m pytest tests -q   (seul pytest est nécessaire)
"""
import re
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
AUTORISEES = {"GET", "POST", "PUT"}


def _methodes(fichiers, motif):
    trouve = []
    for f in fichiers:
        for m in re.finditer(motif, f.read_text(encoding="utf-8")):
            trouve.append((f.relative_to(RACINE).as_posix(), m.group(1), m.group(2)))
    return trouve


def test_appli_de_bureau():
    # compte._appel(...) et les fonctions qui l'enveloppent
    appels = _methodes((RACINE / "wesley").rglob("*.py"), r"""_appel\(\s*["']([A-Z]+)["']\s*,\s*f?["']([^"']*)""")
    assert appels, "aucun appel au serveur de comptes trouvé : le motif du test est à revoir"
    interdits = [a for a in appels if a[1] not in AUTORISEES]
    assert not interdits, f"méthodes bloquées par le proxy du serveur de comptes : {interdits}"


def test_appli_mobile():
    src = RACINE / "interface" / "mobile" / "src"
    appels = _methodes(src.rglob("*.ts*"), r"""\bapi(?:<[^>]*>)?\(\s*["']([A-Z]+)["']\s*,\s*[`"']([^`"']*)""")
    assert appels, "aucun appel au serveur de comptes trouvé : le motif du test est à revoir"
    interdits = [a for a in appels if a[1] not in AUTORISEES]
    assert not interdits, f"méthodes bloquées par le proxy du serveur de comptes : {interdits}"


def test_traiter_ticket_en_post():
    texte = (RACINE / "wesley" / "compte.py").read_text(encoding="utf-8")
    assert re.search(r"""_appel\("POST", f"/v1/admin/tickets/\{int\(tid\)\}", json=corps\)""", texte)
