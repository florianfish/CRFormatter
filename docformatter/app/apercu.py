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
    if bloc.protege:
        return _visible(bloc.texte)
    if avec_diff and bloc.texte != bloc.original and not bloc.inconnus:
        return diff_html(bloc.original, bloc.texte)
    # Texte avec sa mise en forme et ses mots inconnus annotés
    morceaux = []
    for t in bloc.troncons():
        html = _visible(t.texte).replace("\n", "<br>")
        if t.inconnu is not None:
            sugg = ", ".join(t.inconnu.suggestions) or "aucune suggestion"
            html = f'<mark class="inconnu" title="Suggestions : {escape(sugg)}">{html}</mark>'
        for actif, balise in ((t.souligne, "u"), (t.italique, "em"), (t.gras, "strong")):
            if actif:
                html = f"<{balise}>{html}</{balise}>"
        morceaux.append(html)
    return "".join(morceaux)


def _paragraphe_html(p: Bloc, avec_diff: bool) -> str:
    classe = ' class="protege" title="Contient un lien ou un champ automatique : laissé tel quel"' if p.protege else ""
    return f"<p{classe}>{_texte_html(p, avec_diff)}</p>"


def rendre_blocs(blocs: list[Bloc], avec_diff: bool = True) -> Markup:
    """Aperçu du corps du document (les lignes vides successives sont regroupées)."""
    html: list[str] = []
    ligne_vide = False
    for bloc in blocs:
        if bloc.type == "tableau":
            lignes = "".join(
                "<tr>" + "".join(
                    "<td>" + "".join(_paragraphe_html(p, avec_diff) for p in cellule.paragraphes) + "</td>"
                    for cellule in ligne
                ) + "</tr>"
                for ligne in bloc.lignes
            )
            html.append(f"<table>{lignes}</table>")
            ligne_vide = False
        elif not bloc.texte.strip():
            if not ligne_vide:
                html.append('<p class="ligne-vide"></p>')
            ligne_vide = True
        else:
            html.append(_paragraphe_html(bloc, avec_diff))
            ligne_vide = False
    return Markup("\n".join(html))
