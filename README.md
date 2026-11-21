<p align="center">
  <img src="jarvis.png" alt="Jarvis" width="120">
</p>

<h1 align="center">J.A.R.V.I.S.</h1>

<p align="center">
  <strong>A voice assistant that actually drives your computer.</strong><br>
  Say <em>"Jarvis, …"</em>: it opens your apps, clicks, types, reads your screen, codes in VS Code,
  uses your websites (even with 2FA) and manages your servers.<br>
  Powered by Claude, OpenAI or <strong>Ollama (100% local, free)</strong>. macOS and Windows.
</p>

<p align="center">
  <a href="https://github.com/AbdelRMB/MyJarvis/releases/latest"><img alt="Latest release" src="https://img.shields.io/github/v/release/AbdelRMB/MyJarvis?label=release&color=2f81f7"></a>
  <a href="https://github.com/AbdelRMB/MyJarvis/releases"><img alt="Downloads" src="https://img.shields.io/github/downloads/AbdelRMB/MyJarvis/total?color=2f81f7"></a>
  <img alt="Platforms" src="https://img.shields.io/badge/platform-macOS%20(Apple%20silicon)%20%7C%20Windows%2010%2F11-555">
  <img alt="Python 3.12" src="https://img.shields.io/badge/python-3.12-3776ab?logo=python&logoColor=white">
  <a href="LICENSE"><img alt="License: GPL v3" src="https://img.shields.io/badge/license-GPLv3-blue"></a>
  <a href="https://github.com/AbdelRMB/MyJarvis/stargazers"><img alt="GitHub stars" src="https://img.shields.io/github/stars/AbdelRMB/MyJarvis?style=social"></a>
</p>

<p align="center">
  <a href="https://github.com/AbdelRMB/MyJarvis/releases/latest"><strong>⬇ Download</strong></a> ·
  <a href="#-what-you-can-say">Examples</a> ·
  <a href="#-features">Features</a> ·
  <a href="#-privacy--security">Privacy</a> ·
  <a href="CONTRIBUTING.md">Contribute</a> ·
  <a href="README.fr.md">🇫🇷 Français</a>
</p>

<p align="center">
  <a href="docs/demo.mp4"><img src="docs/demo.webp" alt="Jarvis demo: voice command, VS Code and tests, screen analysis, intranet form with 2FA and approval, WhatsApp message" width="800"></a>
  <br><sub>▶ <a href="docs/demo.mp4">Watch in HD (MP4)</a> · the interface is in French, subtitles in English</sub>
</p>

---

## ✨ Why Jarvis?

Most "AI assistants" are a chat window. Jarvis is an **agent with hands**: it uses your mouse, keyboard, apps,
files, browser and servers, and tells you out loud what it did.

- 🎙️ **Hands-free.** Wake word ("Jarvis") detected **on your machine** (openWakeWord + Whisper). Nothing is sent
  until it hears its name. Interrupt it just by talking.
- 🧠 **Your choice of brain.** Claude (smartest), OpenAI, or **Ollama: free, offline, nothing leaves your computer.**
- 🖥️ **Real computer control.** Apps, files, windows, mouse and keyboard, screen vision, terminal, VS Code, git.
- 🌐 **Learns your websites.** Explores your intranet or business tools read-only, records your demonstrations,
  then does the task for you. Signs in on its own, **including 2FA codes** (TOTP computed locally).
- 🔌 **Connectors + any MCP server.** Gmail/IMAP, calendar, GitHub, Notion, SSH servers (with a setup wizard),
  WhatsApp, Spotify, Slack, Home Assistant…
- 📱 **Follows you.** One account: memory, history and to-dos synced across your Mac, PC and phone.
  "On my PC, launch Discord" works from your phone.
- 🔐 **Safe by design.** Asks before anything destructive, encrypted vault for keys and passwords, full action log,
  emergency stop.
- 📦 **Real app, not a script.** Signed and notarized Mac app, Windows installer, one-click updates.

## 💬 What you can say

> "Jarvis, open Discord and put on my focus playlist."
>
> "Look at my screen: why is this build failing?"
>
> "Create an invoice for Dupont on Sage." *(a site it learned)*
>
> "Take a screenshot of the interventions table and send it to Karim on WhatsApp."
>
> "Why is my server slow?" *(over SSH, asks before any sudo command)*
>
> "Remind me to take out the trash at 8 pm." · "Give me my morning briefing."
>
> "From now on, answer in one sentence." *(it remembers your instructions)*

## 🚀 Get started in 2 minutes

1. **Download** the [latest release](https://github.com/AbdelRMB/MyJarvis/releases/latest):

   | Your computer | File |
   |---|---|
   | Mac with Apple silicon (M1–M4) | `Jarvis-<version>-mac-arm64.dmg` |
   | Windows 10/11 PC | `JarvisSetup-<version>.exe` |

2. **Install**: drag Jarvis into Applications (Mac) or run the installer (Windows, no admin rights needed).
3. **Create your account** (or use it locally without one), then pick a brain in **Settings › Brain**:
   paste a [Claude API key](https://platform.claude.com), or install [Ollama](https://ollama.com) and run
   `ollama pull qwen3.5:9b` for a free local brain.

Then say **"Jarvis, …"** or press `Ctrl+Alt+J` (Windows) / `⌃⌥J` (Mac).

> 🤖 **Even easier:** clone this repo, open it in [Claude Code](https://claude.com/claude-code) and say
> **"Install Jarvis"**. The repo ships an install guide (`CLAUDE.md`) and Claude does everything, asking before
> installing anything.

<details>
<summary><strong>Detailed install notes (permissions, SmartScreen, updates)</strong></summary>

**Mac**
1. Open the `.dmg` and drag **Jarvis** into **Applications**. The app is signed and notarized by Apple.
2. In **System Settings › Privacy & Security**, allow Jarvis for **Microphone**, **Accessibility** (shortcuts,
   mouse, keyboard) and **Screen Recording** (so it can see your screen).

Jarvis lives in the **menu bar** and starts when you log in.

**Windows**
1. Run `JarvisSetup-<version>.exe`. If Windows shows "Windows protected your PC", click
   **More info › Run anyway**.
2. Tick **"Start Jarvis with Windows"** if you want it always ready.

Jarvis lives next to the **clock** (notification area).

**First launch**
- If this computer already had a Jarvis memory (older version), it is merged into your account, without duplicates.
- Claude is pay-as-you-go: a Claude Pro subscription doesn't include API credit.
- Ollama needs a graphics card with about 8 GB of memory.

**Updating**: the **Updates** screen shows each version with its description and installs it in one click.
Jarvis can also update itself automatically at the next start.

</details>

> The interface is available in French and English (Settings › Interface). Jarvis speaks French by default.

---

## 🧰 Features

| | |
|---|---|
| **System** | Terminal (PowerShell / zsh), Python scripts, open any app, file or URL, processes, lock / shut down |
| **Files** | Read, write, edit, search (name + content), move, copy, delete (→ trash) |
| **Mouse & keyboard** | Move, click, drag, scroll, type, shortcuts, media / volume, clipboard |
| **Windows** | List, focus, maximize, close, click a button by its text |
| **Vision** | Look at the screen, find an element and click it, analyze an image |
| **Browser** | Its own browser or **yours** (Safari, Chrome, Edge, Brave, Arc on Mac), highlighting each element before acting |
| **Learned sites** | Read-only exploration, demonstrations, tips, auto sign-in with 2FA |
| **Code** | Open in VS Code (file:line), git, scaffold projects (Vite / Next / Node / Python) |
| **Web** | Search with sources, news, read a page, weather, download |
| **Memory** | Remembers what it learns about you, your instructions, and lessons from its own mistakes |
| **Organization** | To-do list, reminders spoken at the right time, morning briefing, routines, automations |
| **Connectors** | Gmail, IMAP, iCal, GitHub, Notion, SSH servers (sudo with approval), WhatsApp, **any MCP server** |
| **Voice** | Microsoft neural voices, Piper (local) or **Kyutai** (very natural, local); custom pronunciation dictionary |
| **Devices** | Control your other computers, to-dos and tickets from your phone |

<details>
<summary><strong>Using Jarvis: shortcuts</strong></summary>

| Action | How |
|---|---|
| Call it | Say **"Jarvis, open Discord"** in one go, or "Jarvis" then your request. Or `Ctrl+Alt+J` / `⌃⌥J`, or click the icon. |
| Silence it | **"Jarvis, stop"** (even while it's talking), or `Ctrl+Alt+S` / `⌃⌥S`, even with the window hidden. |
| Close the window | It only hides. To quit: Jarvis icon › Quit. |
| In the window | `Esc` = stop · `Ctrl+K` = type · `Alt+1…9` = screens |

</details>

## 🔐 Privacy & security

- **Ollama brain = nothing leaves your computer.** With Claude or OpenAI, your messages, memories and tool results
  are sent to that provider.
- **Wake word is 100% local.** Audio is only processed after "Jarvis".
- **Your password never leaves the device.** It derives a sign-in key and a vault key that encrypts your API key and
  passwords before they're sent. Memory and history are stored on the server, protected but not end-to-end encrypted.
  You can also use Jarvis **without an account**.
- **Asks first** before destructive clicks (delete, send, pay…) and every `sudo` command.
- The local interface only listens on `127.0.0.1` (checked Host, per-session token, checked Origin).
- **Emergency stop**: move the mouse to the top-left corner. Every action is logged (`logs/actions.log`).
- **Your data is yours**: Settings › My account › **Download my data** / **Delete my account**.
  [Privacy policy](https://jarvis.abdelrahimriche.com/mobile/confidentialite.html) (in French).

## 🏗️ How it works

```
 "Jarvis, …" ──► openWakeWord + Whisper (local) ──► Agent (Claude / OpenAI / Ollama)
                                                        │  tool calls
                                                        ▼
        apps · files · mouse/keyboard · screen · browser · SSH · MCP servers · connectors
                                                        │
 React interface (pywebview) ◄── FastAPI on 127.0.0.1 ◄─┘──► voice (Microsoft / Piper / Kyutai)
                                                        │
                                   account server (FastAPI + SQLite): memory, history, sync
```

- **Core**: Python 3.12 (`jarvis/`), tools in `jarvis/outils/`, local server `jarvis/web.py`.
- **Interface**: React + TypeScript + Tailwind (`interface/`), shown in a native window (pywebview).
- **Account server**: FastAPI + SQLite (`serveur/`), self-hostable.

---

## 🤝 Contributing

Contributions are very welcome, from typo fixes to new tools. Start with
[`CONTRIBUTING.md`](CONTRIBUTING.md) and the
[good first issues](https://github.com/AbdelRMB/MyJarvis/labels/good%20first%20issue).
Found a bug or have an idea? [Open an issue](https://github.com/AbdelRMB/MyJarvis/issues/new/choose)
(English or French).

If Jarvis is useful to you, **a ⭐ helps a lot**: it's how other people find the project.

<details>
<summary><strong>Development setup</strong></summary>

Full commands are in [`CLAUDE.md`](CLAUDE.md) (in French), which is also Claude's guide.

**Requirements**: Python **3.12** (not 3.13), Node.js **22+**, git. Optional: Ollama.

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

**Layout**

| Folder / file | Role |
|---|---|
| `jarvis/` | Python core: agent, tools (`outils/`), voice, listening, local server (`web.py`), account (`compte.py`), updates |
| `interface/` | React + TypeScript + Tailwind interface, built into `jarvis/static/` |
| `serveur/` | Account server (FastAPI + SQLite), mobile app and legal pages (`mobile/`) |
| `jarvis.spec` / `jarvis-mac.spec` | PyInstaller recipes (Windows / Mac) |
| `installateur.iss` | Windows installer (Inno Setup) |
| `construire.bat` / `construire-mac.sh` | Build the installers |
| `jarvis/version.py` + `CHANGELOG.md` | Version, and the description of each update |

The code, comments and commit messages are in French.

**Live interface**: `cd interface && npm run dev` (http://localhost:5173, wired to the Python server running alongside).

**Adding a tool** in `jarvis/outils/*.py`:
```python
@outil
def my_tool(param: str):
    """Description for the model.
    param: description of the parameter"""
    return "result"
```

**Building the installers**: `bash construire-mac.sh` (Mac) or `construire.bat` (Windows, Inno Setup 6), or on
GitHub: **Actions › Versions de Jarvis › Run workflow**.

**Self-hosting the account server**: run `serveur/app.py` with uvicorn behind an HTTPS proxy (`JARVIS_DB` and
`JARVIS_CLE_APPLI` variables), then set `"serveur_comptes"` and `"cle_appli"` in the app's `config.json`.

**Where is my data?**

| | Mac | Windows |
|---|---|---|
| Device settings, logs, account cache | `~/Library/Application Support/Jarvis` | `%LOCALAPPDATA%\Jarvis` |
| Memory, history, connectors, shared settings | in your **account** (cached locally) | same |
| API key, connector passwords | macOS Keychain + encrypted account vault | Credential Manager + encrypted account vault |

Diagnostics: `logs/jarvis.log` (startup, errors), `logs/perf.log` (model speed), `logs/couts.json`
(estimated Claude API spending).

</details>

## ⭐ Star history

<a href="https://star-history.com/#AbdelRMB/MyJarvis&Date">
  <img src="https://api.star-history.com/svg?repos=AbdelRMB/MyJarvis&type=Date" alt="Star history" width="600">
</a>

## 📄 License

Copyright (C) 2026 Abdelrahim Riche. Jarvis is free software under the
**GNU General Public License v3** (or any later version): you can use, study, modify and share it; modified
versions you distribute must stay under the same license, with their source code. It comes with **absolutely no
warranty**. Full text: [LICENSE](LICENSE).
