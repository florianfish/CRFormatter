# Développement local de DocFormatter.
#   make install   environnement Python (.venv)
#   make run       serveur local avec rechargement auto → http://127.0.0.1:8099
#   make docker    même chose dans le conteneur de l'add-on (Hunspell inclus)
#   make test      tests (make test-docker : dans le conteneur, avec Hunspell)
#   make exemple   génère dev-data/exemples/exemple.docx, un compte rendu mal formaté
#   make e2e       parcours de la secrétaire dans Chrome (lance le conteneur en profil secrétaire)
#
# Variables : PORT=8099  DEV_USER=dev  DEV_EXPERT=1 (0 pour voir l'interface de la secrétaire)
#             SURVEILLE=1 pour activer le dossier surveillé dev-data/share/{entree,sortie}

PORT ?= 8099
DEV_USER ?= dev
DEV_EXPERT ?= 1
SURVEILLE ?= 0
VENV := .venv
PY := $(CURDIR)/$(VENV)/bin/python
IMAGE := docformatter:dev

export PORT DEV_USER DEV_EXPERT SURVEILLE

.PHONY: install run docker docker-down test test-docker exemple e2e clean

$(VENV)/.installe: docformatter/requirements.txt
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -q -r docformatter/requirements.txt pytest httpx
	@command -v hunspell >/dev/null || echo "⚠ hunspell absent : orthographe désactivée en local (sudo apt install hunspell hunspell-fr, ou make docker)"
	touch $@

install: $(VENV)/.installe

run: install
	cd docformatter && \
	DOCFORMATTER_DEV=1 DOCFORMATTER_RELOAD=1 DOCFORMATTER_PORT=$(PORT) \
	DOCFORMATTER_CONFIG=$(CURDIR)/dev-data/config DOCFORMATTER_SHARE=$(CURDIR)/dev-data/share \
	DOCFORMATTER_SURVEILLE=$(SURVEILLE) DOCFORMATTER_DEV_USER=$(DEV_USER) DOCFORMATTER_DEV_EXPERT=$(DEV_EXPERT) \
	$(PY) -m app

docker:
	mkdir -p dev-data/config dev-data/share
	DEV_UID=$$(id -u) DEV_GID=$$(id -g) docker compose up --build

docker-down:
	docker compose down

test: install
	cd docformatter && $(PY) -m pytest -q

test-docker:
	docker build -q -t $(IMAGE) docformatter >/dev/null
	docker run --rm -v $(CURDIR)/docformatter/tests:/opt/docformatter/tests:ro \
		-v $(CURDIR)/docformatter/pytest.ini:/opt/docformatter/pytest.ini:ro $(IMAGE) \
		sh -c 'pip install -q pytest httpx 2>/dev/null; python -m pytest -q -p no:cacheprovider'

exemple: install
	$(PY) scripts/exemple.py dev-data/exemples/exemple.docx

e2e: exemple
	@$(PY) -c "import playwright" 2>/dev/null || $(VENV)/bin/pip install -q playwright
	rm -rf dev-data/e2e && mkdir -p dev-data/e2e/config dev-data/e2e/share
	DEV_UID=$$(id -u) DEV_GID=$$(id -g) PORT=8199 DEV_EXPERT=0 DEV_USER=secretaire \
		docker compose -p docformatter-e2e -f compose.yaml -f compose.e2e.yaml up --build -d --wait
	$(PY) scripts/parcours_secretaire.py http://127.0.0.1:8199/ dev-data/exemples/exemple.docx dev-data/e2e; \
		code=$$?; docker compose -p docformatter-e2e down; exit $$code

clean:
	rm -rf dev-data $(VENV)
