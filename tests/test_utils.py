"""Unit tests for pure MyPolaris helper functions."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

_UTILS_PATH = (
    Path(__file__).resolve().parents[1] / "custom_components" / "mypolaris" / "utils.py"
)
_SPEC = importlib.util.spec_from_file_location("mypolaris_utils", _UTILS_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

build_cookie_header = _MODULE.build_cookie_header
format_ron = _MODULE.format_ron
localize_access_source = _MODULE.localize_access_source
month_name = _MODULE.month_name
parse_money = _MODULE.parse_money
slug_for_entity_id = _MODULE.slug_for_entity_id
sort_by_dmy = _MODULE.sort_by_dmy
year_from_dmy = _MODULE.year_from_dmy


class TestMyPolarisHelpers(unittest.TestCase):
    def test_build_cookie_header_accepts_bare_value(self) -> None:
        self.assertEqual(
            build_cookie_header("abc123"),
            "ASP.NET_SessionId=abc123",
        )

    def test_build_cookie_header_keeps_explicit_cookie_pair(self) -> None:
        self.assertEqual(
            build_cookie_header("ASP.NET_SessionId=abc123;"),
            "ASP.NET_SessionId=abc123",
        )

    def test_parse_money_handles_romanian_formats(self) -> None:
        self.assertEqual(parse_money("1.234,56 RON"), 1234.56)
        self.assertEqual(parse_money("79,36"), 79.36)
        self.assertEqual(parse_money(10), 10.0)
        self.assertIsNone(parse_money("not-a-number"))

    def test_year_from_dmy_extracts_year(self) -> None:
        self.assertEqual(year_from_dmy("08.06.2026"), 2026)
        self.assertIsNone(year_from_dmy("2026-06-08"))

    def test_format_ron_uses_comma_decimal_separator(self) -> None:
        self.assertEqual(format_ron(12.5), "12,50")
        self.assertEqual(format_ron(None), "0,00")

    def test_month_name_returns_romanian_name(self) -> None:
        self.assertEqual(month_name("08.06.2026"), "iunie")
        self.assertEqual(month_name("bad-value"), "necunoscut")

    def test_slug_for_entity_id_normalizes_separators(self) -> None:
        self.assertEqual(
            slug_for_entity_id("Sediul Social / Focsani (Romania)"),
            "sediul_social_focsani_romania",
        )

    def test_localize_access_source_translates_known_labels(self) -> None:
        self.assertEqual(localize_access_source("keepalive"), "mentinere sesiune")
        self.assertEqual(localize_access_source("login"), "autentificare")
        self.assertEqual(localize_access_source("refresh"), "actualizare")
        self.assertEqual(localize_access_source("custom"), "custom")
        self.assertIsNone(localize_access_source(None))

    def test_sort_by_dmy_orders_valid_dates(self) -> None:
        rows = [
            {"DataDocument": "03.05.2026", "id": "may"},
            {"DataDocument": "07.01.2026", "id": "jan"},
            {"DataDocument": "15.03.2026", "id": "mar"},
        ]

        result = sort_by_dmy(rows, "DataDocument")

        self.assertEqual([row["id"] for row in result], ["jan", "mar", "may"])


if __name__ == "__main__":
    unittest.main()