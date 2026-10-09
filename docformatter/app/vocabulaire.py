"""Opérations « non techniques » sur les règles, utilisées par l'interface de la secrétaire.

Chaque opération valide sa saisie avec des messages compréhensibles, puis retourne la
modification à appliquer et la phrase qui apparaîtra dans l'historique.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import NamedTuple

from .rules import LIBELLES_OPTIONS, Regles
from .store import RegleInvalide

LONGUEUR_MAX = 100


class Operation(NamedTuple):
    modification: Callable[[Regles], None]
    description: str


def _texte(valeur: str, quoi: str) -> str:
    valeur = " ".join((valeur or "").split())
    if not valeur:
        raise RegleInvalide(f"Indiquez {quoi}.")
    if len(valeur) > LONGUEUR_MAX:
        raise RegleInvalide(f"Texte trop long ({LONGUEUR_MAX} caractères maximum).")
    return valeur


def vue(regles: Regles) -> dict:
    return {
        "remplacements": [{"texte": t, "par": p} for t, p in regles.corrections.items()],
        "mots": regles.dictionnaire,
        "rubriques": [{"titre": t, "variantes": v} for t, v in regles.sections.items()],
    }


# ---- Mots connus ----------------------------------------------------------------------

def ajouter_mot(mot: str) -> Operation:
    mot = _texte(mot, "le mot")
    if " " in mot:
        raise RegleInvalide("Un seul mot à la fois, sans espace.")

    def modification(r: Regles) -> None:
        if mot.lower() in {m.lower() for m in r.dictionnaire}:
            raise RegleInvalide(f"« {mot} » fait déjà partie des mots connus.")
        r.dictionnaire.append(mot)

    return Operation(modification, f"Mot connu ajouté : « {mot} »")


def retirer_mot(mot: str) -> Operation:
    mot = _texte(mot, "le mot")
    return Operation(
        lambda r: setattr(r, "dictionnaire", [m for m in r.dictionnaire if m.lower() != mot.lower()]),
        f"Mot connu retiré : « {mot} »",
    )


# ---- Remplacements automatiques -------------------------------------------------------

def ajouter_remplacement(texte: str, par: str) -> Operation:
    texte, par = _texte(texte, "le texte à remplacer"), _texte(par, "le texte de remplacement")
    if texte.lower() == par.lower():
        raise RegleInvalide("Le remplacement est identique au texte d'origine.")
    return Operation(
        lambda r: r.corrections.__setitem__(texte.lower(), par),
        f"Remplacement ajouté : « {texte} » → « {par} »",
    )


def retirer_remplacement(texte: str) -> Operation:
    texte = _texte(texte, "le texte à remplacer")
    return Operation(lambda r: r.corrections.pop(texte.lower(), None), f"Remplacement retiré : « {texte} »")


# ---- Rubriques ------------------------------------------------------------------------

def _rubrique(r: Regles, titre: str) -> list[str]:
    if titre not in r.sections:
        raise RegleInvalide(f"La rubrique « {titre} » n'existe plus.")
    return r.sections[titre]


def ajouter_rubrique(titre: str) -> Operation:
    titre = _texte(titre, "le titre de la rubrique")

    def modification(r: Regles) -> None:
        if titre.lower() in {t.lower() for t in r.sections}:
            raise RegleInvalide(f"La rubrique « {titre} » existe déjà.")
        r.sections[titre] = []

    return Operation(modification, f"Rubrique ajoutée : « {titre} »")


def retirer_rubrique(titre: str) -> Operation:
    titre = _texte(titre, "le titre de la rubrique")
    return Operation(lambda r: r.sections.pop(titre, None), f"Rubrique retirée : « {titre} »")


def ajouter_variante(titre: str, variante: str) -> Operation:
    variante = _texte(variante, "l'écriture à reconnaître")

    def modification(r: Regles) -> None:
        variantes = _rubrique(r, titre)
        if variante.lower() in {v.lower() for v in variantes}:
            raise RegleInvalide(f"« {variante} » est déjà reconnu pour « {titre} ».")
        variantes.append(variante)

    return Operation(modification, f"« {variante} » reconnu comme la rubrique « {titre} »")


def retirer_variante(titre: str, variante: str) -> Operation:
    def modification(r: Regles) -> None:
        variantes = _rubrique(r, titre)
        r.sections[titre] = [v for v in variantes if v != variante]

    return Operation(modification, f"« {variante} » n'est plus reconnu comme « {titre} »")


# ---- Mise en forme --------------------------------------------------------------------

def basculer_regle(index: int, nom: str, actif: bool) -> Operation:
    def modification(r: Regles) -> None:
        if not 0 <= index < len(r.remplacements) or r.remplacements[index].nom != nom:
            raise RegleInvalide("Les règles ont changé entre-temps : rechargez la page.")
        r.remplacements[index].actif = actif

    return Operation(modification, f"« {nom} » {'activé' if actif else 'désactivé'}")


def basculer_option(cle: str, actif: bool) -> Operation:
    if cle not in LIBELLES_OPTIONS:
        raise RegleInvalide("Option inconnue.")
    libelle = LIBELLES_OPTIONS[cle][0]
    return Operation(
        lambda r: setattr(r.options, cle, actif), f"« {libelle} » {'activé' if actif else 'désactivé'}"
    )


# ---- Décisions prises depuis un document ----------------------------------------------

def decisions(choix: list[tuple[str, str, str]]) -> Operation | None:
    """`choix` : liste de (mot, "correct" | "remplacer", remplacement)."""
    corrects: list[str] = []
    remplacements: list[tuple[str, str]] = []
    for mot, action, par in choix:
        if action == "correct":
            corrects.append(_texte(mot, "le mot"))
        elif action == "remplacer":
            op_texte, op_par = _texte(mot, "le mot"), _texte(par, f"le remplacement de « {mot} »")
            if op_texte.lower() == op_par.lower():
                raise RegleInvalide(f"Le remplacement de « {mot} » est identique au mot.")
            remplacements.append((op_texte, op_par))
    if not corrects and not remplacements:
        return None

    def modification(r: Regles) -> None:
        connus = {m.lower() for m in r.dictionnaire}
        r.dictionnaire.extend(m for m in corrects if m.lower() not in connus)
        for texte, par in remplacements:
            r.corrections[texte.lower()] = par

    morceaux = []
    if corrects:
        morceaux.append("mots connus ajoutés : " + ", ".join(f"« {m} »" for m in corrects))
    if remplacements:
        morceaux.append("remplacements ajoutés : " + ", ".join(f"« {t} » → « {p} »" for t, p in remplacements))
    return Operation(modification, "Depuis un document — " + " ; ".join(morceaux))
