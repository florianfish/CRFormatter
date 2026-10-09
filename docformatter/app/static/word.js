"use strict";

/*
 * « Copier pour Word » : le document (blocs de l'éditeur, cf. retouche.js) est placé dans le
 * presse-papiers en HTML que Word comprend (mise en forme, mise en page, tableaux) et en texte
 * simple. Utilisé par l'éditeur et par la page de résultat.
 */

const texteDe = (segments) => segments.map((s) => s.texte).join("");

const ALIGNEMENTS_CSS = { centre: "center", droite: "right", justifie: "justify" };

/** Mise en page du paragraphe en CSS (affichage dans la feuille et copie pour Word). */
function styleMiseEnPage(m = {}) {
  const style = {
    marginTop: `${m.espace_avant || 0}pt`,
    marginBottom: `${m.espace_apres || 0}pt`,
    marginLeft: `${m.retrait_gauche || 0}pt`,
  };
  if (m.retrait_premiere_ligne) style.textIndent = `${m.retrait_premiere_ligne}pt`;
  if (m.alignement) style.textAlign = ALIGNEMENTS_CSS[m.alignement];
  if (m.police) style.fontFamily = `"${m.police.replace(/["\\]/g, "")}"`;
  if (m.taille) style.fontSize = `${m.taille}pt`;
  return style;
}

/** Texte d'un segment pour Word : retours à la ligne et tabulations (reconnues par Word). */
function texteWord(texte) {
  const fragment = document.createDocumentFragment();
  texte.split("\n").forEach((ligne, i) => {
    if (i > 0) fragment.append(el("br"));
    ligne.split("\t").forEach((morceau, j) => {
      if (j > 0) fragment.append(el("span", { style: "mso-tab-count:1" }, "\t"));
      if (morceau) fragment.append(morceau);
    });
  });
  return fragment;
}

function paragrapheWord(p) {
  const element = el("p");
  const style = styleMiseEnPage(p.mise_en_page);
  Object.assign(element.style, style);
  if (p.mise_en_page?.interligne) element.style.lineHeight = `${Math.round(p.mise_en_page.interligne * 100)}%`;
  const contenu = el("span");
  Object.assign(contenu.style, { fontFamily: style.fontFamily ?? "", fontSize: style.fontSize ?? "" });
  for (const s of p.segments) {
    let noeud = texteWord(s.texte);
    for (const [cle, balise] of [["souligne", "u"], ["italique", "i"], ["gras", "b"]]) {
      if (s[cle]) noeud = el(balise, {}, noeud);
    }
    contenu.append(noeud);
  }
  if (!texteDe(p.segments)) contenu.append("\u00a0"); // ligne vide conservée par Word
  element.append(contenu);
  return element;
}

function tableauWord(bloc) {
  const bordure = bloc.mise_en_page?.bordures ? "border:solid windowtext 1pt;" : "";
  const table = el("table", { style: "border-collapse:collapse", cellspacing: "0", cellpadding: "0" });
  for (const ligne of bloc.lignes) {
    table.append(el("tr", {}, ligne.map((cellule) => el("td", {
      style: `${bordure}padding:0 5.4pt;vertical-align:top`,
    }, cellule.length ? cellule.map(paragrapheWord) : paragrapheWord({ segments: [] })))));
  }
  return table;
}

/** Le document en HTML (mise en forme pour Word) et en texte simple (autres logiciels). */
function contenuPourWord(blocs) {
  const racine = el("div", {}, blocs.map((b) => (b.type === "tableau" ? tableauWord(b) : paragrapheWord(b))));
  const texte = blocs.map((b) => (b.type === "tableau"
    ? b.lignes.map((ligne) => ligne.map((cellule) => cellule.map((p) => texteDe(p.segments)).join(" ")).join("\t")).join("\r\n")
    : texteDe(b.segments).replace(/\n/g, "\r\n"))).join("\r\n");
  // Sérialisation d'éléments construits avec el() : le texte y est échappé
  return { html: `<html><head><meta charset="utf-8"></head><body>${racine.innerHTML}</body></html>`, texte };
}

/** Copie le document ; retourne false (après avoir prévenu) si le navigateur l'a refusé. */
function copierPourWord(blocs) {
  const { html, texte } = contenuPourWord(blocs);
  // L'événement « copy » permet de fournir le HTML, y compris hors HTTPS (accès par l'adresse locale de HA)
  const ecouteur = (e) => {
    e.preventDefault();
    e.clipboardData.setData("text/html", html);
    e.clipboardData.setData("text/plain", texte);
  };
  document.addEventListener("copy", ecouteur);
  let reussi = false;
  try {
    reussi = document.execCommand("copy");
  } finally {
    document.removeEventListener("copy", ecouteur);
  }
  if (reussi) notifier("Copié ! Dans Word, collez avec Ctrl+V à la place du texte d'origine.");
  else notifier("La copie n'a pas fonctionné : réessayez, ou téléchargez le document.", { type: "erreur" });
  return reussi;
}
