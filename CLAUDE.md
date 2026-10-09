# CLAUDE.md

Add-on Home Assistant (aarch64 Khadas + amd64) qui reformate des comptes rendus médicaux
**sans IA** : règles regex éditables, Hunspell. **Uniquement par copier-coller** : le texte copié dans
Word est collé dans l'outil, corrigé, puis recollé dans Word (« Copier pour Word ») ; il n'y a ni dépôt
de fichier ni dossier surveillé (retirés en 0.7.0). Interface servie via Ingress HA, HA étant exposé
derrière un proxy nginx.

## Commandes

```bash
make run            # serveur dev, rechargement auto, http://127.0.0.1:8099 (pas de Hunspell en local)
make docker         # idem dans le conteneur de l'add-on, avec Hunspell
make test           # pytest (le test d'orthographe est sauté sans Hunspell)
make test-docker    # pytest dans l'image : à lancer avant de conclure sur l'orthographe
make exemple        # dev-data/exemples/exemple.{docx,html} : compte rendu mal formaté (Word / presse-papiers)
make e2e            # parcours complet dans Chrome (Playwright) : à lancer après toute modif d'interface
```

Un seul test : `cd docformatter && ../.venv/bin/pytest tests/test_pipeline.py -k sections`.

## Architecture

Le texte collé est d'abord converti en .docx (`collage.py`), puis traité comme un document :
`colonnes` (résultats d'analyse déplacés dans un tableau sans
bordure, sur le .docx lui-même) → `reader` (docx → `Bloc`) → `sections` (renommage des rubriques) →
`cleaner` (regex, corrections, majuscules) → `spelling` (Hunspell) → `writer` (réécriture sur place).

Le traitement interne reste « sur place » (hérité du dépôt de .docx, il garde le .docx téléchargé
fidèle au collage) : chaque `Bloc` porte l'identifiant (`source`) de son élément Word
(`p12`, `t3`, `t3.0.1.0` pour un paragraphe de cellule, cf. `reader.indexer`) ; `writer.ecrire_docx`
rouvre l'original, ne réécrit que les paragraphes `modifie()` ou annotés (les autres restent
identiques à l'octet), puis reconstruit l'ordre du corps (paragraphes ajoutés / supprimés /
déplacés dans l'éditeur). Paragraphe contenant lien, champ, image, révision… → `protege` : jamais
réécrit. Paragraphe portant un `sectPr` → `fin_section` : ni supprimé ni fusionné.
Le texte est manipulé avec sa mise en forme via `TexteStyle` (positions par caractère) ;
`Format.rpr` garde les propriétés Word d'origine (police, taille…).
Orchestration dans `docformatter/app/pipeline/__init__.py`. Les identifiants se rapportent au
document après `colonnes` (`Resultat.base`, gardé dans `Lot.bases`) : une retouche est toujours
réécrite sur cette base, même si les règles changent ensuite. Le testeur du mode expert passe par
`traiter_texte`, sans docx.

- `rules.py` : modèle pydantic `Regles` ; c'est la seule source de validation (API, import YAML,
  fichier).
- `store.py` : `RulesStore`. **Toute écriture passe par `modifier()`**, ce qui garantit validation,
  écriture atomique, instantané dans `historique/` (auteur + description lisible) et vérification
  de version (HTTP 409). Un fichier invalide est mis de côté et la dernière version valide est rétablie.
- `retouche.py` + `static/retouche.js` : éditeur de retouche. Un document retouché est stocké dans
  `Lot.retouches` et passe par `finaliser_retouche` (orthographe + écriture) : **aucune règle
  automatique n'est réappliquée sur une saisie manuelle**, même si le vocabulaire change.
  Seul un remplacement choisi explicitement depuis la page de résultat y est appliqué.
  Gras / italique / souligné : `Bloc.formats` (plages sur le texte brut, pour que l'orthographe et
  les remplacements restent du texte simple) ; `Bloc.troncons()` les combine aux mots inconnus pour
  l'écriture Word et l'aperçu. L'éditeur échange des *segments* (`retouche.py`).
- `collage.py` + `static/collage.js` : compte rendu collé depuis Word. Le navigateur lit le HTML du
  presse-papiers dans une iframe isolée (styles calculés : Word met police et espacements dans
  une feuille de style), le serveur en fait un .docx qui suit le traitement normal (page de résultat,
  retouche). « Copier pour Word » (`static/word.js`, résultat et éditeur) produit le HTML inverse à partir de
  `Bloc.mise_en_page` (points, cf. `reader.lire_mise_en_page`) via l'événement `copy`, qui
  fonctionne hors HTTPS (contrairement à `navigator.clipboard`).
- `medicaments.py` : noms de médicaments (`defaults/medicaments.txt`, extrait de la base publique de
  l'ANSM par `make medicaments` ; fichier généré, à ne pas modifier à la main). Mots connus pour
  l'orthographe (option `medicaments`), suggestions par ressemblance (`spelling`) et propositions
  pendant la frappe (`api/proposer`, `proposerPendantLaFrappe` dans `commun.js`). Les conditions de
  la base imposent de citer la source et la date : en-tête du fichier, DOCS.md, CHANGELOG.
- `vocabulaire.py` : opérations de la secrétaire ; chacune valide sa saisie avec un message
  compréhensible (`RegleInvalide`, HTTP 422) et fournit la phrase affichée dans l'historique.
- `web.py` : fabrique `creer_app(settings)` ; les tests construisent l'app avec un `Settings` temporaire.
- `defaults/regles.yaml` est copié dans `/config/regles.yaml` **uniquement au premier démarrage** :
  le modifier ne change pas une installation existante.

## Deux usages

- **La secrétaire** (non technique) : Formater, Vocabulaire, Mise en forme,
  Historique. Aucun jargon (pas de « regex », « YAML », « casse »), messages d'erreur en langage courant,
  enregistrement immédiat et bouton « Annuler » après chaque action.
- **Le mode expert** (accessible à tous, séparé pour ne pas encombrer) : règles regex, testeur,
  import/export. Le nom, la description et l'exemple d'une règle regex sont affichés
  sur la page « Mise en forme » : les rédiger sans jargon.

## Règles métier à respecter

- **Ne jamais corriger automatiquement un mot inconnu** : on le surligne et on ajoute un commentaire
  Word avec les suggestions. Seule la liste `corrections` (« Remplacements automatiques »), choisie par un humain, remplace des mots.
- **Ne jamais modifier les chiffres ni les posologies** : on ne fait que les espacer. Les mots qui
  contiennent des chiffres sont exclus des corrections et de l'orthographe.
- Ce qui relève du métier (vocabulaire, sections, typographie) va dans les **règles YAML**, pas dans
  le code. N'ajoutez du code que pour un nouveau *type* de règle.
- Les comptes rendus collés restent en mémoire (`Depot`, 1 h, accessibles seulement par
  leur propriétaire) et ne sont jamais écrits sur disque.

## Sécurité (Ingress)

- Deux entrées. **Ingress** : requêtes venant de `172.30.32.2` (proxy du Supervisor), déjà
  authentifiées par HA. **Accès direct** (option `acces_direct`, ex. nginx sur un sous-domaine) :
  connexion obligatoire (`auth.py` : cookie signé HMAC dépendant du mot de passe, blocage après
  5 échecs par `X-Real-IP`) ; les en-têtes Ingress envoyés par le client y sont ignorés. Toute
  autre requête est refusée. L'utilisateur vient de l'en-tête `X-Remote-User-Name` (historique, propriété
  des documents en mémoire) ; il n'y a pas de rôles, l'authentification est celle de HA. Garder `proxy_headers=False` dans uvicorn, sinon l'IP peut être usurpée.
- `DOCFORMATTER_DEV=1` désactive l'authentification. Ce mode est réservé au développement local.
- Côté JS, insérer le texte via `el()` / `textContent`. `innerHTML` n'est utilisé que pour du HTML
  déjà échappé côté serveur (`apercu.py`).

## Pièges connus

- **URLs relatives obligatoires** dans les gabarits et le JS (`api/vocabulaire`, pas `/api/vocabulaire`) :
  l'app est servie sous un préfixe Ingress, injecté dans `<base href>` à partir de `X-Ingress-Path`.
- **Espaces insécables** : écrivez `\u00a0` / `\u202f` sous forme d'échappements, jamais le caractère
  brut (l'outil Write les convertit en caractères invisibles). Dans le champ `remplacement` d'une
  règle, utilisez `{nbsp}` / `{nnbsp}` : `re.sub` n'interprète pas `\u`.
- Hunspell fr compte « . » parmi les caractères de mot (« dispnée. ») : le mot est nettoyé dans
  `spelling._analyser`. Le mot est relocalisé dans le texte avec `find` plutôt qu'avec l'offset Hunspell.
- Une clé YAML qui contient `: ` doit être entre guillemets (ex. `'Espace insécable avant : ; ! ?'`).
- Ne jamais ajouter de vrai document de patient au dépôt (public) : `.gitignore` exclut les `.docx`
  à la racine ; les tests utilisent `tests/fabrique.py` (courrier fictif de même structure).
- Vérification visuelle : convertir en PDF avec LibreOffice (image Docker locale, voir l'historique
  du projet) et comparer les pages de l'original et du résultat.

## Conventions

- Code, identifiants, messages et documentation **en français** (`regles`, `Bloc`, `formater`…).
- Python 3.12, FastAPI, Jinja2, JS vanilla sans build ni CDN (l'outil doit fonctionner hors ligne).
- Pour publier : incrémenter `version` dans `docformatter/config.yaml` et `CHANGELOG.md`, puis pousser
  sur `main` (la GitHub Action construit `ghcr.io/<compte>/docformatter-{amd64,aarch64}`).
- Le CHANGELOG est affiché dans l'application (bouton de version, `app/version.py`, Markdown limité
  aux titres, listes, **gras** et `code`) : le rédiger pour la secrétaire, sans jargon.
- Les règles par défaut doivent rester couvertes par `test_exemples_des_regles` : toute nouvelle règle
  par défaut a un `exemple` et un résultat attendu dans ce test.
