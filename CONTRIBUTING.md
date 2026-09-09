# Contributing

Keep the program beginner-readable. Use descriptive names, small functions, and comments explaining why a rule exists. Avoid adding a framework or paid service for a task the existing code can handle.

Install locally with `python -m pip install -e .`, then run `python -m unittest discover -s tests -v`.

For parser fixes, create a tiny synthetic HTML sample. Do not commit real adverts, photos, contact information, database files, or access tokens. Put provider-specific selectors in `casa_watch/source.py`.

For a new provider, document its public source, access requirements, request limits, and evidence that the adapter works. Do not silently fall back to sample data on failures. Preserve unknown fields as `None`.

Explain the user-visible change and the checks you ran in your pull request. Open issues with the error message and steps to reproduce; redact personal paths and information.

