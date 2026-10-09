"""Noms de médicaments (spécialités et substances actives, base publique de l'ANSM) livrés avec
l'add-on dans defaults/medicaments.txt (mis à jour par `make medicaments`).

Ils servent de mots connus pour l'orthographe (option « medicaments ») et de propositions dans les
champs « Remplacer par » : taper « dolip » propose « Doliprane ».
"""

from __future__ import annotations

import unicodedata
from functools import lru_cache
from pathlib import Path

from .settings import DEFAULTS_DIR

FICHIER = DEFAULTS_DIR / "medicaments.txt"
NB_PROPOSITIONS = 8
SAISIE_MIN = 2


@lru_cache(maxsize=50_000)
def cle(texte: str) -> str:
    """Forme de comparaison : minuscules, sans accents (« Kardégic » et « kardegic » se valent)."""
    return "".join(c for c in unicodedata.normalize("NFD", texte.lower()) if unicodedata.category(c) != "Mn")


@lru_cache(maxsize=4)
def noms(fichier: Path = FICHIER) -> tuple[str, ...]:
    if not fichier.exists():
        return ()
    lignes = fichier.read_text(encoding="utf-8").splitlines()
    return tuple(l.strip() for l in lignes if l.strip() and not l.startswith("#"))


def mots(fichier: Path = FICHIER) -> list[str]:
    """Mots des noms (« acide acétylsalicylique » → « acide », « acétylsalicylique ») pour Hunspell."""
    return sorted({m for nom in noms(fichier) for m in nom.split()})


def proposer(saisie: str, candidats: list[str]) -> list[str]:
    """Candidats commençant par la saisie, puis la contenant, dans l'ordre donné."""
    recherche = cle(saisie.strip())
    if len(recherche) < SAISIE_MIN:
        return []
    candidats = list(dict.fromkeys(candidats))
    debut = [n for n in candidats if cle(n).startswith(recherche)]
    milieu = [n for n in candidats if recherche in cle(n) and n not in debut]
    return (debut + milieu)[:NB_PROPOSITIONS]
