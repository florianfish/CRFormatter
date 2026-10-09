"use strict";

// Collage depuis Word (lecture : collage.js)
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
