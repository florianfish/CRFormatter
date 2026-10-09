"""Résultats d'analyse sur plusieurs colonnes.

Les lignes de résultats consécutives (« Hb (g/dL) : 13,4 ») sont déplacées dans un tableau sans
bordure d'une ligne et de `nombre` cellules, remplies dans l'ordre de lecture (première moitié à
gauche…). Un tableau plutôt qu'une section Word en colonnes : il survit au copier-coller dans
Word et ne touche pas aux sections du document.

Le regroupement a lieu sur le .docx, avant la lecture : l'éditeur, l'aperçu et l'écriture sur
place voient ce tableau comme n'importe quel autre.
"""

from __future__ import annotations

import io
import math

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

from ..rules import Regles
from .model import Changement
from .reader import est_protege

LARGEUR_PAR_DEFAUT = 9_638  # largeur utile d'une page A4 aux marges de 2 cm (en vingtièmes de point)
CHERCHER_LIGNE_VIDE = 3     # distance maximale (en lignes) pour couper une colonne sur une ligne vide


def _colonnes_de_section(sect_pr) -> int:
    cols = sect_pr.find(qn("w:cols")) if sect_pr is not None else None
    try:
        return int(cols.get(qn("w:num"))) if cols is not None else 1
    except (TypeError, ValueError):
        return 1


def _sections(corps) -> dict:
    """Pour chaque élément du corps, la définition de section (sectPr) qui le régit."""
    resultat = {}
    courante = corps.find(qn("w:sectPr"))
    for enfant in reversed(list(corps.iterchildren())):
        ppr = enfant.find(qn("w:pPr")) if enfant.tag == qn("w:p") else None
        if ppr is not None and ppr.find(qn("w:sectPr")) is not None:
            courante = ppr.find(qn("w:sectPr"))
        resultat[enfant] = courante
    return resultat


def _largeur_utile(sect_pr) -> int:
    if sect_pr is None:
        return LARGEUR_PAR_DEFAUT
    taille, marges = sect_pr.find(qn("w:pgSz")), sect_pr.find(qn("w:pgMar"))
    try:
        return int(taille.get(qn("w:w"))) - int(marges.get(qn("w:left"))) - int(marges.get(qn("w:right")))
    except (AttributeError, TypeError, ValueError):
        return LARGEUR_PAR_DEFAUT


def _decouper(paragraphes: list, vides: set, nombre: int) -> list[list]:
    """Découpe en `nombre` colonnes de hauteur proche, de préférence sur une ligne vide (entre deux
    groupes de résultats, qui disparaît alors) si cela ne coûte pas plus d'une ligne de hauteur."""
    colonnes, debut, n = [], 0, len(paragraphes)
    for k in range(1, nombre):
        restantes = nombre - k  # colonnes après celle-ci

        def hauteur(fin: int, saut: int) -> float:
            return max(fin - debut, (n - fin - saut) / restantes)

        ideal = debut + math.ceil((n - debut) / (restantes + 1))
        candidates = [i for i in range(ideal - CHERCHER_LIGNE_VIDE, ideal + CHERCHER_LIGNE_VIDE + 1)
                      if debut < i < n - 1 and paragraphes[i] in vides]
        meilleure = min(candidates, key=lambda i: hauteur(i, 1), default=None)
        if meilleure is not None and hauteur(meilleure, 1) <= hauteur(ideal, 0) + 1:
            colonnes.append(paragraphes[debut:meilleure])
            debut = meilleure + 1
        else:
            colonnes.append(paragraphes[debut:ideal])
            debut = ideal
    colonnes.append(paragraphes[debut:])
    return colonnes


def _element(balise: str, **attributs) -> object:
    e = OxmlElement(balise)
    for cle, valeur in attributs.items():
        e.set(qn(f"w:{cle}"), str(valeur))
    return e


def _tableau(colonnes: list[list], largeur: int) -> object:
    tbl = OxmlElement("w:tbl")
    tbl_pr = OxmlElement("w:tblPr")
    tbl_pr.append(_element("w:tblW", w=5000, type="pct"))  # pleine largeur, sans style donc sans bordure
    tbl_pr.append(_element("w:tblLayout", type="fixed"))
    marges = OxmlElement("w:tblCellMar")
    marges.append(_element("w:left", w=0, type="dxa"))
    marges.append(_element("w:right", w=113, type="dxa"))
    tbl_pr.append(marges)
    tbl_pr.append(_element("w:tblLook", val="0000", firstRow=0, lastRow=0, firstColumn=0, lastColumn=0,
                           noHBand=1, noVBand=1))
    tbl.append(tbl_pr)
    largeur_colonne = largeur // len(colonnes)
    grille = OxmlElement("w:tblGrid")
    for _ in colonnes:
        grille.append(_element("w:gridCol", w=largeur_colonne))
    tbl.append(grille)
    tr = OxmlElement("w:tr")
    for paragraphes in colonnes:
        tc = OxmlElement("w:tc")
        tc_pr = OxmlElement("w:tcPr")
        tc_pr.append(_element("w:tcW", w=largeur_colonne, type="dxa"))
        tc.append(tc_pr)
        for p in paragraphes or [OxmlElement("w:p")]:  # une cellule contient au moins un paragraphe
            tc.append(p)
        tr.append(tc)
    tbl.append(tr)
    return tbl


def regrouper_resultats(data: bytes, regles: Regles) -> tuple[bytes, list[Changement]]:
    if not regles.options.colonnes_resultats:
        return data, []
    doc = Document(io.BytesIO(data))
    corps = doc.element.body
    motif = regles.colonnes.compiler()
    sections = _sections(corps)

    groupes: list[tuple[list, set, int]] = []
    courant: list = []
    vides: set = set()
    en_attente: list = []  # lignes vides entre deux résultats
    mesures = 0

    def fermer():
        nonlocal courant, vides, en_attente, mesures
        if mesures >= regles.colonnes.minimum:
            groupes.append((courant, vides, mesures))
        courant, vides, en_attente, mesures = [], set(), [], 0

    for enfant in list(corps.iterchildren()):
        ppr = enfant.find(qn("w:pPr")) if enfant.tag == qn("w:p") else None
        candidat = (
            enfant.tag == qn("w:p")
            and not est_protege(enfant)
            and (ppr is None or ppr.find(qn("w:sectPr")) is None)
            and _colonnes_de_section(sections.get(enfant)) == 1  # déjà en colonnes : rien à faire
        )
        if candidat:
            texte = Paragraph(enfant, doc).text
            if motif.search(texte):
                courant += en_attente + [enfant]
                vides.update(en_attente)
                en_attente = []
                mesures += 1
                continue
            if courant and not texte.strip():
                en_attente.append(enfant)
                continue
        fermer()
    fermer()

    if not groupes:
        return data, []
    changements = []
    for paragraphes, lignes_vides, mesures in groupes:
        colonnes = _decouper(paragraphes, lignes_vides, regles.colonnes.nombre)
        position = corps.index(paragraphes[0])
        largeur = _largeur_utile(sections.get(paragraphes[0]))
        gardes = {id(p) for colonne in colonnes for p in colonne}
        for p in paragraphes:
            if id(p) not in gardes:  # ligne vide de coupure entre deux colonnes
                corps.remove(p)
        corps.insert(position, _tableau(colonnes, largeur))  # déplace les paragraphes dans les cellules
        premier = Paragraph(colonnes[0][0], doc).text.strip()
        changements.append(Changement("Résultats sur plusieurs colonnes", f"{premier} … ({mesures} résultats)",
                                      f"{premier} … ({mesures} résultats sur {len(colonnes)} colonnes)"))
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue(), changements
