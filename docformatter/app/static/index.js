"use strict";

const depot = document.getElementById("depot");
const champ = document.getElementById("fichiers");
const selection = document.getElementById("selection");

function afficherSelection() {
  selection.replaceChildren(...[...champ.files].map((f) => el("li", {}, f.name)));
}

champ.addEventListener("change", afficherSelection);
["dragenter", "dragover"].forEach((t) => depot.addEventListener(t, (e) => {
  e.preventDefault();
  depot.classList.add("survol");
}));
["dragleave", "drop"].forEach((t) => depot.addEventListener(t, () => depot.classList.remove("survol")));
depot.addEventListener("drop", (e) => {
  e.preventDefault();
  champ.files = e.dataTransfer.files;
  afficherSelection();
});
document.getElementById("formulaire").addEventListener("submit", () => {
  const bouton = document.getElementById("envoyer");
  bouton.disabled = true;
  bouton.textContent = "Traitement en cours…";
});
