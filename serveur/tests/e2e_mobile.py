"""Test de bout en bout de Wesley mobile : vrai serveur de comptes local + vraie appli (WebKit, iPhone émulé)
+ un « PC » simulé en Python (même protocole que wesley/appareils.py). L'API de Claude est simulée.

Lancer (après `cd interface && npm run build:mobile`) :
    pip install -r serveur/requirements.txt playwright requests cryptography && playwright install webkit
    cd serveur && WESLEY_DB=/tmp/wesley-e2e.db WESLEY_CLE_APPLI=cle-e2e uvicorn app:app --port 8765 &
    python serveur/tests/e2e_mobile.py
"""
import base64
import hashlib
import json
import os
import threading
import time
import uuid

import requests
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from playwright.sync_api import sync_playwright

URL = os.environ.get("WESLEY_URL", "http://127.0.0.1:8765")
H = {"X-Wesley-Appli": "cle-e2e", "User-Agent": "Wesley"}
EMAIL, MDP = f"e2e{int(time.time())}@test.fr", "motdepasse-e2e"

def deriver():
    m = hashlib.scrypt(MDP.encode(), salt=b"wesley-compte:" + EMAIL.encode(), n=2**15, r=8, p=1, dklen=64, maxmem=128*1024*1024)
    return m[:32].hex(), m[32:]

def chiffrer(d, cle):
    n = os.urandom(12)
    return base64.b64encode(n + AESGCM(cle).encrypt(n, json.dumps(d).encode(), b"wesley-ordre")).decode()

def dechiffrer(b, cle):
    r = base64.b64decode(b)
    return json.loads(AESGCM(cle).decrypt(r[:12], r[12:], b"wesley-ordre"))

recus = []

def pc_simule(stop):
    auth, cle = deriver()
    jeton = requests.post(URL + "/v1/connexion", json={"email": EMAIL, "cle_auth": auth, "appareil": "PC-Test"}, headers=H).json()["jeton"]
    h = {**H, "Authorization": f"Bearer {jeton}"}
    requests.post(URL + "/v1/appareils/presence", json={"nom": "PC-Test", "plateforme": "windows", "version": "2.1.0", "accepte": True}, headers=h)
    rev = 0
    while not stop.is_set():
        requests.post(URL + "/v1/appareils/presence", json={"nom": "PC-Test", "plateforme": "windows", "version": "2.1.0", "accepte": True}, headers=h)
        r = requests.get(URL + f"/v1/attendre?depuis={rev}", headers=h, timeout=40).json()
        rev = r["revision"]
        for o in r["ordres"]:
            d = dechiffrer(o["blob"], cle)
            recus.append(d)
            rep = {"ok": True, "resultat": f"Fait sur PC-Test : {d.get('texte', d.get('type'))[-60:]}"}
            requests.post(URL + f"/v1/ordres/{o['id']}/reponse", json={"blob": chiffrer(rep, cle)}, headers=h)
    return h, cle

def ordre_vers_telephone(contenu):
    auth, cle = deriver()
    jeton = requests.post(URL + "/v1/connexion", json={"email": EMAIL, "cle_auth": auth, "appareil": "PC-2"}, headers=H).json()["jeton"]
    h = {**H, "Authorization": f"Bearer {jeton}"}
    tel = next(a for a in requests.get(URL + "/v1/appareils", headers=h).json() if a["plateforme"] == "telephone")
    ordre = {**contenu, "nonce": uuid.uuid4().hex, "ts": time.time(), "de": "PC-2", "vers": tel["id"]}
    oid = requests.post(URL + "/v1/ordres", json={"vers": tel["id"], "blob": chiffrer(ordre, cle)}, headers=h).json()["id"]
    for _ in range(6):
        r = requests.get(URL + f"/v1/ordres/{oid}/attendre", headers=h, timeout=40).json()
        if r["pret"]:
            return dechiffrer(r["blob"], cle)
    return None

CAPTURES = os.environ.get("WESLEY_CAPTURES", "/tmp")


def etape(nom):
    print(f"✓ {nom}", flush=True)

with sync_playwright() as p:
    nav = p.webkit.launch()
    # 1. ordinateur : page de refus
    pc = nav.new_page(viewport={"width": 1440, "height": 900})
    r = pc.goto(URL + "/mobile/")
    assert r.status == 403 and "ne fonctionne que sur un téléphone" in pc.content()
    etape("navigateur d'ordinateur : page de refus (403)")
    # 1b. ordinateur qui se fait passer pour un téléphone (User-Agent) mais sans écran tactile : refus côté page
    faux = nav.new_page(user_agent=p.devices["iPhone 15"]["user_agent"], viewport={"width": 1440, "height": 900})
    faux.goto(URL + "/mobile/")
    faux.wait_for_selector("text=ne fonctionne que sur un téléphone")
    assert faux.locator("text=Se connecter").count() == 0
    etape("User-Agent de téléphone sur un ordinateur : refus côté page")

    # 2. téléphone : création du compte
    ctx = nav.new_context(**p.devices["iPhone 15"], service_workers="block")
    tel = ctx.new_page()
    erreurs = []
    tel.on("pageerror", lambda e: erreurs.append(str(e)))
    tel.goto(URL + "/mobile/")
    tel.click("text=Créer un compte")
    tel.fill("input[autocomplete=given-name]", "Testeur")
    tel.fill("input[type=email]", EMAIL)
    tel.fill("input[type=password]", MDP)
    tel.check("input[type=checkbox]")
    tel.click("button[type=submit]")
    tel.wait_for_selector("text=Bonjour Testeur", timeout=20000)
    tel.screenshot(path=CAPTURES + "/1-assistant.png")
    etape("téléphone : compte créé, écran Wesley affiché")

    # 3. PC simulé en ligne
    stop = threading.Event()
    threading.Thread(target=pc_simule, args=(stop,), daemon=True).start()
    time.sleep(2)

    # 4. À faire
    tel.click("nav >> text=À faire")
    tel.fill("input[placeholder='Nouvelle tâche…']", "Acheter du pain")
    tel.press("input[placeholder='Nouvelle tâche…']", "Enter")
    tel.wait_for_selector("text=Acheter du pain")
    time.sleep(1.5)
    auth, _ = deriver()
    j = requests.post(URL + "/v1/connexion", json={"email": EMAIL, "cle_auth": auth, "appareil": "verif"}, headers=H).json()["jeton"]
    hv = {**H, "Authorization": f"Bearer {j}"}
    doc = requests.get(URL + "/v1/documents/afaire", headers=hv).json()["contenu"]
    assert doc and doc[0]["titre"] == "Acheter du pain" and doc[0]["statut"] == "a_faire", doc
    etape("À faire : tâche ajoutée sur le téléphone, présente dans le compte (format du bureau)")
    # changement fait « sur l'ordinateur » : visible sur le téléphone en temps réel
    doc[0]["statut"] = "en_cours"
    doc.append({**doc[0], "id": "pc000001", "titre": "Ajouté depuis le PC", "statut": "a_faire"})
    requests.put(URL + "/v1/documents/afaire", json={"contenu": doc}, headers=hv)
    tel.wait_for_selector("text=Ajouté depuis le PC", timeout=10000)
    tel.screenshot(path=CAPTURES + "/2-afaire.png")
    etape("À faire : modification faite sur un ordinateur reçue en temps réel")

    # 5. Mémoire
    requests.post(URL + "/v1/faits", json={"fait": "Testeur aime le café serré", "categorie": "preference", "appareil": "PC-Test"}, headers=hv)
    tel.click("nav >> text=Mémoire")
    tel.wait_for_selector("text=Testeur aime le café serré", timeout=10000)
    tel.click("text=Testeur aime le café serré")
    tel.fill("textarea", "Testeur aime le café allongé")
    tel.click("text=Enregistrer")
    time.sleep(1.5)
    faits = requests.get(URL + "/v1/faits", headers=hv).json()
    assert [f["fait"] for f in faits] == ["Testeur aime le café allongé"], faits
    etape("Mémoire : souvenir du PC reçu, modifié sur le téléphone, modification dans le compte")

    # 6. Appareils
    tel.click("nav >> text=Appareils")
    tel.wait_for_selector("text=PC-Test", timeout=10000)
    tel.screenshot(path=CAPTURES + "/3-appareils.png")
    etape("Appareils : le PC est listé")

    # 7. Conversation sans clé API : relais par le PC (ordre chiffré, réponse affichée)
    tel.click("nav >> text=Wesley")
    tel.fill("textarea", "Sur mon PC, ouvre Spotify")
    tel.click("button[aria-label=Envoyer]")
    tel.wait_for_selector("text=Fait sur PC-Test", timeout=40000)
    assert any("ouvre Spotify" in d.get("texte", "") for d in recus), recus
    tel.screenshot(path=CAPTURES + "/4-relais.png")
    etape("Assistant : sans clé API, la demande est traitée par le PC (relais chiffré) et la réponse s'affiche")
    time.sleep(1.5)
    lignes = [l["ligne"] for l in requests.get(URL + "/v1/historique", headers=hv).json()]
    assert any("Testeur: Sur mon PC, ouvre Spotify" in l for l in lignes) and any("Wesley: Fait sur PC-Test" in l for l in lignes), lignes
    etape("Historique : la conversation du téléphone est dans le compte")

    # 8. Ordre du PC vers le téléphone (fichier) avec confirmation à l'écran
    res = {}
    t = threading.Thread(target=lambda: res.update(r=ordre_vers_telephone({"type": "ecrire_fichier", "chemin": "~/Desktop/note.txt",
                                                                            "contenu": base64.b64encode(b"bonjour").decode()})))
    t.start()
    tel.wait_for_selector("text=demande d'exécuter sur ce téléphone", timeout=40000)
    tel.screenshot(path=CAPTURES + "/5-confirmation.png")
    tel.click("text=Accepter")
    t.join(60)
    assert res.get("r", {}).get("ok"), res
    tel.click("nav >> text=Appareils")
    tel.wait_for_selector("text=note.txt")
    etape("Ordre PC → téléphone : confirmation à l'écran, fichier reçu dans « Fichiers reçus »")

    # 9. Plus / Réglages / Automatisations
    tel.click("nav >> text=Plus")
    tel.click("text=Automatisations")
    tel.wait_for_selector("text=Aucune automatisation")
    tel.screenshot(path=CAPTURES + "/7-autos.png")
    tel.click("header button[aria-label=Ajouter]")
    tel.wait_for_timeout(800)
    tel.screenshot(path=CAPTURES + "/8-nouvelle.png")
    tel.fill("input[placeholder^='Phrase']", "mode travail")
    tel.fill("textarea", "Ouvre VS Code et Slack sur mon PC")
    tel.click("text=Créer")
    tel.wait_for_selector("text=Quand tu dis « mode travail »")
    autos = requests.get(URL + "/v1/documents/automatisations", headers=hv).json()["contenu"]
    assert autos[0]["declencheur"]["type"] == "commande" and autos[0]["declencheur"]["phrase"] == "mode travail", autos
    etape("Automatisations : routine créée au format du bureau")
    tel.click("button[aria-label=Retour]")
    tel.click("text=Réglages")
    tel.wait_for_selector("text=Cerveau", timeout=5000)
    tel.screenshot(path=CAPTURES + "/6-reglages.png", full_page=True)
    etape("Réglages : affichés (cerveau en relais faute de clé)")
    for ecran, attendu in (("Services connectés", "Tes services"), ("Tâches de fond", "Nouvelle tâche"), ("Tickets", "Nouveau ticket")):
        tel.click("button[aria-label=Retour]")
        tel.click(f"text={ecran}")
        tel.wait_for_selector(f"text={attendu}", timeout=5000)
    tel.fill("input[placeholder=Titre]", "Test depuis le téléphone")
    tel.click("text=Envoyer au développeur")
    tel.wait_for_selector("text=Ticket envoyé.", timeout=8000)
    tel.wait_for_selector("text=Test depuis le téléphone", timeout=8000)
    t2 = requests.get(URL + "/v1/tickets", headers=hv).json()
    assert t2[0]["plateforme"] == "telephone", t2
    tel.screenshot(path=CAPTURES + "/9-tickets.png")
    etape("Services, Tâches de fond, Tickets : affichés ; ticket envoyé")
    tel.click("nav >> text=Mémoire")
    tel.click("button[aria-label=Journal]")
    tel.wait_for_selector("text=Journal de la mémoire")
    etape("Mémoire : journal affiché")
    tel.click("button[aria-label=Fermer]")
    # 10. Cerveau Claude : clé saisie sur le téléphone (coffre chiffré), boucle outil → réponse (API simulée)
    tel.click("nav >> text=Plus"); tel.click("text=Réglages")
    tel.fill("input[placeholder='Colle ta clé']", "sk-ant-test")
    tel.click("button:text-is('OK')")
    tel.wait_for_selector("text=Clé enregistrée", timeout=8000)
    auth, cle = deriver()
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM as A
    blob = base64.b64decode(requests.get(URL + "/v1/moi", headers=hv).json()["coffre"])
    coffre = json.loads(A(cle).decrypt(blob[:12], blob[12:], b"wesley-coffre"))
    assert coffre["ANTHROPIC_API_KEY"] == "sk-ant-test", coffre
    etape("Réglages : clé API chiffrée dans le coffre du compte (lisible par le bureau)")
    appels = []
    def claude(route):
        corps = json.loads(route.request.post_data)
        appels.append(corps)
        assert route.request.headers["x-api-key"] == "sk-ant-test"
        if len(appels) == 1:
            contenu = [{"type": "tool_use", "id": "t1", "name": "ajouter_a_faire", "input": {"titre": "Appeler le garage", "rappel": "2030-01-01 10:00"}}]
            stop_r = "tool_use"
        else:
            assert corps["messages"][-1]["content"][0]["type"] == "tool_result"
            contenu = [{"type": "text", "text": "C'est noté, je te rappelle d'appeler le garage."}]
            stop_r = "end_turn"
        route.fulfill(status=200, content_type="application/json", headers={"access-control-allow-origin": "*"},
                      body=json.dumps({"content": contenu, "stop_reason": stop_r}))
    tel.route("https://api.anthropic.com/v1/messages", claude)
    tel.click("nav >> text=Wesley")
    tel.fill("textarea", "Rappelle-moi d'appeler le garage")
    tel.click("button[aria-label=Envoyer]")
    tel.wait_for_selector("text=C'est noté", timeout=20000)
    assert any(t["name"] == "demander_a_appareil" for t in appels[0]["tools"] if "name" in t)
    assert "TÉLÉPHONE" in appels[0]["system"][0]["text"] and "café allongé" in appels[0]["system"][0]["text"]
    time.sleep(1.5)
    doc = requests.get(URL + "/v1/documents/afaire", headers=hv).json()["contenu"]
    assert any(x["titre"] == "Appeler le garage" and x["rappel"] == "2030-01-01T10:00" for x in doc), doc
    tel.screenshot(path=CAPTURES + "/10-claude.png")
    etape("Cerveau Claude : outil ajouter_a_faire exécuté sur le téléphone, mémoire dans les instructions, réponse affichée")
    stop.set()
    assert not erreurs, erreurs
    etape("aucune erreur JavaScript")
    nav.close()
print("TOUT EST BON")
