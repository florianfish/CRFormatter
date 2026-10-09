"""Nettoyage du texte : espaces, règles regex, corrections orthographiques connues.

Chaque remplacement se fait sur le texte *avec* sa mise en forme (`TexteStyle`) : le gras ou
le souligné d'un libellé est conservé quand une règle modifie le texte autour.
"""

from __future__ import annotations

import re

from ..rules import Regles, expanser_remplacement
from .model import Bloc, Changement, TexteStyle

# Espaces multiples *entre* deux mots. Les espaces de début de ligne et les tabulations servent
# souvent à aligner (signature, colonnes) : on n'y touche pas.
_ESPACES = re.compile(r"(?<=\S)[ \u2000-\u200a\u3000]{2,}(?=\S)")


def _remplacer_tout(texte: TexteStyle, motif: re.Pattern[str], remplacement) -> int:
    """Remplace toutes les occurrences, de la fin vers le début pour garder les positions."""
    occurrences = list(motif.finditer(texte.texte))
    for m in reversed(occurrences):
        nouveau = remplacement(m) if callable(remplacement) else m.expand(remplacement)
        if nouveau != m.group(0):
            texte.remplacer(m.start(), m.end(), nouveau)
    return len(occurrences)


class Nettoyeur:
    def __init__(self, regles: Regles):
        self.regles = regles
        self.remplacements = [(r, r.compiler()) for r in regles.remplacements if r.actif]
        self.corrections = regles.corrections
        self._motif_corrections = None
        if self.corrections:
            alternatives = sorted(self.corrections, key=len, reverse=True)
            self._motif_corrections = re.compile(
                # Mot entier ; un tiret collé (« -kardegic », puce de liste) n'empêche pas la correction
                r"(?<!\w)(" + "|".join(re.escape(a) for a in alternatives) + r")(?!\w)",
                re.IGNORECASE,
            )

    def nettoyer(self, bloc: Bloc, changements: list[Changement]) -> None:
        texte = TexteStyle(bloc)
        _remplacer_tout(texte, _ESPACES, " ")

        for regle, motif in self.remplacements:
            avant = texte.texte
            try:
                _remplacer_tout(texte, motif, expanser_remplacement(regle.remplacement))
            except (re.error, IndexError) as e:
                raise ValueError(f"règle « {regle.nom} » : remplacement invalide ({e})") from e
            if texte.texte != avant:
                changements.append(Changement(regle.nom, avant, texte.texte))

        self.corriger(texte, changements)
        self._majuscule(texte)
        self._point_final(texte)
        texte.appliquer(bloc)

    def corriger(self, texte: TexteStyle, changements: list[Changement]) -> None:
        """Seulement les remplacements de mots entiers (espaces et ponctuation intacts)."""
        if self._motif_corrections:
            _remplacer_tout(texte, self._motif_corrections, lambda m: self._corriger(m.group(0), changements))

    def _corriger(self, mot: str, changements: list[Changement]) -> str:
        correction = self.corrections[mot.lower()]
        if mot.isupper() and len(mot) > 1:
            correction = correction.upper()
        elif mot[0].isupper():
            correction = correction[0].upper() + correction[1:]
        changements.append(Changement("Correction", mot, correction))
        return correction

    def _majuscule(self, texte: TexteStyle) -> None:
        if not self.regles.options.majuscule_debut:
            return
        # Premier mot du paragraphe (après d'éventuels tiret de liste, espaces ou tabulations),
        # seulement s'il est entièrement en minuscules (pas « pH », « mmHg »).
        m = re.match(r"[\s\-–—•*]*([^\W\d_]+)", texte.texte)
        if m and m.group(1).islower():
            texte.remplacer(m.start(1), m.start(1) + 1, m.group(1)[0].upper())

    def _point_final(self, texte: TexteStyle) -> None:
        contenu = texte.texte.rstrip()
        if (
            self.regles.options.point_final
            and len(contenu.split()) >= 4
            and re.search(r"[\w)»]$", contenu)
            and not contenu.endswith(":")
        ):
            texte.remplacer(len(contenu), len(contenu), ".")


def nettoyer_blocs(blocs: list[Bloc], regles: Regles) -> list[Changement]:
    nettoyeur = Nettoyeur(regles)
    changements: list[Changement] = []
    for bloc in blocs:
        for p in bloc.textuels():
            if not p.protege and p.texte.strip():
                nettoyeur.nettoyer(p, changements)
    return changements
