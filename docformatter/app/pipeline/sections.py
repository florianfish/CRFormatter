"""Structure : titres de section, listes à puces."""

from __future__ import annotations

import re

from .model import Bloc

# Chaque lettre d'une variante accepte ses formes accentuées (« antecedents » ↔ « Antécédents »).
_ACCENTS = {
    "a": "aàâä", "c": "cç", "e": "eéèêë", "i": "iîï", "o": "oôö", "u": "uùûü", "y": "yÿ",
}

# « - HTA », « -HTA », « • HTA », « 1) HTA », « 2. HTA » (mais pas « -3 kg » ni « 12.5 mg »)
_PUCE = re.compile(r"^\s*(?:[-–—•*·▪●➢►]+(?:\s+|(?=[^\W\d_]))|(\d{1,2})\s*[.)]\s+)(?=\S)")

_SEPARATEUR = r"\s*(?::|-\s|–|—)\s*"


def _motif_variante(variante: str) -> str:
    morceaux = []
    for car in variante.lower():
        if car.isspace():
            morceaux.append(r"\s+")
        elif car in "'’":
            morceaux.append(r"['’]\s*")
        elif car in _ACCENTS:
            morceaux.append(f"[{_ACCENTS[car]}]")
        else:
            morceaux.append(re.escape(car))
    return "".join(morceaux)


class DetecteurSections:
    def __init__(self, sections: dict[str, list[str]]):
        variantes: list[tuple[str, str]] = []
        for titre, alias in sections.items():
            for v in {titre, *alias}:
                variantes.append((v, titre))
        # Les variantes les plus longues d'abord : « atcd chirurgicaux » avant « atcd ».
        variantes.sort(key=lambda x: len(x[0]), reverse=True)
        self._motifs = [
            (re.compile(rf"^\s*{_motif_variante(v)}\s*(?:{_SEPARATEUR}(?P<reste>.*))?$",
                        re.IGNORECASE | re.DOTALL), titre)
            for v, titre in variantes
        ]

    def reconnaitre(self, texte: str) -> tuple[str, str, str] | None:
        """Retourne (titre normalisé, partie titre d'origine, reste du texte) ou None.

        « ATCD : HTA, diabète » → ("Antécédents", "ATCD :", "HTA, diabète").
        Le reste n'est séparé que s'il y a un séparateur explicite (« : », « - »),
        pour ne pas couper « Traitement par IPP débuté ».
        """
        for motif, titre in self._motifs:
            m = motif.match(texte)
            if m:
                reste = (m.group("reste") or "").strip()
                prefixe = texte[: m.start("reste")].strip() if m.group("reste") is not None else texte.strip()
                return titre, prefixe, reste
        return None


def _ressemble_a_un_titre(bloc: Bloc) -> bool:
    texte = bloc.texte.strip()
    mots = texte.split()
    if not mots or len(mots) > 6 or len(texte) > 60 or texte.endswith((".", ",", ";")):
        return False
    lettres = [c for c in texte if c.isalpha()]
    if len(lettres) < 3:
        return False
    tout_majuscules = all(c.isupper() for c in lettres)
    return tout_majuscules or texte.endswith(":") or bloc.gras


def _titre_propre(texte: str) -> str:
    texte = texte.strip().rstrip(":").strip()
    if texte.isupper():
        texte = texte.lower()
    return texte[:1].upper() + texte[1:]


def structurer(blocs: list[Bloc], sections: dict[str, list[str]], detecter_titres: bool) -> list[Bloc]:
    detecteur = DetecteurSections(sections)
    resultat: list[Bloc] = []
    for bloc in blocs:
        if bloc.type != "paragraphe":
            resultat.append(bloc)
            continue

        trouve = detecteur.reconnaitre(bloc.texte)
        if trouve:
            titre, prefixe, reste = trouve
            resultat.append(Bloc("titre", texte=titre, original=prefixe))
            if reste:
                resultat.append(_paragraphe_ou_liste(Bloc("paragraphe", texte=reste, original=reste)))
            continue

        puce = _PUCE.match(bloc.texte)
        if not puce and detecter_titres and not bloc.liste_word and _ressemble_a_un_titre(bloc):
            resultat.append(Bloc("titre", texte=_titre_propre(bloc.texte), original=bloc.original))
            continue

        resultat.append(_paragraphe_ou_liste(bloc))
    return resultat


def _paragraphe_ou_liste(bloc: Bloc) -> Bloc:
    puce = _PUCE.match(bloc.texte)
    if puce:
        bloc.type = "liste"
        bloc.numerote = puce.group(1) is not None
        bloc.texte = bloc.texte[puce.end():]
        bloc.original = _PUCE.sub("", bloc.original, count=1)
    elif bloc.liste_word:
        bloc.type = "liste"
    return bloc
