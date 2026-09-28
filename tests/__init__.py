"""Lockdown's own tests. Standard library only, in the spirit of the portal.

These ship inside the Docker image too, so the same suites run in a container:

    python -m unittest discover -s tests -v
    python -m unittest tests.test_event_isolation -v
    docker exec lockdown-portal python3 -m unittest discover -s tests -v
"""
