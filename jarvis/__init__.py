"""Jarvis. À l'import : réseau en IPv4 d'abord (voir _ipv4_d_abord)."""
import socket

_getaddrinfo = socket.getaddrinfo


def _ipv4_d_abord(hote, port, family=0, *args, **kwargs):
    """Beaucoup de box ont un IPv6 cassé : les connexions (compte, Whisper, voix, mises à jour) attendaient
    l'expiration en IPv6 avant d'essayer l'IPv4, et semblaient tourner à l'infini. On garde l'IPv4 quand il existe."""
    res = _getaddrinfo(hote, port, family, *args, **kwargs)
    v4 = [r for r in res if r[0] == socket.AF_INET]
    return v4 or res


socket.getaddrinfo = _ipv4_d_abord
