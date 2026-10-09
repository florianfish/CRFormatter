"""Nettoyage du texte : espaces, règles regex, corrections orthographiques connues."""

from __future__ import annotations

import re

from ..rules import Regles
from .model import Bloc, Changement

_ESPACES = re.compile(r"[ \t\u2000-\u200a\u3000]+")


class Nettoyeur:
    def __init__(self, regles: Regles):
        self.regles = regles
        self.remplacements = [r for r in regles.remplacements if r.actif]
        self.corrections = regles.corrections
        self._motif_corrections = None
        if self.corrections:
            alternatives = sorted(self.corrections, key=len, reverse=True)
            self._motif_corrections = re.compile(
                r"(?<![\w-])(" + "|".join(re.escape(a) for a in alternatives) + r")(?![\w-])",
                re.IGNORECASE,
            )

    def nettoyer(self, texte: str, changements: list[Changement]) -> str:
        texte = _ESPACES.sub(" ", texte).strip()

        for regle in self.remplacements:
            nouveau, n = regle.appliquer(texte)
            if n and nouveau != texte:
                changements.append(Changement(regle.nom, texte, nouveau))
                texte = nouveau

        return self.corriger(texte, changements).strip()

    def corriger(self, texte: str, changements: list[Changement]) -> str:
        """Seulement les remplacements de mots entiers (espaces et ponctuation intacts)."""
        if not self._motif_corrections:
            return texte
        return self._motif_corrections.sub(lambda m: self._corriger(m.group(0), changements), texte)

    def _corriger(self, mot: str, changements: list[Changement]) -> str:
        correction = self.corrections[mot.lower()]
        if mot.isupper() and len(mot) > 1:
            correction = correction.upper()
        elif mot[0].isupper():
            correction = correction[0].upper() + correction[1:]
        changements.append(Changement("Correction", mot, correction))
        return correction

    def finaliser(self, bloc: Bloc) -> None:
        """Règles typographiques dépendant du type de bloc."""
        texte = bloc.texte
        if not texte:
            return
        options = self.regles.options
        if options.majuscule_debut and bloc.type in ("paragraphe", "liste"):
            m = re.search(r"[^\W\d_]+", texte)
            # Seulement si le premier mot est entièrement en minuscules (pas « pH », « mmHg »).
            if m and m.start() == 0 and m.group(0).islower():
                texte = texte[0].upper() + texte[1:]
        if (
            options.point_final
            and bloc.type == "paragraphe"
            and len(texte.split()) >= 4
            and re.search(r"[\w)»]$", texte)
        ):
            texte += "."
        bloc.texte = texte


def nettoyer_blocs(blocs: list[Bloc], regles: Regles) -> list[Changement]:
    nettoyeur = Nettoyeur(regles)
    changements: list[Changement] = []
    for bloc in blocs:
        for b in bloc.textuels():
            if b.type == "titre":
                continue  # titre normalisé par le détecteur de sections
            b.texte = nettoyeur.nettoyer(b.texte, changements)
            nettoyeur.finaliser(b)
    return changements
