# Release Notes

These release tags apply to both the Web dashboard and the Automation monitor in this repository.

## v1.0.0

Initial unified release of the Web dashboard and Automation monitor.

- Web dashboard with traffic visibility and rebuild actions
- Automation monitoring with scheduled tasks and notifications

## Unreleased

- Fix: ensure DNS auto-sync runs after delete/rebuild by preserving mapping before ID update.
- Improve: use explicit UTF-8 for YAML/JSON config + state files and safer JSON writes.
- Improve: add request timeouts for automation Hetzner API calls to avoid indefinite blocking.
- Improve: support Hetzner API pagination for server/snapshot listing (web + automation), preventing partial data on larger accounts.
- Security: make Basic Auth comparison constant-time and return proper `WWW-Authenticate` header on 401.
- DevOps: add GitHub Actions CI workflow to compile-check all Python files on push/PR.
- Cleanup: remove obsolete `version` field from `docker-compose.yml` to avoid Compose warnings.
- GitHub: add PR template and issue templates to standardize collaboration and bug reporting.
- Docs: add GitHub collaboration section in both English and Chinese README.
