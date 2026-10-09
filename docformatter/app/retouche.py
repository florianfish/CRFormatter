"""Retouche manuelle d'un document formaté : format échangé avec l'éditeur et conversions."""

from __future__ import annotations

import copy
import re
from typing import Literal

from pydantic import BaseModel, Field

from .pipeline.cleaner import Nettoyeur
from .pipeline.model import Bloc
from .rules import Regles

TEXTE_MAX = 20_000


class BlocEdite(BaseModel):
    type: Literal["titre", "paragraphe", "liste", "tableau"]
    texte: str = Field("", max_length=TEXTE_MAX)
    numerote: bool = False
    lignes: list[list[str]] = Field(default_factory=list, max_length=500)


class Edition(BaseModel):
    blocs: list[BlocEdite] = Field(max_length=5000)


def _propre(texte: str) -> str:
    """Espaces multiples réduites (les espaces insécables sont conservées)."""
    return re.sub(r"[ \t]+", " ", texte.replace("\u200b", "")).strip()


def vers_editeur(blocs: list[Bloc]) -> list[dict]:
    resultat = []
    for b in blocs:
        if b.type == "tableau":
            resultat.append({"type": "tableau", "lignes": [[c.texte for c in ligne] for ligne in b.lignes]})
        else:
            resultat.append({"type": b.type, "texte": b.texte, "numerote": b.numerote})
    return resultat


def depuis_editeur(edition: Edition) -> list[Bloc]:
    """Blocs saisis → modèle interne. Une saisie sur plusieurs lignes (collage) donne
    plusieurs blocs du même type ; les blocs vides sont ignorés."""
    blocs: list[Bloc] = []
    for b in edition.blocs:
        if b.type == "tableau":
            lignes = [[Bloc("paragraphe", texte=_propre(" ".join(c.splitlines()[:50])))
                       for c in ligne[:30]] for ligne in b.lignes]
            lignes = [ligne for ligne in lignes if ligne]
            if lignes:
                blocs.append(Bloc("tableau", lignes=lignes))
            continue
        for ligne in b.texte.splitlines():
            texte = _propre(ligne)
            if texte:
                blocs.append(Bloc(b.type, texte=texte, original=texte, numerote=b.numerote and b.type == "liste"))
    return blocs


def remplacer_mots(blocs: list[Bloc], remplacements: dict[str, str]) -> list[Bloc]:
    """Remplace des mots entiers (casse conservée), comme les remplacements automatiques."""
    if not remplacements:
        return blocs
    nettoyeur = Nettoyeur(Regles(corrections=remplacements))
    blocs = copy.deepcopy(blocs)
    for bloc in blocs:
        for b in bloc.textuels():
            b.texte = nettoyeur.nettoyer(b.texte, [])
    return blocs
