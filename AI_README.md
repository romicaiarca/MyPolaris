# AI README

This file captures the current intent behind the MyPolaris custom integration so future AI-assisted changes stay aligned with the project direction.

## Product intent

- Package `mypolaris` as a standalone Home Assistant custom integration repository that can be published through HACS.
- Keep the integration practical for real-world Romanian MyPolaris accounts rather than trying to model a generic billing platform.
- Prefer user-visible labels in Romanian to match the existing entity naming used by the component.

## Current behavior we intentionally want

- Support two authentication modes:
  - Browser session cookie (`ASP.NET_SessionId`)
  - Email/password with CapSolver reCAPTCHA v3 token solving, optionally through a shared HTTP proxy when proxyless v3 tokens are rejected
- Default normal polling to 6 hours; keep authenticated sessions alive with a lightweight request every 100 seconds when the normal polling interval is longer than that.
- Expose diagnostic sensors for the last outbound access to MyPolaris and CapSolver solve attempts since integration load.
- Allow multiple Home Assistant config entries, but only one entry per email address.

## Architectural direction

- Keep runtime-only Home Assistant code inside `custom_components/mypolaris/`.
- Keep pure parsing, formatting, and label logic in `custom_components/mypolaris/utils.py` so it can be unit-tested without importing Home Assistant.
- Keep tests in the repository root `tests/` directory so CI can run them directly.
- Treat the README at repository root as the HACS-facing user documentation.

## Testing strategy

- Maintain runnable pure-Python unit tests for helpers and formatting logic.
- Add targeted `pytest-homeassistant-custom-component` tests for config flow, coordinator timing, and entity behavior without changing the HACS runtime package.
- Keep CI lightweight enough to run in a normal GitHub pipeline without needing the live Home Assistant config directory.

## Near-term priorities

- Preserve HACS-compatible repository structure.
- Keep the integration stable in session-cookie mode.
- Keep user-facing text and entity names Romanian-first.
- Improve diagnostics before adding broader feature surface.

## Things to avoid

- Do not spread integration-required modules outside `custom_components/mypolaris/` in the publishable repository.
- Do not rename public entities or user-visible options casually, because existing dashboards may depend on them.
- Do not introduce broad refactors unless they clearly improve testability or authentication reliability.