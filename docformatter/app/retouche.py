"""Retouche manuelle d'un document formaté : format échangé avec l'éditeur et conversions.

L'éditeur manipule des *segments* (morceaux de texte de même mise en forme) ; le modèle interne
garde le texte brut + des plages `Format`, pour que l'orthographe et les remplacements
continuent de travailler sur du texte simple.
"""

from __future__ import annotations

import copy
import re
from typing import Literal

from pydantic import BaseModel, Field

from .pipeline.cleaner import Nettoyeur
from .pipeline.model import Bloc, Format
from .rules import Regles

TEXTE_MAX = 20_000
SEGMENTS_MAX = 2_000
ESPACE_INVISIBLE = "\u200b"


class Segment(BaseModel):
    texte: str = Field("", max_length=TEXTE_MAX)
    gras: bool = False
    italique: bool = False
    souligne: bool = False

    def attributs(self) -> tuple[bool, bool, bool]:
        return self.gras, self.italique, self.souligne


Segments = list[Segment]


class BlocEdite(BaseModel):
    type: Literal["titre", "paragraphe", "liste", "tableau"]
    segments: Segments = Field(default_factory=list, max_length=SEGMENTS_MAX)
    numerote: bool = False
    lignes: list[list[Segments]] = Field(default_factory=list, max_length=500)


class Edition(BaseModel):
    blocs: list[BlocEdite] = Field(max_length=5000)


# ---- Modèle interne → éditeur ----------------------------------------------------------

def _segments(bloc: Bloc) -> list[dict]:
    return [
        {"texte": t.texte, "gras": t.gras, "italique": t.italique, "souligne": t.souligne}
        for t in Bloc("paragraphe", texte=bloc.texte, formats=bloc.formats).troncons()
    ]


def vers_editeur(blocs: list[Bloc]) -> list[dict]:
    resultat = []
    for b in blocs:
        if b.type == "tableau":
            resultat.append({"type": "tableau", "lignes": [[_segments(c) for c in ligne] for ligne in b.lignes]})
        else:
            resultat.append({"type": b.type, "segments": _segments(b), "numerote": b.numerote})
    return resultat


# ---- Éditeur → modèle interne ----------------------------------------------------------

def _texte_et_formats(segments: Segments) -> tuple[str, list[Format]]:
    """Concatène les segments ; espaces multiples réduites (insécables conservées)."""
    texte, formats = "", []
    for seg in segments:
        morceau = re.sub(r"[ \t]+", " ", seg.texte.replace(ESPACE_INVISIBLE, ""))
        if texte.endswith(" ") and morceau.startswith(" "):
            morceau = morceau[1:]
        if morceau and any(seg.attributs()):
            formats.append(Format(len(texte), len(texte) + len(morceau), *seg.attributs()))
        texte += morceau
    return texte, _fusionner(formats)


def _fusionner(formats: list[Format]) -> list[Format]:
    """Fusionne les plages contiguës de même mise en forme."""
    resultat: list[Format] = []
    for f in sorted(formats, key=lambda x: x.debut):
        if resultat and resultat[-1].fin == f.debut and resultat[-1].attributs() == f.attributs():
            resultat[-1].fin = f.fin
        else:
            resultat.append(f)
    return resultat


def _decouper(texte: str, formats: list[Format], debut: int, fin: int) -> tuple[str, list[Format]] | None:
    """Extrait [debut, fin) sans les espaces de bord ; None si la portion est vide."""
    portion = texte[debut:fin]
    debut += len(portion) - len(portion.lstrip())
    fin -= len(portion) - len(portion.rstrip())
    if debut >= fin:
        return None
    extrait = [
        Format(max(f.debut, debut) - debut, min(f.fin, fin) - debut, *f.attributs())
        for f in formats if f.fin > debut and f.debut < fin
    ]
    return texte[debut:fin], extrait


def _cellule(segments: Segments) -> Bloc:
    texte, formats = _texte_et_formats(segments)
    texte = texte.replace("\n", " ")
    morceau = _decouper(texte, formats, 0, len(texte))
    if morceau is None:
        return Bloc("paragraphe")
    return Bloc("paragraphe", texte=morceau[0], original=morceau[0], formats=morceau[1])


def depuis_editeur(edition: Edition) -> list[Bloc]:
    """Blocs saisis → modèle interne. Une saisie sur plusieurs lignes (collage) donne
    plusieurs blocs du même type ; les blocs vides sont ignorés."""
    blocs: list[Bloc] = []
    for b in edition.blocs:
        if b.type == "tableau":
            lignes = [[_cellule(c) for c in ligne[:30]] for ligne in b.lignes]
            lignes = [ligne for ligne in lignes if ligne]
            if lignes:
                blocs.append(Bloc("tableau", lignes=lignes))
            continue
        texte, formats = _texte_et_formats(b.segments)
        debut = 0
        for ligne in texte.split("\n"):
            morceau = _decouper(texte, formats, debut, debut + len(ligne))
            debut += len(ligne) + 1
            if morceau:
                blocs.append(Bloc(b.type, texte=morceau[0], original=morceau[0], formats=morceau[1],
                                  numerote=b.numerote and b.type == "liste"))
    return blocs


# ---- Remplacements dans un document retouché -------------------------------------------

def remplacer_mots(blocs: list[Bloc], remplacements: dict[str, str]) -> list[Bloc]:
    """Remplace des mots entiers (casse conservée), segment par segment pour garder la mise
    en forme. Un mot à cheval sur deux mises en forme n'est pas remplacé."""
    if not remplacements:
        return blocs
    nettoyeur = Nettoyeur(Regles(corrections=remplacements))
    blocs = copy.deepcopy(blocs)
    for bloc in blocs:
        for b in bloc.textuels():
            segments = [
                Segment(texte=nettoyeur.corriger(t.texte, []), gras=t.gras, italique=t.italique, souligne=t.souligne)
                for t in Bloc("paragraphe", texte=b.texte, formats=b.formats).troncons()
            ]
            b.texte, b.formats = _texte_et_formats(segments)
    return blocs
