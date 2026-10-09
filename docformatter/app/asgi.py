"""Point d'entrée ASGI (fabrique), utilisé aussi par le rechargement automatique en développement."""

from fastapi import FastAPI

from .settings import charger_settings
from .web import creer_app


def creer() -> FastAPI:
    return creer_app(charger_settings())
