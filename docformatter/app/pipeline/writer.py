"""Écriture sur place : le document d'origine est conservé (en-têtes, pieds de page, sections,
marges, styles, champs, liens) ; seul le texte des paragraphes modifiés est réécrit."""

from __future__ import annotations

import copy
import io

from docx import Document
from docx.enum.text import WD_COLOR_INDEX
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.run import Run

from .model import Bloc, Inconnu
from .reader import indexer

AUTEUR = "DocFormatter"
# Enfants d'un paragraphe remplacés lors de la réécriture du texte ; le reste (propriétés de
# paragraphe, signets…) est conservé.
A_REMPLACER = {qn("w:r"), qn("w:proofErr")}


def _proprietes(rpr_origine, gras: bool, italique: bool, souligne: bool):
    rpr = copy.deepcopy(rpr_origine) if rpr_origine is not None else OxmlElement("w:rPr")
    # Ordre imposé par le schéma Word : rStyle, rFonts, b, bCs, i, iCs, …, u, …
    apres_style = 0
    for i, enfant in enumerate(rpr):
        if enfant.tag in (qn("w:rStyle"), qn("w:rFonts")):
            apres_style = i + 1
    for actif, balise in ((italique, "w:i"), (gras, "w:b")):
        if actif:
            rpr.insert(apres_style, OxmlElement(balise))
    if souligne:
        u = OxmlElement("w:u")
        u.set(qn("w:val"), "single")
        avant = next((e for e in rpr if e.tag in (qn("w:effect"), qn("w:bdr"), qn("w:shd"), qn("w:fitText"),
                                                   qn("w:vertAlign"), qn("w:rtl"), qn("w:cs"), qn("w:em"),
                                                   qn("w:lang"), qn("w:eastAsianLayout"), qn("w:specVanish"),
                                                   qn("w:oMath"))), None)
        if avant is not None:
            avant.addprevious(u)
        else:
            rpr.append(u)
    return rpr if len(rpr) else None


def _reecrire(p, bloc: Bloc, doc, commentaires: bool) -> None:
    for enfant in list(p):
        if enfant.tag in A_REMPLACER:
            p.remove(enfant)
    runs_par_inconnu: dict[int, tuple[Inconnu, list]] = {}
    for t in bloc.troncons():
        r = OxmlElement("w:r")
        rpr = _proprietes(t.rpr if t.rpr is not None else bloc.rpr_base, t.gras, t.italique, t.souligne)
        if rpr is not None:
            r.append(rpr)
        p.append(r)
        run = Run(r, None)
        run.text = t.texte  # \t et \n deviennent tabulation et retour à la ligne Word
        if t.inconnu is not None:
            run.font.highlight_color = WD_COLOR_INDEX.YELLOW
            runs_par_inconnu.setdefault(id(t.inconnu), (t.inconnu, []))[1].append(run)
    if not commentaires:
        return
    for inconnu, runs in runs_par_inconnu.values():
        texte = ("Mot inconnu. Suggestions : " + ", ".join(inconnu.suggestions)
                 if inconnu.suggestions else "Mot inconnu, aucune suggestion.")
        doc.add_comment(runs, text=texte, author=AUTEUR, initials="DF")


def _nouveau_paragraphe(modele):
    """Paragraphe vide reprenant la mise en page de `modele`, sans sa fin de section."""
    p = OxmlElement("w:p")
    if modele is not None and (ppr := modele.find(qn("w:pPr"))) is not None:
        ppr = copy.deepcopy(ppr)
        for retirer in (qn("w:sectPr"), qn("w:pPrChange")):
            for e in ppr.findall(retirer):
                ppr.remove(e)
        p.append(ppr)
    return p


def _ecrire_paragraphe(element, bloc: Bloc, doc, commentaires: bool) -> None:
    if bloc.protege:
        return
    if bloc.modifie() or bloc.inconnus:
        _reecrire(element, bloc, doc, commentaires)


def ecrire_docx(original: bytes, blocs: list[Bloc], commentaires: bool) -> bytes:
    doc = Document(io.BytesIO(original))
    index = indexer(doc)
    corps = doc.element.body

    ordre = []
    for bloc in blocs:
        if bloc.type == "tableau":
            element = index.elements[bloc.source]
            for p in bloc.textuels():
                _ecrire_paragraphe(index.elements[p.source], p, doc, commentaires)
        else:
            if bloc.source is not None:
                element = index.elements[bloc.source]
            else:
                element = _nouveau_paragraphe(index.elements.get(bloc.origine) if bloc.origine else None)
            _ecrire_paragraphe(element, bloc, doc, commentaires)
        ordre.append((bloc.source, element))

    # Reconstruction de l'ordre du corps (paragraphes ajoutés, supprimés ou déplacés dans l'éditeur).
    # Les éléments ni paragraphe ni tableau (signets…) suivent l'élément qui les précédait.
    presents = {source for source, _ in ordre if source}
    ordre_origine = [k for k in index.elements if "." not in k]
    for enfant in list(corps):
        corps.remove(enfant)
    bruts_par_precedent: dict[str | None, list] = {}
    for brut, precedent in index.bruts:
        # Si l'élément qui le précédait a été supprimé : le dernier élément conservé avant lui
        while precedent is not None and precedent not in presents:
            i = ordre_origine.index(precedent)
            precedent = ordre_origine[i - 1] if i > 0 else None
        bruts_par_precedent.setdefault(precedent, []).append(brut)
    for brut in bruts_par_precedent.pop(None, []):
        corps.append(brut)
    for source, element in ordre:
        corps.append(element)
        for brut in bruts_par_precedent.pop(source, []) if source else []:
            corps.append(brut)
    if index.section_finale is not None:
        corps.append(index.section_finale)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
