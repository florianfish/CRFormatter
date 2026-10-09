"use strict";

let vocabulaire = { remplacements: [], mots: [], rubriques: [] };

function afficher() {
  afficherRemplacements();
  afficherMots();
  afficherRubriques();
}

/** Envoie une modification, rafraîchit l'affichage et propose « Annuler ». */
async function modifier(methode, url, corps) {
  try {
    const r = await api(methode, url, corps);
    vocabulaire = r.vocabulaire;
    afficher();
    notifier(r.message, { annulation: r.annulation, apresAnnulation: charger });
    return true;
  } catch (e) {
    notifier(e.message, { type: "erreur" });
    return false;
  }
}

function filtre(id) {
  return document.getElementById(id).value.trim().toLowerCase();
}

function afficherRemplacements() {
  const f = filtre("filtre-remplacements");
  const lignes = vocabulaire.remplacements.filter(({ texte, par }) =>
    !f || texte.toLowerCase().includes(f) || par.toLowerCase().includes(f));
  document.getElementById("liste-remplacements").replaceChildren(
    ...lignes.map(({ texte, par }) => el("li", {},
      el("span", { class: "remplacement" }, el("del", {}, texte), " → ", el("ins", {}, par)),
      el("button", { type: "button", class: "petit danger", title: `Supprimer « ${texte} »`,
        onclick: () => modifier("DELETE", "api/vocabulaire/remplacement", { texte }) }, "Supprimer"))),
    lignes.length ? [] : el("li", { class: "vide" }, f ? "Aucun résultat." : "Aucun remplacement."));
}

function afficherMots() {
  const f = filtre("filtre-mots");
  const mots = vocabulaire.mots.filter((m) => !f || m.toLowerCase().includes(f));
  const n = vocabulaire.mots.length;
  document.getElementById("compte-mots").textContent = `${n} mot${n > 1 ? "s" : ""} connu${n > 1 ? "s" : ""}`;
  document.getElementById("liste-mots").replaceChildren(
    ...mots.map((mot) => el("li", {}, mot,
      el("button", { type: "button", title: `Retirer « ${mot} »`, "aria-label": `Retirer ${mot}`,
        onclick: () => modifier("DELETE", "api/vocabulaire/mot", { mot }) }, "×"))),
    mots.length ? [] : el("li", { class: "vide" }, f ? "Aucun résultat." : "Aucun mot."));
}

function afficherRubriques() {
  document.getElementById("liste-rubriques").replaceChildren(...vocabulaire.rubriques.map(({ titre, variantes }) => {
    const champ = el("input", { type: "text", placeholder: "autre façon de l'écrire", "aria-label": `Autre écriture de ${titre}` });
    const ajouter = async (e) => {
      e.preventDefault();
      if (await modifier("POST", "api/vocabulaire/variante", { titre, variante: champ.value })) {
        document.querySelector(`[data-rubrique="${CSS.escape(titre)}"] input`)?.focus();
      }
    };
    return el("div", { class: "rubrique", "data-rubrique": titre },
      el("div", { class: "entete-rubrique" },
        el("strong", {}, titre),
        el("button", { type: "button", class: "petit danger",
          onclick: () => confirm(`Supprimer la rubrique « ${titre} » ?`) &&
            modifier("DELETE", "api/vocabulaire/rubrique", { titre }) }, "Supprimer la rubrique")),
      el("span", { class: "aide" }, "Reconnue aussi quand c'est écrit :"),
      el("ul", { class: "etiquettes" }, variantes.map((variante) => el("li", {}, variante,
        el("button", { type: "button", title: `Retirer « ${variante} »`, "aria-label": `Retirer ${variante}`,
          onclick: () => modifier("DELETE", "api/vocabulaire/variante", { titre, variante }) }, "×")))),
      el("form", { class: "ajout-variante", onsubmit: ajouter }, champ,
        el("button", { type: "submit", class: "petit" }, "Ajouter")));
  }));
}

async function charger() {
  vocabulaire = await api("GET", "api/vocabulaire");
  afficher();
}

document.getElementById("form-remplacement").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  if (await modifier("POST", "api/vocabulaire/remplacement", { texte: f.texte.value, par: f.par.value })) {
    f.reset();
    f.texte.focus();
  }
});

document.getElementById("form-mot").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  if (await modifier("POST", "api/vocabulaire/mot", { mot: f.mot.value })) {
    f.reset();
    f.mot.focus();
  }
});

document.getElementById("form-rubrique").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  if (await modifier("POST", "api/vocabulaire/rubrique", { titre: f.titre.value })) f.reset();
});

document.getElementById("filtre-remplacements").addEventListener("input", afficherRemplacements);
document.getElementById("filtre-mots").addEventListener("input", afficherMots);

charger().catch((e) => notifier(e.message, { type: "erreur" }));
