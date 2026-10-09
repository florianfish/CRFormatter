"""Chaîne de traitement : lecture → structure → nettoyage → orthographe → écriture."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from ..rules import Regles
from .cleaner import nettoyer_blocs
from .model import Bloc, Changement
from .reader import lire_docx
from .sections import structurer
from .spelling import Correcteur
from .writer import ecrire_docx


@dataclass
class Resultat:
    blocs: list[Bloc]
    changements: list[Changement]
    docx: bytes = b""
    orthographe_active: bool = False
    inconnus: Counter = field(default_factory=Counter)
    suggestions: dict[str, list[str]] = field(default_factory=dict)


def traiter_blocs(blocs: list[Bloc], regles: Regles, correcteur: Correcteur | None) -> Resultat:
    blocs = structurer(blocs, regles.sections, regles.options.detecter_titres)
    changements = nettoyer_blocs(blocs, regles)
    resultat = Resultat(blocs, changements)

    if regles.options.verifier_orthographe and correcteur is not None and correcteur.disponible:
        textuels = [b for bloc in blocs for b in bloc.textuels() if bloc.type != "titre"]
        for b, inconnus in zip(textuels, correcteur.verifier([b.texte for b in textuels])):
            b.inconnus = inconnus
            for i in inconnus:
                resultat.inconnus[i.mot] += 1
                resultat.suggestions[i.mot] = i.suggestions
        resultat.orthographe_active = True
    return resultat


def formater(data: bytes, regles: Regles, modele: bytes | None, correcteur: Correcteur | None) -> Resultat:
    resultat = traiter_blocs(lire_docx(data), regles, correcteur)
    resultat.docx = ecrire_docx(
        resultat.blocs, modele, commentaires=regles.options.commentaires_orthographe
    )
    return resultat


def traiter_texte(texte: str, regles: Regles, correcteur: Correcteur | None) -> Resultat:
    """Applique les règles à un texte brut (un paragraphe par ligne) : utilisé par le testeur."""
    blocs = [Bloc("paragraphe", texte=l, original=l) for l in texte.splitlines() if l.strip()]
    return traiter_blocs(blocs, regles, correcteur)
