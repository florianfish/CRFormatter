"""Génère un compte rendu volontairement mal formaté pour tester DocFormatter."""

import sys
from pathlib import Path

from docx import Document
from docx.shared import Pt

sortie = Path(sys.argv[1] if len(sys.argv) > 1 else "exemple.docx")
sortie.parent.mkdir(parents=True, exist_ok=True)

d = Document()
r = d.add_paragraph().add_run("compte rendu de consultation")
r.bold, r.font.size = True, Pt(16)
d.add_paragraph("Motif:douleur thoracique depuis 3 jours...")
d.add_paragraph("")
d.add_paragraph("ATCD : HTA , diabéte type 2,dyslipidémie")
d.add_paragraph("ttt habituel:")
d.add_paragraph("-kardegic 75mg\t1/j")
d.add_paragraph("- metformine 1000mg x2/j")
d.add_paragraph("EXAMEN CLINIQUE")
p = d.add_paragraph("patient eupnéique,apyrétique.")
p.add_run().add_break()  # retour à la ligne manuel (Maj+Entrée)
p.add_run("TA: 14/9 ; FC: 88bpm. Douleur \"en étau\", pas d'oedeme des MI. dispnée d'effort.")
d.add_paragraph("Biologie")
t = d.add_table(rows=2, cols=2)
for i, (nom, valeur) in enumerate([("Troponine", "12ng/L"), ("Créat", "80µmol/L")]):
    t.cell(i, 0).text, t.cell(i, 1).text = nom, valeur
d.add_paragraph("CAT : coroscanner a programmer, revoir en consultation dans 1 mois")
d.save(sortie)
print(f"Exemple écrit : {sortie}")
