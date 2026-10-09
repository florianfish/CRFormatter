## 0.5.0

- Accès direct facultatif sans passer par Home Assistant (ex. sous-domaine via nginx, port 8099),
  protégé par une page de connexion (options `acces_direct` et `utilisateurs`).

## 0.4.0

- Éditeur de retouche : modifier le document après les corrections automatiques (texte, titres,
  listes, tableaux, mots signalés, gras / italique / souligné), puis télécharger le .docx
  régénéré avec le modèle Word.

## 0.3.0

- Le mode expert est accessible à tous les utilisateurs du panneau ; l'option `experts` est supprimée.
- Documentation : comment sécuriser l'accès à Home Assistant (compte dédié, double authentification,
  bannissement des tentatives, VPN).

## 0.2.0

- Interface pensée pour une utilisation non technique : pages Vocabulaire, Mise en forme et Historique.
- Choix sur les mots inconnus directement depuis le résultat, puis reformatage immédiat.
- Bouton « Annuler » après chaque modification ; historique complet avec retour à un état précédent.
- Les règles regex, le modèle Word et l'import/export passent en mode expert (option `experts`,
  qui remplace `admins`).
- Un fichier de règles invalide n'empêche plus l'outil de fonctionner ; les modifications manuelles
  du fichier sont prises en compte sans redémarrage.

## 0.1.0

- Première version : formatage, règles éditables, vérification orthographique Hunspell, dossier surveillé.
