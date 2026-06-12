# MyPolaris.ro

[![Sponsor](https://img.shields.io/badge/Support-GitHub%20Sponsors-ea4aaa?logo=githubsponsors)](https://github.com/sponsors/romicaiarca)

Home Assistant custom integration for MyPolaris.ro, packaged as a standalone HACS repository.

This integration exposes contract, balance, unpaid invoice, archive, connectivity, last update, and last access-call data from MyPolaris into Home Assistant.

## Support the project

If this integration is useful in your Home Assistant setup and you want to support ongoing maintenance, fixes, and compatibility updates, you can donate via GitHub Sponsors:

- [Sponsor romicaiarca on GitHub Sponsors](https://github.com/sponsors/romicaiarca)

## Unofficial integration

This project is an unofficial integration and is not affiliated with, endorsed by, or supported by Polaris M. Holding S.R.L.

It works by using authenticated website endpoints observed from the MyPolaris portal, not by using an officially published public API. Because of that, the integration may stop working at any time if the website login flow, cookies, CAPTCHA handling, or backend endpoints change.

## Features

- Session-cookie authentication for accounts that are easier to keep stable from a browser login.
- Credentials + CapSolver authentication for automatic login and session refresh.
- A 6-hour default polling interval, plus a 100-second keepalive for authenticated sessions when the polling interval is longer than that.
- Dedicated diagnostic sensors for the latest outbound MyPolaris call and CapSolver solve attempts since the integration was loaded.
- Multiple Home Assistant config entries, one per MyPolaris email address.
- Romanian-first entity naming and labels.

## Installation

### HACS

1. Open HACS.
2. Open the custom repositories dialog.
3. Add `https://github.com/romicaiarca/MyPolaris` as an `Integration` repository.
4. Search for `MyPolaris.ro` in HACS and install it.
5. Restart Home Assistant.
6. Add the integration from Settings > Devices & Services.

### Manual

1. Copy `custom_components/mypolaris` from this repository into your Home Assistant `custom_components` directory.
2. Restart Home Assistant.
3. Add the integration from Settings > Devices & Services.

## Configuration

The integration currently supports two authentication modes:

- Browser session cookie: paste the `ASP.NET_SessionId` value copied from your browser.
- Credentials + CapSolver: provide email, password, and a valid `CAI-...` or `CAP-...` CapSolver API key. This flow solves the MyPolaris reCAPTCHA v3 token with CapSolver and reuses the ASP.NET session until it expires. If proxyless v3 tokens are rejected, configure an optional HTTP proxy URL such as `http://user:pass@host:port`; the integration will use CapSolver's proxy task type and route MyPolaris requests through the same proxy so Google sees a matching IP.

For browser session-cookie authentication, if the Polaris session expires, open the integration Options dialog and paste a fresh `ASP.NET_SessionId` cookie. Credential authentication will try to refresh the ASP.NET session automatically with CapSolver.

If you use browser-session cookies for multiple MyPolaris accounts, obtain each cookie from a separate incognito/private window or a separate browser profile. In testing, MyPolaris appears to bind the session to the current browser/device profile, so signing in with a different account in the same normal browser profile can replace the previous cookie.

### How to copy `ASP.NET_SessionId` from your browser

For all browsers, start by logging in to your MyPolaris account and keeping the browser tab open on the site.

You can paste either of these into the integration:

- Only the cookie value, for example `l4ah0u4r5ddvt54eqx54cfru`
- The full cookie pair, for example `ASP.NET_SessionId=l4ah0u4r5ddvt54eqx54cfru;`

Sanitized illustrative Chrome DevTools view:

![Illustrative Chrome DevTools view showing Application -> Cookies -> https://my.polaris.ro and the ASP.NET_SessionId value](docs/images/chrome-cookie-devtools.svg)

#### Google Chrome

1. Open `my.polaris.ro` and sign in.
2. Press `F12`, or right-click the page and choose `Inspect`.
3. Open the `Application` tab.
4. In the left sidebar, open `Storage` -> `Cookies`.
5. Click the entry for `https://my.polaris.ro`.
6. Find the row named `ASP.NET_SessionId`.
7. Copy the `Value` column, or copy the full cookie if you prefer.
8. Paste it into the MyPolaris integration in Home Assistant.

#### Mozilla Firefox

1. Open `my.polaris.ro` and sign in.
2. Press `F12`, or right-click the page and choose `Inspect`.
3. Open the `Storage` tab.
4. In the left sidebar, open `Cookies`.
5. Select `https://my.polaris.ro`.
6. Find `ASP.NET_SessionId` in the cookie list.
7. Copy the `Value` field.
8. Paste it into the MyPolaris integration in Home Assistant.

#### Opera

1. Open `my.polaris.ro` and sign in.
2. Press `Ctrl` + `Shift` + `I`, or right-click and choose `Inspect element`.
3. Open the `Application` tab.
4. In the left sidebar, open `Storage` -> `Cookies`.
5. Select `https://my.polaris.ro`.
6. Find `ASP.NET_SessionId`.
7. Copy the `Value` column.
8. Paste it into the MyPolaris integration in Home Assistant.

#### Microsoft Edge

1. Open `my.polaris.ro` and sign in.
2. Press `F12`, or right-click the page and choose `Inspect`.
3. Open the `Application` tab.
4. In the left sidebar, open `Storage` -> `Cookies`.
5. Select `https://my.polaris.ro`.
6. Find `ASP.NET_SessionId`.
7. Copy the `Value` field.
8. Paste it into the MyPolaris integration in Home Assistant.

#### Safari

1. Open `my.polaris.ro` and sign in.
2. If the developer tools menu is not visible, open `Safari` -> `Settings` -> `Advanced` and enable the web developer menu.
3. Open `Develop` -> `Show Web Inspector`.
4. Open the `Storage` tab.
5. Open `Cookies`, then select `my.polaris.ro`.
6. Find `ASP.NET_SessionId`.
7. Copy the `Value` field.
8. Paste it into the MyPolaris integration in Home Assistant.

If you do not see the cookie immediately, refresh the MyPolaris page once and check again.

## Privacy and data handling

- This integration is intended to be used only with your own MyPolaris account.
- Session cookies, credentials, and related configuration are stored in Home Assistant configuration entries and are used only to access the account configured by the user.
- The integration may expose account-related billing information inside Home Assistant, such as balances, invoices, and payments.
- Because the integration relies on website authentication rather than an official API, users should review the provider's published policies and decide whether this usage is acceptable for their environment.

## Exposed entities

- Contract and current balance sensors per location.
- Unpaid invoice count and total per location.
- Yearly invoice and payment archive sensors.
- Connectivity sensor.
- `MyPolaris Ultima Actualizare` timestamp sensor.
- `MyPolaris Ultima Accesare` timestamp sensor with endpoint, method, source, and status attributes.

## Notes and limitations

- MyPolaris does not provide a public documented API; this integration works against the website endpoints currently used by the portal.
- The integration is based on observed website behavior and may require updates whenever the MyPolaris portal changes.
- Session-cookie mode depends on a valid Polaris browser session.
- The config flow prevents adding the same email twice, but multiple different accounts are supported.

## Development and validation

This repository includes a GitHub Actions workflow that runs:

- Hassfest validation
- HACS validation
- Local syntax checks with `compileall`
- Root-level tests from `tests/`, including Home Assistant-native pytest coverage

The extra test dependencies are development-only. HACS still installs only the integration files from `custom_components/mypolaris/`.

You can run the repository test suite with:

```bash
python3 -m pip install -r requirements_test.txt
pytest -q tests
```

## Repository layout

This repository contains exactly one HACS integration:

```text
custom_components/mypolaris/
```

That layout is intentional so the repository can be published directly through HACS.

## License

This project is released under the MIT License. See the `LICENSE` file for details.