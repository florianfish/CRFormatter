"""Version de l'add-on (config.yaml) et nouveautés (CHANGELOG.md), affichées dans l'interface.

Les deux fichiers sont copiés dans l'image (Dockerfile). Le CHANGELOG n'utilise qu'un petit
sous-ensemble de Markdown (titres « ## », listes « - », **gras**, `code`) : converti ici, après
échappement du texte, sans dépendance supplémentaire.
"""

from __future__ import annotations

import re
from functools import lru_cache
from html import escape
from pathlib import Path

import yaml
from markupsafe import Markup

from .settings import APP_DIR

RACINE = APP_DIR.parent


@lru_cache(maxsize=1)
def version(racine: Path = RACINE) -> str:
    try:
        return str(yaml.safe_load((racine / "config.yaml").read_text(encoding="utf-8"))["version"])
    except (OSError, KeyError, TypeError, yaml.YAMLError):
        return ""


def _en_ligne(texte: str) -> str:
    texte = escape(texte, quote=False)
    texte = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", texte)
    return re.sub(r"`(.+?)`", r"<code>\1</code>", texte)


def markdown_simple(texte: str) -> str:
    html: list[str] = []
    element: list[str] | None = None  # élément de liste ou paragraphe en cours
    liste = False

    def fermer_element():
        nonlocal element
        if element is not None:
            balise = "li" if liste else "p"
            html.append(f"<{balise}>{_en_ligne(' '.join(element))}</{balise}>")
            element = None

    def fermer_liste():
        nonlocal liste
        fermer_element()
        if liste:
            html.append("</ul>")
            liste = False

    for ligne in texte.splitlines():
        brute = ligne.strip()
        if not brute:
            fermer_liste()
        elif titre := re.match(r"(#{1,6})\s+(.*)", brute):
            fermer_liste()
            niveau = min(6, len(titre.group(1)) + 1)  # « ## 0.8.0 » → <h3> (le titre de la fenêtre est un <h2>)
            html.append(f"<h{niveau}>{_en_ligne(titre.group(2))}</h{niveau}>")
        elif brute.startswith(("- ", "* ")):
            fermer_element()
            if not liste:
                html.append("<ul>")
                liste = True
            element = [brute[2:]]
        elif element is not None:
            element.append(brute)  # suite de l'élément sur la ligne suivante
        else:
            element = [brute]
    fermer_liste()
    return "\n".join(html)


@lru_cache(maxsize=1)
def nouveautes(racine: Path = RACINE) -> Markup:
    try:
        texte = (racine / "CHANGELOG.md").read_text(encoding="utf-8")
    except OSError:
        return Markup("")
    return Markup(markdown_simple(texte))  # noqa: S704 — texte échappé par _en_ligne
