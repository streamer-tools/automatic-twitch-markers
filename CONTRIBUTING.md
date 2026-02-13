# Contributing

Thanks for contributing to Automatic Twitch Markers.

## Setup
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

## Run Tests
```powershell
python -m unittest discover -s tests -v
```

## Build (Windows)
See [docs/packaging.md](docs/packaging.md).

## Documentation Layout
- User docs: [docs/README.md](docs/README.md)
- Developer docs: [docs/dev/README.md](docs/dev/README.md)
- Historical implementation docs: `docs/dev/archive/`

## Security and Secrets
- Never commit access tokens, refresh tokens, `client_secret`, or auth headers.
- Use `local.config.json` or environment variables for local secrets.
- Keep runtime artifacts (`data/`, `logs/`, DB files) out of commits.
