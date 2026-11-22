"""Codes de double authentification (TOTP, RFC 6238) : les mêmes que Google / Microsoft Authenticator.

On donne à Wesley la clé secrète montrée lors de l'ajout de l'appli d'authentification (sous le QR code : « Impossible
de scanner ? Saisir la clé ») ou l'adresse otpauth://… du QR code ; il calcule le code à 6 chiffres du moment.
"""
import base64
import hashlib
import hmac
import struct
import time
from urllib.parse import parse_qs, unquote, urlparse


def lire(secret_ou_uri: str) -> dict:
    """Clé base32 seule, ou otpauth://totp/...?secret=...&digits=6&period=30&algorithm=SHA1."""
    s = secret_ou_uri.strip()
    p = {"secret": s, "chiffres": 6, "periode": 30, "algo": "sha1"}
    if s.lower().startswith("otpauth://"):
        q = {k: v[0] for k, v in parse_qs(urlparse(s).query).items()}
        p.update(secret=q.get("secret", ""), chiffres=int(q.get("digits", 6)), periode=int(q.get("period", 30)),
                 algo=q.get("algorithm", "SHA1").lower(), compte=unquote(urlparse(s).path.lstrip("/")))
    p["secret"] = p["secret"].replace(" ", "").replace("-", "").upper()
    base64.b32decode(p["secret"] + "=" * (-len(p["secret"]) % 8))   # clé invalide : lève une erreur
    return p


def code(secret_ou_uri: str, instant: float | None = None) -> tuple[str, int]:
    """(code, secondes restantes avant le suivant)."""
    p = lire(secret_ou_uri)
    t = time.time() if instant is None else instant
    cle = base64.b32decode(p["secret"] + "=" * (-len(p["secret"]) % 8))
    compteur = struct.pack(">Q", int(t // p["periode"]))
    h = hmac.new(cle, compteur, getattr(hashlib, p["algo"])).digest()
    o = h[-1] & 0x0F
    n = (struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % (10 ** p["chiffres"])
    return str(n).zfill(p["chiffres"]), int(p["periode"] - t % p["periode"])


def code_frais(secret_ou_uri: str) -> str:
    """Un code qui ne va pas expirer pendant la saisie (attend le suivant s'il reste moins de 4 s)."""
    c, reste = code(secret_ou_uri)
    if reste < 4:
        time.sleep(reste + 0.5)
        c, _ = code(secret_ou_uri)
    return c
