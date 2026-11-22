# -*- mode: python ; coding: utf-8 -*-
# Recette PyInstaller de l'application Wesley : .venv\Scripts\pyinstaller wesley.spec --noconfirm
# Produit dist\Wesley\Wesley.exe (dossier complet, sans console), ensuite empaqueté par installateur.iss.
import os

from PyInstaller.utils.hooks import collect_all, collect_submodules
from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct, StringTable,
                                                 VarFileInfo, VarStruct, VSVersionInfo)

VERSION = open("wesley/version.py", encoding="utf-8").read().split('VERSION = "')[1].split('"')[0]
DEVELOPPEUR = "Abdelrahim Riche"
_v = tuple(int(x) for x in (VERSION.split(".") + ["0", "0", "0"])[:4])
# Clic droit › Propriétés › Détails de Wesley.exe : société, copyright, version
INFOS_VERSION = VSVersionInfo(
    ffi=FixedFileInfo(filevers=_v, prodvers=_v),
    kids=[StringFileInfo([StringTable("040C04B0", [
        StringStruct("CompanyName", DEVELOPPEUR), StringStruct("FileDescription", "Wesley"),
        StringStruct("FileVersion", VERSION), StringStruct("InternalName", "Wesley"),
        StringStruct("LegalCopyright", f"© {DEVELOPPEUR}"), StringStruct("OriginalFilename", "Wesley.exe"),
        StringStruct("ProductName", "Wesley"), StringStruct("ProductVersion", VERSION)])]),
          VarFileInfo([VarStruct("Translation", [0x040C, 1200])])])

datas = [("wesley/static", "wesley/static"), ("voix", "voix"), ("wesley.ico", ".")]
datas += [("eveil", "eveil")] if os.path.exists("eveil/hey_wesley.onnx") else []   # détecteur « Hey Wesley » (facultatif)
binaries = []
hiddenimports = (collect_submodules("wesley") + collect_submodules("uvicorn") + collect_submodules("keyring.backends")
                 + ["pystray._win32", "pynput.keyboard._win32", "pynput.mouse._win32", "win32timezone"])

# paquets avec des fichiers de données ou des DLL (modèles, espeak, WebView2, PortAudio…)
for paquet in ["webview", "openwakeword", "faster_whisper", "ctranslate2", "onnxruntime", "piper", "pywinauto",
               "comtypes", "edge_tts", "sounddevice", "_sounddevice_data", "clr_loader", "pythonnet", "mcp",
               "recurring_ical_events", "icalendar", "tokenizers", "certifi", "ddgs", "pyttsx3", "websockets"]:
    try:
        d, b, h = collect_all(paquet)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as e:
        print(f"(collect_all {paquet} : {e})")

a = Analysis(
    ["lanceur.pyw"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["torch", "tensorflow", "matplotlib", "IPython", "jupyter", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Wesley",
    icon="wesley.ico",
    console=False,          # pas de fenêtre noire
    version=INFOS_VERSION,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Wesley")
