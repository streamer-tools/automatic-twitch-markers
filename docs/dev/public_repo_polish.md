# Public Repo Polish Plan (1.0)

## Summary
Prepare the repository for public release with minimal-risk cleanup:
- Keep docs in repo but separate user docs from dev/archive docs
- Make `README.md` end-user first
- Remove unused stubs/dead code
- Add standard public repo policy files
- Align metadata for `1.0.0`

## Decisions
- Keep docs in repo and reorganize
- Keep README end-user first
- Add `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`
- Move full changelog to `CHANGELOG.md`
- Set `pyproject.toml` version to `1.0.0`
- Use `Development Status :: 5 - Production/Stable`

## Planned Changes

### Docs Reorganization
- Add `docs/README.md` (user docs index)
- Add `docs/dev/README.md` (developer docs index)
- Move implementation plans/walkthroughs to `docs/dev/archive/`
- Move `docs/dev/handoff.md` under developer docs (already completed)
- Keep this file in `docs/dev/public_repo_polish.md`
- Add an archive warning banner to every `docs/dev/archive/*.md`
- Replace `file:///...` links with repo-relative links (no leading slash)

### README
- Lead with portable zip workflow
- Remove AI-context callout from top-level README
- Link out to docs instead of embedding long internal sections
- Replace embedded changelog body with link to `CHANGELOG.md`

### Changelog
- Create root `CHANGELOG.md`
- Keep a Changelog structure:
  - `## [Unreleased]`
  - version sections with dates
  - grouped by `Added/Changed/Fixed/Removed`

### Code Pruning
- Remove `src/twitch_marker_agent/core/agent.py`
- Remove `src/twitch_marker_agent/integrations/*`
- Remove deprecated legacy `EventSubClient` alias from `core/eventsub_ws.py`

### Repo Hygiene
- Add MIT `LICENSE`
- Add `CONTRIBUTING.md`
- Add `SECURITY.md`

### Metadata
- `pyproject.toml`: `version = "1.0.0"`
- `pyproject.toml`: production-stable classifier
- `src/twitch_marker_agent/__init__.py`: align version/author metadata

### Gitignore
Ensure coverage for:
- `__pycache__/`
- `*.py[cod]`
- `dist/`
- `build/`
- `logs/`
- `*.db`
- `.dev/`
- `.venv-build/`
- `test_output/`

## Validation Gates
1. No runtime references to removed stubs:
   - `core.agent`
   - `EventSubClient`
   - `streamerbot_trigger`
   - `twitch_marker_agent.integrations`
2. Historical references allowed only in `docs/dev/archive/`
3. Test suite passes:
   - `python -m unittest discover -s tests -v`
