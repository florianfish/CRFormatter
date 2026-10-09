"""Retouche manuelle d'un document formaté : format échangé avec l'éditeur et conversions.

L'éditeur affiche les paragraphes du document d'origine, chacun repéré par son identifiant
(`source`). Un paragraphe que la personne n'a pas modifié est repris tel quel (polices, tailles…) ;
un paragraphe modifié est réécrit avec la police de son texte d'origine ; un paragraphe ajouté
reprend la mise en page de celui dont il est issu (`origine`).
"""

from __future__ import annotations

import copy
from typing import Literal

from pydantic import BaseModel, Field

from .pipeline.cleaner import Nettoyeur
from .pipeline.model import Bloc, Format, TexteStyle, fusionner
from .rules import Regles
from .store import RegleInvalide

TEXTE_MAX = 20_000
ESPACE_INVISIBLE = "\u200b"


class Segment(BaseModel):
    texte: str = Field("", max_length=TEXTE_MAX)
    gras: bool = False
    italique: bool = False
    souligne: bool = False

    def attributs(self) -> tuple[bool, bool, bool]:
        return self.gras, self.italique, self.souligne


class ParagrapheEdite(BaseModel):
    id: str | None = Field(None, max_length=40)
    origine: str | None = Field(None, max_length=40)
    segments: list[Segment] = Field(default_factory=list, max_length=2_000)


class BlocEdite(ParagrapheEdite):
    type: Literal["paragraphe", "tableau"]
    lignes: list[list[list[ParagrapheEdite]]] = Field(default_factory=list, max_length=500)


class Edition(BaseModel):
    blocs: list[BlocEdite] = Field(max_length=5_000)


# ---- Modèle interne → éditeur ----------------------------------------------------------

def _segments(p: Bloc) -> list[dict]:
    return [
        {"texte": t.texte, "gras": t.gras, "italique": t.italique, "souligne": t.souligne}
        for t in Bloc("paragraphe", texte=p.texte, formats=p.formats).troncons()
    ]


def _paragraphe(p: Bloc) -> dict:
    return {"type": "paragraphe", "id": p.source, "origine": p.origine, "segments": _segments(p),
            "protege": p.protege, "fin_section": p.fin_section, "mise_en_page": p.mise_en_page}


def vers_editeur(blocs: list[Bloc]) -> list[dict]:
    resultat = []
    for b in blocs:
        if b.type == "tableau":
            resultat.append({"type": "tableau", "id": b.source, "mise_en_page": b.mise_en_page, "lignes": [
                [[_paragraphe(p) for p in cellule.paragraphes] for cellule in ligne] for ligne in b.lignes
            ]})
        else:
            resultat.append(_paragraphe(b))
    return resultat


# ---- Éditeur → modèle interne ----------------------------------------------------------

def _memes_segments(saisis: list[Segment], p: Bloc) -> bool:
    return [s.model_dump() for s in saisis if s.texte] == _segments(p)


def _appliquer_segments(p: Bloc, segments: list[Segment]) -> None:
    texte, formats = "", []
    for seg in segments:
        morceau = seg.texte.replace(ESPACE_INVISIBLE, "").replace("\r", "")
        if morceau and any(seg.attributs()):
            formats.append(Format(len(texte), len(texte) + len(morceau), *seg.attributs()))
        texte += morceau
    p.texte, p.formats = texte, fusionner(formats)


class _Conversion:
    def __init__(self, precedents: list[Bloc]):
        self.index: dict[str, Bloc] = {}
        for bloc in precedents:
            for p in [bloc, *bloc.textuels()]:
                if p.source:
                    self.index[p.source] = p
        self.vus: set[str] = set()

    def precedent(self, ident: str) -> Bloc:
        if ident not in self.index:
            raise RegleInvalide("Le document a changé entre-temps : rechargez la page.")
        if ident in self.vus:
            raise RegleInvalide("Un paragraphe apparaît deux fois : rechargez la page.")
        self.vus.add(ident)
        return self.index[ident]

    def paragraphe(self, saisi: ParagrapheEdite) -> Bloc:
        if saisi.id is None:
            # Paragraphe ajouté : il reprend la mise en page et la police de son paragraphe d'origine
            modele = self.index.get(saisi.origine or "")
            if modele is None or modele.type != "paragraphe":
                raise RegleInvalide("Paragraphe ajouté sans modèle : rechargez la page.")
            nouveau = Bloc("paragraphe", origine=modele.source or modele.origine, rpr_base=modele.rpr_base,
                           mise_en_page=dict(modele.mise_en_page))
            _appliquer_segments(nouveau, saisi.segments)
            return nouveau
        precedent = self.precedent(saisi.id)
        bloc = copy.deepcopy(precedent)
        if not precedent.protege and not _memes_segments(saisi.segments, precedent):
            _appliquer_segments(bloc, saisi.segments)  # police d'origine (rpr_base), mise en forme saisie
        return bloc

    def tableau(self, saisi: BlocEdite) -> Bloc:
        tableau = copy.deepcopy(self.precedent(saisi.id or ""))
        if tableau.type != "tableau":
            raise RegleInvalide("Le document a changé entre-temps : rechargez la page.")
        for ligne, ligne_saisie in zip(tableau.lignes, saisi.lignes):
            for cellule, cellule_saisie in zip(ligne, ligne_saisie):
                # Paragraphes de la cellule tels que saisis (ajoutés, supprimés, fusionnés)
                paragraphes = [self.paragraphe(p) for p in cellule_saisie]
                if not paragraphes and cellule.paragraphes:  # une cellule Word garde un paragraphe
                    modele = cellule.paragraphes[0]
                    paragraphes = [Bloc("paragraphe", origine=modele.source, rpr_base=modele.rpr_base,
                                        mise_en_page=dict(modele.mise_en_page))]
                cellule.paragraphes = paragraphes
        return tableau


def depuis_editeur(edition: Edition, precedents: list[Bloc]) -> list[Bloc]:
    conversion = _Conversion(precedents)
    blocs = [conversion.tableau(b) if b.type == "tableau" else conversion.paragraphe(b) for b in edition.blocs]

    # Ce que l'éditeur ne permet pas de supprimer doit toujours être là
    for bloc in precedents:
        if bloc.type == "tableau":
            if bloc.source not in conversion.vus:
                raise RegleInvalide("Un tableau a disparu : rechargez la page.")
            if any(p.protege and p.source not in conversion.vus for p in bloc.textuels()):
                raise RegleInvalide("Un paragraphe protégé a disparu : rechargez la page.")
        elif bloc.source not in conversion.vus and (bloc.protege or bloc.fin_section):
            raise RegleInvalide("Un paragraphe protégé a disparu : rechargez la page.")
    if not any(p.texte.strip() for b in blocs for p in b.textuels()):
        raise RegleInvalide("Le document est vide : ajoutez du texte avant d'enregistrer.")
    return blocs


# ---- Remplacements dans un document retouché -------------------------------------------

def remplacer_mots(blocs: list[Bloc], remplacements: dict[str, str]) -> list[Bloc]:
    """Remplace des mots entiers (casse et mise en forme conservées)."""
    if not remplacements:
        return blocs
    nettoyeur = Nettoyeur(Regles(corrections=remplacements))
    blocs = copy.deepcopy(blocs)
    for bloc in blocs:
        for p in bloc.textuels():
            if not p.protege:
                texte = TexteStyle(p)
                nettoyeur.corriger(texte, [])
                texte.appliquer(p)
    return blocs
