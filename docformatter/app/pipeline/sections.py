"""Rubriques : « ATCD : HTA » → « Antécédents : HTA », directement dans le paragraphe.

La mise en page du document n'est pas modifiée (pas de transformation en titre Word) : seul
le libellé de la rubrique est remplacé par son titre normalisé, avec sa mise en forme.
"""

from __future__ import annotations

import re
import unicodedata

from .model import Bloc, Changement, TexteStyle

# Chaque lettre d'une variante accepte ses formes accentuées (« antecedents » ↔ « Antécédents »).
_ACCENTS = {
    "a": "aàâä", "c": "cç", "e": "eéèêë", "i": "iîï", "o": "oôö", "u": "uùûü", "y": "yÿ",
}
_SEPARATEUR = r"[ \u00a0]*(?::|-\s|–|—)"


def _motif_variante(variante: str) -> str:
    morceaux = []
    for car in variante.lower():
        if car.isspace():
            morceaux.append(r"\s+")
        elif car in "'’":
            morceaux.append(r"['’]\s*")
        elif car in _ACCENTS:
            morceaux.append(f"[{_ACCENTS[car]}]")
        else:
            morceaux.append(re.escape(car))
    return "".join(morceaux)


def _sans_accents(texte: str) -> str:
    texte = unicodedata.normalize("NFD", " ".join(texte.lower().split()))
    return "".join(c for c in texte if unicodedata.category(c) != "Mn").replace("’", "'")


class DetecteurSections:
    def __init__(self, sections: dict[str, list[str]]):
        variantes = [(v, titre) for titre, alias in sections.items() for v in {titre, *alias}]
        # Les variantes les plus longues d'abord : « atcd chirurgicaux » avant « atcd ».
        variantes.sort(key=lambda x: len(x[0]), reverse=True)
        self._motifs = [
            (re.compile(rf"^(\s*)({_motif_variante(v)})(?=\s*$|{_SEPARATEUR})", re.IGNORECASE), titre)
            for v, titre in variantes
        ]

    def reconnaitre(self, texte: str) -> tuple[int, int, str] | None:
        """(début, fin) du libellé de rubrique et titre normalisé, ou None.

        Le libellé n'est reconnu que seul sur sa ligne ou suivi d'un séparateur (« : », « - »),
        pour ne pas toucher « Traitement par IPP débuté ».
        """
        for motif, titre in self._motifs:
            m = motif.match(texte)
            if m:
                return m.start(2), m.end(2), titre
        return None


def renommer_rubriques(blocs: list[Bloc], sections: dict[str, list[str]], changements: list[Changement]) -> None:
    detecteur = DetecteurSections(sections)
    for bloc in blocs:
        for p in bloc.textuels():
            if p.protege or not p.texte.strip():
                continue
            trouve = detecteur.reconnaitre(p.texte)
            if trouve is None:
                continue
            debut, fin, titre = trouve
            libelle = p.texte[debut:fin]
            if _sans_accents(libelle) == _sans_accents(titre):
                continue  # déjà le bon libellé (la casse choisie par le médecin est respectée)
            texte = TexteStyle(p)
            # « ATCD » en majuscules → « ANTÉCÉDENTS » : on garde le choix de casse du médecin
            texte.remplacer(debut, fin, titre.upper() if libelle.isupper() and len(libelle) > 4 else titre)
            avant = p.texte
            texte.appliquer(p)
            changements.append(Changement("Rubrique", avant, p.texte))
