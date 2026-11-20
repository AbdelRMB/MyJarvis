<p align="center">
  <strong>English</strong> · <a href="README.fr.md">Français</a>
</p>

# J.A.R.V.I.S. — your personal desktop assistant

Jarvis is an assistant that **drives your computer** for you: it opens your apps, manages your files, clicks and
types for you, looks at your screen, codes in VS Code, searches the web… Talk to it ("Jarvis, open Discord") or type,
and it answers out loud.

- **macOS** (Apple silicon) and **Windows 10/11**.
- **Pick its brain**: Claude (Anthropic API, the smartest), OpenAI, or Ollama (free, 100% local).
- **One account per person**: your memory, history, connectors and settings follow you on all your devices. Your
  API key and passwords are encrypted with your password: the server cannot read them.
- **Built-in updates**: the app shows new versions and what they contain, and installs them in one click.

> The app's interface is available in French and English (Settings › Interface). Jarvis speaks French by default.

---

## Install Jarvis with Claude (easiest)

This repository includes an installation guide for [Claude Code](https://claude.com/claude-code) (`CLAUDE.md`):
**Claude can install Jarvis by itself**, end to end.

1. Install Claude Code, then get the project:
   ```bash
   git clone https://github.com/AbdelRMB/MyJarvis.git
   cd MyJarvis
   claude
   ```
2. Just tell it: **"Install Jarvis"**.

Claude detects your system and asks whether you just want to use Jarvis or develop it. It downloads and installs
everything, then walks you through permissions and creating your account. It asks before installing any software on
your computer, and you type any passwords yourself.

---

## Install Jarvis manually

### 1. Download

Open the **[Releases](https://github.com/AbdelRMB/MyJarvis/releases)** tab and get the latest version:

| Your computer | File |
|---|---|
| Mac with Apple silicon (M1, M2, M3…) | `Jarvis-<version>-mac-arm64.dmg` |
| Windows 10/11 PC | `JarvisSetup-<version>.exe` |

### 2. Install

**On Mac**
1. Open the `.dmg` and drag **Jarvis** into **Applications**. The app is signed and notarized by Apple: it opens
   normally.
2. In **System Settings › Privacy & Security**, allow Jarvis for the **Microphone**, **Accessibility** (shortcuts,
   mouse, keyboard) and **Screen Recording** (so it can see your screen).

Jarvis lives in the **menu bar**, top right. It starts automatically when you log in.

**On Windows**
1. Run `JarvisSetup-<version>.exe` (no administrator rights needed). If Windows shows "Windows protected your PC",
   click **More info › Run anyway**.
2. Tick **"Start Jarvis with Windows"** if you want it always ready.

Jarvis lives next to the **clock** (notification area).

### 3. First launch

1. **Create your account** (first name, email, password) or sign in. You can also use Jarvis **locally**, without an
   account: nothing is then sent to the server.
   - If this computer already had a Jarvis memory (older version, OneDrive), it is added to your account
     automatically, without duplicates.
2. **Pick the brain** in **Settings › Brain**:
   - **Claude**: paste your API key, created at [platform.claude.com](https://platform.claude.com) › API keys.
     It's pay-as-you-go, and a Claude Pro subscription doesn't include API credit.
   - **Ollama**: free and local. Install [Ollama](https://ollama.com), then run `ollama pull qwen3.5:9b`.
     You need a graphics card with about 8 GB of memory.
3. You're set. Say **"Jarvis, …"**.

### Updating

- In the app: **Updates** screen. You see each new version with its description, and install the latest one or a
  specific version. No need to uninstall.
- Or search for **"Mettre à jour Jarvis"** in the Start menu (Windows) or Spotlight (Mac).

---

## Using Jarvis

| Action | How |
|---|---|
| Call it | Say **"Jarvis, open Discord"** in one go, or "Jarvis" then your request. Or `Ctrl+Alt+J` (Windows) / `⌃ Ctrl + ⌥ Option + J` (Mac), or click the icon. |
| Silence it | **"Jarvis, stop"** (even while it's talking), or `Ctrl+Alt+S` / `⌃⌥S`, even with the window hidden. |
| Close the window | It only hides. To quit: Jarvis icon › Quit. |
| Shortcuts in the window | `Esc` = stop · `Ctrl+K` = type · `Alt+1…9` = screens |

- **Quiet start**: at startup, Jarvis runs in the background without opening its window; it appears when you call it.
- **100% local listening**: the word "Jarvis" is recognized on your computer (openWakeWord + a small Whisper).
  Nothing is sent until it hears its name.
- **Voice**: Microsoft neural (very natural, online) or Piper (100% local). Settings › Voice.

### What it can do
- **System**: terminal (PowerShell / zsh), Python scripts, open any app, file or URL, processes, lock/shut down
- **Files**: read, write, edit, search (name + content), move, copy, delete (→ trash)
- **Mouse and keyboard**: move, click, drag, scroll, type, shortcuts, media/volume, clipboard
- **Windows**: list, focus, maximize, close, click a button by its text
- **Vision**: look at the screen, find an element and click it, analyze an image
- **Code**: open in VS Code (file:line), git, create a project (Vite / Next / Node / Python)
- **Web**: search, news, read a page, weather, download
- **Memory**: remembers what it learns about you, with a history of your conversations across all your devices
- **Connectors**: Gmail, other IMAP mail, calendar (iCal), GitHub, Notion, SSH servers (VPS), and
  **any MCP server** (Spotify, Slack, Home Assistant…)
- **Your other devices**: "on my PC, launch Discord", including from your phone

### Screens
Grouped into sections in the left sidebar: **Assistant**, **To-do** · *My memory*: History, Memory ·
*Automate*: Tasks, Automations, Connectors · *My machines*: My devices, System, Activity, Arsenal ·
*Jarvis*: Settings, Updates, Tickets.

### Security and privacy
- The local interface only listens on `127.0.0.1` (checked Host, per-session token, checked Origin).
- **Account**: your password never leaves the device. It derives a sign-in key and a vault key, which encrypts your
  API key and passwords before they are sent. Your memory and history are stored on the server, protected but not
  end-to-end encrypted.
- **Your data is yours**: Settings › My account › **Download my data** or **Delete my account** (everything is
  erased from the server). Details in the
  [privacy policy](https://jarvis.abdelrahimriche.com/mobile/confidentialite.html) (in French).
- With the Claude or OpenAI brain, your messages, memories and tool results are sent to that provider. With Ollama,
  nothing leaves your computer.
- **Emergency stop**: move the mouse to the top-left corner of the screen (pyautogui aborts the action). Every action
  is logged (`logs/actions.log`).

---

## Development

Full commands are in [`CLAUDE.md`](CLAUDE.md) (in French), which is also Claude's guide. In short:

**Requirements**: Python **3.12**, Node.js **22+**, git. Optional: Ollama.

```bash
# Mac
python3.12 -m venv .venv-mac && .venv-mac/bin/pip install -r requirements-mac.txt
(cd interface && npm ci && npm run build)
.venv-mac/bin/python lanceur.pyw
```
```powershell
# Windows
py -3.12 -m venv .venv; .venv\Scripts\pip install -r requirements.txt -r requirements-voix.txt
cd interface; npm ci; npm run build; cd ..
.venv\Scripts\pythonw lanceur.pyw          # or jarvis-web.bat (browser) / jarvis.bat (terminal)
```

### Layout
| Folder / file | Role |
|---|---|
| `jarvis/` | The Python core: agent, tools (`outils/`), voice, listening, local server (`web.py`), account (`compte.py`), updates |
| `interface/` | React + TypeScript + Tailwind interface, built into `jarvis/static/` |
| `serveur/` | Account server (FastAPI + SQLite), mobile app and legal pages (`mobile/`) |
| `jarvis.spec` / `jarvis-mac.spec` | PyInstaller recipes (Windows / Mac) |
| `installateur.iss` | Windows installer (Inno Setup) |
| `construire.bat` / `construire-mac.sh` | Build the installers |
| `jarvis/version.py` + `CHANGELOG.md` | Version, and the description of each update |

The code, comments and commit messages are in French.

### Live interface
```bash
cd interface
npm run dev        # http://localhost:5173, wired to the Python server running alongside
npm run build      # rebuilds jarvis/static
```

### Adding a tool
In `jarvis/outils/*.py`:
```python
@outil
def my_tool(param: str):
    """Description for the model.
    param: description of the parameter"""
    return "result"
```

### Building the installers
- Mac: `bash construire-mac.sh` → `installateur/Jarvis-<version>-mac-arm64.dmg` (signed and notarized when a
  Developer ID certificate is available)
- Windows: `construire.bat` (requires Inno Setup 6) → `installateur\JarvisSetup-<version>.exe`
- Or on GitHub: **Actions › Versions de Jarvis › Run workflow** (Windows and/or Mac box).

### Publishing a version
1. Bump `jarvis/version.py`.
2. Describe the version at the top of `CHANGELOG.md` (`## x.y.z` section, written for users).
3. Push to `main`, then run `./publier-mac.sh` (Mac) or `publier.bat` (Windows). The script builds your machine's
   installer, creates the version in Releases, and asks GitHub to build the other system's one.

### Account server
The server code is in `serveur/app.py`. The official server's deployment configuration is not published. To use your
own server: run `app.py` with uvicorn behind an HTTPS proxy (`JARVIS_DB` and `JARVIS_CLE_APPLI` variables), then set
`"serveur_comptes"` and `"cle_appli"` in the app's `config.json`.

---

## Where is my data?

| | Mac | Windows |
|---|---|---|
| Device settings, logs, account cache | `~/Library/Application Support/Jarvis` | `%LOCALAPPDATA%\Jarvis` |
| Memory, history, connectors, shared settings | in your **account** (and cached locally) | same |
| API key, connector passwords | macOS Keychain + encrypted account vault | Credential Manager + encrypted account vault |

Diagnostics: `logs/jarvis.log` (startup, errors), `logs/perf.log` (model speed), `logs/couts.json`
(estimated Claude API spending).

## License

Copyright (C) 2026 Abdelrahim Riche

Jarvis is free software: you can redistribute it and/or modify it under the terms of the
**GNU General Public License version 3** (or any later version), as published by the Free Software Foundation.
Any modified version you distribute must stay under this same license, with its source code.
Jarvis comes **with absolutely no warranty**. Full text: [LICENSE](LICENSE).
