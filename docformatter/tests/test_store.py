import os

import pytest
import yaml

from app.rules import Regles
from app.store import ConflitVersion, RegleInvalide, RulesStore


@pytest.fixture
def store(tmp_path):
    return RulesStore(tmp_path / "regles.yaml", tmp_path / "historique")


def ajouter(mot):
    return lambda r: r.dictionnaire.append(mot)


def test_premier_demarrage(store):
    assert store.get().remplacements  # règles par défaut copiées
    [v] = store.historique()
    assert v.description == "Version initiale des règles"


def test_historique_et_annulation(store):
    initiale = store.historique()[0].id
    precedente = store.modifier(ajouter("apixaban2"), "secretaire", "Mot connu ajouté : « apixaban2 »")
    assert precedente == initiale
    assert "apixaban2" in store.get().dictionnaire
    v = store.historique()[0]
    assert (v.auteur, v.description) == ("secretaire", "Mot connu ajouté : « apixaban2 »")

    store.restaurer(precedente, "secretaire")
    assert "apixaban2" not in store.get().dictionnaire
    assert store.historique()[0].description.startswith("Retour à la version du ")
    assert len(store.historique()) == 3


def test_modification_invalide_sans_effet(store):
    avant = store.get()
    with pytest.raises(RegleInvalide, match="serait remplacé par lui-même"):
        store.modifier(lambda r: r.corrections.__setitem__("hta", "HTA"), "x", "test")
    assert store.get() == avant and len(store.historique()) == 1


def test_conflit_de_version(store):
    version = store.version
    store.modifier(ajouter("a1"), "x", "a1")
    with pytest.raises(ConflitVersion):
        store.modifier(ajouter("a2"), "x", "a2", version_attendue=version)


def test_fichier_invalide_au_demarrage(tmp_path, store):
    store.modifier(ajouter("apixaban2"), "x", "ajout")
    store.path.write_text("options: [cassé", encoding="utf-8")

    repare = RulesStore(store.path, store.historique_dir)
    assert "apixaban2" in repare.get().dictionnaire  # dernière version valide rétablie
    assert "invalide" in repare.alerte
    assert list(tmp_path.glob("regles.invalide-*.yaml"))  # fichier fautif conservé
    assert Regles.model_validate(repare.get().model_dump())


def test_fichier_invalide_sans_historique(tmp_path):
    (tmp_path / "regles.yaml").write_text("remplacements: [{nom: x, motif: '('}]", encoding="utf-8")
    store = RulesStore(tmp_path / "regles.yaml", tmp_path / "historique")
    assert "règles par défaut" in store.alerte and store.get().remplacements


def test_modification_manuelle_prise_en_compte(store):
    data = yaml.safe_load(store.path.read_text(encoding="utf-8"))
    data["dictionnaire"].append("manuel")
    store.path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    os.utime(store.path, ns=(1, 1))  # garantit une signature différente
    assert "manuel" in store.get().dictionnaire
    assert store.historique()[0].description == "Modification manuelle du fichier de règles"


def test_modification_manuelle_invalide_en_cours_de_route(tmp_path, store):
    store.path.write_text("pas: [valide", encoding="utf-8")
    os.utime(store.path, ns=(1, 1))
    assert store.get().remplacements  # l'outil continue de fonctionner
    assert store.alerte and list(tmp_path.glob("regles.invalide-*.yaml"))
    store.modifier(ajouter("ok"), "x", "ok")
    assert store.alerte is None  # une modification réussie efface l'alerte


def test_restaurer_version_inconnue(store):
    with pytest.raises(RegleInvalide):
        store.restaurer("20000101-000000-000000", "x")
    with pytest.raises(RegleInvalide):
        store.restaurer("../../etc/passwd", "x")
