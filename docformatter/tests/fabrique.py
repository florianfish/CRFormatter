"""Compte rendu fictif reproduisant la structure d'un courrier hospitalier réel :
en-tête de première page différent, en-tête des pages suivantes avec un champ PAGE, pied de
page, section à deux colonnes, lien hypertexte, signet, tabulation, rubriques en gras souligné.
Aucune donnée réelle : les documents réels ne doivent jamais entrer dans le dépôt (public)."""

from __future__ import annotations

import io

from docx import Document
from docx.enum.section import WD_SECTION
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Cm

W = nsdecls("w", "r")


def _rubrique(doc, libelle: str, suite: str = ""):
    p = doc.add_paragraph()
    r = p.add_run(libelle)
    r.bold = r.underline = True
    if suite:
        p.add_run(suite)
    return p


def _colonnes(section, nombre: int):
    cols = section._sectPr.find(qn("w:cols"))
    if cols is None:
        cols = OxmlElement("w:cols")
        section._sectPr.append(cols)
    cols.set(qn("w:num"), str(nombre))


def _lien(paragraphe, texte: str, url: str):
    r_id = paragraphe.part.relate_to(url, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
                                     is_external=True)
    paragraphe._p.append(parse_xml(
        f'<w:hyperlink {W} r:id="{r_id}"><w:r><w:rPr><w:u w:val="single"/></w:rPr>'
        f"<w:t>{texte}</w:t></w:r></w:hyperlink>"
    ))


def compte_rendu() -> bytes:
    doc = Document()
    section = doc.sections[0]
    section.left_margin = section.right_margin = Cm(1)
    section.different_first_page_header_footer = True
    section.first_page_header.paragraphs[0].text = "EN-TÊTE PREMIÈRE PAGE — Service de médecine interne"
    entete = section.header.paragraphs[0]
    entete.text = "DUPONT Jean, page "
    entete._p.append(parse_xml(f'<w:fldSimple {W} w:instr=" PAGE "><w:r><w:t>1</w:t></w:r></w:fldSimple>'))
    section.footer.paragraphs[0].text = "PIED DE PAGE — Hôpital fictif"
    section.first_page_footer.paragraphs[0].text = "PIED DE PAGE — Hôpital fictif"

    doc.add_paragraph("")
    doc.add_paragraph("Ville, le lundi 5 octobre 2026")
    titre = doc.add_paragraph()
    titre.alignment = 1
    r = titre.add_run("COMPTE-RENDU DE CONSULTATION")
    r.bold = r.underline = True
    doc.add_paragraph("")
    doc.add_paragraph("Chère Consœur, Cher Confrère,")
    doc.element.body.append(parse_xml(f'<w:bookmarkEnd {W} w:id="0"/>'))
    _rubrique(doc, "Motif de consultation", " :")
    doc.add_paragraph("douleur thoracique depuis 3 jours...")
    _rubrique(doc, "ATCD", " : HTA , diabéte type 2")
    doc.add_paragraph("-suivi pulmonaire Dr Martin")
    doc.add_paragraph("Poids : 72kg")
    _rubrique(doc, "Biologiquement", " :")

    # Section continue à deux colonnes pour la biologie
    _colonnes(doc.add_section(WD_SECTION.CONTINUOUS), 2)
    for ligne in ("Hb (g/dL) : 13,4", "Plaquettes (Giga/L) : 294", "CRP (mg/L) : <1.0", "Na (mmol/L) : 144"):
        doc.add_paragraph(ligne)
    _colonnes(doc.add_section(WD_SECTION.CONTINUOUS), 1)

    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = "Créatinine", "96µmol/L"
    table.cell(1, 0).text, table.cell(1, 1).text = "Ferritine", "72 µg/l"

    doc.add_paragraph("\t                    Docteur Martin")
    contacts = doc.add_paragraph("Via la plateforme de télé-expertise : ")
    _lien(contacts, "www.exemple-fictif.fr", "https://www.exemple-fictif.fr")

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
