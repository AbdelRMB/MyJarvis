"""Protection commune : aucun test n'écrit dans les vraies notifications de Wesley (notifications.json du dossier
de développement) ni n'annonce quoi que ce soit à voix haute."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def _pas_de_vraies_notifications(monkeypatch):
    from wesley import notifications
    monkeypatch.setattr(notifications, "ajouter", lambda *a, **k: {})
    try:
        from wesley import annonces
        monkeypatch.setattr(annonces, "annoncer", lambda *a, **k: None)
    except Exception:
        pass
