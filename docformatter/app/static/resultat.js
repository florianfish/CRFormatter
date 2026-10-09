"use strict";

// Saisir un remplacement coche automatiquement « Remplacer par ».
document.querySelectorAll(".mot .remplacer input[type=text]").forEach((champ) => {
  const radio = champ.closest("label").querySelector("input[type=radio]");
  ["input", "focus"].forEach((t) => champ.addEventListener(t, () => { radio.checked = true; }));
});

const annuler = document.getElementById("annuler-decisions");
if (annuler) {
  annuler.addEventListener("click", async () => {
    try {
      await api("POST", "api/historique/restaurer", { id: annuler.closest("[data-annulation]").dataset.annulation, annulation: true });
      location.reload();
    } catch (e) {
      notifier(e.message, { type: "erreur" });
    }
  });
}
