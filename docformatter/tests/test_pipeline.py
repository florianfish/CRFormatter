import io
from pathlib import Path

import pytest
from docx import Document

from app.pipeline import formater, traiter_texte
from app.pipeline.model import Bloc
from app.pipeline.reader import lire_docx
from app.pipeline.spelling import Correcteur
from app.rules import Regles, lire_yaml

NBSP = "\u00a0"
DEFAUTS = Path(__file__).resolve().parents[1] / "defaults" / "regles.yaml"


@pytest.fixture
def regles() -> Regles:
    return lire_yaml(DEFAUTS.read_text(encoding="utf-8"))


def textes(res):
    return [(b.type, b.texte) for b in res.blocs]


def test_regles_par_defaut_valides(regles):
    assert regles.remplacements and regles.sections


def test_exemples_des_regles(regles):
    attendus = {
        "Points de suspension": "Douleur… puis amélioration",
        "Espace après une virgule": "HTA, diabète, créatinine 1,2 mg/dL",
        "Millilitres en mL": f"500{NBSP}mL de sérum physiologique",
        "Espacer les unités": f"Kardégic 75{NBSP}mg, poids 72{NBSP}kg, SpO2 98{NBSP}%",
        "Espaces avant : ; ! ?": f"TA{NBSP}: 13/8{NBSP}; FC{NBSP}: 72 bpm. RDV à 10:30",
    }
    par_nom = {r.nom: r for r in regles.remplacements}
    for nom, attendu in attendus.items():
        assert par_nom[nom].appliquer(par_nom[nom].exemple)[0] == attendu, nom
    # Chaque règle par défaut a une description et un exemple qui la déclenche (page « Mise en forme »)
    for r in regles.remplacements:
        assert r.description and r.appliquer(r.exemple)[1], r.nom


def test_section_avec_contenu_sur_la_meme_ligne(regles):
    res = traiter_texte("ATCD : HTA, diabète\nttt habituel:\n- kardegic 75mg", regles, None)
    assert textes(res) == [
        ("titre", "Antécédents"),
        ("paragraphe", "HTA, diabète"),
        ("titre", "Traitement habituel"),
        ("liste", f"Kardégic 75{NBSP}mg"),
    ]


def test_section_sans_separateur_non_coupee(regles):
    res = traiter_texte("Traitement par IPP débuté hier", regles, None)
    assert textes(res) == [("paragraphe", "Traitement par IPP débuté hier")]


def test_titre_en_majuscules_non_repertorie(regles):
    res = traiter_texte("EVOLUTION DANS LE SERVICE\nPatient stable", regles, None)
    assert textes(res)[0] == ("titre", "Evolution dans le service")


def test_mesure_courte_pas_un_titre(regles):
    res = traiter_texte("TA : 13/8", regles, None)
    assert res.blocs[0].type == "paragraphe"


def test_puces_et_nombres(regles):
    res = traiter_texte("-HTA\n1) diabète\n-3 kg en un mois\n12.5 mg le matin", regles, None)
    assert [(b.type, b.numerote) for b in res.blocs] == [
        ("liste", False), ("liste", True), ("paragraphe", False), ("paragraphe", False),
    ]


def test_corrections_conservent_la_casse(regles):
    res = traiter_texte("Hypertention connue, OEDEME des membres inférieurs, tachychardie", regles, None)
    assert res.blocs[0].texte == "Hypertension connue, ŒDÈME des membres inférieurs, tachycardie"
    assert {(c.avant, c.apres) for c in res.changements if c.regle == "Correction"} >= {
        ("Hypertention", "Hypertension"), ("tachychardie", "tachycardie"),
    }


def test_majuscule_debut_respecte_les_unites(regles):
    res = traiter_texte("pH à 7,32\nmise sous antibiotiques", regles, None)
    assert [b.texte for b in res.blocs] == ["pH à 7,32", "Mise sous antibiotiques"]


def _docx(*paragraphes: str) -> bytes:
    doc = Document()
    for p in paragraphes:
        doc.add_paragraph(p)
    t = doc.add_table(rows=1, cols=2)
    t.cell(0, 0).text = "Hb"
    t.cell(0, 1).text = "12g/dL"
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_aller_retour_docx(regles):
    sortie = formater(_docx("ATCD:HTA", "", "Examen   clinique :", "patient   eupnéique"), regles, None, None).docx
    blocs = lire_docx(sortie)
    assert [b.texte for b in blocs if b.type == "paragraphe"] == ["Antécédents", "HTA", "Examen clinique",
                                                                   "Patient eupnéique"]
    assert blocs[-1].type == "tableau" and blocs[-1].lignes[0][1].texte == f"12{NBSP}g/dL"
    assert Document(io.BytesIO(sortie)).paragraphs[0].style.name == "Heading 1"


@pytest.mark.skipif(not Correcteur([]).disponible, reason="hunspell non installé")
def test_orthographe(regles):
    res = traiter_texte("Patient eupnéique, apyrétique, présentant une dispnée. HTA, HbA1c 7 %.", regles,
                        Correcteur(regles.dictionnaire))
    assert [i.mot for i in res.blocs[0].inconnus] == ["dispnée"]
    assert "dyspnée" in res.blocs[0].inconnus[0].suggestions

    sortie = formater(_docx("Patient présentant une dispnée"), regles, None, Correcteur([])).docx
    doc = Document(io.BytesIO(sortie))
    assert any("dyspnée" in c.text for c in doc.comments)


def test_bloc_sans_inconnus_textuels():
    t = Bloc("tableau", lignes=[[Bloc("paragraphe", texte="a")]])
    assert [b.texte for b in t.textuels()] == ["a"]


def test_mot_inconnu_a_cheval_sur_deux_mises_en_forme():
    from app.pipeline.model import Format, Inconnu
    from app.pipeline.writer import ecrire_docx

    inconnu = Inconnu(4, 11, "dispnée", ["dyspnée"])
    bloc = Bloc("paragraphe", texte="Une dispnée", formats=[Format(0, 7, gras=True)], inconnus=[inconnu])
    assert [(t.texte, t.gras, t.inconnu is not None) for t in bloc.troncons()] == [
        ("Une ", True, False), ("dis", True, True), ("pnée", False, True),
    ]
    doc = Document(io.BytesIO(ecrire_docx([bloc], None, commentaires=True)))
    runs = [r for r in doc.paragraphs[0].runs if r.text]  # sans le run de référence du commentaire
    assert [(r.text, bool(r.bold)) for r in runs] == [("Une ", True), ("dis", True), ("pnée", False)]
    assert len(doc.comments) == 1 and "dyspnée" in next(iter(doc.comments)).text
