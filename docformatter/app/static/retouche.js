"use strict";

/*
 * Éditeur de retouche, sur les paragraphes du document d'origine :
 *   { type: "paragraphe", id, origine, segments, protege, fin_section }
 *   { type: "tableau", id, lignes: [[ [paragraphe] ]] }   (cellule = liste de paragraphes)
 * où un segment est { texte, gras, italique, souligne }. `id` relie le paragraphe à celui du
 * document Word ; un paragraphe ajouté n'a pas d'id mais une `origine` (mise en page reprise).
 * La frappe met à jour l'état sans redessiner ; les actions de structure (couper, fusionner,
 * déplacer…) sont mémorisées pour « ↶ Annuler » puis redessinent la feuille.
 */

const donnees = JSON.parse(document.getElementById("donnees").textContent);
const feuille = document.getElementById("feuille");
const URL_API = feuille.dataset.api;
const STYLES = ["gras", "italique", "souligne"];

let blocs = donnees.blocs;
let inconnus = donnees.inconnus;      // [{ mot, nombre, suggestions }]
let telechargement = donnees.telechargement;
let reference = JSON.stringify(blocs); // dernier état enregistré
let courant = null;                    // position du dernier paragraphe ayant eu le focus
let avantSaisie = null;                // état au début de la saisie dans un paragraphe (pour « Annuler »)
const pile = [];                       // états précédents pour « Annuler »

// Gras / italique / souligné produisent des balises <b>, <i>, <u> plutôt que des styles CSS.
document.execCommand("styleWithCSS", false, false);

// ---- État ---------------------------------------------------------------------------

const instantane = () => JSON.stringify(blocs);

function memoriser(etat = instantane()) {
  if (pile[pile.length - 1] !== etat) pile.push(etat);
  if (pile.length > 200) pile.shift();
}

/** Clôt la saisie en cours : l'état d'avant la frappe devient une étape de « Annuler ». */
function validerSaisie() {
  if (avantSaisie && avantSaisie !== instantane()) memoriser(avantSaisie);
  avantSaisie = null;
}

/** Toute action de structure : clôt la saisie, mémorise l'état courant, puis modifie. */
function modifierStructure(action) {
  validerSaisie();
  memoriser();
  action();
}

function modifie() {
  return instantane() !== reference;
}

function majEtat() {
  const m = modifie();
  document.getElementById("enregistrer").disabled = !m;
  document.getElementById("etat").textContent = m ? "Modifications non enregistrées" : "Enregistré";
  document.getElementById("telecharger").textContent = m ? "Enregistrer et télécharger" : "Télécharger";
  document.querySelector('[data-action="annuler"]').disabled = pile.length === 0;
}

/** Paragraphe désigné par une position : { index } ou { index, ligne, colonne, k } (cellule). */
function paragrapheDe(pos) {
  if (!pos || pos.index >= blocs.length) return null;
  const bloc = blocs[pos.index];
  if (pos.ligne == null) return bloc.type === "paragraphe" ? bloc : null;
  return bloc.lignes?.[pos.ligne]?.[pos.colonne]?.[pos.k] ?? null;
}

function tousLesParagraphes() {
  return blocs.flatMap((b) => (b.type === "tableau" ? b.lignes.flat(2) : [b]));
}

// ---- Segments (texte + mise en forme) -----------------------------------------------

const memeStyle = (a, b) => STYLES.every((s) => !!a[s] === !!b[s]);
const texteDe = (segments) => segments.map((s) => s.texte).join("");

/** Fusionne les segments voisins de même mise en forme et retire les segments vides. */
function normaliser(segments) {
  const resultat = [];
  for (const s of segments) {
    if (!s.texte) continue;
    const dernier = resultat[resultat.length - 1];
    if (dernier && memeStyle(dernier, s)) dernier.texte += s.texte;
    else resultat.push({ texte: s.texte, gras: !!s.gras, italique: !!s.italique, souligne: !!s.souligne });
  }
  return resultat;
}

/** Coupe une liste de segments à la position `pos` du texte. */
function couper(segments, pos) {
  const avant = [];
  const apres = [];
  let vu = 0;
  for (const s of segments) {
    const fin = vu + s.texte.length;
    if (fin <= pos) avant.push({ ...s });
    else if (vu >= pos) apres.push({ ...s });
    else {
      avant.push({ ...s, texte: s.texte.slice(0, pos - vu) });
      apres.push({ ...s, texte: s.texte.slice(pos - vu) });
    }
    vu = fin;
  }
  return [normaliser(avant), normaliser(apres)];
}

/** Lit le contenu d'une zone éditable : texte et mise en forme (balises ou styles en ligne). */
function lireSegments(racine) {
  const segments = [];
  const parcourir = (noeud, style) => {
    if (noeud.nodeType === Node.TEXT_NODE) {
      segments.push({ texte: noeud.data, ...style });
      return;
    }
    if (noeud.nodeType !== Node.ELEMENT_NODE) return;
    if (noeud.tagName === "BR") {
      // Un <br> final est ajouté par le navigateur pour garder la ligne visible : pas un retour à la ligne
      if (noeud.nextSibling || noeud.parentNode !== racine) segments.push({ texte: "\n", ...style });
      return;
    }
    const s = { ...style };
    const balise = noeud.tagName;
    const css = noeud.style;
    if (["B", "STRONG"].includes(balise) || (css && (css.fontWeight === "bold" || Number(css.fontWeight) >= 600))) s.gras = true;
    if (["I", "EM"].includes(balise) || css?.fontStyle === "italic") s.italique = true;
    if (balise === "U" || css?.textDecorationLine?.includes("underline") || css?.textDecoration?.includes("underline")) s.souligne = true;
    noeud.childNodes.forEach((enfant) => parcourir(enfant, s));
  };
  racine.childNodes.forEach((enfant) => parcourir(enfant, { gras: false, italique: false, souligne: false }));
  return normaliser(segments);
}

// ---- Rendu du texte (mise en forme + mots inconnus surlignés) ------------------------

function motifInconnus() {
  if (!inconnus.length) return null;
  const mots = inconnus.map(({ mot }) => mot.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  return new RegExp(`(?<![\\p{L}\\p{N}])(${mots.join("|")})(?![\\p{L}\\p{N}])`, "gu");
}

function texteAvecRetours(texte) {
  const fragment = document.createDocumentFragment();
  texte.split("\n").forEach((morceau, i) => {
    if (i > 0) fragment.append(document.createElement("br"));
    if (morceau) fragment.append(morceau);
  });
  return fragment;
}

function surligner(texte, motif) {
  const fragment = document.createDocumentFragment();
  if (!motif) {
    fragment.append(texteAvecRetours(texte));
    return fragment;
  }
  let pos = 0;
  for (const m of texte.matchAll(motif)) {
    fragment.append(texteAvecRetours(texte.slice(pos, m.index)));
    const info = inconnus.find((x) => x.mot === m[0]);
    fragment.append(el("mark", { class: "inconnu", title: info?.suggestions.length
      ? `Suggestions : ${info.suggestions.join(", ")}` : "Mot inconnu" }, m[0]));
    pos = m.index + m[0].length;
  }
  fragment.append(texteAvecRetours(texte.slice(pos)));
  return fragment;
}

function rendreSegments(segments) {
  const motif = motifInconnus();
  const fragment = document.createDocumentFragment();
  for (const s of segments) {
    let noeud = surligner(s.texte, motif);
    for (const [style, balise] of [["souligne", "u"], ["italique", "i"], ["gras", "b"]]) {
      if (s[style]) {
        const enveloppe = document.createElement(balise);
        enveloppe.append(noeud);
        noeud = enveloppe;
      }
    }
    fragment.append(noeud);
  }
  return fragment;
}

// ---- Curseur ------------------------------------------------------------------------

function positionCurseur(element) {
  const sel = getSelection();
  if (!sel.rangeCount) return 0;
  const r = sel.getRangeAt(0);
  const avant = r.cloneRange();
  avant.selectNodeContents(element);
  avant.setEnd(r.startContainer, r.startOffset);
  // Les <br> comptent pour un caractère (« \n ») dans le texte
  const fragment = avant.cloneContents();
  return fragment.textContent.length + fragment.querySelectorAll("br").length;
}

function placerCurseur(element, offset) {
  element.focus();
  const sel = getSelection();
  const r = document.createRange();
  let reste = offset ?? Infinity;
  const parcours = document.createTreeWalker(element, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
  let noeud;
  while ((noeud = parcours.nextNode())) {
    if (noeud.nodeType === Node.ELEMENT_NODE) {
      if (noeud.tagName === "BR") {
        if (reste === 0) { r.setStartBefore(noeud); break; }
        reste -= 1;
      }
      continue;
    }
    if (reste <= noeud.length) { r.setStart(noeud, reste); break; }
    reste -= noeud.length;
  }
  if (!noeud) {
    r.selectNodeContents(element);
    r.collapse(false);
  } else {
    r.collapse(true);
  }
  sel.removeAllRanges();
  sel.addRange(r);
}

function elementDe(pos) {
  if (!pos) return null;
  const { index, ligne, colonne, k } = pos;
  return ligne == null
    ? feuille.querySelector(`[data-index="${index}"]`)
    : feuille.querySelector(`[data-index="${index}"] [data-ligne="${ligne}"][data-colonne="${colonne}"][data-k="${k}"]`);
}

// ---- Rendu de la feuille ------------------------------------------------------------

function zoneParagraphe(element, p, pos) {
  element.append(rendreSegments(p.segments));
  element.addEventListener("focus", () => {
    courant = pos;
    avantSaisie = instantane();
    majBarre();
  });
  if (p.protege) {
    element.classList.add("protege");
    element.title = "Ce paragraphe contient un lien, un champ automatique ou une image : il est conservé tel quel.";
    element.tabIndex = 0;
    return;
  }
  element.contentEditable = "true";
  element.spellcheck = false;
  element.classList.add("editable");
  element.addEventListener("input", () => {
    if (!element.textContent && !element.querySelector("br + br")) element.replaceChildren();
    p.segments = lireSegments(element);
    majEtat();
  });
  element.addEventListener("blur", () => {
    // Un élément retiré par un nouveau rendu perd aussi le focus : rien à faire dans ce cas.
    if (!element.isConnected) return;
    validerSaisie();
    element.replaceChildren(rendreSegments(p.segments)); // met à jour le surlignage
    majEtat();
  });
  // Collage et glisser-déposer : texte brut uniquement (pas de mise en forme étrangère)
  element.addEventListener("paste", (e) => {
    e.preventDefault();
    document.execCommand("insertText", false, e.clipboardData.getData("text/plain"));
  });
  element.addEventListener("drop", (e) => e.preventDefault());
  element.addEventListener("keydown", (e) => clavier(e, element, pos));
}

function elementBloc(bloc, index) {
  if (bloc.type === "tableau") {
    const table = el("table", { class: "bloc-tableau", "data-index": index });
    bloc.lignes.forEach((ligne, l) => {
      const tr = el("tr");
      ligne.forEach((cellule, c) => {
        const td = el("td");
        cellule.forEach((p, k) => {
          const element = el("p", { class: "bloc", "data-ligne": l, "data-colonne": c, "data-k": k });
          zoneParagraphe(element, p, { index, ligne: l, colonne: c, k });
          td.append(element);
        });
        tr.append(td);
      });
      table.append(tr);
    });
    return table;
  }
  const element = el("p", { class: "bloc", "data-index": index });
  if (bloc.fin_section) {
    element.classList.add("fin-section");
    element.title = "Fin de section : change la mise en page (colonnes, marges) de ce qui suit.";
  }
  zoneParagraphe(element, bloc, { index });
  return element;
}

function rendre(focus = null, offset = null) {
  feuille.replaceChildren(...blocs.map((bloc, i) => elementBloc(bloc, i)));
  const element = elementDe(focus);
  if (element) placerCurseur(element, offset);
  else { courant = null; majBarre(); }
  afficherMots();
  majEtat();
}

// ---- Clavier ------------------------------------------------------------------------

function clavier(e, element, pos) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
    e.preventDefault();
    enregistrer();
    return;
  }
  // Ctrl+B / Ctrl+I / Ctrl+U et Maj+Entrée (retour à la ligne) : gérés par le navigateur
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    if (pos.ligne != null) return; // pas de nouveau paragraphe dans une cellule
    const p = blocs[pos.index];
    const curseur = positionCurseur(element);
    modifierStructure(() => {
      const [avant, apres] = couper(p.segments, curseur);
      p.segments = avant;
      blocs.splice(pos.index + 1, 0, {
        type: "paragraphe", id: null, origine: p.id ?? p.origine, segments: apres, protege: false, fin_section: false,
      });
    });
    rendre({ index: pos.index + 1 }, 0);
  } else if (e.key === "Backspace" && pos.ligne == null && pos.index > 0
             && getSelection().isCollapsed && positionCurseur(element) === 0) {
    const p = blocs[pos.index];
    const precedent = blocs[pos.index - 1];
    if (precedent.type !== "paragraphe" || precedent.protege || p.fin_section) return;
    e.preventDefault();
    const jonction = texteDe(precedent.segments).length;
    modifierStructure(() => {
      precedent.segments = normaliser([...precedent.segments, ...p.segments]);
      blocs.splice(pos.index, 1);
    });
    rendre({ index: pos.index - 1 }, jonction);
  }
}

// ---- Barre d'outils -----------------------------------------------------------------

function majBarre() {
  const p = paragrapheDe(courant);
  const editable = p && !p.protege;
  const corps = p && courant.ligne == null;
  const bouton = (action) => document.querySelector(`[data-action="${action}"]`);
  for (const action of ["gras", "italique", "souligne"]) bouton(action).disabled = !editable;
  bouton("monter").disabled = !corps || p.fin_section || courant.index === 0;
  bouton("descendre").disabled = !corps || p.fin_section || courant.index >= blocs.length - 1;
  bouton("supprimer").disabled = !corps || p.protege || p.fin_section;
  bouton("ajouter-paragraphe").disabled = !courant;
  majBoutonsStyle();
}

/** Boutons G / I / S enfoncés selon la mise en forme sous le curseur. */
function majBoutonsStyle() {
  const dansFeuille = feuille.contains(getSelection().anchorNode);
  for (const [action, commande] of [["gras", "bold"], ["italique", "italic"], ["souligne", "underline"]]) {
    const actif = dansFeuille && document.queryCommandState(commande);
    document.querySelector(`[data-action="${action}"]`).setAttribute("aria-pressed", actif ? "true" : "false");
  }
}
document.addEventListener("selectionchange", majBoutonsStyle);

/** Gras / italique / souligné sur la sélection : le navigateur modifie le texte, l'événement
 *  « input » met ensuite l'état à jour. */
function styler(commande) {
  if (!courant || !feuille.contains(getSelection().anchorNode)) return;
  document.execCommand(commande);
  majBoutonsStyle();
}

/** Paragraphe du corps dont un nouveau paragraphe reprend la mise en page. */
function modeleAvant(index) {
  for (let i = index; i >= 0; i--) {
    const b = blocs[i];
    if (b.type === "paragraphe" && !b.fin_section) return b.id ?? b.origine;
  }
  const premier = blocs.find((b) => b.type === "paragraphe");
  return premier ? premier.id ?? premier.origine : null;
}

const actions = {
  gras: () => styler("bold"),
  italique: () => styler("italic"),
  souligne: () => styler("underline"),
  monter() {
    const { index } = courant;
    modifierStructure(() => { [blocs[index - 1], blocs[index]] = [blocs[index], blocs[index - 1]]; });
    rendre({ index: index - 1 });
  },
  descendre() {
    const { index } = courant;
    modifierStructure(() => { [blocs[index + 1], blocs[index]] = [blocs[index], blocs[index + 1]]; });
    rendre({ index: index + 1 });
  },
  supprimer() {
    const { index } = courant;
    modifierStructure(() => blocs.splice(index, 1));
    rendre(blocs.length ? { index: Math.min(index, blocs.length - 1) } : null);
  },
  "ajouter-paragraphe"() {
    const index = courant.index + 1;
    const origine = modeleAvant(courant.index);
    if (!origine) return;
    modifierStructure(() => blocs.splice(index, 0, {
      type: "paragraphe", id: null, origine, segments: [], protege: false, fin_section: false,
    }));
    rendre({ index }, 0);
  },
  annuler() {
    validerSaisie();
    if (!pile.length) return;
    blocs = JSON.parse(pile.pop());
    rendre(paragrapheDe(courant) ? courant : null);
  },
};

document.querySelectorAll(".barre-outils button").forEach((bouton) => {
  // mousedown : garde le focus (et donc le curseur ou la sélection) dans le texte
  bouton.addEventListener("mousedown", (e) => e.preventDefault());
  bouton.addEventListener("click", () => actions[bouton.dataset.action]());
});

// ---- Mots à vérifier ----------------------------------------------------------------

function remplacerPartout(mot, par) {
  const echappe = mot.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const motif = new RegExp(`(?<![\\p{L}\\p{N}])${echappe}(?![\\p{L}\\p{N}])`, "gu");
  for (const p of tousLesParagraphes()) {
    if (!p.protege) p.segments = p.segments.map((s) => ({ ...s, texte: s.texte.replace(motif, par) }));
  }
}

function afficherMots() {
  const liste = document.getElementById("liste-mots");
  if (!inconnus.length) {
    liste.replaceChildren(el("li", { class: "vide" }, "Aucun mot à vérifier."));
    return;
  }
  liste.replaceChildren(...inconnus.map((info) => {
    const { mot, nombre, suggestions } = info;
    const idListe = `sugg-${mot}`;
    const champ = el("input", { type: "text", value: suggestions[0] ?? "", list: idListe, "aria-label": `Remplacer ${mot} par` });
    const toujours = el("input", { type: "checkbox" });
    return el("li", {},
      el("div", {}, el("mark", {}, mot), nombre > 1 ? ` (${nombre} fois)` : ""),
      el("button", { type: "button", class: "petit", onclick: async () => {
        try {
          const r = await api("POST", "api/vocabulaire/mot", { mot });
          inconnus = inconnus.filter((x) => x !== info);
          rendre(courant);
          notifier(r.message, { annulation: r.annulation, apresAnnulation: () => {
            inconnus.push(info);
            rendre(courant);
          } });
        } catch (e) {
          notifier(e.message, { type: "erreur" });
        }
      } }, "Le mot est correct"),
      el("div", { class: "remplacer-mot" }, champ,
        el("datalist", { id: idListe }, suggestions.map((s) => el("option", { value: s }))),
        el("button", { type: "button", class: "petit", onclick: async () => {
          const par = champ.value.trim();
          if (!par) { champ.focus(); return; }
          modifierStructure(() => remplacerPartout(mot, par));
          inconnus = inconnus.filter((x) => x !== info);
          rendre(courant);
          if (toujours.checked) {
            try {
              const r = await api("POST", "api/vocabulaire/remplacement", { texte: mot, par });
              notifier(`${r.message} (pour les prochains documents)`, { annulation: r.annulation, apresAnnulation: () => {} });
            } catch (e) {
              notifier(e.message, { type: "erreur" });
            }
          }
        } }, "Remplacer")),
      el("label", { class: "toujours" }, toujours, "Toujours remplacer ce mot"));
  }));
}

// ---- Enregistrement -----------------------------------------------------------------

function charger(r) {
  blocs = r.blocs;
  inconnus = r.inconnus;
  telechargement = r.telechargement;
  reference = instantane();
  document.getElementById("telecharger").href = `telecharger/${telechargement}`;
  rendre(paragrapheDe(courant) ? courant : null);
}

async function enregistrer() {
  const bouton = document.getElementById("enregistrer");
  bouton.disabled = true;
  try {
    charger(await api("PUT", URL_API, { blocs }));
    document.getElementById("revenir-auto").hidden = false;
    notifier("Retouches enregistrées.");
    return true;
  } catch (e) {
    notifier(e.message, { type: "erreur" });
    majEtat();
    return false;
  }
}

document.getElementById("enregistrer").addEventListener("click", enregistrer);

document.getElementById("telecharger").addEventListener("click", async (e) => {
  if (!modifie()) return; // lien direct vers le .docx enregistré
  e.preventDefault();
  if (await enregistrer()) location.href = `telecharger/${telechargement}`;
});

document.getElementById("revenir-auto").addEventListener("click", async () => {
  if (!confirm("Abandonner toutes vos retouches et revenir au document corrigé automatiquement ?")) return;
  try {
    memoriser();
    charger(await api("DELETE", URL_API));
    document.getElementById("revenir-auto").hidden = true;
    notifier("Retouches abandonnées.");
  } catch (e) {
    notifier(e.message, { type: "erreur" });
  }
});

window.addEventListener("beforeunload", (e) => {
  if (modifie()) e.preventDefault();
});

rendre();
