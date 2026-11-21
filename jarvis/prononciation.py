"""Prononciation : prépare le texte avant la synthèse vocale pour que Jarvis dise correctement les mots techniques,
sigles, versions, unités, liens, chemins et noms de marques (quelle que soit la voix : Microsoft, Piper, Kyutai).

- DICTIONNAIRE : mot (insensible à la casse) -> façon de le dire, écrite pour une voix française.
- Sigles inconnus en majuscules (2 à 5 lettres) : épelés (« SSD » -> « èss èss dé »).
- Versions, unités, symboles, adresses web, e-mails, chemins, extensions, noms_avec_tirets et motsEnCamelCase.
- L'utilisateur peut ajouter les siennes (« on dit "Kyutaï" ») : config « prononciations » (outil apprendre_prononciation).
"""
import re

from .config import CONFIG

LETTRES = {"a": "a", "b": "bé", "c": "cé", "d": "dé", "e": "e", "f": "èf", "g": "jé", "h": "ache", "i": "i", "j": "ji",
           "k": "ka", "l": "èl", "m": "èm", "n": "ène", "o": "o", "p": "pé", "q": "ku", "r": "èr", "s": "èss", "t": "té",
           "u": "u", "v": "vé", "w": "double vé", "x": "ix", "y": "i grec", "z": "zèd"}

# mot = prononciation (une par ligne ; « | » sépare plusieurs écritures du même mot)
_BRUT = """
api = a pé i
apis = a pé i
json = djé-zonne
yaml = ya-mel
toml = to-mel
xml = ix èm èl
html = ache té èm èl
css = cé èss èss
sql = èss ku èl
mysql = maï èss ku èl
postgresql | postgres = post-gresse
sqlite = èss ku lite
nosql = no èss ku èl
mongodb = mongo dé bé
redis = rédisse
url | urls = u èr èl
uri = u èr i
http = ache té té pé
https = ache té té pé èss
ssh = èss èss ache
ssl = èss èss èl
tls = té èl èss
ftp = èf té pé
sftp = èss èf té pé
dns = dé ène èss
ip = i pé
ipv4 = i pé vé 4
ipv6 = i pé vé 6
tcp = té cé pé
udp = u dé pé
vpn = vé pé ène
vps = vé pé èss
cpu = cé pé u
gpu = jé pé u
ram = rame
ssd = èss èss dé
hdd = ache dé dé
usb = u èss bé
usb-c = u èss bé cé
hdmi = ache dé èm i
wifi | wi-fi = wi-fi
bluetooth = blou-tousse
ia = i a
llm = èl èl èm
gpt = jé pé té
chatgpt = tchat jé pé té
openai = opène a i
anthropic = anne-tro-pique
claude = clôde
haiku = haïkou
opus = opusse
ollama = olama
mistral = mistral
llama = lama
gemini = djé-mi-naï
copilot = copilote
whisper = ouisse-peur
piper = paï-peur
kyutai = kyou-taï
mlx = èm èl ix
onnx = o ène ène ix
cuda = kouda
pytorch = paï-torche
tensorflow = tenseur-flo
numpy = num-paï
pandas = pandasse
python = pi-tonne
pip = pip
venv = vé-ène-vé
django = djan-go
flask = flasque
fastapi = fast a pé i
uvicorn = u-vi-corne
node | nodejs | node.js = nodde
npm = ène pé èm
npx = ène pé ix
pnpm = pé ène pé èm
yarn = yarne
deno = dé-no
bun = beune
javascript = java-script
typescript = taïpe-script
js = ji èss
ts = té èss
py = paï
md = èm dé
txt = texte
sh = èss ache
env = ène-vé
cfg = config
log = logue
logs = logues
jsx = ji èss ix
tsx = té èss ix
react = ri-akt
vue | vuejs = vu
angular = angu-lar
svelte = svelte
nextjs | next.js = nekst
vite = vite
webpack = ouèbe-pak
tailwind = teil-ouinnde
zustand = tsou-chtann
php = pé ache pé
laravel = la-ra-vel
ruby = rou-bi
rust = reust
golang = go-lang
kotlin = kot-line
swift = souift
swiftui = souift u i
xcode = ix-code
java = java
c++ = cé plus plus
c# = cé charpe
.net | dotnet = dot-nète
powershell = pa-oueur-chel
bash = bache
zsh = zède-èss-ache
shell = chel
sudo = sou-dou
apt = a pé té
brew | homebrew = brou
git = guite
github = guite-heube
gitlab = guite-labe
gitea = guite-i-a
bitbucket = bite-beuquette
commit = comite
commits = comites
push = pouche
merge = meurdj
rebase = ri-béze
branch = branche
checkout = tchèque-a-out
pr = pé èr
docker = doqueur
dockerfile = doqueur-faïle
compose = com-pose
kubernetes | k8s = kou-beur-né-tisse
jenkins = djène-kinnse
nginx = ène-djine-ix
apache = apache
cloudflare = claoud-flère
aws = a double vé èss
azure = ajeur
gcp = jé cé pé
ovh | ovhcloud = o vé ache
vercel = veur-sel
netlify = nète-li-faï
heroku = é-ro-kou
firebase = faïeur-béze
supabase = soupa-béze
linux = li-nuxe
ubuntu = ou-boun-tou
debian = dé-bi-anne
macos = mac o èss
ios = aï o èss
ipados = aï pad o èss
android = an-droïde
windows = ouinne-doze
iphone = aï-faune
ipad = aï-pad
macbook = mac-bouk
imac = aï-mac
airpods = èr-podze
icloud = aï-claoud
onedrive = ouane-draïve
dropbox = drop-boxe
google = gou-gueule
gmail = jé-mèl
outlook = aout-louk
youtube = you-tioube
spotify = spo-ti-faï
discord = disse-corde
slack = slak
notion = nauche-eune
trello = trélo
figma = figma
canva = canva
photoshop = photo-chop
excel = ixe-sel
word = oueurde
powerpoint = pa-oueur-pointe
teams = tímze
zoom = zoum
whatsapp = ouatsap
telegram = télégramme
signal = signal
instagram = insta-gramme
tiktok = tik-tok
twitter = touiteur
linkedin = linke-dine
facebook = fèsse-bouk
reddit = rèdite
twitch = touitche
netflix = nète-flix
amazon = amazone
paypal = pé-pal
stripe = straïpe
chrome = crome
firefox = faïeur-fox
safari = safari
edge = èdje
vscode | vs code = vé èss code
vim = vim
neovim = néo-vim
emacs = i-maxe
jetbrains = djète-brèïnze
intellij = intèli-dji
pycharm = paï-tcharme
cursor = keur-seur
backend = bak-ènde
frontend = fronte-ènde
fullstack = foul-stak
devops = dève-opse
build = bilde
builds = bildes
deploy = di-ploï
debug = di-beug
bug = beug
bugs = beugues
feature = fi-tcheur
features = fi-tcheurs
release = ri-lize
releases = ri-lizes
update = eup-dète
upgrade = eup-grède
download = daoun-lode
upload = eup-lode
login = lo-guine
logout = log-aoute
password = passe-oueurde
token = to-quène
tokens = to-quènes
prompt = prompte
prompts = promptes
cache = cache
server = seur-veur
cluster = cleus-teur
container = conté-neur
framework = frème-oueurke
library = laï-brè-ri
package = pa-kèdje
packages = pa-kèdjes
script = script
scripts = scripts
runtime = reune-taïme
webhook = ouèbe-houk
endpoint = ènde-pointe
payload = pé-lode
dashboard = dache-borde
workflow = oueurk-flo
pipeline = paï-pe-laïne
timeout = taïme-aoute
localhost = locale-host
cookie = couki
cookies = coukis
startup = starte-eup
mail = mèl
email | e-mail = i-mèl
emails | e-mails = i-mèls
smartphone = smarte-faune
software = sofete-ouèr
hardware = hard-ouèr
firmware = feurme-ouèr
streaming = stri-mingue
podcast = pod-caste
playlist = plé-liste
gaming = gué-mingue
online = onne-laïne
offline = off-laïne
check = tchèque
checklist = tchèque-liste
meeting = mi-tingue
deadline = dède-laïne
ok = o-ké
okay = o-ké
etc = ètsétéra
cv = cé vé
pdf = pé dé èf
png = pé ène jé
jpg | jpeg = jé-pègue
gif = jif
svg = èss vé jé
mp3 = èm pé 3
mp4 = èm pé 4
csv = cé èss vé
zip = zipe
dmg = dé èm jé
exe = ixe
iso = i-zo
qr = ku èr
faq = èf a ku
rgpd = èr jé pé dé
saas = sasse
b2b = bé tou bé
ui = u i
ux = u ix
id = i dé
ids = i dé
cli = cé èl i
gui = jé u i
ide = i dé e
sdk = èss dé ka
oauth = o-oth
2fa = double authentification
jwt = ji double vé té
cors = corse
crud = creude
rest = reste
graphql = graf ku èl
grpc = jé èr pé cé
mcp = èm cé pé
rss = èr èss èss
seo = èss e o
cdn = cé dé ène
lan = lane
wan = ouane
nas = nasse
raid = rède
bios = bi-ose
uefi = u e èf i
ok google = o-ké gou-gueule
siri = siri
alexa = alèxa
jarvis = djar-visse
"""


def _charger_dictionnaire() -> dict:
    d = {}
    for ligne in _BRUT.strip().splitlines():
        if "=" not in ligne:
            continue
        mots, dire = ligne.split("=", 1)
        for m in mots.split("|"):
            if m.strip():
                d[m.strip().lower()] = dire.strip()
    return d


DICTIONNAIRE = _charger_dictionnaire()
UNITES = {"Ko": "kilo-octets", "Mo": "méga-octets", "Go": "giga-octets", "To": "téra-octets", "KB": "kilo-octets",
          "MB": "méga-octets", "GB": "giga-octets", "TB": "téra-octets", "Mb/s": "mégabits par seconde",
          "Mbps": "mégabits par seconde", "Gbps": "gigabits par seconde", "MHz": "mégahertz", "GHz": "gigahertz",
          "Hz": "hertz", "ms": "millisecondes", "km/h": "kilomètres heure", "km": "kilomètres", "kg": "kilos",
          "°C": "degrés", "°": "degrés", "W": "watts", "kW": "kilowatts", "kWh": "kilowattheures", "fps": "images par seconde",
          "px": "pixels", "dpi": "points par pouce", "mAh": "milliampères-heure"}
_LOGICIELS = r"(?:version|v|python|node|ios|macos|android|windows|java|php|ruby|go|rust|jarvis|ubuntu|debian|swift|chrome|firefox)"


def _epeler(sigle: str) -> str:
    return " ".join(LETTRES.get(c.lower(), c) for c in sigle)


def _nombre_en_points(m) -> str:
    return " point ".join(m.group(0).lstrip("vV").split("."))


def _url(m) -> str:
    hote = re.sub(r"^www\.", "", m.group(2))
    return "le lien vers " + hote.replace(".", " point ")


def _chemin(m) -> str:
    nom = m.group(0).rstrip("/").split("/")[-1].split("\\")[-1]
    return f"le fichier {nom}" if "." in nom else f"le dossier {nom}"


def _fichier(m) -> str:
    nom, ext = m.group(1), m.group(2)
    dire = DICTIONNAIRE.get(ext.lower()) or (_epeler(ext) if len(ext) <= 4 else ext)
    return f"{nom} point {dire}"


def preparer(texte: str, langue: str = "") -> str:
    """Le texte tel qu'il doit être prononcé."""
    langue = langue or CONFIG.get("langue") or "fr"
    t = texte
    # emojis et symboles décoratifs
    t = re.sub(r"[\U0001F000-\U0001FAFF☀-➿️]", "", t)
    # e-mails, adresses web, chemins
    t = re.sub(r"\b([\w.+-]+)@([\w-]+(?:\.[\w-]+)+)\b",
               lambda m: f"{m.group(1)} arobase {m.group(2).replace('.', ' point ')}", t)
    t = re.sub(r"(https?://)?((?:www\.)?[\w-]+(?:\.[\w-]+)*\.(?:com|fr|org|net|io|dev|ai|app|co|be|ch|ca|eu|me|tv|gg|sh))(/\S*)?",
               lambda m: _url(m) if (m.group(1) or m.group(3) or m.group(2).startswith("www.")) else m.group(2).replace(".", " point "), t)
    t = re.sub(r"(?:~|[A-Za-z]:)?(?:[/\\][\w.-]*\w){2,}[/\\]?", _chemin, t)
    if langue != "fr":
        return re.sub(r"\s{2,}", " ", t).strip()
    # versions : « v1.8.2 », « Python 3.12 », « 1.8.2 »
    t = re.sub(r"\bv?\d+\.\d+\.\d+(?:\.\d+)?\b", _nombre_en_points, t)
    t = re.sub(rf"(?i)(\b{_LOGICIELS}\s+)(\d+)\.(\d+)\b", lambda m: f"{m.group(1)}{m.group(2)} point {m.group(3)}", t)
    t = re.sub(r"\b(\d+)\.(\d+)\b", r"\1 virgule \2", t)                 # 3.5 -> 3 virgule 5
    # fichiers : « app.py », « rapport.pdf »
    t = re.sub(r"\b([\w-]+)\.([A-Za-z0-9]{1,5})\b(?!\.\w)", _fichier, t)
    # unités après un nombre
    for u, dire in sorted(UNITES.items(), key=lambda x: -len(x[0])):
        t = re.sub(rf"(\d)\s?{re.escape(u)}(?![\w/])", rf"\1 {dire}", t)
    # symboles
    t = re.sub(r"(\d)\s?%", r"\1 pour cent", t)
    t = re.sub(r"(\d)\s?€", r"\1 euros", t)
    t = re.sub(r"\$\s?(\d+(?:[.,]\d+)?)", r"\1 dollars", t)
    t = re.sub(r"(\d)\s?\$", r"\1 dollars", t)
    t = re.sub(r"\s(?:->|=>|→)\s", " puis ", t)
    t = re.sub(r"\s&\s", " et ", t)
    t = re.sub(r"#(\d+)", r"numéro \1", t)
    t = re.sub(r"\b(\d+)\s?x\s?(\d+)\b", r"\1 par \2", t)
    # noms_en_snake_case, mots-avec-tirets techniques, motsEnCamelCase
    t = re.sub(r"\b(\w+)_(\w+)\b", lambda m: m.group(0).replace("_", " "), t)
    t = re.sub(r"\b([a-z]+)([A-Z][a-z]+)+\b", lambda m: re.sub(r"(?<=[a-z])(?=[A-Z])", " ", m.group(0)), t)
    # dictionnaire (+ les prononciations apprises de l'utilisateur), du plus long au plus court
    perso = {k.lower(): v for k, v in (CONFIG.get("prononciations") or {}).items()}
    dico = {**DICTIONNAIRE, **perso}
    for mot in sorted(dico, key=len, reverse=True):
        t = re.sub(rf"(?<![\w.'’@-]){re.escape(mot)}(?![\w'’@-])", dico[mot], t, flags=re.I)
    # sigles restants en majuscules (2 à 5 lettres) : épelés, sauf les mots courants
    t = re.sub(r"\b[A-Z]{2,5}\b", lambda m: m.group(0) if m.group(0) in _MOTS_MAJ else _epeler(m.group(0)), t)
    return re.sub(r"\s{2,}", " ", t).strip()


# mots en majuscules qui se lisent comme des mots (pas épelés)
_MOTS_MAJ = {"OK", "NASA", "UNESCO", "OTAN", "ONU", "COVID", "SNCF", "RATP", "CAF", "SMIC", "PACS", "CAC", "BAC", "LOL",
             "STOP", "JE", "TU", "IL", "LA", "LE", "LES", "DE", "DU", "ET", "OU", "UN", "UNE", "EN", "AU", "AUX", "PAS",
             "OUI", "NON", "MOI", "TOI", "LUI", "NOUS", "VOUS", "EUX"}


def apprendre(mot: str, prononciation: str):
    from .config import sauver_config
    perso = dict(CONFIG.get("prononciations") or {})
    perso[mot.strip()] = prononciation.strip()
    CONFIG["prononciations"] = perso
    sauver_config(["prononciations"])
