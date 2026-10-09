"""Représentation intermédiaire d'un compte rendu, indépendante de Word."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

TypeBloc = Literal["titre", "paragraphe", "liste", "tableau"]


@dataclass
class Inconnu:
    """Mot absent des dictionnaires, repéré à la position [debut, fin) du texte."""

    debut: int
    fin: int
    mot: str
    suggestions: list[str] = field(default_factory=list)


@dataclass
class Bloc:
    type: TypeBloc
    texte: str = ""
    original: str = ""
    # Indices de lecture
    gras: bool = False
    liste_word: bool = False
    numerote: bool = False
    # Tableaux : une liste de lignes, chaque ligne une liste de cellules (Bloc paragraphe)
    lignes: list[list[Bloc]] = field(default_factory=list)
    inconnus: list[Inconnu] = field(default_factory=list)

    def textuels(self) -> list[Bloc]:
        """Blocs porteurs de texte (lui-même, ou les cellules d'un tableau)."""
        if self.type == "tableau":
            return [c for ligne in self.lignes for c in ligne]
        return [self]


@dataclass
class Changement:
    regle: str
    avant: str
    apres: str
