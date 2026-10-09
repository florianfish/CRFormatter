"""Génère un compte rendu fictif volontairement mal rédigé, présenté comme un courrier
hospitalier (en-tête de première page, en-tête des pages suivantes, pied de page)."""

import sys
from pathlib import Path

from docx import Document
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls
from docx.shared import Cm, Pt

sortie = Path(sys.argv[1] if len(sys.argv) > 1 else "exemple.docx")
sortie.parent.mkdir(parents=True, exist_ok=True)

d = Document()
section = d.sections[0]
section.left_margin = section.right_margin = Cm(1.5)
section.different_first_page_header_footer = True
section.first_page_header.paragraphs[0].text = "HÔPITAL FICTIF — Service de médecine interne — Dr Martin"
section.header.paragraphs[0].text = "DUPONT Jean, né le 01/01/1950, page "
section.header.paragraphs[0]._p.append(parse_xml(
    f'<w:fldSimple {nsdecls("w")} w:instr=" PAGE "><w:r><w:t>1</w:t></w:r></w:fldSimple>'))
for pied in (section.footer, section.first_page_footer):
    pied.paragraphs[0].text = "Hôpital fictif – 1 rue de l'Exemple – 00000 VILLE"


def rubrique(libelle, suite=""):
    p = d.add_paragraph()
    r = p.add_run(libelle)
    r.bold = r.underline = True
    if suite:
        p.add_run(suite)


titre = d.add_paragraph()
titre.alignment = 1
r = titre.add_run("COMPTE-RENDU DE CONSULTATION")
r.bold, r.font.size = True, Pt(13)
d.add_paragraph("")
rubrique("Motif", ":douleur thoracique depuis 3 jours...")
rubrique("ATCD", " : HTA , diabéte type 2,dyslipidémie")
rubrique("ttt habituel", ":")
d.add_paragraph("-kardegic 75mg\t1/j")
d.add_paragraph("- metformine 1000mg x2/j")
rubrique("Examen clinique", " :")
p = d.add_paragraph("patient eupnéique,apyrétique.")
p.add_run().add_break()  # retour à la ligne manuel (Maj+Entrée)
p.add_run("TA: 14/9 ; FC: 88bpm. Douleur \"en étau\", pas d'oedeme des MI. dispnée d'effort.")
rubrique("Biologie", " :")
t = d.add_table(rows=2, cols=2)
for i, (nom, valeur) in enumerate([("Troponine", "12ng/L"), ("Créat", "80µmol/L")]):
    t.cell(i, 0).text, t.cell(i, 1).text = nom, valeur
rubrique("CAT", " : coroscanner a programmer, revoir en consultation dans 1 mois")
d.add_paragraph("")
d.add_paragraph("\t\t\t\t\t\tDocteur Martin")
d.save(sortie)
print(f"Exemple écrit : {sortie}")
