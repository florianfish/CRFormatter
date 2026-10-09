"""Rendu HTML de l'aperçu : texte final, différences avec l'original, mots inconnus."""

from __future__ import annotations

import difflib
import re
from html import escape

from markupsafe import Markup

from .pipeline.model import Bloc

_JETONS = re.compile(r"\s+|[^\W_]+|[^\w\s]|_", re.UNICODE)


def _visible(t: str) -> str:
    """Rend visibles les espaces insécables ajoutées."""
    return escape(t).replace("\u00a0", '<span class="nbsp">\u00a0</span>').replace(
        "\u202f", '<span class="nbsp">\u202f</span>'
    )


def diff_html(avant: str, apres: str) -> str:
    a, b = _JETONS.findall(avant), _JETONS.findall(apres)
    morceaux = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            morceaux.append(_visible("".join(a[i1:i2])))
            continue
        if i2 > i1:
            morceaux.append(f"<del>{_visible(''.join(a[i1:i2]))}</del>")
        if j2 > j1:
            morceaux.append(f"<ins>{_visible(''.join(b[j1:j2]))}</ins>")
    return "".join(morceaux)


def _texte_html(bloc: Bloc, avec_diff: bool) -> str:
    if not bloc.inconnus:
        return diff_html(bloc.original, bloc.texte) if avec_diff else _visible(bloc.texte)
    # Avec mots inconnus : on montre le texte final annoté (le diff est déjà visible ailleurs).
    morceaux, pos = [], 0
    for inc in sorted(bloc.inconnus, key=lambda x: x.debut):
        morceaux.append(_visible(bloc.texte[pos : inc.debut]))
        sugg = ", ".join(inc.suggestions) or "aucune suggestion"
        morceaux.append(
            f'<mark class="inconnu" data-mot="{escape(inc.mot)}" '
            f'data-suggestions="{escape(",".join(inc.suggestions))}" '
            f'title="Suggestions : {escape(sugg)}">{escape(inc.mot)}</mark>'
        )
        pos = inc.fin
    morceaux.append(_visible(bloc.texte[pos:]))
    return "".join(morceaux)


def rendre_blocs(blocs: list[Bloc], avec_diff: bool = True) -> Markup:
    html: list[str] = []
    liste_ouverte: str | None = None
    for bloc in blocs:
        balise_liste = ("ol" if bloc.numerote else "ul") if bloc.type == "liste" else None
        if liste_ouverte and liste_ouverte != balise_liste:
            html.append(f"</{liste_ouverte}>")
            liste_ouverte = None
        if balise_liste and not liste_ouverte:
            html.append(f"<{balise_liste}>")
            liste_ouverte = balise_liste

        if bloc.type == "titre":
            titre = escape(bloc.texte)
            origine = (
                f' <span class="origine" title="Texte d\'origine">← {escape(bloc.original)}</span>'
                if avec_diff and bloc.original.strip().rstrip(": ").lower() != bloc.texte.lower()
                else ""
            )
            html.append(f"<h3>{titre}{origine}</h3>")
        elif bloc.type == "liste":
            html.append(f"<li>{_texte_html(bloc, avec_diff)}</li>")
        elif bloc.type == "tableau":
            lignes = "".join(
                "<tr>" + "".join(f"<td>{_texte_html(c, avec_diff)}</td>" for c in ligne) + "</tr>"
                for ligne in bloc.lignes
            )
            html.append(f"<table>{lignes}</table>")
        else:
            html.append(f"<p>{_texte_html(bloc, avec_diff)}</p>")
    if liste_ouverte:
        html.append(f"</{liste_ouverte}>")
    return Markup("\n".join(html))
