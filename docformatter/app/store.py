"""Stockage des règles : fichier YAML + historique de toutes les versions.

- Chaque modification enregistre un instantané complet dans `historique/` (date, auteur,
  description lisible) : on peut revenir à n'importe quelle version, ce qui sert aussi de
  bouton « Annuler ».
- Un `regles.yaml` invalide (modification manuelle ratée) n'empêche jamais l'outil de
  fonctionner : le fichier fautif est mis de côté et la dernière version valide est rétablie.
- Une modification manuelle valide du fichier est prise en compte sans redémarrage.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from .rules import Regles, ecrire_yaml, lire_yaml
from .settings import DEFAULTS_DIR

log = logging.getLogger("docformatter")

NB_VERSIONS = 100
SYSTEME = "DocFormatter"


@dataclass
class Version:
    id: str
    date: str  # ISO 8601
    auteur: str
    description: str

    @property
    def date_lisible(self) -> str:
        d = datetime.fromisoformat(self.date)
        mois = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
        return f"{d.day} {mois[d.month - 1]} {d.year} à {d:%H:%M}"


class ConflitVersion(Exception):
    pass


class RegleInvalide(ValueError):
    """Modification refusée, avec un message compréhensible par un non-technicien."""


def _horodatage() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S-%f")


class RulesStore:
    def __init__(self, path: Path, historique_dir: Path):
        self.path = path
        self.historique_dir = historique_dir
        self.alerte: str | None = None
        self._lock = threading.Lock()
        historique_dir.mkdir(parents=True, exist_ok=True)

        if not path.exists():
            shutil.copy(DEFAULTS_DIR / "regles.yaml", path)
        try:
            self._regles = lire_yaml(path.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001 — YAML, encodage ou validation
            self._regles = self._reparer(e)

        derniere = self._derniere_version()
        if derniere is None:
            self._instantane(SYSTEME, "Version initiale des règles")
        elif self._lire_instantane(derniere.id) != self._regles:
            self._instantane(SYSTEME, "Modification manuelle du fichier de règles")
        self._signature_fichier = self._signature()

    # ---- Lecture ----------------------------------------------------------------------

    def _signature(self) -> tuple[int, int]:
        st = self.path.stat()
        return st.st_mtime_ns, st.st_size

    @property
    def version(self) -> str:
        """Empreinte du contenu : sert à détecter les modifications concurrentes."""
        return hashlib.sha256(ecrire_yaml(self._regles).encode()).hexdigest()[:16]

    def get(self) -> Regles:
        with self._lock:
            self._recharger_si_modifie()
            return self._regles.model_copy(deep=True)

    def _recharger_si_modifie(self) -> None:
        if self._signature() == self._signature_fichier:
            return
        try:
            regles = lire_yaml(self.path.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            self._regles = self._reparer(e)
        else:
            if regles != self._regles:
                self._regles = regles
                self._instantane(SYSTEME, "Modification manuelle du fichier de règles")
                log.info("regles.yaml modifié à la main : rechargé")
        self._signature_fichier = self._signature()

    def _reparer(self, erreur: Exception) -> Regles:
        """Met le fichier invalide de côté et rétablit la dernière version valide."""
        mis_de_cote = self.path.with_name(f"regles.invalide-{_horodatage()}.yaml")
        shutil.move(self.path, mis_de_cote)
        log.error("regles.yaml invalide (%s) : conservé sous %s", erreur, mis_de_cote.name)

        for v in self.historique():
            try:
                regles = self._lire_instantane(v.id)
            except Exception:  # noqa: BLE001
                continue
            origine = f"la version du {v.date_lisible}"
            break
        else:
            regles = lire_yaml((DEFAULTS_DIR / "regles.yaml").read_text(encoding="utf-8"))
            origine = "les règles par défaut"

        self._ecrire(regles)
        self.alerte = (
            f"Le fichier des règles était abîmé : l'outil a automatiquement repris {origine}. "
            f"Vous pouvez continuer à travailler normalement. (Détail technique : {erreur} ; "
            f"fichier conservé sous le nom « {mis_de_cote.name} ».)"
        )
        return regles

    # ---- Écriture ---------------------------------------------------------------------

    def _ecrire(self, regles: Regles) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(ecrire_yaml(regles), encoding="utf-8")
        tmp.replace(self.path)  # remplacement atomique : jamais de fichier à moitié écrit

    def modifier(
        self,
        modification: Callable[[Regles], None],
        auteur: str,
        description: str,
        version_attendue: str | None = None,
    ) -> str:
        """Applique `modification` aux règles courantes, valide et enregistre.

        Retourne l'identifiant de la version précédente (pour « Annuler »).
        """
        with self._lock:
            self._recharger_si_modifie()
            if version_attendue is not None and version_attendue != self.version:
                raise ConflitVersion()
            precedente = self._derniere_version()
            regles = self._regles.model_copy(deep=True)
            modification(regles)
            try:
                regles = Regles.model_validate(regles.model_dump())
            except ValidationError as e:
                raise RegleInvalide(
                    " ; ".join(err["msg"].removeprefix("Value error, ") for err in e.errors())
                ) from e
            self._ecrire(regles)
            self._regles = regles
            self._signature_fichier = self._signature()
            self._instantane(auteur, description)
            self.alerte = None
            return precedente.id if precedente else ""

    def remplacer(self, regles: Regles, auteur: str, description: str, version_attendue: str | None = None) -> str:
        def tout_remplacer(r: Regles) -> None:
            for champ in Regles.model_fields:
                setattr(r, champ, getattr(regles, champ))

        return self.modifier(tout_remplacer, auteur, description, version_attendue)

    # ---- Historique -------------------------------------------------------------------

    def _instantane(self, auteur: str, description: str) -> Version:
        v = Version(_horodatage(), datetime.now().isoformat(timespec="seconds"), auteur, description)
        (self.historique_dir / f"{v.id}.yaml").write_text(ecrire_yaml(self._regles), encoding="utf-8")
        (self.historique_dir / f"{v.id}.json").write_text(
            json.dumps(asdict(v), ensure_ascii=False), encoding="utf-8"
        )
        for ancienne in self.historique()[NB_VERSIONS:]:
            for ext in (".yaml", ".json"):
                (self.historique_dir / f"{ancienne.id}{ext}").unlink(missing_ok=True)
        return v

    def historique(self) -> list[Version]:
        """Versions, de la plus récente à la plus ancienne."""
        versions = []
        for meta in sorted(self.historique_dir.glob("*.json"), reverse=True):
            try:
                versions.append(Version(**json.loads(meta.read_text(encoding="utf-8"))))
            except Exception:  # noqa: BLE001 — métadonnée illisible : version ignorée
                log.warning("Historique : %s illisible", meta.name)
        return versions

    def _derniere_version(self) -> Version | None:
        versions = self.historique()
        return versions[0] if versions else None

    def _lire_instantane(self, id_: str) -> Regles:
        if not id_.replace("-", "").isdigit():
            raise KeyError(id_)
        return lire_yaml((self.historique_dir / f"{id_}.yaml").read_text(encoding="utf-8"))

    def trouver(self, id_: str) -> Version | None:
        return next((v for v in self.historique() if v.id == id_), None)

    def restaurer(self, id_: str, auteur: str, description: str | None = None) -> str:
        cible = self.trouver(id_)
        if cible is None:
            raise RegleInvalide("Cette version n'existe plus dans l'historique.")
        regles = self._lire_instantane(id_)
        return self.remplacer(regles, auteur, description or f"Retour à la version du {cible.date_lisible}")
