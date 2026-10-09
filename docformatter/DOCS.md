# DocFormatter

Mise en forme des comptes rendus médicaux Word (.docx), sans IA et sans service externe :
tout le traitement a lieu sur votre serveur Home Assistant.

## Ce que fait l'outil

Le document est corrigé **sur place** : en-têtes et pieds de page (y compris ceux de la première
page), marges, colonnes, styles, alignements, liens et champs automatiques sont conservés à l'identique.
Seul le texte des paragraphes du corps est corrigé.

1. **Rubriques** : renomme les libellés de rubrique écrits autrement (« ATCD : » → « Antécédents : »,
   « ttt habituel : » → « Traitement habituel : »), en gardant leur mise en forme (gras, souligné…).
2. **Nettoyage** : espaces en trop, typographie française (espaces insécables, guillemets « »),
   unités (`75mg` → `75 mg`), majuscule en début de paragraphe… via des règles modifiables.
3. **Corrections connues** : remplace automatiquement une liste de fautes fréquentes.
4. **Orthographe** : Hunspell (fr_FR) + votre dictionnaire médical. Les mots inconnus sont
   **surlignés en jaune avec un commentaire de suggestions, jamais corrigés automatiquement**.

Les paragraphes contenant un lien, un champ automatique ou une image sont laissés intacts.

Les chiffres et posologies ne sont jamais modifiés, seulement espacés.

## Utilisation au quotidien

L'outil s'ouvre dans la barre latérale de Home Assistant (« Comptes rendus ») :

- **Formater** : déposer un ou plusieurs .docx, puis télécharger le résultat. Les mots inconnus
  sont listés en haut : pour chacun, choisir « Le mot est correct » ou « Remplacer par… », puis
  « Enregistrer mes choix et reformater ». L'outil s'en souviendra pour les prochains documents.
- **Retoucher** (bouton sur chaque document du résultat) : modifier le texte déjà corrigé — gras,
  italique, souligné, ajouter, déplacer ou supprimer un paragraphe, remplacer un mot signalé.
  L'éditeur montre le corps du document ; en-têtes, pieds de page et mise en page sont conservés
  dans le .docx produit. Les corrections automatiques ne sont jamais réappliquées sur un document retouché.
- **Vocabulaire** : remplacements automatiques (fautes, abréviations), mots connus, rubriques et
  leurs différentes écritures. Chaque modification est enregistrée immédiatement.
- **Mise en forme** : interrupteurs pour activer ou désactiver chaque correction, avec un exemple.
- **Historique** : toutes les modifications, avec leur date et leur auteur ; on peut revenir à
  n'importe quel état précédent. Chaque modification propose aussi un bouton « Annuler » immédiat.
- **Expert** : création de règles avancées (expressions régulières), testeur, import/export des règles.

## Configuration

| Option | Description |
| --- | --- |
| `dossier_surveille` | Active le traitement automatique de `/share/docformatter/entree` → `/share/docformatter/sortie`. |
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

Avec nginx, pensez aussi à autoriser des envois de fichiers suffisamment gros dans le bloc `server`
(la valeur par défaut, 1 Mo, est trop faible) :

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

Les documents envoyés depuis l'interface sont traités en mémoire. Le résultat reste téléchargeable
pendant une heure par l'utilisateur qui l'a produit, puis il est effacé ; rien n'est écrit sur disque.
Avec le dossier surveillé, en revanche, les fichiers restent dans `/share/docformatter` jusqu'à ce que
vous les supprimiez.
