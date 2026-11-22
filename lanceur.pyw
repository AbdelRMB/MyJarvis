"""Point d'entrée de l'application de bureau (double-clic, démarrage Windows, et .exe PyInstaller)."""
import os
import sys

if not getattr(sys, "frozen", False):
    ici = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, ici)
    os.chdir(ici)

from wesley.app import main  # noqa: E402

main()
