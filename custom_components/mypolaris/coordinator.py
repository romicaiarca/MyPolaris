"""MyPolaris coordinator with hardened auth + NopeCHA."""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Callable

import aiohttp
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .utils import (
    build_cookie_header,
    parse_money as _parse_money_helper,
    year_from_dmy as _year_from_dmy_helper,
)

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://my.polaris.ro"
HOME_URL = f"{BASE_URL}/"
LOGIN_URL = f"{BASE_URL}/Login.aspx"
AUTH_URL = f"{BASE_URL}/Login.aspx/Autentificare"
INIT_URL = f"{BASE_URL}/Default.aspx/Init"
PDL_URL = f"{BASE_URL}/InvoicesAndPayments.aspx/LoadPuncteDeLucru"
LOCATII_URL = f"{BASE_URL}/Contact.aspx/GetListaLocatii"
SOLD_URL = f"{BASE_URL}/InvoicesAndPayments.aspx/LoadDataSold"
FACTURI_URL = f"{BASE_URL}/InvoicesAndPayments.aspx/LoadDataFacturi"
PLATI_URL = f"{BASE_URL}/InvoicesAndPayments.aspx/LoadDataPlati"
KEEPALIVE_INTERVAL = timedelta(seconds=100)
NOPECHA_TOKEN_URL = "https://api.nopecha.com/token/"
NOPECHA_INCOMPLETE_JOB_CODE = 14
NOPECHA_UNAVAILABLE_FEATURE_CODE = 18
NOPECHA_POLL_INTERVAL = 3
NOPECHA_MAX_POLLS = 30

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) HomeAssistant-MyPolaris/2.0 Chrome/124.0.0.0 Safari/537.36"
)

BASE_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": BASE_URL,
    "Referer": LOGIN_URL,
}

SITEKEY_PATTERNS = (
    r'data-sitekey="([^"]+)"',
    r"grecaptcha\.execute\(['\"]([^'\"]+)['\"]",
    r"grecaptcha\.render\([^,]+,\s*\{[^}]*sitekey\s*:\s*['\"]([^'\"]+)['\"]",
    r"sitekey\s*[:=]\s*['\"]([^'\"]+)['\"]",
)


class MyPolarisSessionExpired(UpdateFailed):
    """Raised when MyPolaris rejects the current ASP.NET session."""


async def _read_nopecha_json(resp: aiohttp.ClientResponse) -> dict[str, Any]:
    """Read a NopeCHA response body as JSON."""
    text = await resp.text()
    try:
        data = json.loads(text) if text else {}
    except ValueError as err:
        raise UpdateFailed(
            f"NopeCHA returned invalid JSON (HTTP {resp.status}): {text[:200]}"
        ) from err
    if not isinstance(data, dict):
        raise UpdateFailed(f"NopeCHA returned an unexpected payload: {data!r}")
    return data


def _format_nopecha_error(prefix: str, status: int, data: dict[str, Any]) -> str:
    """Format a NopeCHA error without leaking request details."""
    message = data.get("message") or data.get("type") or data.get("error")
    code = data.get("code") or data.get("error")
    if status == 402 or code == NOPECHA_UNAVAILABLE_FEATURE_CODE:
        return (
            f"{prefix}: the NopeCHA reCAPTCHA v2 token API is unavailable for "
            "this API key's current plan. MyPolaris email login needs token API "
            "access to refresh the ASP.NET session. Use a NopeCHA key with "
            "reCAPTCHA v2 token access, or switch this integration to browser "
            "session cookie authentication."
        )
    if code is not None and message:
        return f"{prefix}: {message} (HTTP {status}, code {code})"
    if message:
        return f"{prefix}: {message} (HTTP {status})"
    return f"{prefix}: HTTP {status}, response={data!r}"


async def solve_recaptcha_with_nopecha(
    session: aiohttp.ClientSession,
    api_key: str,
    sitekey: str,
    url: str,
) -> str:
    """Solve the MyPolaris reCAPTCHA v2 challenge via NopeCHA."""
    api_key = (api_key or "").strip()
    if not api_key:
        raise UpdateFailed("NopeCHA API key is required.")

    headers = {"Content-Type": "application/json"}
    payload = {
        "key": api_key,
        "type": "recaptcha2",
        "sitekey": sitekey,
        "url": url,
        "data": {"theme": "light"},
        "enterprise": False,
        "useragent": USER_AGENT,
    }

    async with session.post(
        NOPECHA_TOKEN_URL,
        json=payload,
        headers=headers,
    ) as resp:
        data = await _read_nopecha_json(resp)
        if resp.status >= 400:
            raise UpdateFailed(
                _format_nopecha_error("NopeCHA submit failed", resp.status, data)
            )

    job_id = data.get("data")
    if not isinstance(job_id, str) or not job_id:
        raise UpdateFailed(f"NopeCHA did not return a job ID: {data!r}")
    _LOGGER.debug("NopeCHA reCAPTCHA job created: %s", job_id)

    for attempt in range(NOPECHA_MAX_POLLS):
        await asyncio.sleep(NOPECHA_POLL_INTERVAL)
        async with session.get(
            NOPECHA_TOKEN_URL,
            params={"key": api_key, "id": job_id},
            headers=headers,
        ) as resp:
            data = await _read_nopecha_json(resp)
            if (
                resp.status == 409
                or data.get("code") == NOPECHA_INCOMPLETE_JOB_CODE
                or data.get("error") == NOPECHA_INCOMPLETE_JOB_CODE
            ):
                continue
            if resp.status >= 400:
                raise UpdateFailed(
                    _format_nopecha_error("NopeCHA result failed", resp.status, data)
                )

        token = data.get("data")
        if isinstance(token, str) and token:
            _LOGGER.debug(
                "NopeCHA solved reCAPTCHA in ~%ss",
                NOPECHA_POLL_INTERVAL * (attempt + 1),
            )
            return token
        raise UpdateFailed(f"NopeCHA returned an unexpected result: {data!r}")

    raise UpdateFailed("NopeCHA timeout - reCAPTCHA was not solved in time.")


class MyPolarisCoordinator(DataUpdateCoordinator):
    """Polls my.polaris.ro for contract/balance data."""

    def __init__(
        self,
        hass: HomeAssistant,
        email: str,
        password: str,
        api_key: str,
        update_interval: timedelta,
        session: aiohttp.ClientSession,
        session_cookie: str = "",
    ) -> None:
        self.email = email
        self.password = password
        self.api_key = api_key
        self.session = session
        self.session_cookie = (session_cookie or "").strip()
        self._authenticated = bool(self.session_cookie)
        self.config_entry_id: str | None = None
        self._cancel_keepalive: Callable[[], None] | None = None
        self._access_listeners: list[Callable[[], None]] = []
        self._last_access_at: datetime | None = None
        self._last_access_endpoint: str | None = None
        self._last_access_method: str | None = None
        self._last_access_source: str | None = None
        self._last_access_status: int | None = None
        super().__init__(
            hass, _LOGGER, name="MyPolaris", update_interval=update_interval
        )

    def async_start_keepalive(self) -> None:
        """Keep authenticated sessions alive between coordinator refreshes."""
        if self._cancel_keepalive is not None:
            return
        if not self.session_cookie and not self._authenticated:
            return
        if self.update_interval is not None and self.update_interval <= KEEPALIVE_INTERVAL:
            return
        self._cancel_keepalive = async_track_time_interval(
            self.hass,
            self._async_keepalive,
            KEEPALIVE_INTERVAL,
        )

    def async_stop_keepalive(self) -> None:
        """Cancel the session keepalive timer if it is running."""
        if self._cancel_keepalive is None:
            return
        self._cancel_keepalive()
        self._cancel_keepalive = None

    @property
    def last_access_at(self) -> datetime | None:
        """Return when the last MyPolaris HTTP request completed."""
        return self._last_access_at

    @property
    def last_access_endpoint(self) -> str | None:
        """Return the last accessed MyPolaris endpoint path."""
        return self._last_access_endpoint

    @property
    def last_access_method(self) -> str | None:
        """Return the HTTP verb used for the last MyPolaris request."""
        return self._last_access_method

    @property
    def last_access_source(self) -> str | None:
        """Return the logical source of the last MyPolaris request."""
        return self._last_access_source

    @property
    def last_access_status(self) -> int | None:
        """Return the HTTP status of the last MyPolaris request."""
        return self._last_access_status

    @callback
    def async_add_access_listener(
        self, update_callback: Callable[[], None]
    ) -> Callable[[], None]:
        """Register a callback for last-access updates."""
        self._access_listeners.append(update_callback)

        @callback
        def _remove_listener() -> None:
            if update_callback in self._access_listeners:
                self._access_listeners.remove(update_callback)

        return _remove_listener

    @callback
    def _record_last_access(
        self,
        url: str,
        *,
        method: str,
        source: str,
        status: int | None,
    ) -> None:
        """Track the most recent MyPolaris endpoint access."""
        endpoint = url
        if url.startswith(BASE_URL):
            endpoint = url[len(BASE_URL):] or "/"

        self._last_access_at = datetime.now().astimezone()
        self._last_access_endpoint = endpoint
        self._last_access_method = method
        self._last_access_source = source
        self._last_access_status = status

        for listener in tuple(self._access_listeners):
            listener()

    async def _post_json(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        source: str = "refresh",
        referer: str | None = None,
    ) -> dict[str, Any]:
        """POST JSON and parse the ASP.NET ``{"d": ...}`` envelope."""
        headers = {**BASE_HEADERS, "Content-Type": "application/json; charset=utf-8"}
        if referer is not None:
            headers["Referer"] = referer
        if self.session_cookie:
            headers["Cookie"] = self._cookie_header()
        async with self.session.post(
            url,
            json=payload,
            headers=headers,
            allow_redirects=False,
        ) as resp:
            text = await resp.text()
            ctype = resp.headers.get("Content-Type", "")
            self._record_last_access(
                url,
                method="POST",
                source=source,
                status=resp.status,
            )
            if resp.status in (302, 401, 403):
                raise MyPolarisSessionExpired(
                    f"MyPolaris session expired or unauthorized (HTTP {resp.status})."
                )
            if "application/json" not in ctype and (
                "Login.aspx" in text or "autentific" in text.lower()
            ):
                raise MyPolarisSessionExpired(
                    "MyPolaris redirected the request to the login page."
                )
            if resp.status >= 400 or "application/json" not in ctype:
                raise UpdateFailed(
                    f"Unexpected response from {url} "
                    f"(status={resp.status}, ctype={ctype!r}): {text[:200]}"
                )
            try:
                return await resp.json(content_type=None)
            except (aiohttp.ContentTypeError, ValueError) as err:
                raise UpdateFailed(
                    f"Invalid JSON from {url}: {err} -- body: {text[:200]}"
                ) from err

    def _cookie_header(self) -> str:
        """Build a ``Cookie`` header value from the configured session cookie.

        Accepts a bare ASP.NET_SessionId value, an already-formatted
        ``ASP.NET_SessionId=...`` pair, or a full Cookie string with multiple pairs.
        """
        return build_cookie_header(self.session_cookie)

    def _extract_sitekey(self, html: str) -> str | None:
        for pat in SITEKEY_PATTERNS:
            m = re.search(pat, html)
            if m:
                return m.group(1)
        return None

    def _can_auto_login(self) -> bool:
        """Return whether the entry has enough data to refresh sessions."""
        return bool(self.email and self.password and self.api_key)

    async def _async_login(self) -> None:
        """Create a fresh authenticated MyPolaris ASP.NET session."""
        self._authenticated = False
        if not self.password.strip():
            raise UpdateFailed("MyPolaris password is required for email login.")
        if not self.api_key.strip():
            raise UpdateFailed("NopeCHA API key is required for email login.")

        async with self.session.get(
            LOGIN_URL,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
            allow_redirects=False,
        ) as resp:
            login_html = await resp.text()
            self._record_last_access(
                LOGIN_URL,
                method="GET",
                source="login",
                status=resp.status,
            )
            if resp.status != 200:
                raise UpdateFailed(f"Login.aspx returned HTTP {resp.status}")

        sitekey = self._extract_sitekey(login_html)
        if not sitekey:
            raise UpdateFailed(
                "Could not find reCAPTCHA sitekey on Login.aspx. "
                "The page layout may have changed."
            )

        token = await solve_recaptcha_with_nopecha(
            self.session,
            self.api_key,
            sitekey,
            LOGIN_URL,
        )

        auth_payload = {
            "Email": self.email,
            "Parola": self.password,
            "Cod": "",
            "token": token,
        }
        auth_resp = await self._post_json(
            AUTH_URL,
            auth_payload,
            source="login",
        )
        d = auth_resp.get("d") or {}
        if d.get("Login2Steps"):
            raise UpdateFailed(
                "2FA is enabled on this MyPolaris account - not supported."
            )
        if not d.get("EsteOK"):
            msg = (
                d.get("MesajEroare")
                or d.get("MesajCustom")
                or d.get("Mesaj")
                or "unknown error"
            )
            raise UpdateFailed(f"Login failed: {msg}")

        self._authenticated = True

    @staticmethod
    def _parse_money(raw: Any) -> float | None:
        return _parse_money_helper(raw)

    @staticmethod
    def _year_from_dmy(raw: Any) -> int | None:
        """Extract the year from a ``DD.MM.YYYY`` string."""
        return _year_from_dmy_helper(raw)

    def _normalize_invoice(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Normalize invoice rows returned by different MyPolaris endpoints."""
        return {
            "NrDocument": raw.get("NrDocument"),
            "SerieDocument": raw.get("SerieDocument"),
            "DataDocument": raw.get("DataDocument_Proxy"),
            "DataScadenta": raw.get("DataScadenta_Proxy"),
            "Valoare": self._parse_money(raw.get("Valoare_Proxy") or raw.get("Valoare")),
            "Rest": self._parse_money(raw.get("Rest_Proxy") or raw.get("Rest")),
            "Moneda": raw.get("MonedaCod"),
            "DePlata": bool(raw.get("DePlata")),
            "IdFactura": raw.get("IdFactura"),
            "IdContract": raw.get("IdContract"),
        }

    async def _async_keepalive(self, _now: datetime) -> None:
        """Send a lightweight authenticated request to keep the session warm."""
        try:
            keepalive_resp = await self._post_json(
                INIT_URL,
                {},
                source="keepalive",
                referer=HOME_URL,
            )
        except MyPolarisSessionExpired as err:
            self._authenticated = False
            _LOGGER.debug("MyPolaris keepalive found an expired session: %s", err)
            return
        except UpdateFailed as err:
            _LOGGER.debug("MyPolaris keepalive failed: %s", err)
            return

        if not (keepalive_resp.get("d") or {}).get("EsteOK"):
            _LOGGER.debug(
                "MyPolaris keepalive returned unexpected payload: %s",
                keepalive_resp,
            )

    async def _fetch_location(self, loc: dict[str, str]) -> dict[str, Any]:
        """Fetch sold/facturi/plati for a single PdL and aggregate them."""
        pdl_id = loc["id"]
        denumire = loc.get("denumire") or "Necunoscut"

        sold_resp = await self._post_json(SOLD_URL, {"IdPunctDeLucru": pdl_id})
        sold_d = sold_resp.get("d") or {}
        sold = self._parse_money(sold_d.get("Sold"))
        sold_table = sold_d.get("SoldTable") or []

        facturi: list[dict[str, Any]] = []
        try:
            fac_resp = await self._post_json(
                FACTURI_URL, {"IdPunctDeLucru": pdl_id}
            )
            fac_d = fac_resp.get("d") or {}
            if fac_d.get("EsteOK"):
                for f in fac_d.get("Facturi") or []:
                    facturi.append(self._normalize_invoice(f))
        except UpdateFailed as err:
            _LOGGER.warning("Could not load invoices for PdL %s: %s", pdl_id, err)

        plati: list[dict[str, Any]] = []
        try:
            pl_resp = await self._post_json(
                PLATI_URL, {"IdPunctDeLucru": pdl_id}
            )
            pl_d = pl_resp.get("d") or {}
            if pl_d.get("EsteOK"):
                for p in pl_d.get("Plati") or []:
                    plati.append({
                        "NrDoc": p.get("NrDoc"),
                        "TipDoc": p.get("TipDoc"),
                        "DataDoc": p.get("DataDoc_Proxy"),
                        "Suma": self._parse_money(p.get("Suma_Proxy") or p.get("Suma")),
                        "Moneda": p.get("MonedaCod"),
                        "IdRegistru": p.get("IdRegistru"),
                    })
        except UpdateFailed as err:
            _LOGGER.warning("Could not load payments for PdL %s: %s", pdl_id, err)

        # LoadDataSold is the authoritative source for current outstanding
        # balances; LoadDataFacturi can lag behind or expose DePlata=0 even when
        # a row still has a non-zero Rest.
        facturi_neplatite = [
            self._normalize_invoice(f)
            for f in sold_table
            if (self._parse_money(f.get("Rest_Proxy") or f.get("Rest")) or 0.0) > 0
        ]
        if not facturi_neplatite:
            facturi_neplatite = [
                f for f in facturi if ((f.get("Rest") or 0.0) > 0 or f["DePlata"])
            ]
        facturi_neplatite_total = round(
            sum((f["Rest"] or f["Valoare"] or 0.0) for f in facturi_neplatite), 2
        )

        facturi_by_year: dict[int, list[dict[str, Any]]] = {}
        for f in facturi:
            y = self._year_from_dmy(f.get("DataDocument"))
            if y is not None:
                facturi_by_year.setdefault(y, []).append(f)

        plati_by_year: dict[int, list[dict[str, Any]]] = {}
        for p in plati:
            y = self._year_from_dmy(p.get("DataDoc"))
            if y is not None:
                plati_by_year.setdefault(y, []).append(p)

        facturi_count_by_year = {
            y: len(items) for y, items in facturi_by_year.items()
        }
        plati_sum_by_year = {
            y: round(sum((p["Suma"] or 0.0) for p in items), 2)
            for y, items in plati_by_year.items()
        }

        if sold is None:
            sold_factura = None
        elif round(sold, 2) == 0.0:
            sold_factura = "Nu"
        else:
            sold_factura = f"{sold:.2f} RON"

        return {
            "id": pdl_id,
            "denumire": denumire,
            "sold_curent": sold,
            "sold_factura": sold_factura,
            "facturi": facturi,
            "plati": plati,
            "facturi_neplatite": facturi_neplatite,
            "facturi_neplatite_count": len(facturi_neplatite),
            "facturi_neplatite_total": facturi_neplatite_total,
            "facturi_by_year": facturi_by_year,
            "plati_by_year": plati_by_year,
            "facturi_count_by_year": facturi_count_by_year,
            "plati_sum_by_year": plati_sum_by_year,
            "years": sorted(set(facturi_by_year) | set(plati_by_year)),
        }

    async def _async_fetch_authenticated_data(self) -> dict[str, Any]:
        """Fetch all MyPolaris data using the current authenticated session."""
        loc_resp = await self._post_json(LOCATII_URL, {"tip": "0"})
        loc_d = loc_resp.get("d") or {}
        if not loc_d.get("EsteOK"):
            msg = (
                loc_d.get("MesajEroare")
                or loc_d.get("MesajCustom")
                or loc_d.get("Mesaj")
                or ""
            )
            _LOGGER.debug("GetListaLocatii raw payload: %s", loc_resp)
            if (
                not msg
                or "autenti" in msg.lower()
                or "login" in msg.lower()
                or "sesi" in msg.lower()
            ):
                raise MyPolarisSessionExpired(
                    f"GetListaLocatii failed because the session expired: "
                    f"{msg or 'EsteOK=false'}"
                )
            raise UpdateFailed(f"GetListaLocatii failed: {msg or 'EsteOK=false'}.")
        lista_raw = loc_d.get("lista") or []
        if not lista_raw:
            raise UpdateFailed("No locations returned by GetListaLocatii.")

        locatii = [
            {"id": str(loc.get("ID")), "denumire": loc.get("Denumire", "")}
            for loc in lista_raw
            if loc.get("ID") is not None
        ]

        # Fetch SOLD / FACTURI / PLATI for every location in parallel.
        per_loc = await asyncio.gather(*(self._fetch_location(loc) for loc in locatii))
        by_locatie: dict[str, dict[str, Any]] = {
            loc["id"]: bucket for loc, bucket in zip(locatii, per_loc)
        }

        # Keep a "primary" pointer (first location) for any legacy
        # consumers and for the integration-level device naming.
        primary = locatii[0]
        primary_bucket = by_locatie[primary["id"]]

        return {
            "locatii": locatii,
            "by_locatie": by_locatie,
            "primary_locatie_id": primary["id"],
            "primary_locatie_denumire": primary["denumire"],
            "ultima_actualizare": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            # Back-compat top-level mirrors (primary location).
            "denumire": primary_bucket.get("denumire"),
            "contract_date": primary_bucket.get("denumire"),
            "sold_curent": primary_bucket.get("sold_curent"),
            "sold_factura": primary_bucket.get("sold_factura"),
            "pdl_id": primary["id"],
            "locatie_id": primary["id"],
            "locatie_denumire": primary["denumire"],
        }

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            if not self.session_cookie and not self._authenticated:
                await self._async_login()

            try:
                return await self._async_fetch_authenticated_data()
            except MyPolarisSessionExpired as err:
                self._authenticated = False
                if self.session_cookie:
                    raise UpdateFailed(
                        "MyPolaris session expired. Paste a fresh "
                        "ASP.NET_SessionId cookie from your browser, or "
                        "configure email/password with a NopeCHA API key."
                    ) from err
                if not self._can_auto_login():
                    raise

                _LOGGER.info(
                    "MyPolaris session expired; refreshing it with NopeCHA."
                )
                await self._async_login()
                return await self._async_fetch_authenticated_data()

        except UpdateFailed:
            raise
        except Exception as err:
            _LOGGER.exception("MyPolaris update failed")
            raise UpdateFailed(f"Polaris: {err}") from err

    async def async_unload(self) -> None:
        """Stop coordinator-owned timers."""
        self.async_stop_keepalive()
