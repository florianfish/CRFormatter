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

// ---- Collage depuis Word ------------------------------------------------------------

const zoneCollage = document.getElementById("zone-collage");
// Le cadre n'accepte que le collage : la frappe directe n'y a pas de sens
zoneCollage.addEventListener("beforeinput", (e) => e.preventDefault());
zoneCollage.addEventListener("drop", (e) => e.preventDefault());
zoneCollage.addEventListener("paste", async (e) => {
  e.preventDefault();
  if (zoneCollage.classList.contains("en-cours")) return;
  zoneCollage.classList.add("en-cours");
  zoneCollage.dataset.attente = "Correction en cours…";
  try {
    const blocs = await lireCollage(e.clipboardData);
    const r = await api("POST", "api/coller", { blocs });
    location.href = r.adresse;
  } catch (erreur) {
    notifier(erreur.message, { type: "erreur" });
    zoneCollage.classList.remove("en-cours");
    zoneCollage.dataset.attente = "Collez ici le compte rendu (Ctrl+V)";
  }
});
