import logging
import os

import uvicorn

from .settings import charger_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
settings = charger_settings()
if settings.dev:
    logging.getLogger("docformatter").warning(
        "Mode développement : authentification désactivée (utilisateur « %s »)", settings.dev_utilisateur,
    )
uvicorn.run(
    "app.asgi:creer",
    factory=True,
    host=os.environ.get("DOCFORMATTER_HOST") or ("127.0.0.1" if settings.dev else "0.0.0.0"),
    port=settings.port,
    proxy_headers=False,
    # Redémarre à chaque modification d'un .py (gabarits et static sont relus à chaque requête).
    reload=settings.dev and os.environ.get("DOCFORMATTER_RELOAD") == "1",
    reload_dirs=[os.path.dirname(__file__)],
)
