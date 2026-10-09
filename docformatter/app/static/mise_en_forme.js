"use strict";

document.querySelectorAll(".interrupteur input").forEach((caseACocher) => {
  caseACocher.addEventListener("change", async () => {
    const { type, index, nom, cle } = caseACocher.dataset;
    const actif = caseACocher.checked;
    const libelle = caseACocher.closest("label").querySelector("strong").textContent;
    try {
      const r = type === "regle"
        ? await api("POST", "api/mise-en-forme/regle", { index: Number(index), nom, actif })
        : await api("POST", "api/mise-en-forme/option", { cle, actif });
      notifier(`« ${libelle} » ${actif ? "activé" : "désactivé"}.`, { annulation: r.annulation });
    } catch (e) {
      caseACocher.checked = !actif;
      notifier(e.message, { type: "erreur" });
    }
  });
});
