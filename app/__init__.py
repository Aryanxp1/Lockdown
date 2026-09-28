"""Lockdown — a self-hosted, offline hackathon and competition platform.

The package is deliberately dependency free: everything below uses only the
Python standard library so that `docker compose up` works with the network
switched off and nothing has to be downloaded at build or boot time.

See ARCHITECTURE.md for the layout and DATA-MODEL.md for the schema.
"""

__version__ = "1.0.0"
__all__ = ["__version__"]
