"use strict";

let version = null;
let regles = [];      // règles regex en cours d'édition
let reference = null; // dernière version enregistrée (JSON) pour détecter les modifications

function charger(donnees) {
  version = donnees.version;
  regles = donnees.remplacements;
  reference = JSON.stringify(regles);
  afficherRegles();
  majEtat();
}

function majEtat() {
  const modifie = JSON.stringify(regles) !== reference;
  document.getElementById("enregistrer").disabled = !modifie;
  document.getElementById("annuler").disabled = !modifie;
  document.getElementById("etat").textContent = modifie ? "Modifications non enregistrées" : "";
  return modifie;
}

// ---- Édition des règles ---------------------------------------------------------------

const delais = new WeakMap();

function testerRegle(regle, sortie) {
  clearTimeout(delais.get(sortie));
  if (!regle.exemple) { sortie.replaceChildren(); return; }
  delais.set(sortie, setTimeout(async () => {
    try {
      const r = await api("POST", "expert/api/tester-regle", {
        motif: regle.motif, remplacement: regle.remplacement,
        ignorer_casse: regle.ignorer_casse, exemple: regle.exemple,
      });
      if (r.erreur) {
        sortie.className = "test-regle erreur";
        sortie.replaceChildren(r.erreur);
      } else {
        sortie.className = "test-regle";
        const diff = el("span");
        diff.innerHTML = r.diff; // HTML échappé côté serveur (apercu.diff_html)
        sortie.replaceChildren(
          el("span", { class: "occurrences" }, r.occurrences ? `${r.occurrences} remplacement(s) → ` : "Aucune correspondance → "),
          diff);
      }
    } catch (e) {
      sortie.replaceChildren(e.message);
    }
  }, 300));
}

function champ(regle, cle, libelle, { apresSaisie, ...attrs } = {}) {
  return el("label", { class: "champ" }, libelle,
    el("input", { type: "text", value: regle[cle] ?? "", spellcheck: false, ...attrs,
      oninput: (e) => { regle[cle] = e.target.value; apresSaisie?.(); majEtat(); } }));
}

function afficherRegles() {
  document.getElementById("liste-regles").replaceChildren(...regles.map((regle, i) => {
    const sortie = el("div", { class: "test-regle" });
    const tester = () => testerRegle(regle, sortie);
    const deplacer = (delta) => {
      const j = i + delta;
      if (j < 0 || j >= regles.length) return;
      [regles[i], regles[j]] = [regles[j], regles[i]];
      afficherRegles();
      majEtat();
    };
    const carte = el("div", { class: `regle ${regle.actif ? "" : "inactive"}` },
      el("div", { class: "ligne" },
        el("span", { class: "numero" }, `${i + 1}`),
        el("label", { class: "case", title: "Active" },
          el("input", { type: "checkbox", checked: regle.actif,
            onchange: (e) => { regle.actif = e.target.checked; carte.classList.toggle("inactive", !regle.actif); majEtat(); } })),
        el("input", { type: "text", class: "nom", value: regle.nom, placeholder: "Nom affiché à la secrétaire",
          oninput: (e) => { regle.nom = e.target.value; majEtat(); } }),
        el("button", { type: "button", class: "petit", title: "Monter", onclick: () => deplacer(-1) }, "↑"),
        el("button", { type: "button", class: "petit", title: "Descendre", onclick: () => deplacer(1) }, "↓"),
        el("button", { type: "button", class: "petit danger", title: "Supprimer",
          onclick: () => {
            if (!confirm(`Supprimer la règle « ${regle.nom} » ?`)) return;
            regles.splice(i, 1);
            afficherRegles();
            majEtat();
          } }, "Supprimer")),
      el("div", { class: "ligne" }, champ(regle, "description", "Description (langage courant)")),
      el("div", { class: "ligne" },
        champ(regle, "motif", "Motif", { class: "code", apresSaisie: tester }),
        champ(regle, "remplacement", "Remplacement", { class: "code", apresSaisie: tester }),
        el("label", { class: "case" },
          el("input", { type: "checkbox", checked: regle.ignorer_casse,
            onchange: (e) => { regle.ignorer_casse = e.target.checked; tester(); majEtat(); } }),
          "Ignorer la casse")),
      el("div", { class: "ligne" }, champ(regle, "exemple", "Exemple", { apresSaisie: tester })),
      sortie);
    tester();
    return carte;
  }));
}

// ---- Événements -----------------------------------------------------------------------

document.querySelectorAll(".onglets button").forEach((bouton) => {
  bouton.addEventListener("click", () => {
    document.querySelectorAll(".onglets button").forEach((b) => b.classList.toggle("actif", b === bouton));
    document.querySelectorAll(".onglet").forEach((s) => { s.hidden = s.id !== `onglet-${bouton.dataset.onglet}`; });
  });
});

document.getElementById("ajout-regle").addEventListener("click", () => {
  regles.push({ nom: "Nouvelle règle", description: "", motif: "", remplacement: "",
    ignorer_casse: false, actif: true, exemple: "" });
  afficherRegles();
  majEtat();
  document.querySelector("#liste-regles .regle:last-child .nom").select();
});

document.getElementById("enregistrer").addEventListener("click", async () => {
  try {
    charger(await api("PUT", "expert/api/remplacements", { version, remplacements: regles }));
    notifier("Règles enregistrées. Elles s'appliquent aux prochains documents.");
  } catch (e) {
    notifier(e.message, { type: "erreur" });
  }
});

document.getElementById("annuler").addEventListener("click", async () => {
  if (confirm("Abandonner les modifications non enregistrées ?")) charger(await api("GET", "expert/api/remplacements"));
});

document.getElementById("lancer-test").addEventListener("click", async () => {
  const sortie = document.getElementById("resultat-test");
  try {
    const r = await api("POST", "expert/api/tester", {
      remplacements: regles, texte: document.getElementById("texte-test").value,
    });
    if (r.erreur) { sortie.replaceChildren(el("p", { class: "erreur" }, r.erreur)); return; }
    const apercu = el("div", { class: "apercu" });
    apercu.innerHTML = r.html; // HTML échappé côté serveur (apercu.rendre_blocs)
    sortie.replaceChildren(
      el("p", { class: "legende" }, "Résultat — ",
        `${r.changements.length} modification(s), ${r.inconnus.length} mot(s) inconnu(s)`,
        r.inconnus.length ? ` : ${r.inconnus.map(([m]) => m).join(", ")}` : ""),
      apercu,
      el("details", {}, el("summary", {}, "Règles appliquées"),
        el("ul", {}, r.changements.map((c) => el("li", {}, `${c.regle} : « ${c.avant} » → « ${c.apres} »`)))));
  } catch (e) {
    sortie.replaceChildren(el("p", { class: "erreur" }, e.message));
  }
});

document.getElementById("import").addEventListener("change", async (e) => {
  const fichier = e.target.files[0];
  e.target.value = "";
  if (!fichier || !confirm("L'import remplace toutes les règles, vocabulaire compris. Continuer ?")) return;
  const fd = new FormData();
  fd.append("fichier", fichier);
  try {
    await api("POST", "expert/import", fd);
    charger(await api("GET", "expert/api/remplacements"));
    notifier("Règles importées (annulable depuis l'historique).");
  } catch (err) {
    notifier(err.message, { type: "erreur" });
  }
});

document.getElementById("modele").addEventListener("change", async (e) => {
  const fichier = e.target.files[0];
  e.target.value = "";
  if (!fichier) return;
  const fd = new FormData();
  fd.append("fichier", fichier);
  try {
    await api("POST", "expert/modele", fd);
    document.getElementById("modele-actuel").textContent = "personnalisé";
    notifier("Modèle enregistré.");
  } catch (err) {
    notifier(err.message, { type: "erreur" });
  }
});

document.getElementById("modele-defaut").addEventListener("click", async () => {
  if (!confirm("Supprimer le modèle personnalisé et revenir au modèle par défaut ?")) return;
  await api("DELETE", "expert/modele");
  document.getElementById("modele-actuel").textContent = "par défaut";
  notifier("Modèle par défaut rétabli.");
});

window.addEventListener("beforeunload", (e) => {
  if (reference !== null && majEtat()) e.preventDefault();
});

api("GET", "expert/api/remplacements").then(charger).catch((e) => notifier(e.message, { type: "erreur" }));
