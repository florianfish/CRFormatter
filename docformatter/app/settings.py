"""Configuration de l'application.

En production (add-on Home Assistant) :
- /data/options.json : options saisies dans l'onglet « Configuration » de l'add-on ;
- /data              : données privées de l'add-on (clé de signature des sessions) ;
- /config            : dossier persistant de l'add-on (règles, historique, dictionnaires).

En développement, ces chemins sont surchargés par des variables d'environnement
DOCFORMATTER_* (voir README).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
DEFAULTS_DIR = APP_DIR.parent / "defaults"

# Adresse du proxy Ingress du Supervisor (accès via la barre latérale HA, déjà authentifié).
INGRESS_PROXY_IP = "172.30.32.2"
# Accès direct (proxy nginx…) : mots de passe trop courts refusés, l'outil étant exposé sur Internet.
MOT_DE_PASSE_MIN = 10

log = logging.getLogger("docformatter")


@dataclass
class Settings:
    dev: bool = False
    config_dir: Path = Path("/config")
    data_dir: Path = Path("/data")
    port: int = 8099
    # Accès direct sans passer par l'Ingress (ex. sous-domaine via nginx) : connexion obligatoire
    acces_direct: bool = False
    utilisateurs: dict[str, str] = field(default_factory=dict)  # identifiant → mot de passe
    # Mode développement : utilisateur simulé (pas d'en-têtes Ingress en local)
    dev_utilisateur: str = "dev"

    @property
    def regles_path(self) -> Path:
        return self.config_dir / "regles.yaml"

    @property
    def historique_dir(self) -> Path:
        return self.config_dir / "historique"

    @property
    def cle_sessions_path(self) -> Path:
        return self.data_dir / "cle-sessions"

    @property
    def dictionnaires_dir(self) -> Path:
        """Listes de mots supplémentaires (*.txt / *.dic), un mot par ligne."""
        return self.config_dir / "dictionnaires"


def charger_settings() -> Settings:
    env = os.environ
    s = Settings(
        dev=env.get("DOCFORMATTER_DEV") == "1",
        config_dir=Path(env.get("DOCFORMATTER_CONFIG", "/config")),
        data_dir=Path(env.get("DOCFORMATTER_DATA", "/data")),
        port=int(env.get("DOCFORMATTER_PORT", "8099")),
        dev_utilisateur=env.get("DOCFORMATTER_DEV_USER", "dev"),
    )
    options_path = Path(env.get("DOCFORMATTER_OPTIONS", "/data/options.json"))
    if options_path.exists():
        options = json.loads(options_path.read_text(encoding="utf-8"))
        s.acces_direct = bool(options.get("acces_direct", False))
        for u in options.get("utilisateurs", []):
            nom, mot_de_passe = str(u.get("nom", "")).strip().lower(), str(u.get("mot_de_passe", ""))
            if not nom:
                continue
            if len(mot_de_passe) < MOT_DE_PASSE_MIN:
                log.error("Utilisateur « %s » ignoré : mot de passe de moins de %d caractères", nom, MOT_DE_PASSE_MIN)
                continue
            s.utilisateurs[nom] = mot_de_passe
        if s.acces_direct and not s.utilisateurs:
            log.error("Accès direct activé sans utilisateur valide : personne ne pourra se connecter")
    s.config_dir.mkdir(parents=True, exist_ok=True)
    s.data_dir.mkdir(parents=True, exist_ok=True)
    s.dictionnaires_dir.mkdir(parents=True, exist_ok=True)
    return s
