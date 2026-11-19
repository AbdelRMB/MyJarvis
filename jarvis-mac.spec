# -*- mode: python ; coding: utf-8 -*-
# Recette PyInstaller de Jarvis pour macOS — à lancer SUR UN MAC : ./construire-mac.sh
# Produit dist/Jarvis.app (appli de barre des menus, sans icône dans le Dock).
from PyInstaller.utils.hooks import collect_all, collect_submodules

VERSION = open("jarvis/version.py", encoding="utf-8").read().split('VERSION = "')[1].split('"')[0]

datas = [("jarvis/static", "jarvis/static"), ("voix", "voix")]
binaries = []
hiddenimports = (collect_submodules("jarvis") + collect_submodules("uvicorn") + collect_submodules("keyring.backends")
                 + ["pystray._darwin", "pynput.keyboard._darwin", "pynput.mouse._darwin"])

for paquet in ["webview", "openwakeword", "faster_whisper", "ctranslate2", "onnxruntime", "piper", "edge_tts",
               "sounddevice", "_sounddevice_data", "recurring_ical_events", "icalendar", "tokenizers", "certifi",
               "ddgs", "objc", "Foundation", "AppKit", "WebKit", "Quartz", "ApplicationServices"]:
    try:
        d, b, h = collect_all(paquet)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as e:
        print(f"(collect_all {paquet} : {e})")

# mcp : tout sauf mcp.cli (qui exige typer et fait échouer collect_all)
d, b, h = collect_all("mcp", filter_submodules=lambda nom: not nom.startswith("mcp.cli"))
datas += d
binaries += b
hiddenimports += h

a = Analysis(
    ["lanceur.pyw"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["torch", "tensorflow", "matplotlib", "IPython", "jupyter", "pytest", "pywinauto", "comtypes",
              "pythonnet", "clr_loader", "win32api", "win32con", "pygetwindow"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Jarvis", console=False, argv_emulation=False,
          target_arch=None, codesign_identity=None, entitlements_file="entitlements.plist")
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Jarvis")
app = BUNDLE(
    coll,
    name="Jarvis.app",
    icon="jarvis.png",
    bundle_identifier="com.abdel.jarvis",
    version=VERSION,
    info_plist={
        "CFBundleName": "Jarvis",
        "CFBundleDisplayName": "Jarvis",
        "CFBundleShortVersionString": VERSION,
        "LSUIElement": True,                     # icône dans la barre des menus, pas dans le Dock
        "LSMinimumSystemVersion": "12.0",
        "NSHighResolutionCapable": True,
        "NSMicrophoneUsageDescription": "Jarvis écoute quand tu l'appelles (« Jarvis, … ») et transcrit ta voix sur ton Mac.",
        "NSAppleEventsUsageDescription": "Jarvis pilote tes applications (ouvrir, fermer, régler le volume) quand tu le lui demandes.",
        "NSScreenCaptureUsageDescription": "Jarvis regarde ton écran quand tu lui demandes ce qui s'y trouve.",
    },
)
