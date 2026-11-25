"""Publication : choix des cases du workflow versions.yml après une publication locale."""
import pytest

pytest.importorskip("requests")

import publier


def test_depuis_mac_apple_silicon():
    assert publier.entrees_autres("darwin", "arm64") == {
        "windows": True, "mac": False, "mac_intel": True}


def test_depuis_mac_intel():
    assert publier.entrees_autres("darwin", "x86_64") == {
        "windows": True, "mac": True, "mac_intel": False}


def test_depuis_windows():
    assert publier.entrees_autres("win32", "AMD64") == {
        "windows": False, "mac": True, "mac_intel": True}
