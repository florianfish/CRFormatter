## 0.6.0

- **Résultats d'analyse sur plusieurs colonnes** : les lignes « Hb (g/dL) : 13,4 » consécutives
  sont regroupées sur 2 colonnes (tableau sans bordure), y compris après un copier-coller.
- Éditeur : `Suppr` en fin de ligne rattache la ligne suivante ; lignes ajoutées, supprimées ou
  fusionnées aussi dans les cellules de tableau (colonnes de résultats).
- **Coller un compte rendu depuis Word** : le texte copié dans Word est corrigé puis ouvert dans
  l'éditeur ; « Copier pour Word » le recolle dans le document d'origine avec sa mise en forme
  (gras, italique, souligné, alignement, retraits, espacements, police, taille, tableaux).
- **Correction sur place** : le document d'origine est conservé (en-têtes et pieds de page de chaque
  page, marges, colonnes, styles, liens, champs) ; seul le texte des paragraphes est corrigé.
- Les rubriques sont renommées sur place (« ATCD : » → « Antécédents : ») en gardant leur mise en forme.
- L'éditeur de retouche travaille sur les paragraphes du document réel ; les paragraphes contenant
  un lien ou un champ automatique sont protégés.
- Suppression du « modèle Word » (devenu inutile) et de l'option « Détecter les titres ».
- Nouvelle règle « Espace après les deux-points » ; correction des mots collés à un tiret de liste.

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
