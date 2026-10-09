# DocFormatter

Mise en forme des comptes rendus médicaux Word (.docx), sans IA et sans service externe :
tout le traitement a lieu sur votre serveur Home Assistant.

## Ce que fait l'outil

1. **Structure** : reconnaît les titres de section (« ATCD : », « ttt habituel », « EXAMEN CLINIQUE »…)
   et les remplace par un titre normalisé ; transforme les lignes « - … » en vraies listes à puces.
2. **Nettoyage** : espaces en trop, typographie française (espaces insécables, guillemets « »),
   unités (`75mg` → `75 mg`), majuscule en début de paragraphe… via des règles modifiables.
3. **Corrections connues** : remplace automatiquement une liste de fautes fréquentes.
4. **Orthographe** : Hunspell (fr_FR) + votre dictionnaire médical. Les mots inconnus sont
   **surlignés en jaune avec un commentaire de suggestions, jamais corrigés automatiquement**.
5. **Mise en page** : le document est réécrit à partir d'un modèle Word (styles, marges, en-tête, logo).

Les chiffres et posologies ne sont jamais modifiés, seulement espacés.

## Utilisation au quotidien

L'outil s'ouvre dans la barre latérale de Home Assistant (« Comptes rendus ») :

- **Formater** : déposer un ou plusieurs .docx, puis télécharger le résultat. Les mots inconnus
  sont listés en haut : pour chacun, choisir « Le mot est correct » ou « Remplacer par… », puis
  « Enregistrer mes choix et reformater ». L'outil s'en souviendra pour les prochains documents.
- **Vocabulaire** : remplacements automatiques (fautes, abréviations), mots connus, rubriques et
  leurs différentes écritures. Chaque modification est enregistrée immédiatement.
- **Mise en forme** : interrupteurs pour activer ou désactiver chaque correction, avec un exemple.
- **Historique** : toutes les modifications, avec leur date et leur auteur ; on peut revenir à
  n'importe quel état précédent. Chaque modification propose aussi un bouton « Annuler » immédiat.
- **Expert** : création de règles avancées (expressions régulières),
  testeur, modèle Word, import/export des règles.

## Configuration

| Option | Description |
| --- | --- |
| `dossier_surveille` | Active le traitement automatique de `/share/docformatter/entree` → `/share/docformatter/sortie`. |

## Fichiers et sécurité des règles

Dans `/addon_configs/<id>_docformatter/` (accessible avec l'add-on Samba ou File editor) :

- `regles.yaml` : règles actuelles. Une modification manuelle est prise en compte sans redémarrage ;
- `historique/` : les 100 dernières versions des règles (date, auteur, description) ;
- `modele.docx` : modèle Word personnalisé (facultatif) ;
- `dictionnaires/` : listes de mots supplémentaires (`.txt` ou `.dic`, un mot par ligne).

Si `regles.yaml` devient invalide (par exemple après une modification manuelle ratée), l'outil
continue de fonctionner : le fichier fautif est renommé `regles.invalide-<date>.yaml`, la dernière
version valide est rétablie et un avertissement s'affiche en haut des pages.

Ce dossier est inclus dans les sauvegardes Home Assistant : configurez-les vers un stockage externe
(NAS, cloud) pour vous protéger d'une panne de la carte SD ou du disque.

## Sécuriser l'accès

L'outil n'ouvre aucun port : il n'est joignable qu'à travers Home Assistant (Ingress), qui exige
d'être connecté. Tout utilisateur HA voyant le panneau « Comptes rendus » a accès à toutes les
pages. Protéger l'outil revient donc à protéger la connexion à Home Assistant.

1. **Un compte dédié pour la secrétaire** (Paramètres › Personnes › Ajouter) : *non administrateur*,
   avec un mot de passe robuste. Elle voit le panneau sans pouvoir toucher au reste de HA.
2. **Double authentification** (code à usage unique, application Authenticator) pour chaque compte :
   Profil › Modules d'authentification multifacteur. C'est la protection la plus efficace contre
   un mot de passe deviné ou volé.
3. **Bannissement des tentatives répétées** dans `configuration.yaml`. Derrière nginx, HA doit
   connaître l'IP réelle des visiteurs, sinon c'est nginx lui-même qui serait banni :

   ```yaml
   http:
     use_x_forwarded_for: true
     trusted_proxies:
       - 172.30.33.0/24   # adapter : adresse ou réseau de votre nginx
     ip_ban_enabled: true
     login_attempts_threshold: 5
   ```

4. **Option « Peut uniquement se connecter depuis le réseau local »** sur un compte qui n'a pas
   besoin d'accès extérieur (Paramètres › Personnes › l'utilisateur).
5. **Encore plus strict** : ne plus exposer HA sur Internet et passer par un VPN (Tailscale ou
   WireGuard, disponibles en add-on). Seuls les appareils inscrits au VPN peuvent alors se connecter.

Avec nginx, pensez aussi à autoriser des envois de fichiers suffisamment gros dans le bloc `server`
(la valeur par défaut, 1 Mo, est trop faible) :

```nginx
client_max_body_size 25m;
```

## Confidentialité

Les documents envoyés depuis l'interface sont traités en mémoire. Le résultat reste téléchargeable
pendant une heure par l'utilisateur qui l'a produit, puis il est effacé ; rien n'est écrit sur disque.
Avec le dossier surveillé, en revanche, les fichiers restent dans `/share/docformatter` jusqu'à ce que
vous les supprimiez.
