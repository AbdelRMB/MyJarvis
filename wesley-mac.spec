# -*- mode: python ; coding: utf-8 -*-
# Recette PyInstaller de Wesley pour macOS — à lancer SUR UN MAC : ./construire-mac.sh
# Produit dist/Wesley.app (appli de barre des menus, sans icône dans le Dock).
import os

from PyInstaller.utils.hooks import collect_all, collect_submodules

VERSION = open("wesley/version.py", encoding="utf-8").read().split('VERSION = "')[1].split('"')[0]

datas = [("wesley/static", "wesley/static"), ("voix", "voix")]
datas += [("eveil", "eveil")] if os.path.exists("eveil/hey_wesley.onnx") else []   # détecteur « Hey Wesley » (facultatif)
binaries = []
hiddenimports = (collect_submodules("wesley") + collect_submodules("uvicorn") + collect_submodules("keyring.backends")
                 + ["pystray._darwin", "pynput.keyboard._darwin", "pynput.mouse._darwin"])

for paquet in ["webview", "openwakeword", "faster_whisper", "ctranslate2", "onnxruntime", "piper", "edge_tts",
               "sounddevice", "_sounddevice_data", "recurring_ical_events", "icalendar", "tokenizers", "certifi",
               "ddgs", "objc", "Foundation", "AppKit", "WebKit", "Quartz", "ApplicationServices", "websockets",
               "sherpa_onnx", "ScreenCaptureKit", "CoreMedia", "av"]:
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
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Wesley", console=False, argv_emulation=False,
          target_arch=None, codesign_identity=None, entitlements_file="entitlements.plist")
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Wesley")
app = BUNDLE(
    coll,
    name="Wesley.app",
    icon="wesley.png",
    bundle_identifier="com.abdel.wesley",
    version=VERSION,
    info_plist={
        "CFBundleName": "Wesley",
        "CFBundleDisplayName": "Wesley",
        "CFBundleShortVersionString": VERSION,
        "NSHumanReadableCopyright": "© Abdelrahim Riche",
        "LSUIElement": True,                     # icône dans la barre des menus, pas dans le Dock
        "LSMinimumSystemVersion": "12.0",
        "NSHighResolutionCapable": True,
        "NSMicrophoneUsageDescription": "Wesley écoute quand tu l'appelles (« Wesley, … ») et transcrit ta voix ou tes réunions sur ton Mac.",
        "NSAppleEventsUsageDescription": "Wesley pilote tes applications (ouvrir, fermer, régler le volume) quand tu le lui demandes.",
        "NSScreenCaptureUsageDescription": "Wesley regarde ton écran quand tu lui demandes ce qui s'y trouve, et capte le son du Mac pour transcrire tes réunions en ligne.",
    },
)
