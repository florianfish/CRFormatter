"""Lecture d'un .docx en blocs de texte brut (la mise en forme d'origine est ignorée)."""

from __future__ import annotations

import io
import unicodedata

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from .model import Bloc


def _normaliser(texte: str) -> str:
    return unicodedata.normalize("NFC", texte)


def _lire_paragraphe(p: Paragraph) -> list[Bloc]:
    texte = _normaliser(p.text)
    runs = [r for r in p.runs if r.text.strip()]
    gras = bool(runs) and all(r.bold for r in runs)
    style = (p.style.name if p.style is not None else "") or ""
    liste_word = p._p.pPr is not None and p._p.pPr.numPr is not None
    liste_word = liste_word or style.lower().startswith(("list", "liste"))
    # Les retours à la ligne manuels (Maj+Entrée) séparent souvent des paragraphes.
    return [
        Bloc("paragraphe", texte=ligne, original=ligne, gras=gras, liste_word=liste_word)
        for ligne in texte.split("\n")
        if ligne.strip()
    ]


def _lire_tableau(t: Table) -> Bloc:
    lignes: list[list[Bloc]] = []
    for row in t.rows:
        cellules = []
        for cell in row.cells:
            texte = " ".join(_normaliser(cell.text).split("\n"))
            cellules.append(Bloc("paragraphe", texte=texte, original=texte))
        lignes.append(cellules)
    return Bloc("tableau", lignes=lignes)


def lire_docx(data: bytes) -> list[Bloc]:
    doc = Document(io.BytesIO(data))
    blocs: list[Bloc] = []
    for element in doc.iter_inner_content():
        if isinstance(element, Paragraph):
            blocs.extend(_lire_paragraphe(element))
        elif isinstance(element, Table):
            blocs.append(_lire_tableau(element))
    return blocs
