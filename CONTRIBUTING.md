# Contributing

1. Create a Python virtual environment and install `requirements.txt`.
2. Set `PYTHONPATH=src` in your shell.
3. Make a focused change and add or update automated tests.
4. Run `python -m pytest -q` and `python -m compileall -q src app.py tests`.
5. Open a pull request describing the change and its verification.

Do not commit `.env` files, secrets, local SQLite databases, virtual environments, sample datasets, or private trace exports.
