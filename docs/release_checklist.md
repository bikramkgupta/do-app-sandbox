# Release Checklist

Use this checklist for every tagged release.

## Pre-release quality gates

- [ ] `make check` passes locally or in CI
- [ ] Unit tests pass (`cd tests && make test-unit`)
- [ ] Critical cloud tests pass for release candidates
- [ ] `pip-audit` has no untriaged critical/high vulnerabilities
- [ ] Changelog/release notes are prepared

## Security and supply chain

- [ ] Dependabot PR backlog triaged
- [ ] CodeQL and secret scan workflows passing on `main`
- [ ] SBOM generated and uploaded as release artifact
- [ ] Build provenance attestation generated for `dist/*`

## Packaging and publishing

- [ ] Version in `pyproject.toml` is final and tagged
- [ ] `python -m build` succeeds
- [ ] `twine check dist/*` succeeds
- [ ] Publish workflow succeeded
- [ ] PyPI package install smoke test passes

## Manual container publish runbook (python-service only)

Use this for the dedicated manual workflow in `.github/workflows/build-images.yml`.

- [ ] Open **Actions** → **Build and Push Sandbox Images** → **Run workflow**
- [ ] Set `publish_python_service_latest` = `true`
- [ ] Set `confirm_target` = `digitalocean-labs/sandbox-python-service:latest`
- [ ] Confirm workflow runs in a repository owned by `digitalocean-labs`
- [ ] Verify job `publish-python-service-manual` passes smoke check (`/health`)
- [ ] Verify tag is pullable:

```bash
docker manifest inspect ghcr.io/digitalocean-labs/sandbox-python-service:latest
```

## Post-release

- [ ] Verify README install commands for new version
- [ ] Announce release notes and breaking changes
- [ ] Create follow-up issues for deferred work
