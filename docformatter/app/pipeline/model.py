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
class Format:
    """Mise en forme appliquée à la plage [debut, fin) du texte."""

    debut: int
    fin: int
    gras: bool = False
    italique: bool = False
    souligne: bool = False

    def attributs(self) -> tuple[bool, bool, bool]:
        return self.gras, self.italique, self.souligne


@dataclass
class Troncon:
    """Morceau de texte homogène : même mise en forme et même mot inconnu (ou aucun)."""

    texte: str
    gras: bool = False
    italique: bool = False
    souligne: bool = False
    inconnu: Inconnu | None = None


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
    # Gras / italique / souligné (saisis dans l'éditeur de retouche), plages sans chevauchement
    formats: list[Format] = field(default_factory=list)

    def troncons(self) -> list[Troncon]:
        """Découpe le texte selon la mise en forme et les mots inconnus (écriture Word, aperçu)."""
        bornes = {0, len(self.texte)}
        for x in [*self.formats, *self.inconnus]:
            bornes.update((max(0, min(x.debut, len(self.texte))), max(0, min(x.fin, len(self.texte)))))
        bornes_triees = sorted(bornes)
        resultat = []
        for debut, fin in zip(bornes_triees, bornes_triees[1:]):
            if debut == fin:
                continue
            f = next((f for f in self.formats if f.debut <= debut and fin <= f.fin), None)
            i = next((i for i in self.inconnus if i.debut <= debut and fin <= i.fin), None)
            g, it, so = f.attributs() if f else (False, False, False)
            resultat.append(Troncon(self.texte[debut:fin], g, it, so, i))
        return resultat

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
