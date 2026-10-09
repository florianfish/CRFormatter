"""Connexion pour l'accès direct (hors Ingress Home Assistant), par exemple via un proxy nginx.

- Les identifiants viennent des options de l'add-on.
- La session est un jeton signé (HMAC-SHA256) dans un cookie HttpOnly / SameSite=Strict.
  La signature dépend du mot de passe : le changer déconnecte toutes les sessions de ce compte.
- Les tentatives répétées sont freinées par adresse IP.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time
from pathlib import Path

COOKIE = "docformatter_session"
DUREE_SESSION = 12 * 3600
ECHECS_MAX = 5
FENETRE_ECHECS = 15 * 60


def charger_cle(path: Path) -> bytes:
    """Clé de signature, créée au premier démarrage et conservée dans /data (privé à l'add-on)."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(secrets.token_bytes(32))
        path.chmod(0o600)
    return path.read_bytes()


class Sessions:
    def __init__(self, cle: bytes, utilisateurs: dict[str, str]):
        self.cle = cle
        self.utilisateurs = utilisateurs

    def _signature(self, utilisateur: str, charge: str) -> str:
        cle_compte = hmac.new(self.cle, self.utilisateurs[utilisateur].encode(), hashlib.sha256).digest()
        return hmac.new(cle_compte, charge.encode(), hashlib.sha256).hexdigest()

    def verifier_identifiants(self, utilisateur: str, mot_de_passe: str) -> bool:
        attendu = self.utilisateurs.get(utilisateur)
        # Comparaison à temps constant, effectuée même pour un identifiant inconnu
        correct = hmac.compare_digest((attendu or secrets.token_hex(16)).encode(), mot_de_passe.encode())
        return attendu is not None and correct

    def creer(self, utilisateur: str) -> str:
        charge = f"{utilisateur}|{int(time.time()) + DUREE_SESSION}"
        jeton = f"{charge}|{self._signature(utilisateur, charge)}"
        return base64.urlsafe_b64encode(jeton.encode()).decode()

    def verifier(self, jeton: str | None) -> str | None:
        """Retourne l'utilisateur de la session, ou None si absente, expirée ou falsifiée."""
        if not jeton:
            return None
        try:
            utilisateur, expiration, signature = base64.urlsafe_b64decode(jeton.encode()).decode().rsplit("|", 2)
            if utilisateur not in self.utilisateurs or int(expiration) < time.time():
                return None
        except (ValueError, UnicodeDecodeError):
            return None
        attendue = self._signature(utilisateur, f"{utilisateur}|{expiration}")
        return utilisateur if hmac.compare_digest(attendue, signature) else None


class Limiteur:
    """Bloque une adresse après ECHECS_MAX échecs de connexion dans la fenêtre glissante."""

    def __init__(self):
        self._echecs: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recents(self, adresse: str) -> list[float]:
        limite = time.time() - FENETRE_ECHECS
        recents = [t for t in self._echecs.get(adresse, []) if t > limite]
        self._echecs[adresse] = recents
        return recents

    def bloque(self, adresse: str) -> bool:
        with self._lock:
            return len(self._recents(adresse)) >= ECHECS_MAX

    def echec(self, adresse: str) -> None:
        with self._lock:
            self._recents(adresse).append(time.time())

    def reussite(self, adresse: str) -> None:
        with self._lock:
            self._echecs.pop(adresse, None)
