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
