"""Représentation intermédiaire d'un compte rendu.

Le document Word d'origine n'est jamais reconstruit : chaque `Bloc` garde l'identifiant
(`source`) du paragraphe ou du tableau dont il provient, et l'écriture ne remplace que le
texte des paragraphes modifiés. En-têtes, pieds de page, sections, styles, champs et liens
restent ceux du document d'origine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

TypeBloc = Literal["paragraphe", "tableau", "cellule"]


@dataclass
class Inconnu:
    """Mot absent des dictionnaires, repéré à la position [debut, fin) du texte."""

    debut: int
    fin: int
    mot: str
    suggestions: list[str] = field(default_factory=list)


@dataclass
class Format:
    """Mise en forme de la plage [debut, fin) du texte.

    `rpr` est une copie des propriétés Word du morceau d'origine (police, taille, couleur…) ;
    gras / italique / souligné sont les mises en forme directes, modifiables dans l'éditeur.
    """

    debut: int
    fin: int
    gras: bool = False
    italique: bool = False
    souligne: bool = False
    rpr: Any = None

    def attributs(self) -> tuple[bool, bool, bool]:
        return self.gras, self.italique, self.souligne

    def cle(self) -> tuple:
        """Identité de mise en forme (hors position), pour comparer et fusionner."""
        from lxml import etree

        return (*self.attributs(), etree.tostring(self.rpr) if self.rpr is not None else None)


@dataclass
class Troncon:
    """Morceau de texte homogène : même mise en forme et même mot inconnu (ou aucun)."""

    texte: str
    gras: bool = False
    italique: bool = False
    souligne: bool = False
    rpr: Any = None
    inconnu: Inconnu | None = None


@dataclass
class Bloc:
    type: TypeBloc
    texte: str = ""
    original: str = ""
    # Identifiant de l'élément Word d'origine (« p12 », « t3 », « t3.0.1.0 ») ; None si créé
    source: str | None = None
    # Paragraphe créé dans l'éditeur : identifiant du paragraphe dont il reprend la mise en page
    origine: str | None = None
    # Contenu que l'outil ne sait pas réécrire sans risque (lien, champ, image…) : laissé intact
    protege: bool = False
    # Porte une fin de section Word (changement de colonnes, de marges…) : ni supprimé ni fusionné
    fin_section: bool = False
    # Propriétés Word du texte (police, taille…) appliquées au texte saisi sans mise en forme d'origine
    rpr_base: Any = None
    # Mise en page lue (alignement, retraits, espacements en points, interligne, police, taille) :
    # affichée dans l'éditeur et reprise par « Copier pour Word »
    mise_en_page: dict[str, Any] = field(default_factory=dict)
    # Tableau : lignes de cellules ; cellule : ses paragraphes
    lignes: list[list[Bloc]] = field(default_factory=list)
    paragraphes: list[Bloc] = field(default_factory=list)
    inconnus: list[Inconnu] = field(default_factory=list)
    formats: list[Format] = field(default_factory=list)
    # Empreinte du contenu lu dans le document : un paragraphe inchangé n'est pas réécrit
    empreinte_origine: tuple | None = None

    def empreinte(self) -> tuple:
        return self.texte, tuple((f.debut, f.fin, *f.cle()) for f in fusionner(self.formats))

    def modifie(self) -> bool:
        return self.empreinte_origine is None or self.empreinte() != self.empreinte_origine

    def troncons(self) -> list[Troncon]:
        """Découpe le texte selon la mise en forme et les mots inconnus (écriture Word, aperçu)."""
        n = len(self.texte)
        bornes = {0, n}
        for x in [*self.formats, *self.inconnus]:
            bornes.update((max(0, min(x.debut, n)), max(0, min(x.fin, n))))
        bornes_triees = sorted(bornes)
        resultat = []
        for debut, fin in zip(bornes_triees, bornes_triees[1:]):
            if debut == fin:
                continue
            f = next((f for f in self.formats if f.debut <= debut and fin <= f.fin), None)
            i = next((i for i in self.inconnus if i.debut <= debut and fin <= i.fin), None)
            g, it, so = f.attributs() if f else (False, False, False)
            resultat.append(Troncon(self.texte[debut:fin], g, it, so, f.rpr if f else None, i))
        return resultat

    def textuels(self) -> list[Bloc]:
        """Paragraphes porteurs de texte : lui-même, ou ceux des cellules d'un tableau."""
        if self.type == "tableau":
            return [p for ligne in self.lignes for cellule in ligne for p in cellule.paragraphes]
        if self.type == "cellule":
            return self.paragraphes
        return [self]


def fusionner(formats: list[Format]) -> list[Format]:
    """Trie et fusionne les plages contiguës de même mise en forme."""
    resultat: list[Format] = []
    for f in sorted(formats, key=lambda x: x.debut):
        if f.debut >= f.fin:
            continue
        if resultat and resultat[-1].fin == f.debut and resultat[-1].cle() == f.cle():
            resultat[-1] = Format(resultat[-1].debut, f.fin, *f.attributs(), f.rpr)
        else:
            resultat.append(Format(f.debut, f.fin, *f.attributs(), f.rpr))
    return resultat


class TexteStyle:
    """Texte d'un paragraphe avec la mise en forme de chaque caractère : permet de remplacer
    une portion de texte sans perdre la mise en forme du reste.

    Le texte inséré prend la mise en forme du premier caractère remplacé (ou, pour une simple
    insertion, du caractère qui précède).
    """

    def __init__(self, bloc: Bloc):
        self.texte = bloc.texte
        self.styles: list[Format | None] = [None] * len(bloc.texte)
        for f in bloc.formats:
            for i in range(max(0, f.debut), min(f.fin, len(self.texte))):
                self.styles[i] = f

    def remplacer(self, debut: int, fin: int, nouveau: str) -> None:
        if debut < fin:
            style = self.styles[debut]
        else:
            style = self.styles[debut - 1] if debut > 0 else (self.styles[0] if self.styles else None)
        self.texte = self.texte[:debut] + nouveau + self.texte[fin:]
        self.styles[debut:fin] = [style] * len(nouveau)

    def appliquer(self, bloc: Bloc) -> None:
        formats = []
        for i, style in enumerate(self.styles):
            if style is not None:
                formats.append(Format(i, i + 1, *style.attributs(), style.rpr))
        bloc.texte = self.texte
        bloc.formats = fusionner(formats)


@dataclass
class Changement:
    regle: str
    avant: str
    apres: str
