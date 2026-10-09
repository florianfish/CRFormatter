"""Configuration de l'application.

En production (add-on Home Assistant) :
- /data/options.json : options saisies dans l'onglet « Configuration » de l'add-on ;
- /config            : dossier persistant de l'add-on (règles, modèle Word, sauvegardes) ;
- /share/docformatter: dossier surveillé, accessible via le partage Samba de HA.

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

# Adresse du proxy Ingress du Supervisor : seule source autorisée en production.
INGRESS_PROXY_IP = "172.30.32.2"

log = logging.getLogger("docformatter")


@dataclass
class Settings:
    dev: bool = False
    config_dir: Path = Path("/config")
    share_dir: Path = Path("/share/docformatter")
    # Identifiants HA ayant accès au mode expert (regex, modèle Word, import/export)
    experts: list[str] = field(default_factory=list)
    dossier_surveille: bool = False
    port: int = 8099
    # Mode développement : utilisateur simulé (pas d'en-têtes Ingress en local)
    dev_utilisateur: str = "dev"
    dev_expert: bool = True

    @property
    def regles_path(self) -> Path:
        return self.config_dir / "regles.yaml"

    @property
    def historique_dir(self) -> Path:
        return self.config_dir / "historique"

    @property
    def modele_path(self) -> Path:
        return self.config_dir / "modele.docx"

    @property
    def dictionnaires_dir(self) -> Path:
        """Listes de mots supplémentaires (*.txt / *.dic), un mot par ligne."""
        return self.config_dir / "dictionnaires"


def charger_settings() -> Settings:
    env = os.environ
    s = Settings(
        dev=env.get("DOCFORMATTER_DEV") == "1",
        config_dir=Path(env.get("DOCFORMATTER_CONFIG", "/config")),
        share_dir=Path(env.get("DOCFORMATTER_SHARE", "/share/docformatter")),
        port=int(env.get("DOCFORMATTER_PORT", "8099")),
        dev_utilisateur=env.get("DOCFORMATTER_DEV_USER", "dev"),
        dev_expert=env.get("DOCFORMATTER_DEV_EXPERT", "1") == "1",
    )
    options_path = Path(env.get("DOCFORMATTER_OPTIONS", "/data/options.json"))
    if options_path.exists():
        options = json.loads(options_path.read_text(encoding="utf-8"))
        s.experts = [a.strip().lower() for a in options.get("experts", []) if a.strip()]
        s.dossier_surveille = bool(options.get("dossier_surveille", False))
    if "DOCFORMATTER_SURVEILLE" in env:
        s.dossier_surveille = env["DOCFORMATTER_SURVEILLE"] == "1"
    s.config_dir.mkdir(parents=True, exist_ok=True)
    s.dictionnaires_dir.mkdir(parents=True, exist_ok=True)
    return s
