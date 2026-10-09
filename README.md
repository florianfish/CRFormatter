# DocFormatter

Add-on Home Assistant de mise en forme des comptes rendus médicaux (.docx), sans IA.
Documentation utilisateur : [docformatter/DOCS.md](docformatter/DOCS.md).

## Installation dans Home Assistant

1. À chaque push sur `main`, la GitHub Action lance les tests puis publie les images `amd64` et
   `aarch64` sur `ghcr.io/florianfish/docformatter-<arch>` (publiques, comme le dépôt).
2. Home Assistant télécharge l'image correspondant à la `version` de `docformatter/config.yaml` :
   attendre la fin de l'action avant de mettre à jour l'add-on. Pour tester une modification sans
   publier, commenter la ligne `image:` : le Supervisor construit alors l'image sur la Khadas.
3. Dans HA : Paramètres › Modules complémentaires › Boutique › ⋮ › Dépôts → ajouter
   `https://github.com/florianfish/CRFormatter`.
4. Installer et démarrer **DocFormatter** : « Comptes rendus » apparaît dans la barre latérale.
5. Sécuriser l'accès : voir la section « Sécuriser l'accès » de [DOCS.md](docformatter/DOCS.md).

Pour publier une nouvelle version : incrémenter `version` dans `docformatter/config.yaml`
(et `CHANGELOG.md`), puis pousser sur `main`.

## Développement local

| Commande | Effet |
| --- | --- |
| `make run` | Serveur local avec rechargement automatique : http://127.0.0.1:8099 |
| `make docker` | Même chose dans le conteneur de l'add-on (Hunspell inclus, code monté) |
| `make test` | Tests (`make test-docker` : dans le conteneur, avec l'orthographe) |
| `make exemple` | Génère `dev-data/exemples/exemple.docx`, un compte rendu mal formaté |
| `make e2e` | Parcours complet de la secrétaire dans Chrome (formatage, vocabulaire, retouche…) |

`make run` crée le `.venv` au premier lancement. Sans Hunspell sur la machine
(`sudo apt install hunspell hunspell-fr`), l'orthographe est désactivée : utiliser `make docker`.

Variables utiles :

```bash
make run DEV_USER=secretaire              # simuler un autre utilisateur HA
make run SURVEILLE=1                    # dossier surveillé dev-data/share/entree → sortie
make run PORT=8100
```

Les règles et l'historique de développement sont dans `dev-data/config/`
(ignoré par git) ; supprimer `dev-data/config/regles.yaml` repart des règles par défaut.

En mode développement, l'authentification est désactivée et le serveur n'écoute que sur
127.0.0.1 : ne jamais activer `DOCFORMATTER_DEV=1` ailleurs qu'en local.

## Architecture

```
docformatter/
├── config.yaml, build.yaml, Dockerfile   add-on HA (Ingress, port 8099)
├── defaults/regles.yaml                  règles copiées au premier démarrage
└── app/
    ├── pipeline/
    │   ├── reader.py     .docx → blocs reliés à leurs paragraphes Word (lien, champ → protégé)
    │   ├── sections.py   renommage des rubriques sur place
    │   ├── cleaner.py    regex, corrections connues, majuscules
    │   ├── spelling.py   Hunspell (mode pipe), mots inconnus + suggestions
    │   └── writer.py     réécriture sur place des seuls paragraphes modifiés
    ├── rules.py          modèle des règles (validation pydantic), lecture/écriture YAML
    ├── store.py          stockage des règles : historique, annulation, réparation d'un fichier invalide
    ├── vocabulaire.py    opérations simples de la secrétaire (mots, remplacements, rubriques…)
    ├── retouche.py       éditeur de retouche : format échangé, conversion vers les blocs
    ├── web.py            FastAPI : formatage, vocabulaire, mise en forme, historique, mode expert
    ├── watcher.py        dossier surveillé /share/docformatter
    └── templates/, static/
```

Sécurité : en production, l'application n'accepte que les connexions du proxy Ingress du Supervisor
(`172.30.32.2`) et identifie l'utilisateur via l'en-tête `X-Remote-User-Name` ajouté par HA.
Tout utilisateur HA ayant accès au panneau a accès à toutes les pages, mode expert compris :
l'authentification est entièrement déléguée à Home Assistant.
