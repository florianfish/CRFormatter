"""Chaîne de traitement : colonnes → lecture → rubriques → nettoyage → orthographe → écriture sur place."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from ..rules import Regles
from .cleaner import nettoyer_blocs
from .colonnes import regrouper_resultats
from .model import Bloc, Changement
from .reader import lire_docx
from .sections import renommer_rubriques
from .spelling import Correcteur
from .writer import ecrire_docx


@dataclass
class Resultat:
    blocs: list[Bloc]
    changements: list[Changement]
    docx: bytes = b""
    # Document de départ réellement lu (après regroupement en colonnes) : les identifiants des
    # paragraphes s'y rapportent, une retouche doit donc être réécrite sur ce même document
    base: bytes = b""
    orthographe_active: bool = False
    inconnus: Counter = field(default_factory=Counter)
    suggestions: dict[str, list[str]] = field(default_factory=dict)


def _verifier(resultat: Resultat, regles: Regles, correcteur: Correcteur | None) -> None:
    if not (regles.options.verifier_orthographe and correcteur is not None and correcteur.disponible):
        return
    paragraphes = [p for bloc in resultat.blocs for p in bloc.textuels() if not p.protege]
    for p, inconnus in zip(paragraphes, correcteur.verifier([p.texte for p in paragraphes])):
        p.inconnus = inconnus
        for i in inconnus:
            resultat.inconnus[i.mot] += 1
            resultat.suggestions[i.mot] = i.suggestions
    resultat.orthographe_active = True


def traiter_blocs(blocs: list[Bloc], regles: Regles, correcteur: Correcteur | None) -> Resultat:
    changements: list[Changement] = []
    renommer_rubriques(blocs, regles.sections, changements)
    changements += nettoyer_blocs(blocs, regles)
    resultat = Resultat(blocs, changements)
    _verifier(resultat, regles, correcteur)
    return resultat


def formater(data: bytes, regles: Regles, correcteur: Correcteur | None) -> Resultat:
    base, colonnes = regrouper_resultats(data, regles)
    resultat = traiter_blocs(lire_docx(base), regles, correcteur)
    resultat.changements[:0] = colonnes
    resultat.base = base
    resultat.docx = ecrire_docx(base, resultat.blocs, commentaires=regles.options.commentaires_orthographe)
    return resultat


def finaliser_retouche(data: bytes, blocs: list[Bloc], regles: Regles, correcteur: Correcteur | None) -> Resultat:
    """Document retouché à la main : seulement l'orthographe et l'écriture, sans aucune règle
    automatique (les choix de la personne qui a retouché priment)."""
    for bloc in blocs:
        for p in bloc.textuels():
            p.inconnus = []
            p.original = p.texte  # l'aperçu ne montre plus de différences
    resultat = Resultat(blocs, [], base=data)
    _verifier(resultat, regles, correcteur)
    resultat.docx = ecrire_docx(data, blocs, commentaires=regles.options.commentaires_orthographe)
    return resultat


def traiter_texte(texte: str, regles: Regles, correcteur: Correcteur | None) -> Resultat:
    """Applique les règles à un texte brut (un paragraphe par ligne) : utilisé par le testeur."""
    blocs = [Bloc("paragraphe", texte=l, original=l) for l in texte.splitlines() if l.strip()]
    return traiter_blocs(blocs, regles, correcteur)
