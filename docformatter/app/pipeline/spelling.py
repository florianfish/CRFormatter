"""Vérification orthographique hors ligne avec Hunspell (mode pipe ispell « -a »).

Les mots inconnus sont signalés, jamais remplacés : en médecine, une correction
automatique fausse (molécule, posologie) est plus dangereuse qu'une faute.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
from collections.abc import Iterable
from pathlib import Path

from .model import Inconnu

log = logging.getLogger("docformatter")

NB_SUGGESTIONS = 5


def _a_ignorer(mot: str, dictionnaire: set[str]) -> bool:
    if len(mot) <= 2 or any(c.isdigit() for c in mot):
        return True
    # Sigles (HTA, ECG) et casse mixte technique (HbA1c, mmHg, pH)
    if any(c.isupper() for c in mot[1:]):
        return True
    return mot.lower() in dictionnaire


# Tiret qui n'est pas entre deux lettres (puce « -Suivi », tiret isolé) : Hunspell le collerait au mot.
_TIRET_ISOLE = re.compile(r"(?<![^\W\d_])-|-(?![^\W\d_])")


def _pour_hunspell(texte: str) -> str:
    """Texte envoyé à Hunspell : même longueur (les mots sont relocalisés par position)."""
    return _TIRET_ISOLE.sub(" ", texte.replace("\n", " ").replace("\t", " "))


class Correcteur:
    def __init__(self, mots_supplementaires: Iterable[str], langue: str = "fr_FR"):
        self.langue = langue
        self.binaire = shutil.which("hunspell")
        self.dictionnaire = {m.lower() for m in mots_supplementaires}
        # Dictionnaire personnel Hunspell : les mots ajoutés servent aussi aux suggestions.
        self._perso = tempfile.NamedTemporaryFile(
            "w", suffix=".dic", prefix="docformatter-", encoding="utf-8", delete=False
        )
        self._perso.write("\n".join(sorted(set(mots_supplementaires))) + "\n")
        self._perso.close()
        if not self.disponible:
            log.warning("Hunspell introuvable : vérification orthographique désactivée")

    @property
    def disponible(self) -> bool:
        return self.binaire is not None

    def __del__(self):
        Path(self._perso.name).unlink(missing_ok=True)

    def verifier(self, textes: list[str]) -> list[list[Inconnu]]:
        resultats: list[list[Inconnu]] = [[] for _ in textes]
        if not self.disponible:
            return resultats
        indices = [i for i, t in enumerate(textes) if t.strip()]
        if not indices:
            return resultats
        # « ^ » en début de ligne : la ligne est du texte, jamais une commande ispell.
        entree = "".join("^" + _pour_hunspell(textes[i]) + "\n" for i in indices)
        sortie = subprocess.run(
            [self.binaire, "-a", "-i", "utf-8", "-d", self.langue, "-p", self._perso.name],
            input=entree, capture_output=True, text=True, encoding="utf-8", timeout=60, check=True,
        ).stdout
        lignes = sortie.split("\n")[1:]  # 1re ligne : bannière de version
        blocs_reponse = "\n".join(lignes).split("\n\n")
        for i, reponse in zip(indices, blocs_reponse):
            resultats[i] = self._analyser(textes[i], reponse.splitlines())
        return resultats

    def _analyser(self, texte: str, lignes: list[str]) -> list[Inconnu]:
        inconnus: list[Inconnu] = []
        curseur = 0
        for ligne in lignes:
            if not ligne or ligne[0] not in "&#":
                continue
            entete, _, suggestions = ligne.partition(": ")
            # Le dictionnaire fr compte « . » parmi les caractères de mot (abréviations « etc. »).
            mot = entete.split(" ")[1].strip(".-'’")
            if not mot:
                continue
            # On relocalise le mot dans le texte plutôt que de se fier à l'offset
            # (exprimé en octets ou en caractères selon les versions).
            debut = texte.find(mot, curseur)
            if debut < 0:
                continue
            curseur = debut + len(mot)
            if _a_ignorer(mot, self.dictionnaire):
                continue
            sugg = [s.strip() for s in suggestions.split(",") if s.strip()] if ligne[0] == "&" else []
            inconnus.append(Inconnu(debut, curseur, mot, sugg[:NB_SUGGESTIONS]))
        return inconnus


def charger_mots(dictionnaire: list[str], dossier: Path) -> list[str]:
    """Dictionnaire des règles + fichiers de mots déposés dans /config/dictionnaires."""
    mots = list(dictionnaire)
    for fichier in sorted(dossier.glob("*.txt")) + sorted(dossier.glob("*.dic")):
        for ligne in fichier.read_text(encoding="utf-8", errors="replace").splitlines():
            mot = ligne.split("/")[0].strip()  # format .dic : mot/drapeaux
            if mot and not mot.isdigit() and not mot.startswith("#"):
                mots.append(mot)
    return mots
