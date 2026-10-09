ARG BUILD_FROM=python:3.12-slim-bookworm
FROM ${BUILD_FROM}

RUN apt-get update \
    && apt-get install -y --no-install-recommends hunspell hunspell-fr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/docformatter
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY defaults ./defaults
# Version et nouveautés affichées dans l'interface (app/version.py)
COPY config.yaml CHANGELOG.md ./

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
EXPOSE 8099
CMD ["python", "-m", "app"]
