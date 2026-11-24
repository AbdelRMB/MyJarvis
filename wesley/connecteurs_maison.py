"""Connecteurs simples (une adresse et un jeton, pas d'application à déclarer) :

- Home Assistant : la maison connectée (« éteins les lumières du salon », « il fait combien dans la chambre ? »).
  Jeton d'accès longue durée : Home Assistant › ton profil › Sécurité › Jetons d'accès longue durée.
- Discord / Slack : envoyer un message dans un salon (adresse « webhook » du salon). Utile aux automatisations
  (« préviens l'équipe sur Slack quand le site tombe »).
"""
import requests

from .connecteurs import Connecteur


class HomeAssistant(Connecteur):
    type = "homeassistant"
    nom = "Home Assistant"
    description = "Ta maison connectée : lumières, prises, chauffage, capteurs, scènes…"
    icone = "home"
    champs = [{"nom": "url", "libelle": "Adresse de Home Assistant", "type": "text",
               "aide": "ex : http://homeassistant.local:8123 ou ton adresse Nabu Casa"},
              {"nom": "jeton", "libelle": "Jeton d'accès longue durée", "type": "secret"}]
    aide = ("Dans Home Assistant : clique sur ton profil (en bas à gauche) › onglet Sécurité › « Jetons d'accès longue "
            "durée » › Créer un jeton. Copie-le ici avec l'adresse de ton Home Assistant.")

    def _url(self, chemin: str) -> str:
        return self.v("url").rstrip("/") + chemin

    def _appel(self, methode: str, chemin: str, **kw):
        r = requests.request(methode, self._url(chemin), timeout=20,
                             headers={"Authorization": f"Bearer {self.v('jeton')}", "Content-Type": "application/json"}, **kw)
        if r.status_code == 401:
            raise RuntimeError("Jeton Home Assistant refusé (expiré ou supprimé).")
        r.raise_for_status()
        return r.json() if r.content else None

    def etiquette(self) -> str:
        return self.conf.get("nom") or self.v("url").split("//")[-1].split("/")[0] or "Home Assistant"

    def tester(self):
        etats = self._appel("GET", "/api/states")
        return f"Connecté : {len(etats)} appareils et capteurs."

    def fonctions(self):
        def ha_etats(filtre: str = ""):
            """Liste les appareils et capteurs de la maison (Home Assistant) avec leur état : lumières, prises, thermostats, capteurs de température…
            filtre: mot à chercher dans le nom ou l'identifiant (ex : « salon », « light », « temperature ») ; vide = tout"""
            f = filtre.strip().lower()
            lignes = []
            for e in self._appel("GET", "/api/states"):
                nom = e.get("attributes", {}).get("friendly_name") or e["entity_id"]
                if f and f not in nom.lower() and f not in e["entity_id"].lower():
                    continue
                unite = e.get("attributes", {}).get("unit_of_measurement") or ""
                lignes.append(f"{e['entity_id']} — {nom} : {e['state']}{(' ' + unite) if unite else ''}")
            return "\n".join(lignes[:150]) or "Rien ne correspond."

        def ha_action(entite: str, action: str, valeur: str = ""):
            """Agit sur un appareil de la maison (Home Assistant) : allumer, éteindre, basculer, régler une température, lancer une scène…
            entite: identifiant de l'appareil (ex : light.salon ; voir ha_etats)
            action: turn_on, turn_off, toggle, ou un service du domaine (ex : set_temperature, open_cover, activate pour une scène)
            valeur: facultatif : luminosité en % pour une lumière, température pour un thermostat…"""
            domaine = entite.split(".")[0]
            service = {"activate": "turn_on"}.get(action, action)
            donnees = {"entity_id": entite}
            if valeur:
                if domaine == "light":
                    donnees["brightness_pct"] = int(float(valeur))
                elif domaine == "climate":
                    donnees["temperature"] = float(valeur)
                elif domaine in ("cover",):
                    donnees["position"] = int(float(valeur))
                else:
                    donnees["value"] = valeur
            self._appel("POST", f"/api/services/{domaine}/{service}", json=donnees)
            etat = self._appel("GET", f"/api/states/{entite}")
            return f"{entite} : {etat.get('state') if etat else 'fait'}."
        return [("ha_etats", ha_etats), ("ha_action", ha_action)]


class Webhook(Connecteur):
    type = "webhook"
    nom = "Discord / Slack"
    description = "Envoyer un message dans un salon Discord ou Slack (adresse webhook du salon)."
    icone = "send"
    champs = [{"nom": "nom", "libelle": "Nom du salon", "type": "text", "aide": "ex : équipe, alertes, famille"},
              {"nom": "url", "libelle": "Adresse webhook", "type": "secret",
               "aide": "Discord : paramètres du salon › Intégrations › Webhooks ; Slack : Incoming Webhooks"}]
    aide = ("Discord : paramètres du salon › Intégrations › Webhooks › Nouveau webhook › Copier l'URL.\n"
            "Slack : api.slack.com/apps › ton appli › Incoming Webhooks › Add New Webhook to Workspace › copier l'URL.")

    def envoyer(self, texte: str):
        url = self.v("url")
        corps = {"content": texte[:1900]} if "discord" in url else {"text": texte[:3900]}
        r = requests.post(url, json=corps, timeout=20)
        if r.status_code >= 300:
            raise RuntimeError(f"Le salon a refusé le message (HTTP {r.status_code}).")

    def tester(self):
        return "Adresse enregistrée (rien n'est envoyé pendant le test, pour ne pas déranger le salon)."

    def fonctions(self):
        def salon_envoyer(texte: str):
            """Envoie un message dans le salon Discord / Slack de l'utilisateur.
            texte: le message"""
            self.envoyer(texte)
            return f"Message envoyé dans « {self.etiquette()} »."
        return [("salon_envoyer", salon_envoyer)]
