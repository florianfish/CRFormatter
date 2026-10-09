# DocFormatter

Add-on Home Assistant de mise en forme des comptes rendus médicaux (.docx), sans IA.
Documentation utilisateur : [docformatter/DOCS.md](docformatter/DOCS.md).

## Installation dans Home Assistant

1. À chaque push sur `main`, la GitHub Action lance les tests puis publie les images `amd64` et
   `aarch64` sur `ghcr.io/florianfish/docformatter-<arch>`. Après la première publication, rendre
   ces deux paquets **publics** (GitHub › Packages › Package settings) pour que Home Assistant
   puisse les télécharger.
2. Décommenter la ligne `image:` de `docformatter/config.yaml`. Tant qu'elle est commentée, le
   Supervisor construit l'image directement sur la Khadas : c'est plus lent mais pratique pour tester.
3. Dans HA : Paramètres › Modules complémentaires › Boutique › ⋮ › Dépôts → ajouter
   `https://github.com/florianfish/CRFormatter`.
4. Installer **DocFormatter**, renseigner votre nom d'utilisateur HA dans l'option `experts`, démarrer.

Pour publier une nouvelle version : incrémenter `version` dans `docformatter/config.yaml`
(et `CHANGELOG.md`), puis pousser sur `main`.

## Développement local

| Commande | Effet |
| --- | --- |
| `make run` | Serveur local avec rechargement automatique : http://127.0.0.1:8099 |
| `make docker` | Même chose dans le conteneur de l'add-on (Hunspell inclus, code monté) |
| `make test` | Tests (`make test-docker` : dans le conteneur, avec l'orthographe) |
| `make exemple` | Génère `dev-data/exemples/exemple.docx`, un compte rendu mal formaté |

`make run` crée le `.venv` au premier lancement. Sans Hunspell sur la machine
(`sudo apt install hunspell hunspell-fr`), l'orthographe est désactivée : utiliser `make docker`.

Variables utiles :

```bash
make run DEV_EXPERT=0 DEV_USER=secretaire   # voir l'interface de la secrétaire (sans mode expert)
make run SURVEILLE=1                    # dossier surveillé dev-data/share/entree → sortie
make run PORT=8100
```

Les règles, le modèle et l'historique de développement sont dans `dev-data/config/`
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
    │   ├── reader.py     .docx → blocs (paragraphes, tableaux)
    │   ├── sections.py   titres de section, listes à puces
    │   ├── cleaner.py    regex, corrections connues, majuscules
    │   ├── spelling.py   Hunspell (mode pipe), mots inconnus + suggestions
    │   └── writer.py     blocs → .docx à partir du modèle Word
    ├── rules.py          modèle des règles (validation pydantic), lecture/écriture YAML
    ├── store.py          stockage des règles : historique, annulation, réparation d'un fichier invalide
    ├── vocabulaire.py    opérations simples de la secrétaire (mots, remplacements, rubriques…)
    ├── web.py            FastAPI : formatage, vocabulaire, mise en forme, historique, mode expert
    ├── watcher.py        dossier surveillé /share/docformatter
    └── templates/, static/
```

Sécurité : en production, l'application n'accepte que les connexions du proxy Ingress du Supervisor
(`172.30.32.2`) et identifie l'utilisateur via l'en-tête `X-Remote-User-Name` ajouté par HA.
Tout utilisateur ayant accès au panneau peut formater et gérer le vocabulaire ; le mode expert
(regex, modèle Word, import/export) est réservé aux utilisateurs listés dans l'option `experts`.
