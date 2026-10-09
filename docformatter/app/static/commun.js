"use strict";

/** Crée un élément DOM. Le texte passe toujours par textContent (jamais d'injection HTML). */
function el(tag, attrs = {}, ...enfants) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k === "class") e.className = v;
    else if (typeof v === "boolean") e[k] = v;
    else e.setAttribute(k, v);
  }
  for (const enfant of enfants.flat()) {
    if (enfant != null) e.append(enfant instanceof Node ? enfant : document.createTextNode(enfant));
  }
  return e;
}

/** Appel JSON relatif à <base href> (compatible Ingress). Lève une Error avec le message serveur. */
async function api(methode, url, corps) {
  const options = { method: methode, headers: {} };
  if (corps instanceof FormData) options.body = corps;
  else if (corps !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(corps);
  }
  const reponse = await fetch(url, options);
  let donnees = {};
  try { donnees = await reponse.json(); } catch { /* réponse vide */ }
  if (!reponse.ok) throw new Error(donnees.erreur || donnees.detail || `Erreur ${reponse.status}`);
  return donnees;
}

/**
 * Notification en bas de l'écran. Si `annulation` est fourni (identifiant de la version
 * précédente), un bouton « Annuler » permet de revenir en arrière en un clic.
 */
function notifier(texte, { type = "succes", annulation = null, apresAnnulation = () => location.reload() } = {}) {
  const zone = document.getElementById("notification");
  clearTimeout(zone._delai);
  const enfants = [el("span", {}, texte)];
  if (annulation) {
    enfants.push(el("button", { type: "button", onclick: async () => {
      try {
        await api("POST", "api/historique/restaurer", { id: annulation, annulation: true });
        notifier("Modification annulée.");
        apresAnnulation();
      } catch (e) {
        notifier(e.message, { type: "erreur" });
      }
    } }, "Annuler"));
  }
  zone.replaceChildren(...enfants);
  zone.className = `notification ${type}`;
  zone.hidden = false;
  zone._delai = setTimeout(() => { zone.hidden = true; }, annulation ? 10000 : 5000);
}

/**
 * Champ « Remplacer par » : au fil de la frappe, sa liste de suggestions (<datalist>) est complétée
 * par le vocabulaire et les noms de médicaments (« dolip » → « Doliprane »). Les suggestions
 * d'origine (orthographe) restent en tête.
 */
function proposerPendantLaFrappe(champ) {
  let liste = champ.list;
  if (!liste) {
    liste = el("datalist", { id: `propositions-${Math.random().toString(36).slice(2)}` });
    champ.after(liste);
    champ.setAttribute("list", liste.id);
  }
  const initiales = [...liste.options].map((o) => o.value);
  const remplir = (valeurs) => liste.replaceChildren(...[...new Set(valeurs)].map((v) => el("option", { value: v })));
  let delai;
  champ.addEventListener("input", () => {
    clearTimeout(delai);
    const saisie = champ.value.trim();
    if (saisie.length < 2) { remplir(initiales); return; }
    delai = setTimeout(async () => {
      try {
        const r = await api("GET", `api/proposer?q=${encodeURIComponent(saisie)}`);
        if (champ.value.trim() === saisie) remplir([...initiales, ...r.propositions]);
      } catch { /* sans propositions : le champ reste utilisable */ }
    }, 150);
  });
}

// ---- Version et nouveautés ------------------------------------------------------------

(() => {
  const bouton = document.getElementById("ouvrir-nouveautes");
  const fenetre = document.getElementById("nouveautes");
  if (!bouton || !fenetre) return;
  const CLE = "docformatter.version-vue";
  const lire = () => { try { return localStorage.getItem(CLE); } catch { return null; } };
  // Point discret tant que les nouveautés de cette version n'ont pas été consultées (sur ce navigateur)
  bouton.classList.toggle("nouvelle", lire() !== bouton.dataset.version);
  bouton.addEventListener("click", () => {
    fenetre.showModal();
    bouton.classList.remove("nouvelle");
    try { localStorage.setItem(CLE, bouton.dataset.version); } catch { /* navigation privée */ }
  });
  // Clic à côté de la fenêtre : fermeture
  fenetre.addEventListener("click", (e) => { if (e.target === fenetre) fenetre.close(); });
})();
