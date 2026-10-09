"""Dossier surveillé : /share/docformatter/entree → /share/docformatter/sortie."""

from __future__ import annotations

import logging
import shutil
import threading
import time
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger("docformatter")

INTERVALLE = 5  # secondes
DELAI_STABILITE = 3  # un fichier encore en cours de copie n'est pas traité


class Surveillant(threading.Thread):
    def __init__(self, racine: Path, traiter: Callable[[bytes], bytes]):
        super().__init__(daemon=True, name="surveillant")
        self.entree = racine / "entree"
        self.sortie = racine / "sortie"
        self.traites = self.entree / "traites"
        self.erreurs = self.entree / "erreurs"
        self.traiter = traiter
        self._arret = threading.Event()
        for d in (self.entree, self.sortie, self.traites, self.erreurs):
            d.mkdir(parents=True, exist_ok=True)

    def arreter(self) -> None:
        self._arret.set()

    def run(self) -> None:
        log.info("Dossier surveillé actif : %s", self.entree)
        while not self._arret.wait(INTERVALLE):
            self.passe()

    def passe(self) -> None:
        maintenant = time.time()
        for fichier in sorted(self.entree.glob("*.docx")):
            if fichier.name.startswith("~$"):  # fichier verrou de Word
                continue
            if maintenant - fichier.stat().st_mtime < DELAI_STABILITE:
                continue
            try:
                (self.sortie / fichier.name).write_bytes(self.traiter(fichier.read_bytes()))
                shutil.move(fichier, self.traites / fichier.name)
                log.info("Formaté : %s", fichier.name)
            except Exception as e:  # noqa: BLE001 — un fichier en erreur ne doit pas bloquer les autres
                log.exception("Échec du traitement de %s", fichier.name)
                shutil.move(fichier, self.erreurs / fichier.name)
                (self.erreurs / f"{fichier.name}.erreur.txt").write_text(str(e), encoding="utf-8")
