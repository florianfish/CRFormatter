"""Règles de mise en forme : modèle, validation, lecture et écriture YAML."""

from __future__ import annotations

import re

import yaml
from pydantic import BaseModel, Field, field_validator


# Raccourcis utilisables dans le champ « remplacement » des règles regex.
PLACEHOLDERS = {"{nbsp}": "\u00a0", "{nnbsp}": "\u202f"}


def expanser_remplacement(remplacement: str) -> str:
    for cle, valeur in PLACEHOLDERS.items():
        remplacement = remplacement.replace(cle, valeur)
    return remplacement


class Remplacement(BaseModel):
    nom: str = Field(min_length=1)
    description: str = ""  # en langage courant, affichée sur la page « Mise en forme »
    motif: str = Field(min_length=1)
    remplacement: str = ""
    ignorer_casse: bool = False
    actif: bool = True
    exemple: str = ""

    @field_validator("motif")
    @classmethod
    def motif_valide(cls, v: str) -> str:
        try:
            re.compile(v)
        except re.error as e:
            raise ValueError(f"expression régulière invalide : {e}") from e
        return v

    def compiler(self) -> re.Pattern[str]:
        return re.compile(self.motif, re.IGNORECASE if self.ignorer_casse else 0)

    def appliquer(self, texte: str) -> tuple[str, int]:
        try:
            return self.compiler().subn(expanser_remplacement(self.remplacement), texte)
        except (re.error, IndexError) as e:
            # Référence de groupe invalide (\3 alors que le motif n'a que 2 groupes…)
            raise ValueError(f"règle « {self.nom} » : remplacement invalide ({e})") from e


# Libellé et explication des options, affichés sur la page « Mise en forme ».
LIBELLES_OPTIONS = {
    "majuscule_debut": ("Majuscule en début de paragraphe", "patient stable", "Patient stable"),
    "point_final": ("Point à la fin des paragraphes", "Patient stable ce jour", "Patient stable ce jour."),
    "verifier_orthographe": ("Signaler les mots inconnus", "dispnée", "dispnée (surligné en jaune)"),
    "commentaires_orthographe": ("Proposer des corrections en commentaire dans Word", "dispnée",
                                 "commentaire « Suggestions : dyspnée »"),
}


class Options(BaseModel):
    majuscule_debut: bool = True
    point_final: bool = False
    verifier_orthographe: bool = True
    commentaires_orthographe: bool = True


class Regles(BaseModel):
    options: Options = Options()
    remplacements: list[Remplacement] = []
    corrections: dict[str, str] = {}
    dictionnaire: list[str] = []
    sections: dict[str, list[str]] = {}

    @field_validator("corrections")
    @classmethod
    def corrections_valides(cls, v: dict[str, str]) -> dict[str, str]:
        propre: dict[str, str] = {}
        for faute, correction in v.items():
            faute, correction = faute.strip(), correction.strip()
            if not faute or not correction:
                raise ValueError("un remplacement doit avoir un texte et sa correction")
            if faute.lower() == correction.lower():
                raise ValueError(f"« {faute} » serait remplacé par lui-même")
            propre[faute.lower()] = correction
        return dict(sorted(propre.items()))

    @field_validator("dictionnaire")
    @classmethod
    def dictionnaire_propre(cls, v: list[str]) -> list[str]:
        return sorted({m.strip() for m in v if m.strip()}, key=str.lower)

    @field_validator("sections")
    @classmethod
    def sections_valides(cls, v: dict[str, list[str]]) -> dict[str, list[str]]:
        propre: dict[str, list[str]] = {}
        for titre, variantes in v.items():
            titre = titre.strip()
            if not titre:
                raise ValueError("une rubrique doit avoir un titre")
            propre[titre] = [x.strip() for x in variantes if x.strip()]
        return propre


def lire_yaml(texte: str) -> Regles:
    data = yaml.safe_load(texte) or {}
    if not isinstance(data, dict):
        raise ValueError("le fichier de règles doit contenir un dictionnaire YAML")
    return Regles.model_validate(data)


def ecrire_yaml(regles: Regles) -> str:
    return yaml.safe_dump(
        regles.model_dump(), allow_unicode=True, sort_keys=False, width=120
    )
