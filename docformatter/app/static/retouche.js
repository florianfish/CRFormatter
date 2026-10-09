"use strict";

/*
 * Éditeur de retouche. Le document est une liste de blocs :
 *   { type: "titre" | "paragraphe" | "liste", texte, numerote }  ou  { type: "tableau", lignes: [[texte]] }
 * La frappe met à jour l'état sans redessiner ; les actions de structure (couper, fusionner,
 * déplacer, changer de type…) sont mémorisées pour « ↶ Annuler » puis redessinent la feuille.
 */

const donnees = JSON.parse(document.getElementById("donnees").textContent);
const feuille = document.getElementById("feuille");
const URL_API = feuille.dataset.api;

let blocs = donnees.blocs;
let inconnus = donnees.inconnus;      // [{ mot, nombre, suggestions }]
let telechargement = donnees.telechargement;
let reference = JSON.stringify(blocs); // dernier état enregistré
let courant = null;                    // { index, ligne?, colonne? } : dernier élément ayant eu le focus
let avantSaisie = null;                // état au début de la saisie dans un bloc (pour « Annuler »)
const pile = [];                       // états précédents pour « Annuler »

const PLAINTEXT = (() => {
  const d = document.createElement("div");
  d.contentEditable = "plaintext-only";
  return d.contentEditable === "plaintext-only" ? "plaintext-only" : "true";
})();

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

// ---- Surlignage des mots inconnus ---------------------------------------------------

function motifInconnus() {
  if (!inconnus.length) return null;
  const mots = inconnus.map(({ mot }) => mot.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  return new RegExp(`(?<![\\p{L}\\p{N}])(${mots.join("|")})(?![\\p{L}\\p{N}])`, "gu");
}

function surligner(texte) {
  const motif = motifInconnus();
  const fragment = document.createDocumentFragment();
  if (!motif) {
    fragment.append(texte);
    return fragment;
  }
  let pos = 0;
  for (const m of texte.matchAll(motif)) {
    fragment.append(texte.slice(pos, m.index));
    const info = inconnus.find((x) => x.mot === m[0]);
    fragment.append(el("mark", { class: "inconnu", title: info?.suggestions.length
      ? `Suggestions : ${info.suggestions.join(", ")}` : "Mot inconnu" }, m[0]));
    pos = m.index + m[0].length;
  }
  fragment.append(texte.slice(pos));
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
  return avant.toString().length;
}

function placerCurseur(element, offset) {
  element.focus();
  const sel = getSelection();
  const r = document.createRange();
  const parcours = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
  let reste = offset ?? Infinity;
  let noeud;
  while ((noeud = parcours.nextNode())) {
    if (reste <= noeud.length) {
      r.setStart(noeud, reste);
      r.collapse(true);
      sel.removeAllRanges();
      sel.addRange(r);
      return;
    }
    reste -= noeud.length;
  }
  r.selectNodeContents(element);
  r.collapse(false);
  sel.removeAllRanges();
  sel.addRange(r);
}

function elementDe(cible) {
  if (!cible) return null;
  const { index, ligne, colonne } = cible;
  return ligne == null
    ? feuille.querySelector(`[data-index="${index}"]`)
    : feuille.querySelector(`[data-index="${index}"] [data-ligne="${ligne}"][data-colonne="${colonne}"]`);
}

// ---- Rendu --------------------------------------------------------------------------

function zoneEditable(element, lire, ecrire, position) {
  element.contentEditable = PLAINTEXT;
  element.spellcheck = false;
  element.classList.add("editable");
  element.append(surligner(lire()));
  element.addEventListener("focus", () => {
    courant = position;
    avantSaisie = instantane();
    majBarre();
  });
  element.addEventListener("input", () => {
    ecrire(element.textContent);
    majEtat();
  });
  element.addEventListener("blur", () => {
    // Un élément retiré par un nouveau rendu perd aussi le focus : rien à faire dans ce cas.
    if (!element.isConnected) return;
    validerSaisie();
    element.replaceChildren(surligner(lire())); // met à jour le surlignage
    majEtat();
  });
  if (PLAINTEXT !== "plaintext-only") {
    element.addEventListener("paste", (e) => {
      e.preventDefault();
      document.execCommand("insertText", false, e.clipboardData.getData("text/plain"));
    });
  }
}

function elementBloc(bloc, index, numero) {
  if (bloc.type === "tableau") {
    const table = el("table", { class: "bloc bloc-tableau", "data-index": index });
    bloc.lignes.forEach((ligne, l) => {
      const tr = el("tr");
      ligne.forEach((_, c) => {
        const td = el("td", { "data-ligne": l, "data-colonne": c });
        zoneEditable(td, () => bloc.lignes[l][c], (t) => { bloc.lignes[l][c] = t; }, { index, ligne: l, colonne: c });
        td.addEventListener("keydown", (e) => { if (e.key === "Enter") e.preventDefault(); });
        tr.append(td);
      });
      table.append(tr);
    });
    return table;
  }

  const balise = bloc.type === "titre" ? "h2" : "p";
  const element = el(balise, { class: `bloc bloc-${bloc.type}`, "data-index": index });
  if (bloc.type === "liste") element.dataset.puce = bloc.numerote ? `${numero}.` : "•";
  zoneEditable(element, () => bloc.texte, (t) => { bloc.texte = t; }, { index });
  element.addEventListener("keydown", (e) => clavier(e, element, index));
  return element;
}

function rendre(focus = null, offset = null) {
  let numero = 0;
  feuille.replaceChildren(...blocs.map((bloc, i) => {
    numero = bloc.type === "liste" && bloc.numerote ? numero + 1 : 0;
    return elementBloc(bloc, i, numero);
  }));
  if (!blocs.length) {
    feuille.append(el("p", { class: "vide" }, "Le document est vide. Utilisez « + Paragraphe » pour ajouter du texte."));
  }
  const element = elementDe(focus);
  if (element) placerCurseur(element, offset);
  else { courant = null; majBarre(); }
  afficherMots();
  majEtat();
}

// ---- Clavier : couper / fusionner des paragraphes ------------------------------------

function clavier(e, element, index) {
  const bloc = blocs[index];
  if (e.key === "Enter" && !e.isComposing) {
    e.preventDefault();
    const pos = positionCurseur(element);
    const type = bloc.type === "titre" ? "paragraphe" : bloc.type;
    // Entrée sur une puce vide : on sort de la liste, comme dans Word
    if (bloc.type === "liste" && !bloc.texte) {
      modifierStructure(() => { bloc.type = "paragraphe"; });
      rendre({ index }, 0);
      return;
    }
    modifierStructure(() => {
      const apres = bloc.texte.slice(pos);
      bloc.texte = bloc.texte.slice(0, pos);
      blocs.splice(index + 1, 0, { type, texte: apres, numerote: bloc.numerote && type === "liste" });
    });
    rendre({ index: index + 1 }, 0);
  } else if (e.key === "Backspace" && getSelection().isCollapsed && positionCurseur(element) === 0 && index > 0) {
    const precedent = blocs[index - 1];
    if (precedent.type === "tableau") return;
    e.preventDefault();
    const jonction = precedent.texte.length;
    modifierStructure(() => {
      precedent.texte += bloc.texte;
      blocs.splice(index, 1);
    });
    rendre({ index: index - 1 }, jonction);
  } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
    e.preventDefault();
    enregistrer();
  }
}

// ---- Barre d'outils -----------------------------------------------------------------

function majBarre() {
  const bloc = courant ? blocs[courant.index] : null;
  const select = document.getElementById("type-bloc");
  select.disabled = !bloc || bloc.type === "tableau";
  if (bloc && bloc.type !== "tableau") {
    select.value = bloc.type === "liste" ? (bloc.numerote ? "numero" : "puce") : bloc.type;
  }
  for (const action of ["monter", "descendre", "supprimer"]) {
    document.querySelector(`[data-action="${action}"]`).disabled = !bloc;
  }
  document.querySelector(".outils-tableau").hidden = !bloc || bloc.type !== "tableau";
}

const actions = {
  monter() {
    const { index } = courant;
    if (index === 0) return;
    modifierStructure(() => { [blocs[index - 1], blocs[index]] = [blocs[index], blocs[index - 1]]; });
    rendre({ ...courant, index: index - 1 });
  },
  descendre() {
    const { index } = courant;
    if (index >= blocs.length - 1) return;
    modifierStructure(() => { [blocs[index + 1], blocs[index]] = [blocs[index], blocs[index + 1]]; });
    rendre({ ...courant, index: index + 1 });
  },
  supprimer() {
    const { index } = courant;
    modifierStructure(() => blocs.splice(index, 1));
    rendre(blocs.length ? { index: Math.min(index, blocs.length - 1) } : null);
  },
  "ajouter-paragraphe"() {
    const index = courant ? courant.index + 1 : blocs.length;
    modifierStructure(() => blocs.splice(index, 0, { type: "paragraphe", texte: "", numerote: false }));
    rendre({ index }, 0);
  },
  "ajouter-tableau"() {
    const index = courant ? courant.index + 1 : blocs.length;
    modifierStructure(() => blocs.splice(index, 0, { type: "tableau", lignes: [["", ""], ["", ""]] }));
    rendre({ index, ligne: 0, colonne: 0 });
  },
  "ajouter-ligne"() {
    const t = blocs[courant.index];
    const l = courant.ligne + 1;
    modifierStructure(() => t.lignes.splice(l, 0, t.lignes[0].map(() => "")));
    rendre({ ...courant, ligne: l, colonne: 0 });
  },
  "supprimer-ligne"() {
    const t = blocs[courant.index];
    modifierStructure(() => {
      t.lignes.splice(courant.ligne, 1);
      if (!t.lignes.length) blocs.splice(courant.index, 1);
    });
    const reste = blocs[courant.index]?.lignes?.length;
    rendre(reste ? { ...courant, ligne: Math.min(courant.ligne, reste - 1) } : null);
  },
  "ajouter-colonne"() {
    const t = blocs[courant.index];
    const c = courant.colonne + 1;
    modifierStructure(() => t.lignes.forEach((ligne) => ligne.splice(c, 0, "")));
    rendre({ ...courant, colonne: c });
  },
  "supprimer-colonne"() {
    const t = blocs[courant.index];
    modifierStructure(() => {
      t.lignes.forEach((ligne) => ligne.splice(courant.colonne, 1));
      if (!t.lignes[0].length) blocs.splice(courant.index, 1);
    });
    const reste = blocs[courant.index]?.lignes?.[0]?.length;
    rendre(reste ? { ...courant, colonne: Math.min(courant.colonne, reste - 1) } : null);
  },
  annuler() {
    validerSaisie();
    if (!pile.length) return;
    blocs = JSON.parse(pile.pop());
    rendre(courant && courant.index < blocs.length ? courant : null);
  },
};

document.querySelectorAll(".barre-outils button").forEach((bouton) => {
  // mousedown : garde le focus (et donc le curseur) dans le texte
  bouton.addEventListener("mousedown", (e) => e.preventDefault());
  bouton.addEventListener("click", () => actions[bouton.dataset.action]());
});

document.getElementById("type-bloc").addEventListener("change", (e) => {
  if (!courant) return;
  const bloc = blocs[courant.index];
  modifierStructure(() => {
    bloc.type = { titre: "titre", paragraphe: "paragraphe", puce: "liste", numero: "liste" }[e.target.value];
    bloc.numerote = e.target.value === "numero";
  });
  rendre({ index: courant.index });
});

// ---- Mots à vérifier ----------------------------------------------------------------

function remplacerPartout(mot, par) {
  const echappe = mot.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const motif = new RegExp(`(?<![\\p{L}\\p{N}])${echappe}(?![\\p{L}\\p{N}])`, "gu");
  for (const bloc of blocs) {
    if (bloc.type === "tableau") bloc.lignes = bloc.lignes.map((l) => l.map((c) => c.replace(motif, par)));
    else bloc.texte = bloc.texte.replace(motif, par);
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
  rendre(courant && courant.index < blocs.length ? courant : null);
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
  if (!confirm("Abandonner toutes vos retouches et revenir au document mis en forme automatiquement ?")) return;
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
