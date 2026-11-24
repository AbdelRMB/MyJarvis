"""Tableau de santé, bot Telegram (sécurité de la liaison) et Home Assistant, sans réseau.

Lancer : python -m pytest tests/test_sante_telegram_maison.py -q
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wesley import sante  # noqa: E402


def test_sante_compte_les_echecs(tmp_path, monkeypatch):
    monkeypatch.setattr(sante, "FICHIER", tmp_path / "sante.json")
    sante._cache.clear()
    sante.outil("ouvrir_application", 0.2, "Ouvert : Spotify")
    sante.outil("terminal", 1.0, "Erreur : commande introuvable")
    sante.outil("terminal", 3.0, "OK")
    sante.demande("claude", 4.0)
    sante.demande("claude", 2.0, "Erreur du service Anthropic (529)")
    r = sante.resume(7)
    assert r["appels"] == 3 and r["echecs"] == 1
    t = r["outils"][0]
    assert t["nom"] == "terminal" and t["echecs"] == 1 and t["duree"] == 2.0 and "introuvable" in t["erreur"]
    assert r["cerveaux"][0] == {"nom": "claude", "n": 2, "echecs": 1, "taux": 0.5, "duree": 3.0, "erreur": "Erreur du service Anthropic (529)"}
    assert "terminal : 1/2 échecs" in sante.texte(7)
    sante.enregistrer_maintenant()
    assert (tmp_path / "sante.json").exists()


# ---------- Telegram ----------
@pytest.fixture
def bot(monkeypatch):
    pytest.importorskip("requests")
    from wesley import connecteurs, telegram
    envoyes = []
    b = telegram.Telegram("telegram", {"appareil": telegram.MACHINE})
    b.code = "123456"
    monkeypatch.setattr(b, "_api", lambda methode, delai=40, fichiers=None, **p: envoyes.append((methode, p)) or {})
    stock = {"telegram": {"type": "telegram", "actif": True, "conf": {}}}
    monkeypatch.setattr(telegram, "_lire", lambda: stock)
    monkeypatch.setattr(telegram, "_ecrire", lambda d: stock.update(d))
    monkeypatch.setattr(b, "_repondre", lambda chat, demande: f"Fait : {demande}")
    return b, envoyes, stock


def _msg(chat, texte):
    return {"chat": {"id": chat}, "text": texte}


def test_un_inconnu_est_ignore_sans_reponse(bot):
    b, envoyes, _ = bot
    b._message(_msg(999, "lance Spotify"))
    b._message(_msg(999, "/start 000000"))
    assert envoyes == [] and b.chats() == []


def test_liaison_avec_le_bon_code_puis_reponse(bot):
    b, envoyes, stock = bot
    b._message(_msg(42, "/start 123456"))
    assert b.chats() == [42] and stock["telegram"]["conf"]["chats"] == "42" and b.code == ""
    assert envoyes[-1][0] == "sendMessage" and "relié" in envoyes[-1][1]["text"]
    b._message(_msg(42, "envoie-moi le devis"))
    assert envoyes[-1][1]["text"] == "Fait : envoie-moi le devis"
    b._message(_msg(7, "/start 123456"))          # le code ne sert qu'une fois
    assert b.chats() == [42]


def test_un_seul_ordinateur_repond(monkeypatch):
    pytest.importorskip("requests")
    from wesley import telegram
    assert telegram.Telegram("t", {"appareil": "AutrePC"}).repond_ici() is False
    assert telegram.Telegram("t", {}).repond_ici() is True


def test_long_message_coupe(bot):
    b, envoyes, _ = bot
    b.conf["chats"] = "42"
    b.envoyer("x" * 9000)
    assert [len(p["text"]) for m, p in envoyes if m == "sendMessage"] == [4000, 4000, 1000]


# ---------- Home Assistant ----------
def test_home_assistant(monkeypatch):
    pytest.importorskip("requests")
    from wesley import connecteurs_maison as cm
    appels = []
    etats = [{"entity_id": "light.salon", "state": "off", "attributes": {"friendly_name": "Lumière du salon"}},
             {"entity_id": "sensor.chambre_temperature", "state": "19.5", "attributes": {"friendly_name": "Chambre", "unit_of_measurement": "°C"}}]

    class Rep:
        def __init__(self, d):
            self.d, self.status_code, self.content = d, 200, b"x"

        def json(self):
            return self.d

        def raise_for_status(self):
            pass

    def requete(methode, url, **kw):
        appels.append((methode, url, kw.get("json")))
        if url.endswith("/api/states"):
            return Rep(etats)
        if "/api/states/" in url:
            return Rep({"state": "on"})
        return Rep([])
    monkeypatch.setattr(cm.requests, "request", requete)
    ha = cm.HomeAssistant("homeassistant", {"url": "http://ha.local:8123"})
    monkeypatch.setattr(ha, "v", lambda c: {"url": "http://ha.local:8123", "jeton": "abc"}[c])
    fs = dict(ha.fonctions())
    assert "19.5 °C" in fs["ha_etats"]("chambre") and "light.salon" not in fs["ha_etats"]("chambre")
    assert fs["ha_action"]("light.salon", "turn_on", "60") == "light.salon : on."
    assert ("POST", "http://ha.local:8123/api/services/light/turn_on", {"entity_id": "light.salon", "brightness_pct": 60}) in appels
