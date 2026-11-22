import argparse
import sys
import threading

from rich.console import Console
from rich.panel import Panel

from . import memoire, voix
from .agent import Wesley
from .config import CONFIG

c = Console()

AIDE = """[bold]Commandes[/]
/voix      bascule le mode vocal (micro push-to-talk + réponse parlée)
/think     active/désactive la réflexion du modèle (plus lent, plus malin)
/memoire   affiche ce que Wesley sait de toi
/scan      re-scanne ton PC (projets, applis, VS Code)
/reset     nouvelle conversation
/quit      quitter (Wesley mémorise ce qu'il a appris)
Arrêt d'urgence souris : envoie la souris dans le coin haut-gauche de l'écran."""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voix", action="store_true")
    args = ap.parse_args()
    mode_voix = args.voix

    if not memoire.SYSTEME.exists():
        with c.status("Premier lancement : je scanne ton PC..."):
            memoire.scanner_systeme()

    wesley = Wesley()
    c.print(Panel.fit(f"[bold cyan]Wesley[/]  ·  {CONFIG['modele']} via Ollama  ·  /aide", border_style="cyan"))

    def sur_texte(t):
        c.print(t, end="", markup=False, highlight=False)

    def sur_outil(nom, a, res):
        if res is None:
            apercu = ", ".join(f"{k}={str(v)[:60]!r}" for k, v in a.items())
            c.print(f"\n[dim]⚙ {nom}({apercu})[/]")
        else:
            c.print(f"[dim]  ↳ {res[:160].replace(chr(10), ' ')}[/]")

    while True:
        try:
            if mode_voix:
                input("\n[Entrée pour parler] ")
                texte = voix.ecouter()
                c.print(f"[bold green]Toi :[/] {texte}")
            else:
                texte = c.input("\n[bold green]Toi ›[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            texte = "/quit"
        if not texte:
            continue
        cmd = texte.lower()
        if cmd in ("/quit", "/exit", "/q"):
            with c.status("Je mémorise ce que j'ai appris..."):
                for f in wesley.extraire_souvenirs():
                    c.print(f"[dim]{f}[/]")
            c.print("[cyan]À plus, Abdel.[/]")
            return
        if cmd == "/aide":
            c.print(AIDE); continue
        if cmd == "/reset":
            wesley.reset(); c.print("[dim]Nouvelle conversation.[/]"); continue
        if cmd == "/scan":
            memoire.scanner_systeme(); wesley.reset(); c.print("[dim]PC re-scanné.[/]"); continue
        if cmd == "/memoire":
            c.print(memoire.profil_texte()[0] or "(vide)"); continue
        if cmd == "/think":
            CONFIG["reflexion"] = not CONFIG["reflexion"]; c.print(f"[dim]Réflexion : {CONFIG['reflexion']}[/]"); continue
        if cmd == "/voix":
            mode_voix = not mode_voix; c.print(f"[dim]Mode vocal : {mode_voix}[/]"); continue

        c.print("[bold cyan]Wesley ›[/] ", end="")
        try:
            rep = wesley.demander(texte, sur_texte=sur_texte, sur_outil=sur_outil)
        except KeyboardInterrupt:
            c.print("\n[yellow]Interrompu.[/]"); continue
        except Exception as e:
            c.print(f"\n[red]Erreur : {e}[/]"); continue
        c.print()
        if mode_voix:
            threading.Thread(target=voix.parler, args=(rep,), daemon=True).start()


if __name__ == "__main__":
    sys.exit(main())
