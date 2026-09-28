"""Entry point: `python3 -m app`.

Boots the database, seeds the fixtures when the database is empty, prints the
demo logins, and serves the portal. No arguments are required, and nothing is
downloaded: the portal is the standard library plus this repository.
"""

from __future__ import annotations

import argparse
import sys

from . import boot, config, db


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m app",
                                     description="Lockdown competition portal")
    parser.add_argument("--host", default=None, help="bind address (default %s)" % config.HOST)
    parser.add_argument("--port", type=int, default=None,
                        help="port to listen on (default %d)" % config.PORT)
    parser.add_argument("--reset", action="store_true",
                        help="delete existing data and re-seed from fixtures.json")
    parser.add_argument("--seed-only", action="store_true",
                        help="seed the database and exit without serving")
    parser.add_argument("--quiet", action="store_true", help="do not print the login banner")
    args = parser.parse_args(argv)

    migration = db.init_db()
    if migration.get("changed"):
        print("[boot] schema migrated %d -> %d (%s)" % (
            migration["from"], migration["to"],
            ", ".join(migration["added"]) or "tables only"), flush=True)
        if migration.get("created"):
            print("[boot] ensured: %s" % ", ".join(migration["created"]), flush=True)
    result = boot.seed(force=args.reset, quiet=args.quiet)
    if result.get("seeded"):
        summary = result.get("summary", {})
        print("[boot] seeded in %ss from %s" % (summary.get("seconds"), config.FIXTURES_PATH),
              flush=True)
    else:
        print("[boot] database already seeded (%s). Use --reset to rebuild." % result.get("reason"),
              flush=True)

    if args.seed_only:
        return 0

    port = args.port or config.PORT
    print("[boot] gallery: %s/projects" % config.BASE_URL, flush=True)
    print("[boot] sign in: %s/login  (see the credentials above)" % config.BASE_URL, flush=True)
    try:
        from . import server
        server.serve(host=args.host, port=port)
    except OSError as exc:
        print("[boot] cannot bind port %d: %s" % (port, exc), file=sys.stderr)
        print("[boot] try --port 8081 or set PORTAL_PORT", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
