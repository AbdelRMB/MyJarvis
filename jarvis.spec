# -*- mode: python ; coding: utf-8 -*-
# Recette PyInstaller de l'application Jarvis : .venv\Scripts\pyinstaller jarvis.spec --noconfirm
# Produit dist\Jarvis\Jarvis.exe (dossier complet, sans console), ensuite empaqueté par installateur.iss.
from PyInstaller.utils.hooks import collect_all, collect_submodules
from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct, StringTable,
                                                 VarFileInfo, VarStruct, VSVersionInfo)

VERSION = open("jarvis/version.py", encoding="utf-8").read().split('VERSION = "')[1].split('"')[0]
DEVELOPPEUR = "AbdelRMB"
_v = tuple(int(x) for x in (VERSION.split(".") + ["0", "0", "0"])[:4])
# Clic droit › Propriétés › Détails de Jarvis.exe : société, copyright, version
INFOS_VERSION = VSVersionInfo(
    ffi=FixedFileInfo(filevers=_v, prodvers=_v),
    kids=[StringFileInfo([StringTable("040C04B0", [
        StringStruct("CompanyName", DEVELOPPEUR), StringStruct("FileDescription", "Jarvis"),
        StringStruct("FileVersion", VERSION), StringStruct("InternalName", "Jarvis"),
        StringStruct("LegalCopyright", f"© {DEVELOPPEUR}"), StringStruct("OriginalFilename", "Jarvis.exe"),
        StringStruct("ProductName", "Jarvis"), StringStruct("ProductVersion", VERSION)])]),
          VarFileInfo([VarStruct("Translation", [0x040C, 1200])])])

datas = [("jarvis/static", "jarvis/static"), ("voix", "voix"), ("jarvis.ico", ".")]
binaries = []
hiddenimports = (collect_submodules("jarvis") + collect_submodules("uvicorn") + collect_submodules("keyring.backends")
                 + ["pystray._win32", "pynput.keyboard._win32", "pynput.mouse._win32", "win32timezone"])

# paquets avec des fichiers de données ou des DLL (modèles, espeak, WebView2, PortAudio…)
for paquet in ["webview", "openwakeword", "faster_whisper", "ctranslate2", "onnxruntime", "piper", "pywinauto",
               "comtypes", "edge_tts", "sounddevice", "_sounddevice_data", "clr_loader", "pythonnet", "mcp",
               "recurring_ical_events", "icalendar", "tokenizers", "certifi", "ddgs", "pyttsx3"]:
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
    name="Jarvis",
    icon="jarvis.ico",
    console=False,          # pas de fenêtre noire
    version=INFOS_VERSION,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Jarvis")
