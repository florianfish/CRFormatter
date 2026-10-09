"use strict";

// Saisir un remplacement coche automatiquement « Remplacer par » ; noms proposés pendant la frappe.
document.querySelectorAll(".mot .remplacer input[type=text]").forEach((champ) => {
  const radio = champ.closest("label").querySelector("input[type=radio]");
  ["input", "focus"].forEach((t) => champ.addEventListener(t, () => { radio.checked = true; }));
  proposerPendantLaFrappe(champ);
});

// Compte rendu collé : retour dans Word sans passer par la retouche
document.querySelectorAll("button.copier").forEach((bouton) => {
  bouton.addEventListener("click", () => {
    copierPourWord(JSON.parse(document.getElementById(`blocs-${bouton.dataset.document}`).textContent));
  });
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
