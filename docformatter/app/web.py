"""Application web (servie via Ingress Home Assistant).

Tout utilisateur HA ayant accès au panneau a accès à tout : l'authentification est celle de HA.
Le mode expert (regex, testeur, import/export) est séparé pour ne pas encombrer
les pages du quotidien, pas pour des raisons de droits.
"""

from __future__ import annotations

import copy
import io
import logging
import secrets
import threading
import time
import zipfile
from collections import Counter
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import Body, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup
from pydantic import BaseModel, ValidationError

from . import vocabulaire as voc
from .apercu import diff_html, rendre_blocs
from .collage import Collage, docx_depuis_collage
from .auth import COOKIE, DUREE_SESSION, Limiteur, Sessions, charger_cle
from .pipeline import finaliser_retouche, formater, traiter_texte
from .pipeline.model import Bloc
from .pipeline.spelling import Correcteur, charger_mots
from .retouche import Edition, depuis_editeur, remplacer_mots, vers_editeur
from .rules import LIBELLES_OPTIONS, Regles, Remplacement, ecrire_yaml, lire_yaml
from .settings import APP_DIR, INGRESS_PROXY_IP, Settings
from .store import ConflitVersion, RegleInvalide, RulesStore
from .watcher import Surveillant

log = logging.getLogger("docformatter")

TAILLE_MAX = 20 * 1024 * 1024
DUREE_CONSERVATION = 3600  # documents gardés en mémoire 1 h, jamais écrits sur disque
NOM_COLLAGE = "Compte rendu collé.docx"
MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@dataclass
class Fichier:
    nom: str
    contenu: bytes
    media_type: str


@dataclass
class Lot:
    """Documents d'un envoi : originaux (pour reformater après ajout de vocabulaire),
    résultat courant de chaque document et retouches manuelles."""

    originaux: list[tuple[str, bytes]]
    version_regles: str = ""
    rendu: dict[str, Any] = field(default_factory=dict)
    message: dict[str, str] | None = None
    blocs: dict[int, list[Bloc]] = field(default_factory=dict)      # résultat courant par document
    retouches: dict[int, list[Bloc]] = field(default_factory=dict)  # saisies manuelles par document
    telechargements: dict[int, str] = field(default_factory=dict)   # clé du .docx courant


class Depot:
    """Objets en mémoire, accessibles uniquement par l'utilisateur qui les a créés."""

    def __init__(self):
        self._objets: dict[str, tuple[str, float, Any]] = {}
        self._lock = threading.Lock()

    def ajouter(self, objet: Any, proprietaire: str) -> str:
        cle = secrets.token_urlsafe(16)
        with self._lock:
            self._purger()
            self._objets[cle] = (proprietaire, time.time(), objet)
        return cle

    def lire(self, cle: str, utilisateur: str, type_: type) -> Any:
        with self._lock:
            self._purger()
            entree = self._objets.get(cle)
        if entree is None or entree[0] != utilisateur or not isinstance(entree[2], type_):
            return None
        return entree[2]

    def _purger(self) -> None:
        limite = time.time() - DUREE_CONSERVATION
        for cle in [c for c, (_, cree, _) in self._objets.items() if cree < limite]:
            del self._objets[cle]


def _content_disposition(nom: str) -> str:
    ascii_ = nom.encode("ascii", "replace").decode().replace('"', "")
    return f"attachment; filename=\"{ascii_}\"; filename*=UTF-8''{quote(nom)}"


def _erreurs_validation(e: ValidationError) -> str:
    return " ; ".join(
        f"{' › '.join(str(x) for x in err['loc'])} : {err['msg'].removeprefix('Value error, ')}"
        for err in e.errors()
    )


class TestRegle(BaseModel):
    motif: str
    remplacement: str = ""
    ignorer_casse: bool = False
    exemple: str = ""


class TestRegles(BaseModel):
    remplacements: list[dict]
    texte: str


def creer_app(settings: Settings) -> FastAPI:
    surveillant: Surveillant | None = None

    @asynccontextmanager
    async def cycle_de_vie(_app: FastAPI):
        if surveillant:
            surveillant.start()
        yield
        if surveillant:
            surveillant.arreter()

    app = FastAPI(title="DocFormatter", docs_url=None, redoc_url=None, openapi_url=None,
                  lifespan=cycle_de_vie)
    templates = Jinja2Templates(directory=APP_DIR / "templates")
    templates.env.filters["diff"] = lambda c: Markup(diff_html(c.avant, c.apres))
    store = RulesStore(settings.regles_path, settings.historique_dir)
    depot = Depot()
    app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")

    def correcteur(regles: Regles) -> Correcteur:
        return Correcteur(charger_mots(regles.dictionnaire, settings.dictionnaires_dir))

    def formater_octets(data: bytes) -> bytes:
        regles = store.get()
        return formater(data, regles, correcteur(regles)).docx

    # ---- Sécurité ---------------------------------------------------------------------

    sessions = Sessions(charger_cle(settings.cle_sessions_path), settings.utilisateurs)
    limiteur = Limiteur()

    @app.middleware("http")
    async def securite(request: Request, call_next):
        request.state.direct = False
        if settings.dev:
            request.state.utilisateur = settings.dev_utilisateur
            request.state.base = ""
        elif request.client is not None and request.client.host == INGRESS_PROXY_IP:
            # Via la barre latérale HA : le Supervisor a déjà authentifié l'utilisateur.
            request.state.utilisateur = (request.headers.get("x-remote-user-name") or "").lower()
            request.state.base = request.headers.get("x-ingress-path", "")
        elif not settings.acces_direct:
            return Response("Accès refusé : activez l'option « acces_direct » de l'add-on.", status_code=403)
        else:
            # Accès direct (proxy nginx…) : connexion obligatoire. Les en-têtes Ingress éventuellement
            # envoyés par le client sont ignorés.
            request.state.direct = True
            request.state.base = ""
            utilisateur = sessions.verifier(request.cookies.get(COOKIE))
            chemin = request.url.path
            if utilisateur is None and chemin != "/connexion" and not chemin.startswith("/static/"):
                if request.method == "GET" and "text/html" in request.headers.get("accept", ""):
                    return RedirectResponse(f"/connexion?suite={quote(chemin)}", status_code=303)
                return JSONResponse({"erreur": "Session expirée : reconnectez-vous."}, status_code=401)
            request.state.utilisateur = utilisateur or ""
        reponse = await call_next(request)
        reponse.headers["X-Content-Type-Options"] = "nosniff"
        reponse.headers["Referrer-Policy"] = "no-referrer"
        return reponse

    def page(request: Request, nom: str, actif: str = "", status_code: int = 200, **ctx) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            nom,
            {"base": request.state.base, "utilisateur": request.state.utilisateur, "actif": actif,
             "direct": request.state.direct,
             "alerte": store.alerte if request.state.utilisateur or not request.state.direct else None, **ctx},
            status_code=status_code,
        )

    def appliquer(request: Request, op: voc.Operation, version: str | None = None) -> str:
        """Enregistre une opération ; retourne l'identifiant de version permettant d'annuler."""
        precedente = store.modifier(op.modification, request.state.utilisateur or "inconnu",
                                    op.description, version)
        log.info("%s : %s", request.state.utilisateur, op.description)
        return precedente

    @app.exception_handler(RegleInvalide)
    async def regle_invalide(_request: Request, e: RegleInvalide):
        return JSONResponse({"erreur": str(e)}, status_code=422)

    @app.exception_handler(ConflitVersion)
    async def conflit(_request: Request, _e: ConflitVersion):
        return JSONResponse(
            {"erreur": "Les règles ont été modifiées entre-temps (autre onglet ou autre personne). "
                       "Rechargez la page avant d'enregistrer."},
            status_code=409,
        )

    # ---- Connexion (accès direct uniquement) ------------------------------------------

    def suite_sure(suite: str) -> str:
        """Évite une redirection vers un autre site après connexion."""
        return suite if suite.startswith("/") and not suite.startswith("//") else "/"

    @app.get("/connexion", response_class=HTMLResponse)
    def page_connexion(request: Request, suite: str = "/"):
        if not request.state.direct or request.state.utilisateur:
            return RedirectResponse(f"{request.state.base}{suite_sure(suite)}", status_code=303)
        return page(request, "connexion.html", sans_menu=True, suite=suite_sure(suite))

    @app.post("/connexion", response_class=HTMLResponse)
    async def connexion(request: Request):
        if not request.state.direct:
            return RedirectResponse(f"{request.state.base}/", status_code=303)
        formulaire = await request.form()
        identifiant = str(formulaire.get("identifiant", "")).strip().lower()
        suite = suite_sure(str(formulaire.get("suite", "/")))
        adresse = request.headers.get("x-real-ip") or (request.client.host if request.client else "?")

        def refus(message: str) -> HTMLResponse:
            return page(request, "connexion.html", status_code=401, sans_menu=True, suite=suite,
                        identifiant=identifiant, erreur=message)

        if limiteur.bloque(adresse):
            log.warning("Connexion refusée (trop de tentatives) depuis %s", adresse)
            return refus("Trop de tentatives. Réessayez dans un quart d'heure.")
        if not sessions.verifier_identifiants(identifiant, str(formulaire.get("mot_de_passe", ""))):
            limiteur.echec(adresse)
            log.warning("Échec de connexion pour « %s » depuis %s", identifiant, adresse)
            return refus("Identifiant ou mot de passe incorrect.")
        limiteur.reussite(adresse)
        log.info("Connexion de %s depuis %s", identifiant, adresse)
        reponse = RedirectResponse(suite, status_code=303)
        reponse.set_cookie(COOKIE, sessions.creer(identifiant), max_age=DUREE_SESSION, httponly=True,
                           samesite="lax", path="/",
                           secure=request.headers.get("x-forwarded-proto") == "https")
        return reponse

    @app.post("/deconnexion")
    def deconnexion(request: Request):
        reponse = RedirectResponse(f"{request.state.base}/connexion", status_code=303)
        reponse.delete_cookie(COOKIE, path="/")
        return reponse

    # ---- Formatage --------------------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    def accueil(request: Request):
        return page(request, "index.html", actif="formater")

    @app.post("/formater")
    def formater_fichiers(request: Request, fichiers: list[UploadFile] = File(...)):
        originaux, refus = [], []
        for f in fichiers:
            nom = Path(f.filename or "document.docx").name
            data = f.file.read(TAILLE_MAX + 1)
            if not nom.lower().endswith(".docx"):
                refus.append(f"{nom} : seuls les fichiers Word .docx sont acceptés.")
            elif len(data) > TAILLE_MAX:
                refus.append(f"{nom} : fichier trop volumineux (20 Mo maximum).")
            else:
                originaux.append((nom, data))
        lot = Lot(originaux)
        if refus:
            lot.message = {"type": "erreur", "texte": " ".join(refus)}
        cle = depot.ajouter(lot, request.state.utilisateur)
        return RedirectResponse(f"{request.state.base}/lot/{cle}", status_code=303)

    @app.post("/api/coller")
    def coller(request: Request, collage: Collage):
        """Compte rendu collé depuis Word : traité comme un fichier déposé (récapitulatif des corrections)."""
        if collage.vide():
            raise RegleInvalide("Le texte collé est vide : copiez le compte rendu dans Word puis recommencez.")
        lot = Lot([(NOM_COLLAGE, docx_depuis_collage(collage))])
        return {"adresse": f"lot/{depot.ajouter(lot, request.state.utilisateur)}"}

    def nom_sortie(nom: str) -> str:
        return f"{Path(nom).stem} - formaté.docx"

    def rendre_lot(lot: Lot, utilisateur: str) -> dict[str, Any]:
        """Formate (ou reformate si les règles ont changé) tous les documents du lot.

        Un document retouché à la main n'est pas reformaté : seules l'orthographe et la
        réécriture du document sont recalculées, les saisies sont conservées telles quelles.
        """
        if lot.rendu and lot.version_regles == store.version:
            return lot.rendu
        regles = store.get()
        corr = correcteur(regles)
        resultats, sorties = [], []
        inconnus: Counter = Counter()
        suggestions: dict[str, list[str]] = {}
        orthographe = False
        for i, (nom, data) in enumerate(lot.originaux):
            entree: dict[str, Any] = {"nom": nom, "index": i, "retouche": i in lot.retouches,
                                      "colle": nom == NOM_COLLAGE}
            try:
                if i in lot.retouches:
                    res = finaliser_retouche(data, copy.deepcopy(lot.retouches[i]), regles, corr)
                else:
                    res = formater(data, regles, corr)
            except Exception:  # noqa: BLE001
                log.exception("Échec du traitement de %s", nom)
                entree["erreur"] = "Ce document n'a pas pu être lu. Est-ce bien un fichier Word valide ?"
            else:
                sorties.append((nom_sortie(nom), res.docx))
                inconnus.update(res.inconnus)
                suggestions.update(res.suggestions)
                orthographe = orthographe or res.orthographe_active
                lot.blocs[i] = res.blocs
                lot.telechargements[i] = depot.ajouter(Fichier(nom_sortie(nom), res.docx, MIME_DOCX), utilisateur)
                entree.update(
                    cle=lot.telechargements[i],
                    apercu=rendre_blocs(res.blocs, avec_diff=i not in lot.retouches),
                    changements=res.changements,
                    nb_inconnus=len(res.inconnus),
                    orthographe=res.orthographe_active,
                )
                if entree["colle"]:
                    entree["blocs"] = vers_editeur(res.blocs)  # pour « Copier pour Word »
            resultats.append(entree)

        cle_zip = None
        if len(sorties) > 1:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                for nom_fichier, contenu in sorties:
                    z.writestr(nom_fichier, contenu)
            cle_zip = depot.ajouter(
                Fichier("comptes-rendus-formatés.zip", buf.getvalue(), "application/zip"), utilisateur)

        lot.rendu = {
            "resultats": resultats,
            "cle_zip": cle_zip,
            "orthographe": orthographe,
            "inconnus": [(mot, n, suggestions.get(mot, [])) for mot, n in inconnus.most_common()],
        }
        lot.version_regles = store.version
        return lot.rendu

    def lire_lot(request: Request, cle: str) -> Lot:
        lot = depot.lire(cle, request.state.utilisateur, Lot)
        if lot is None:
            raise HTTPException(404, "Ces documents ne sont plus disponibles (plus d'une heure) : déposez-les à nouveau.")
        return lot

    def lire_document(request: Request, cle: str, n: int) -> Lot:
        lot = lire_lot(request, cle)
        rendre_lot(lot, request.state.utilisateur)
        if n not in lot.blocs:
            raise HTTPException(404, "Document introuvable.")
        return lot

    @app.get("/lot/{cle}", response_class=HTMLResponse)
    def afficher_lot(request: Request, cle: str):
        lot = lire_lot(request, cle)
        rendu = rendre_lot(lot, request.state.utilisateur)
        message, lot.message = lot.message, None
        return page(request, "resultat.html", actif="formater", cle_lot=cle, message=message, **rendu)

    @app.post("/lot/{cle}/decisions")
    async def decisions(request: Request, cle: str):
        lot = lire_lot(request, cle)
        formulaire = await request.form()
        choix = []
        i = 0
        while f"mot-{i}" in formulaire:
            choix.append((str(formulaire[f"mot-{i}"]), str(formulaire.get(f"choix-{i}", "")),
                          str(formulaire.get(f"par-{i}", ""))))
            i += 1
        try:
            op = voc.decisions(choix)
            if op is None:
                lot.message = {"type": "info", "texte": "Aucun choix n'a été fait : rien n'a changé."}
            else:
                precedente = await run_in_threadpool(appliquer, request, op)
                # Les documents retouchés ne sont pas reformatés : on y applique directement
                # les remplacements choisis ici.
                remplacements = {m: par.strip() for m, action, par in choix if action == "remplacer"}
                for n, blocs in list(lot.retouches.items()):
                    lot.retouches[n] = remplacer_mots(blocs, remplacements)
                lot.message = {"type": "succes", "annulation": precedente,
                               "texte": "C'est noté ! Le document a été reformaté avec votre vocabulaire."}
        except RegleInvalide as e:
            lot.message = {"type": "erreur", "texte": str(e)}
        return RedirectResponse(f"{request.state.base}/lot/{cle}", status_code=303)

    # ---- Retouche manuelle ------------------------------------------------------------

    @app.get("/lot/{cle}/document/{n}", response_class=HTMLResponse)
    def page_retouche(request: Request, cle: str, n: int):
        lot = lire_document(request, cle, n)
        return page(request, "retouche.html", actif="formater", cle_lot=cle, index=n,
                    nom_document=lot.originaux[n][0], colle=lot.originaux[n][0] == NOM_COLLAGE,
                    retouche=n in lot.retouches,
                    donnees={"blocs": vers_editeur(lot.blocs[n]), **etat_document(lot, n)})

    def etat_document(lot: Lot, n: int) -> dict[str, Any]:
        compte: Counter = Counter()
        suggestions: dict[str, list[str]] = {}
        for bloc in lot.blocs[n]:
            for b in bloc.textuels():
                for inc in b.inconnus:
                    compte[inc.mot] += 1
                    suggestions[inc.mot] = inc.suggestions
        return {
            "inconnus": [{"mot": m, "nombre": nb, "suggestions": suggestions[m]} for m, nb in compte.most_common()],
            "telechargement": lot.telechargements[n],
        }

    @app.get("/api/lot/{cle}/document/{n}")
    def lire_retouche(request: Request, cle: str, n: int):
        lot = lire_document(request, cle, n)
        return {"blocs": vers_editeur(lot.blocs[n]), **etat_document(lot, n)}

    @app.put("/api/lot/{cle}/document/{n}")
    def enregistrer_retouche(request: Request, cle: str, n: int, edition: Edition):
        lot = lire_document(request, cle, n)
        blocs = depuis_editeur(edition, lot.blocs[n])
        lot.retouches[n] = blocs
        lot.rendu = {}  # force le recalcul (orthographe, .docx) de ce document
        rendre_lot(lot, request.state.utilisateur)
        return {"blocs": vers_editeur(lot.blocs[n]), **etat_document(lot, n)}

    @app.delete("/api/lot/{cle}/document/{n}")
    def abandonner_retouche(request: Request, cle: str, n: int):
        lot = lire_document(request, cle, n)
        lot.retouches.pop(n, None)
        lot.rendu = {}
        rendre_lot(lot, request.state.utilisateur)
        return {"blocs": vers_editeur(lot.blocs[n]), **etat_document(lot, n)}

    @app.get("/telecharger/{cle}")
    def telecharger(request: Request, cle: str):
        f = depot.lire(cle, request.state.utilisateur, Fichier)
        if f is None:
            raise HTTPException(404, "Fichier expiré ou introuvable : déposez à nouveau le document.")
        return Response(f.contenu, media_type=f.media_type,
                        headers={"Content-Disposition": _content_disposition(f.nom)})

    # ---- Vocabulaire ------------------------------------------------------------------

    @app.get("/vocabulaire", response_class=HTMLResponse)
    def page_vocabulaire(request: Request):
        return page(request, "vocabulaire.html", actif="vocabulaire")

    @app.get("/api/vocabulaire")
    def lire_vocabulaire():
        return voc.vue(store.get())

    def reponse_vocabulaire(request: Request, op: voc.Operation) -> dict:
        precedente = appliquer(request, op)
        return {"vocabulaire": voc.vue(store.get()), "annulation": precedente, "message": op.description}

    @app.post("/api/vocabulaire/mot")
    def ajouter_mot(request: Request, mot: str = Body(..., embed=True)):
        return reponse_vocabulaire(request, voc.ajouter_mot(mot))

    @app.delete("/api/vocabulaire/mot")
    def retirer_mot(request: Request, mot: str = Body(..., embed=True)):
        return reponse_vocabulaire(request, voc.retirer_mot(mot))

    @app.post("/api/vocabulaire/remplacement")
    def ajouter_remplacement(request: Request, texte: str = Body(...), par: str = Body(...)):
        return reponse_vocabulaire(request, voc.ajouter_remplacement(texte, par))

    @app.delete("/api/vocabulaire/remplacement")
    def retirer_remplacement(request: Request, texte: str = Body(..., embed=True)):
        return reponse_vocabulaire(request, voc.retirer_remplacement(texte))

    @app.post("/api/vocabulaire/rubrique")
    def ajouter_rubrique(request: Request, titre: str = Body(..., embed=True)):
        return reponse_vocabulaire(request, voc.ajouter_rubrique(titre))

    @app.delete("/api/vocabulaire/rubrique")
    def retirer_rubrique(request: Request, titre: str = Body(..., embed=True)):
        return reponse_vocabulaire(request, voc.retirer_rubrique(titre))

    @app.post("/api/vocabulaire/variante")
    def ajouter_variante(request: Request, titre: str = Body(...), variante: str = Body(...)):
        return reponse_vocabulaire(request, voc.ajouter_variante(titre, variante))

    @app.delete("/api/vocabulaire/variante")
    def retirer_variante(request: Request, titre: str = Body(...), variante: str = Body(...)):
        return reponse_vocabulaire(request, voc.retirer_variante(titre, variante))

    # ---- Mise en forme ----------------------------------------------------------------

    @app.get("/mise-en-forme", response_class=HTMLResponse)
    def page_mise_en_forme(request: Request):
        regles = store.get()
        regles_affichees = []
        for i, r in enumerate(regles.remplacements):
            try:
                apres = r.appliquer(r.exemple)[0] if r.exemple else ""
            except ValueError:
                apres = ""
            regles_affichees.append({"index": i, "nom": r.nom, "description": r.description,
                                     "actif": r.actif, "avant": r.exemple, "apres": apres})
        options = [{"cle": cle, "libelle": lib, "avant": avant, "apres": apres,
                    "actif": getattr(regles.options, cle)}
                   for cle, (lib, avant, apres) in LIBELLES_OPTIONS.items()]
        return page(request, "mise_en_forme.html", actif="mise-en-forme",
                    regles=regles_affichees, options=options)

    @app.post("/api/mise-en-forme/regle")
    def basculer_regle(request: Request, index: int = Body(...), nom: str = Body(...), actif: bool = Body(...)):
        return {"annulation": appliquer(request, voc.basculer_regle(index, nom, actif))}

    @app.post("/api/mise-en-forme/option")
    def basculer_option(request: Request, cle: str = Body(...), actif: bool = Body(...)):
        return {"annulation": appliquer(request, voc.basculer_option(cle, actif))}

    # ---- Historique -------------------------------------------------------------------

    @app.get("/historique", response_class=HTMLResponse)
    def page_historique(request: Request):
        return page(request, "historique.html", actif="historique", versions=store.historique())

    @app.post("/api/historique/restaurer")
    def restaurer(request: Request, id: str = Body(...), annulation: bool = Body(False)):
        cible = store.trouver(id)
        description = None
        if annulation and cible is not None:
            derniere = store.historique()[0]
            description = f"Annulation : {derniere.description}"
        precedente = store.restaurer(id, request.state.utilisateur or "inconnu", description)
        return {"annulation": precedente}

    # ---- Mode expert ------------------------------------------------------------------

    @app.get("/expert", response_class=HTMLResponse)
    def page_expert(request: Request):
        return page(request, "expert.html", actif="expert",
                    dictionnaires=sorted(p.name for p in settings.dictionnaires_dir.iterdir()))

    @app.get("/expert/api/remplacements")
    def lire_remplacements(request: Request):
        regles = store.get()
        return {"version": store.version, "remplacements": [r.model_dump() for r in regles.remplacements]}

    @app.put("/expert/api/remplacements")
    def enregistrer_remplacements(request: Request, version: str = Body(...), remplacements: list[dict] = Body(...)):
        try:
            valides = [Remplacement.model_validate(r) for r in remplacements]
        except ValidationError as e:
            return JSONResponse({"erreur": _erreurs_validation(e)}, status_code=422)
        appliquer(request, voc.Operation(lambda r: setattr(r, "remplacements", valides),
                                         "Règles de mise en forme modifiées (mode expert)"), version)
        return lire_remplacements(request)

    @app.post("/expert/api/tester-regle")
    def tester_regle(request: Request, test: TestRegle):
        try:
            regle = Remplacement(nom="test", motif=test.motif, remplacement=test.remplacement,
                                 ignorer_casse=test.ignorer_casse)
            resultat, n = regle.appliquer(test.exemple)
        except (ValidationError, ValueError) as e:
            msg = _erreurs_validation(e) if isinstance(e, ValidationError) else str(e)
            return {"erreur": msg}
        return {"resultat": resultat, "diff": diff_html(test.exemple, resultat), "occurrences": n}

    @app.post("/expert/api/tester")
    def tester(request: Request, test: TestRegles):
        """Teste des règles regex non enregistrées, avec le vocabulaire actuel."""
        try:
            regles = store.get()
            regles.remplacements = [Remplacement.model_validate(r) for r in test.remplacements]
            res = traiter_texte(test.texte, regles, correcteur(regles))
        except ValidationError as e:
            return {"erreur": _erreurs_validation(e)}
        except ValueError as e:
            return {"erreur": str(e)}
        return {
            "html": str(rendre_blocs(res.blocs)),
            "changements": [c.__dict__ for c in res.changements],
            "inconnus": res.inconnus.most_common(),
        }

    @app.get("/expert/export")
    def exporter(request: Request):
        return Response(ecrire_yaml(store.get()), media_type="application/x-yaml",
                        headers={"Content-Disposition": _content_disposition("regles.yaml")})

    @app.post("/expert/import")
    def importer(request: Request, fichier: UploadFile = File(...)):
        try:
            regles = lire_yaml(fichier.file.read(TAILLE_MAX).decode("utf-8"))
        except ValidationError as e:
            return JSONResponse({"erreur": _erreurs_validation(e)}, status_code=422)
        except Exception as e:  # noqa: BLE001 — YAML ou encodage invalide
            return JSONResponse({"erreur": f"Fichier invalide : {e}"}, status_code=422)
        store.remplacer(regles, request.state.utilisateur, f"Import du fichier « {fichier.filename} » (mode expert)")
        return {"ok": True}

    # ---- Dossier surveillé ------------------------------------------------------------

    if settings.dossier_surveille:
        surveillant = Surveillant(settings.share_dir, formater_octets)

    return app
