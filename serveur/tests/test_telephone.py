"""Wesley mobile ne s'ouvre que sur un téléphone ; l'appli de bureau garde l'accès à l'API.

Lancer : cd serveur && WESLEY_DB=/tmp/wesley-test.db python -m pytest tests -q
"""
import os
import sys
import tempfile

os.environ.setdefault("WESLEY_DB", os.path.join(tempfile.mkdtemp(), "wesley.db"))
os.environ["WESLEY_CLE_APPLI"] = "cle-test"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

import app as serveur  # noqa: E402

client = TestClient(serveur.app)
ANDROID = "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Mobile Safari/537.36"
IPHONE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 19_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
          "Version/19.0 Mobile/15E148 Safari/604.1")
IPAD = ("Mozilla/5.0 (iPad; CPU OS 19_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/19.0 "
        "Mobile/15E148 Safari/604.1")
MAC = "Mozilla/5.0 (Macintosh; Intel Mac OS X 15_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/19.0 Safari/605.1.15"
WINDOWS = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"
TABLETTE = "Mozilla/5.0 (Linux; Android 15; SM-X910) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"


def get(chemin, ua, **h):
    return client.get(chemin, headers={"User-Agent": ua, **h})


def test_page_mobile_sur_telephone():
    for ua in (ANDROID, IPHONE):
        r = get("/mobile/config.js", ua)
        assert r.status_code == 200, ua
        assert "private" in r.headers["cache-control"]


def test_page_mobile_refusee_sur_ordinateur():
    for ua in (MAC, WINDOWS, TABLETTE, IPAD, "curl/8.0"):
        r = get("/mobile/", ua)
        assert r.status_code == 403, ua
        assert "ne fonctionne que sur un téléphone" in r.text
        assert r.headers["cache-control"] == "no-store"
        assert get("/mobile/config.js", ua).status_code == 403   # la clé de l'appli n'est pas donnée


def test_indice_client_mobile():
    # Chrome envoie Sec-CH-UA-Mobile : « ?0 » (mode ordinateur) l'emporte sur un User-Agent Android trompeur
    assert get("/mobile/config.js", ANDROID, **{"Sec-CH-UA-Mobile": "?0"}).status_code == 403
    assert get("/mobile/config.js", WINDOWS, **{"Sec-CH-UA-Mobile": "?1"}).status_code == 200


def test_pages_legales_partout():
    for chemin in ("/mobile/confidentialite.html", "/mobile/mentions-legales.html"):
        assert get(chemin, WINDOWS).status_code == 200


def test_api_navigateur_ordinateur_refusee():
    h = {"X-Wesley-Appli": "cle-test"}
    assert client.get("/v1/sante", headers={"User-Agent": WINDOWS, **h}).status_code == 403
    assert client.get("/v1/sante", headers={"User-Agent": ANDROID, **h}).status_code == 200


def test_appli_de_bureau_non_concernee():
    # l'appli de bureau (requests, User-Agent « Wesley ») garde l'accès à l'API
    assert client.get("/v1/sante", headers={"User-Agent": "Wesley", "X-Wesley-Appli": "cle-test"}).status_code == 200
    # et sans la clé, toujours le 404 habituel
    assert client.get("/v1/sante", headers={"User-Agent": "Wesley"}).status_code == 404
