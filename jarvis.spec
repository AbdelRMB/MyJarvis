# -*- mode: python ; coding: utf-8 -*-
# Recette PyInstaller de l'application Jarvis : .venv\Scripts\pyinstaller jarvis.spec --noconfirm
# Produit dist\Jarvis\Jarvis.exe (dossier complet, sans console), ensuite empaqueté par installateur.iss.
from PyInstaller.utils.hooks import collect_all, collect_submodules

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
    version=None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Jarvis")
