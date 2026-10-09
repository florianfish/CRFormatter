"""Lecture d'un .docx : un bloc par paragraphe ou tableau du corps, relié à son élément Word."""

from __future__ import annotations

import copy
import io
import unicodedata
from dataclasses import dataclass

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

from .model import Bloc, Format, fusionner

# Contenu qu'une réécriture du texte casserait : le paragraphe est laissé tel quel.
BALISES_PROTEGEES = {
    qn(t) for t in (
        "w:hyperlink", "w:fldSimple", "w:fldChar", "w:instrText", "w:drawing", "w:pict", "w:object",
        "w:footnoteReference", "w:endnoteReference", "w:commentReference", "w:sdt", "w:ins", "w:del",
        "w:moveFrom", "w:moveTo", "w:smartTag", "w:customXml", "w:sym", "w:ruby", "w:oMath", "w:oMathPara",
    )
} | {"{http://schemas.openxmlformats.org/markup-compatibility/2006}AlternateContent"}
# Éléments d'une mise en forme de texte que l'éditeur gère lui-même
PROPRIETES_EDITABLES = {qn("w:b"), qn("w:bCs"), qn("w:i"), qn("w:iCs"), qn("w:u")}


@dataclass
class Index:
    """Éléments du document repérés par identifiant, et éléments du corps non éditables."""

    elements: dict[str, object]
    # Éléments de niveau corps qui ne sont ni paragraphe ni tableau (signets, contrôles de contenu…),
    # avec l'identifiant de l'élément qui les précède (pour les remettre à leur place).
    bruts: list[tuple[object, str | None]]
    section_finale: object | None


def indexer(doc) -> Index:
    elements: dict[str, object] = {}
    bruts: list[tuple[object, str | None]] = []
    section_finale = None
    precedent = None
    for i, enfant in enumerate(doc.element.body.iterchildren()):
        if enfant.tag == qn("w:p"):
            ident = f"p{i}"
        elif enfant.tag == qn("w:tbl"):
            ident = f"t{i}"
            for r, tr in enumerate(enfant.iterchildren(qn("w:tr"))):
                for c, tc in enumerate(tr.iterchildren(qn("w:tc"))):
                    for k, p in enumerate(tc.iterchildren(qn("w:p"))):
                        elements[f"{ident}.{r}.{c}.{k}"] = p
        elif enfant.tag == qn("w:sectPr"):
            section_finale = enfant
            continue
        else:
            bruts.append((enfant, precedent))
            continue
        elements[ident] = enfant
        precedent = ident
    return Index(elements, bruts, section_finale)


def _normaliser(texte: str) -> str:
    return unicodedata.normalize("NFC", texte)


def proprietes_texte(run_element) -> object | None:
    """Copie des propriétés Word d'un morceau de texte, sans gras / italique / souligné."""
    rpr = run_element.find(qn("w:rPr"))
    if rpr is None:
        return None
    rpr = copy.deepcopy(rpr)
    for enfant in list(rpr):
        if enfant.tag in PROPRIETES_EDITABLES or enfant.tag == qn("w:rPrChange"):
            rpr.remove(enfant)
    return rpr if len(rpr) else None


def est_protege(p) -> bool:
    if any(e.tag in BALISES_PROTEGEES for e in p.iter()):
        return True
    # Saut de page ou de colonne manuel
    return any(br.get(qn("w:type")) in ("page", "column") for br in p.iter(qn("w:br")))


ALIGNEMENTS = {WD_ALIGN_PARAGRAPH.CENTER: "centre", WD_ALIGN_PARAGRAPH.RIGHT: "droite",
               WD_ALIGN_PARAGRAPH.JUSTIFY: "justifie"}


def _police(rpr) -> tuple[str | None, float | None]:
    if rpr is None:
        return None, None
    polices, taille = rpr.find(qn("w:rFonts")), rpr.find(qn("w:sz"))
    nom = polices.get(qn("w:ascii")) if polices is not None else None
    try:
        return nom, int(taille.get(qn("w:val"))) / 2 if taille is not None else None
    except (TypeError, ValueError):
        return nom, None


def _police_du_style(paragraphe: Paragraph) -> tuple[str | None, float | None]:
    nom = taille = None
    style = paragraphe.style
    while style is not None and (nom is None or taille is None):
        nom = nom or style.font.name
        taille = taille or (style.font.size.pt if style.font.size else None)
        style = style.base_style
    return nom, taille


def lire_mise_en_page(paragraphe: Paragraph, rpr) -> dict:
    """Mise en page directe du paragraphe ; police et taille de son texte, à défaut de sa marque
    de paragraphe (paragraphe vide), à défaut de son style."""
    f = paragraphe.paragraph_format
    m: dict = {}
    if f.alignment in ALIGNEMENTS:
        m["alignement"] = ALIGNEMENTS[f.alignment]
    for cle, valeur in (("retrait_gauche", f.left_indent), ("retrait_premiere_ligne", f.first_line_indent),
                        ("espace_avant", f.space_before), ("espace_apres", f.space_after)):
        if valeur is not None:
            m[cle] = round(valeur.pt, 1)
    if isinstance(f.line_spacing, float):  # multiple de l'interligne simple (pas une hauteur fixe)
        m["interligne"] = round(f.line_spacing, 2)
    ppr = paragraphe._p.find(qn("w:pPr"))
    sources = [_police(rpr), _police(ppr.find(qn("w:rPr")) if ppr is not None else None)]
    sources.append(_police_du_style(paragraphe))
    nom = next((n for n, _ in sources if n), None)
    taille = next((t for _, t in sources if t), None)
    if nom:
        m["police"] = nom
    if taille:
        m["taille"] = taille
    return m


def lire_paragraphe(p, ident: str, doc) -> Bloc:
    paragraphe = Paragraph(p, doc)
    ppr = p.find(qn("w:pPr"))
    bloc = Bloc(
        "paragraphe",
        source=ident,
        protege=est_protege(p),
        fin_section=ppr is not None and ppr.find(qn("w:sectPr")) is not None,
    )
    texte, formats = "", []
    for run in paragraphe.runs:  # morceaux directs (les liens et champs rendent le paragraphe protégé)
        morceau = _normaliser(run.text)
        if not morceau:
            continue
        rpr = proprietes_texte(run._r)
        if bloc.rpr_base is None and rpr is not None:
            bloc.rpr_base = rpr
        formats.append(Format(len(texte), len(texte) + len(morceau), bool(run.bold), bool(run.italic),
                              bool(run.underline), rpr))
        texte += morceau
    if bloc.protege:
        texte = _normaliser(paragraphe.text)
    bloc.texte = bloc.original = texte
    bloc.formats = fusionner(formats)
    bloc.mise_en_page = lire_mise_en_page(paragraphe, bloc.rpr_base)
    bloc.empreinte_origine = bloc.empreinte()
    return bloc


def a_des_bordures(tbl) -> bool:
    """Tableau quadrillé (style « Grille » ou bordures directes) : repris par « Copier pour Word »."""
    tblpr = tbl.find(qn("w:tblPr"))
    if tblpr is None:
        return False
    style = tblpr.find(qn("w:tblStyle"))
    if style is not None and any(m in (style.get(qn("w:val")) or "").lower() for m in ("grid", "grille")):
        return True
    bordures = tblpr.find(qn("w:tblBorders"))
    return bordures is not None and any(b.get(qn("w:val")) not in (None, "nil", "none") for b in bordures)


def mise_en_page_tableau(tbl) -> dict:
    m = {"bordures": a_des_bordures(tbl)}
    largeur = tbl.find(qn("w:tblPr") + "/" + qn("w:tblW"))
    if largeur is not None and largeur.get(qn("w:type")) == "pct" and largeur.get(qn("w:w")) in ("5000", "100%"):
        m["pleine_largeur"] = True  # ex. résultats regroupés en colonnes : colonnes de même largeur
    return m


def lire_docx(data: bytes) -> list[Bloc]:
    doc = Document(io.BytesIO(data))
    index = indexer(doc)
    blocs: list[Bloc] = []
    for ident, element in index.elements.items():
        if "." in ident:
            continue  # paragraphe de cellule : lu avec son tableau
        if ident.startswith("p"):
            blocs.append(lire_paragraphe(element, ident, doc))
            continue
        tableau = Bloc("tableau", source=ident, mise_en_page=mise_en_page_tableau(element))
        for r, tr in enumerate(element.iterchildren(qn("w:tr"))):
            ligne = []
            for c, tc in enumerate(tr.iterchildren(qn("w:tc"))):
                cellule = Bloc("cellule")
                cellule.paragraphes = [lire_paragraphe(p, f"{ident}.{r}.{c}.{k}", doc)
                                       for k, p in enumerate(tc.iterchildren(qn("w:p")))]
                ligne.append(cellule)
            tableau.lignes.append(ligne)
        blocs.append(tableau)
    return blocs
