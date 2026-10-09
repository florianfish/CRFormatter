"""Extrait de la Base de données publique des médicaments (ANSM) la liste des noms de médicaments
livrée avec l'add-on : noms commerciaux (« Doliprane ») et substances actives (« paracétamol »).

Usage : medicaments.py SORTIE.txt [DOSSIER_BDPM]
Sans DOSSIER_BDPM (contenant CIS_bdpm.txt et CIS_COMPO_bdpm.txt), les fichiers sont téléchargés.
Conditions de réutilisation de la base : citer la source et la date de mise à jour (en-tête du fichier).
"""

import datetime
import re
import sys
import unicodedata
import urllib.request
from pathlib import Path

SITE = "https://base-donnees-publique.medicaments.gouv.fr"
FICHIERS = ("CIS_bdpm.txt", "CIS_COMPO_bdpm.txt")
HOMEOPATHIE = re.compile(r"degré de dilution|homéopathi", re.IGNORECASE)
MOT = re.compile(r"^[^\W\d_]+(?:-[^\W\d_]+)*$")  # lettres, éventuellement reliées par des tirets


def lire(url_ou_chemin: str, encodage: str = "latin-1") -> str:  # fichiers de la base en ISO-8859-1
    if url_ou_chemin.startswith("https://"):
        requete = urllib.request.Request(url_ou_chemin, headers={"User-Agent": "Mozilla/5.0 DocFormatter"})
        with urllib.request.urlopen(requete, timeout=120) as reponse:
            donnees = reponse.read()
    else:
        donnees = Path(url_ou_chemin).read_bytes()
    return donnees.decode(encodage)


def date_de_mise_a_jour() -> str:
    try:
        page = lire(f"{SITE}/telechargement", "utf-8")
    except OSError:
        return "inconnue"
    trouve = re.search(r"mise à jour le (\d{2}/\d{2}/\d{4})", page)
    return trouve.group(1) if trouve else "inconnue"


def sans_accents(texte: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texte.lower()) if unicodedata.category(c) != "Mn")


def majuscule(nom: str) -> str:
    return "-".join(partie.capitalize() for partie in nom.split("-"))


def substances(compositions: str) -> set[str]:
    resultat = set()
    for ligne in compositions.splitlines():
        colonnes = ligne.split("\t")
        if len(colonnes) < 4 or HOMEOPATHIE.search(colonnes[3]):
            continue
        nom = re.sub(r"\([^)]*\)", " ", colonnes[3])  # « TAMOXIFÈNE (CITRATE DE) » → « TAMOXIFÈNE »
        nom = " ".join(nom.split()).lower().strip(" ,.'")
        mots = nom.split()
        if mots and len(mots) <= 4 and all(MOT.match(m.strip("'")) for m in mots if m not in ("d'", "l'")):
            resultat.add(nom)
    return resultat


def specialites(bdpm: str, connues: set[str]) -> set[str]:
    """Nom commercial : premier mot de la dénomination (« DOLIPRANE 1000 mg, comprimé »).
    Un générique (« METFORMINE BIOGARAN ») commence par sa substance, déjà dans la liste."""
    mots_substances = {sans_accents(m) for s in connues for m in s.split()}
    resultat = set()
    for ligne in bdpm.splitlines():
        colonnes = ligne.split("\t")
        if len(colonnes) < 5 or colonnes[4] != "Autorisation active" or HOMEOPATHIE.search(colonnes[1]):
            continue
        premier = colonnes[1].split(",")[0].split()[0].strip(".")
        if len(premier) >= 3 and MOT.match(premier) and sans_accents(premier) not in mots_substances:
            resultat.add(majuscule(premier.lower()))
    return resultat


def main() -> None:
    sortie = Path(sys.argv[1])
    source = sys.argv[2] if len(sys.argv) > 2 else None
    textes = [lire(f"{source}/{f}" if source else f"{SITE}/download/file/{f}") for f in FICHIERS]
    dci = substances(textes[1])
    noms = sorted(specialites(textes[0], dci) | dci, key=lambda n: (n.lower(), n))
    sortie.parent.mkdir(parents=True, exist_ok=True)
    sortie.write_text(
        "# Noms de médicaments : spécialités (noms commerciaux) et substances actives.\n"
        f"# Source : Base de données publique des médicaments (ANSM), {SITE}\n"
        f"# Mise à jour de la base : {date_de_mise_a_jour()} ; extraction : {datetime.date.today():%d/%m/%Y}\n"
        "# Fichier produit par scripts/medicaments.py (make medicaments) : ne pas modifier à la main.\n"
        + "\n".join(noms) + "\n",
        encoding="utf-8",
    )
    print(f"{len(noms)} noms écrits dans {sortie}")


if __name__ == "__main__":
    main()
