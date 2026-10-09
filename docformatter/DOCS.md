# DocFormatter

Mise en forme des comptes rendus médicaux par copier-coller depuis Word, sans IA et sans service
externe : tout le traitement a lieu sur votre serveur Home Assistant.

## Ce que fait l'outil

Le texte du compte rendu est copié dans Word, collé dans l'outil, corrigé, puis recollé dans le
document d'origine. Les en-têtes, pieds de page et la mise en page du document ne quittent jamais Word.

1. **Rubriques** : renomme les libellés de rubrique écrits autrement (« ATCD : » → « Antécédents : »,
   « ttt habituel : » → « Traitement habituel : »), en gardant leur mise en forme (gras, souligné…).
2. **Nettoyage** : espaces en trop, typographie française (espaces insécables, guillemets « »),
   unités (`75mg` → `75 mg`), majuscule en début de paragraphe… via des règles modifiables.
3. **Corrections connues** : remplace automatiquement une liste de fautes fréquentes.
4. **Résultats d'analyse sur plusieurs colonnes** : au moins 4 lignes consécutives de type
   « Hb (g/dL) : 13,4 » sont placées sur 2 colonnes (tableau sans bordure) pour gagner de la
   hauteur de page. Désactivable dans « Mise en forme » ; nombre de colonnes, minimum et motif dans les règles (`colonnes`).
5. **Orthographe** : Hunspell (fr_FR) + votre dictionnaire médical. Les mots inconnus sont
   **surlignés en jaune, jamais corrigés automatiquement** ; des suggestions sont proposées.

Les chiffres et posologies ne sont jamais modifiés, seulement espacés.

## Utilisation au quotidien

L'outil s'ouvre dans la barre latérale de Home Assistant (« Comptes rendus ») :

- **Formater** : dans Word, sélectionner le texte du compte rendu et le copier (`Ctrl+C`), puis le
  coller (`Ctrl+V`) dans le cadre de la page. Le résultat montre l'aperçu, le détail des corrections
  et les mots inconnus : pour chacun, choisir « Le mot est correct » ou « Remplacer par… », puis
  « Enregistrer mes choix et reformater ». L'outil s'en souviendra pour les prochains comptes rendus.
- **Copier pour Word** (sur le résultat ou dans l'éditeur), puis `Ctrl+V` dans Word, à la place du
  texte d'origine toujours sélectionné : gras, italique, souligné, alignements, retraits,
  espacements, police, taille et tableaux sont repris. Les listes Word sont recollées comme des
  paragraphes commençant par un tiret (ou leur numéro), avec le même retrait ; les images et les
  liens ne sont pas repris (ne pas les inclure dans la sélection). « Télécharger » donne aussi le
  texte corrigé en .docx.
- **Retoucher** : modifier le texte déjà corrigé — gras, italique, souligné, ajouter, déplacer ou
  supprimer un paragraphe ou une ligne vide, remplacer un mot signalé. Les corrections automatiques
  ne sont jamais réappliquées sur un texte retouché.
- **Vocabulaire** : remplacements automatiques (fautes, abréviations), mots connus, rubriques et
  leurs différentes écritures. Chaque modification est enregistrée immédiatement.
- **Mise en forme** : interrupteurs pour activer ou désactiver chaque correction, avec un exemple.
- **Historique** : toutes les modifications, avec leur date et leur auteur ; on peut revenir à
  n'importe quel état précédent. Chaque modification propose aussi un bouton « Annuler » immédiat.
- **Expert** : création de règles avancées (expressions régulières), testeur, import/export des règles.

## Configuration

| Option | Description |
| --- | --- |
| `acces_direct` | Autorise l'accès sans passer par Home Assistant (voir « Accès direct par un sous-domaine »). |
| `utilisateurs` | Identifiants et mots de passe (10 caractères minimum) pour l'accès direct. |

## Fichiers et sécurité des règles

Dans `/addon_configs/<id>_docformatter/` (accessible avec l'add-on Samba ou File editor) :

- `regles.yaml` : règles actuelles. Une modification manuelle est prise en compte sans redémarrage ;
- `historique/` : les 100 dernières versions des règles (date, auteur, description) ;
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

Avec nginx, pensez aussi à autoriser des envois suffisamment gros dans le bloc `server` : un long
compte rendu collé avec sa mise en forme peut dépasser la valeur par défaut (1 Mo) :

```nginx
client_max_body_size 25m;
```

## Accès direct par un sous-domaine (proxy nginx)

Pour ouvrir l'outil sur sa propre adresse (ex. `https://cr.mondomaine.fr`) sans passer par
l'interface Home Assistant :

1. Dans la configuration de l'add-on, activer `acces_direct` et créer au moins un utilisateur.
   Une page de connexion protège alors cet accès ; après 5 échecs, une adresse IP est bloquée
   15 minutes. La session dure 12 heures. Changer un mot de passe déconnecte ce compte partout.
2. Dans l'add-on « NGINX Home Assistant SSL proxy » (ou équivalent), pointer vers le port **8099**
   de l'add-on. Son nom d'hôte est `<id>-docformatter`, où `<id>` est le préfixe visible dans
   l'URL de la page de l'add-on (ex. `cfbf20f4`) :

   ```nginx
   server {
       listen 443 ssl;
       server_name cr.mondomaine.fr;

       ssl_certificate     /ssl/fullchain.pem;
       ssl_certificate_key /ssl/privkey.pem;
       ssl_protocols TLSv1.2 TLSv1.3;

       client_max_body_size 25M;

       # DNS interne du Supervisor : l'IP de l'add-on change quand il est recréé
       resolver 172.30.32.3 valid=30s ipv6=off;

       location / {
           set $docformatter http://cfbf20f4-docformatter:8099;
           proxy_pass $docformatter;
           proxy_http_version 1.1;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   ```

   `X-Real-IP` sert au blocage des tentatives répétées, `X-Forwarded-Proto` à sécuriser le cookie
   de session (HTTPS uniquement). Inutile d'ouvrir un port dans l'onglet « Réseau » de l'add-on :
   nginx le joint par le réseau interne de Home Assistant.

L'accès par la barre latérale de Home Assistant continue de fonctionner en parallèle.

## Confidentialité

Le texte collé est traité en mémoire. Le résultat reste disponible pendant une heure pour
l'utilisateur qui l'a produit, puis il est effacé ; rien n'est écrit sur disque.
