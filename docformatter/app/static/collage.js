"use strict";

/*
 * Lecture d'un compte rendu collé depuis Word. Le HTML du presse-papiers est affiché dans une
 * iframe isolée (sans scripts ni images) pour obtenir les styles calculés : Word met la police
 * et les espacements dans une feuille de style (classe MsoNormal) plutôt que sur chaque paragraphe.
 * Résultat envoyé au serveur (cf. collage.py) :
 *   { type: "paragraphe", segments, mise_en_page } | { type: "tableau", bordures, lignes }
 */

const PX_EN_PT = 0.75;
const BLOCS = new Set(["P", "DIV", "H1", "H2", "H3", "H4", "H5", "H6", "LI", "BLOCKQUOTE", "PRE", "DT", "DD"]);
const IGNORES = new Set(["SCRIPT", "STYLE", "TEMPLATE", "HEAD", "TITLE", "META", "LINK", "IMG", "SVG", "OBJECT", "IFRAME"]);
const PUCES = new Set(["·", "\uf0b7", "§", "\uf0a7", "o", "Ø", "\uf0d8", "ü", "\uf0fc", "–", "•", "-"]);

const arrondi = (x, pas = 0.5) => Math.round(x / pas) * pas;
const pt = (valeur) => arrondi((parseFloat(valeur) || 0) * PX_EN_PT);

/** Charge le HTML collé dans une iframe isolée et attend son rendu. */
function documentIsole(html) {
  const propre = new DOMParser().parseFromString(html, "text/html");
  propre.querySelectorAll("script, img, link, iframe, object, embed, meta[http-equiv]").forEach((e) => e.remove());
  const cadre = el("iframe", { sandbox: "allow-same-origin", "aria-hidden": "true", tabindex: "-1" });
  Object.assign(cadre.style, { position: "absolute", left: "-10000px", top: "0", width: "800px", height: "600px", visibility: "hidden" });
  return new Promise((resolve) => {
    cadre.addEventListener("load", () => resolve(cadre), { once: true });
    cadre.srcdoc = `<!doctype html>${propre.documentElement.outerHTML}`;
    document.body.append(cadre);
  });
}

function miseEnPage(element, vue) {
  const css = vue.getComputedStyle(element);
  const m = {};
  const alignement = { center: "centre", right: "droite", end: "droite", justify: "justifie" }[css.textAlign];
  if (alignement) m.alignement = alignement;
  const gauche = pt(css.marginLeft) + pt(css.paddingLeft);
  if (gauche) m.retrait_gauche = gauche;
  if (pt(css.textIndent)) m.retrait_premiere_ligne = pt(css.textIndent);
  m.espace_avant = Math.max(0, pt(css.marginTop));
  m.espace_apres = Math.max(0, pt(css.marginBottom));
  const taille = parseFloat(css.fontSize);
  const hauteur = parseFloat(css.lineHeight);
  if (taille && hauteur) m.interligne = Math.min(5, Math.max(0.5, arrondi(hauteur / taille, 0.01)));
  return m;
}

function style(element, vue, bloc) {
  const css = vue.getComputedStyle(element);
  let souligne = false;
  for (let e = element; e && e !== bloc.parentNode; e = e.parentElement) {
    if (vue.getComputedStyle(e).textDecorationLine.includes("underline")) { souligne = true; break; }
  }
  return {
    gras: css.fontWeight === "bold" || Number(css.fontWeight) >= 600,
    italique: css.fontStyle === "italic",
    souligne,
    police: css.fontFamily.split(",")[0].replace(/["']/g, "").trim(),
    taille: arrondi(parseFloat(css.fontSize) * PX_EN_PT),
  };
}

/** Police et taille majoritaires du paragraphe (en nombre de caractères). */
function policeMajoritaire(segments) {
  const compte = new Map();
  for (const s of segments) {
    const cle = `${s.police}|${s.taille}`;
    compte.set(cle, (compte.get(cle) || 0) + s.texte.trim().length + 0.001);
  }
  const [cle] = [...compte.entries()].sort((a, b) => b[1] - a[1])[0] || [""];
  const [police, taille] = cle.split("|");
  return { police: police || undefined, taille: Number(taille) || undefined };
}

/** Espaces du code HTML : réduits comme à l'affichage, retirés en début et fin de paragraphe. */
function finaliser(paragraphe, policeParDefaut) {
  const segments = [];
  for (const s of paragraphe.segments) {
    let texte = s.brut ? s.texte : s.texte.replace(/[ \t\r\n]+/g, " ");
    const precedent = segments[segments.length - 1];
    const finPrecedente = precedent ? precedent.texte.slice(-1) : "\n";
    if (!s.brut && (finPrecedente === " " || finPrecedente === "\n" || finPrecedente === "\t")) texte = texte.replace(/^ /, "");
    if (texte) segments.push({ ...s, texte });
  }
  while (segments.length && !segments[segments.length - 1].brut) {
    const dernier = segments[segments.length - 1];
    dernier.texte = dernier.texte.replace(/ +$/, "");
    if (dernier.texte) break;
    segments.pop();
  }
  // Paragraphe vide de Word (« &nbsp; ») : ligne vide
  const vide = !segments.some((s) => s.texte.replace(/[\s ]/g, ""));
  const police = vide ? policeParDefaut : policeMajoritaire(segments);
  return {
    segments: vide ? [] : segments.map(({ texte, gras, italique, souligne }) => ({ texte, gras, italique, souligne })),
    mise_en_page: { ...paragraphe.mise_en_page, ...Object.fromEntries(Object.entries(police).filter(([, v]) => v)) },
  };
}

function lireContenu(racine, vue) {
  const resultat = [];
  let courant = null;
  const policeDe = (element) => {
    const s = style(element, vue, element);
    return { police: s.police, taille: s.taille };
  };

  const fermer = (garderVide = false) => {
    if (courant && (garderVide || courant.segments.some((s) => s.texte.trim()))) {
      resultat.push({ type: "paragraphe", ...finaliser(courant, policeDe(courant.element)) });
    }
    courant = null;
  };
  const ouvrir = (element) => { courant = { element, segments: [], mise_en_page: miseEnPage(element, vue) }; };

  const parcourir = (noeud, bloc) => {
    for (const enfant of noeud.childNodes) {
      if (enfant.nodeType === Node.TEXT_NODE) {
        if (!courant) ouvrir(bloc);
        courant.segments.push({ texte: enfant.data, ...style(enfant.parentElement, vue, bloc) });
        continue;
      }
      if (enfant.nodeType !== Node.ELEMENT_NODE || IGNORES.has(enfant.tagName)) continue;
      const css = vue.getComputedStyle(enfant);
      if (css.display === "none") continue;
      const attribut = enfant.getAttribute("style") || "";
      if (enfant.tagName === "BR") {
        if (!courant) ouvrir(bloc);
        courant.segments.push({ texte: "\n", brut: true, ...style(noeud, vue, bloc) });
      } else if (/mso-tab-count/.test(attribut)) {
        if (!courant) ouvrir(bloc);
        courant.segments.push({ texte: "\t", brut: true, ...style(enfant, vue, bloc) });
      } else if (/mso-list:\s*Ignore/i.test(attribut)) {
        // Puce ou numéro d'une liste Word : remplacé par un tiret ou gardé (« 1. »), suivi d'une tabulation
        if (!courant) ouvrir(bloc);
        const marque = enfant.textContent.replace(/[\s ]+/g, "");
        courant.segments.push({ texte: `${PUCES.has(marque) ? "-" : marque}\t`, brut: true, ...style(enfant, vue, bloc) });
      } else if (enfant.tagName === "TABLE") {
        fermer();
        resultat.push(lireTableau(enfant, vue));
      } else if (BLOCS.has(enfant.tagName) || ["block", "list-item", "flex", "grid"].includes(css.display)) {
        fermer();
        ouvrir(enfant);
        const sienne = courant;
        parcourir(enfant, enfant);
        // Paragraphe vide gardé (ligne vide), sauf s'il ne fait qu'entourer d'autres paragraphes
        fermer(courant === sienne);
      } else {
        parcourir(enfant, bloc);
      }
    }
  };
  parcourir(racine, racine);
  fermer();
  return resultat;
}

function lireTableau(table, vue) {
  const cellule = (td) => {
    const contenu = lireContenu(td, vue).filter((b) => b.type === "paragraphe");
    return contenu.length ? contenu.map(({ segments, mise_en_page }) => ({ segments, mise_en_page })) : [];
  };
  const premiere = table.querySelector("td, th");
  const bordure = premiere ? vue.getComputedStyle(premiere).borderTopStyle : "none";
  return {
    type: "tableau",
    bordures: !["none", "hidden"].includes(bordure),
    lignes: [...table.rows].map((tr) => [...tr.cells].map(cellule)),
  };
}

/** Contenu du presse-papiers → blocs. Sans HTML (texte simple) : un paragraphe par ligne. */
async function lireCollage(donnees) {
  const html = donnees.getData("text/html");
  if (!html.trim()) {
    return donnees.getData("text/plain").replace(/\r/g, "").split("\n").map((ligne) => ({
      type: "paragraphe", segments: ligne ? [{ texte: ligne }] : [], mise_en_page: {},
    }));
  }
  const cadre = await documentIsole(html);
  try {
    return lireContenu(cadre.contentDocument.body, cadre.contentWindow);
  } finally {
    cadre.remove();
  }
}
