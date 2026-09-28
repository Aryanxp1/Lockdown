# Lockdown competition portal.
#
# The application is Python standard library only (http.server + sqlite3), so
# this build installs nothing: no pip, no npm, no apt. The base interpreter is
# the only thing that comes from outside, and it is fetched once - after that
# the image can be rebuilt from the local cache.
#
#   docker compose up      ->  http://127.0.0.1:8081
#
# Everything the portal writes goes to $PORTAL_DATA_DIR (/data), which the
# compose file puts on a named volume.
FROM python:3.12-alpine

# Unbuffered so `docker compose up` shows the boot banner and demo logins
# immediately instead of after the first flush.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORTAL_HOST=0.0.0.0 \
    PORTAL_PORT=8081 \
    PORTAL_DATA_DIR=/data \
    PORTAL_FIXTURES=/app/fixtures.json \
    PORTAL_SEED=1 \
    PORTAL_RESET=0

# Run as an unprivileged user. /data is created and owned here so that the
# named volume inherits that ownership the first time it is created.
RUN addgroup -S portal \
 && adduser -S -D -H -G portal portal \
 && mkdir -p /data \
 && chown -R portal:portal /data

WORKDIR /app

# The portal package plus the official fixture data it seeds itself from.
# run.py, .dogfood.toml and tests/ come along so the acceptance suite and the
# unittest suites can be run from inside the container without a host install.
COPY --chown=portal:portal app/ ./app/
COPY --chown=portal:portal tests/ ./tests/
COPY --chown=portal:portal fixtures.json run.py .dogfood.toml ./

VOLUME ["/data"]
EXPOSE 8081
USER portal:portal

# There is no /healthz route in the app and adding one would mean changing the
# application, so probe the public gallery instead: 200 there proves the
# router, the seeded database and the template layer are all alive.
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=4 \
  CMD ["python", "-c", "import os,sys,urllib.request;url='http://127.0.0.1:'+os.environ.get('PORTAL_PORT','8081')+'/gallery';sys.exit(0 if urllib.request.urlopen(url,timeout=5).getcode()==200 else 1)"]

# `python -m app` initialises the schema, seeds fixtures.json on an empty
# database, prints the demo session cookies and serves.
CMD ["python", "-m", "app"]
