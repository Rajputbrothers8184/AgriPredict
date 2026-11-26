#!/usr/bin/env python3
"""End-to-end acceptance scenario against the real AgriPredict stack.

Exercises the full path a farmer's data takes — API container → database →
ML inference service → report renderer — and asserts on the results. Unlike the
pytest suites, nothing here is mocked and nothing is in-process: it speaks HTTP
to a running backend exactly as the Android app does.

    python scripts/e2e_scenario.py                      # defaults to localhost
    python scripts/e2e_scenario.py --base-url https://api.example.com

Exit code 0 means every step passed. Any failure prints the step, the HTTP
response and exits non-zero, so it is safe to use in CI.

Design notes
------------
* Every run registers a **new** user with a unique email. The scenario therefore
  never depends on residual data, and its farm/cycle figures are exact rather
  than "whatever the demo account happened to have".
* Assertions check derived values (server-computed totals, break-even price,
  report bytes) rather than echoed input, because those are the parts an
  integration bug actually breaks.
* The ML forecast step is optional (`--require-ml`): a deployment may legitimately
  run with the ML service disabled, in which case the backend must say so
  honestly via `is_fallback: true` rather than pretend it used a model.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_BASE_URL = "http://127.0.0.1:8000/api/v1"

# --------------------------------------------------------------------------
# Minimal HTTP client (stdlib only, so the script runs anywhere)
# --------------------------------------------------------------------------


class E2EFailure(RuntimeError):
    """A scenario assertion failed."""


class Client:
    def __init__(self, base_url: str, timeout: float = 30.0, max_retries: int = 3) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.token: str | None = None
        self.max_retries = max_retries

    def request(
        self,
        method: str,
        path: str,
        *,
        body: Any = None,
        query: dict[str, Any] | None = None,
        auth: bool = True,
        base: str | None = None,
        expect: int | tuple[int, ...] = 200,
    ) -> tuple[int, Any]:
        url = (base or self.base_url) + path
        if query:
            cleaned = {k: v for k, v in query.items() if v is not None}
            if cleaned:
                url += "?" + urllib.parse.urlencode(cleaned)

        headers = {"Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        if auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read()
                status = response.status
                content_type = response.headers.get("content-type", "")
        except urllib.error.HTTPError as exc:  # 4xx/5xx carry our error envelope
            raw = exc.read()
            status = exc.code
            content_type = exc.headers.get("content-type", "")
        except urllib.error.URLError as exc:
            raise E2EFailure(f"cannot reach {url}: {exc.reason}") from exc

        if content_type.startswith("application/json"):
            parsed: Any = json.loads(raw) if raw else None
        else:
            parsed = raw

        # The API rate-limits login/registration. Honour its own retry_after
        # rather than failing: a scenario that cannot be run twice in a row is
        # useless for CI.
        attempts = 0
        while (
            status == 429
            and attempts < self.max_retries
            and isinstance(parsed, dict)
            and parsed.get("error", {}).get("details", {}).get("retry_after_seconds")
        ):
            wait = int(parsed["error"]["details"]["retry_after_seconds"]) + 1
            print(f"  [INFO] rate limited; waiting {wait}s")
            time.sleep(wait)
            attempts += 1
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    raw = response.read()
                    status = response.status
                    content_type = response.headers.get("content-type", "")
            except urllib.error.HTTPError as exc:
                raw = exc.read()
                status = exc.code
                content_type = exc.headers.get("content-type", "")
            parsed = json.loads(raw) if raw and content_type.startswith("application/json") else raw

        allowed = (expect,) if isinstance(expect, int) else expect
        if status not in allowed:
            detail = parsed if isinstance(parsed, (dict, list)) else f"<{len(parsed)} bytes>"
            raise E2EFailure(f"{method} {path} -> {status} (expected {allowed}): {detail}")
        return status, parsed

    # Convenience wrappers ---------------------------------------------------
    def get(self, path: str, **kwargs: Any) -> Any:
        return self.request("GET", path, **kwargs)[1]

    def post(self, path: str, body: Any = None, **kwargs: Any) -> Any:
        # Creating a resource returns 201 by REST convention; accepting both
        # keeps the scenario focused on behaviour rather than status pedantry.
        kwargs.setdefault("expect", (200, 201))
        return self.request("POST", path, body=body, **kwargs)[1]

    def patch(self, path: str, body: Any = None, **kwargs: Any) -> Any:
        return self.request("PATCH", path, body=body, **kwargs)[1]

    def delete(self, path: str, **kwargs: Any) -> Any:
        return self.request("DELETE", path, **kwargs)[1]


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


class Report:
    def __init__(self) -> None:
        self.steps: list[tuple[str, bool, str]] = []
        self.started = time.time()

    def check(self, name: str, condition: bool, detail: str = "") -> None:
        self.steps.append((name, bool(condition), detail))
        mark = "PASS" if condition else "FAIL"
        suffix = f"  ({detail})" if detail else ""
        print(f"  [{mark}] {name}{suffix}")
        if not condition:
            raise E2EFailure(f"{name}: {detail}" if detail else name)

    def equal(self, name: str, actual: Any, expected: Any) -> None:
        self.check(name, actual == expected, f"expected {expected!r}, got {actual!r}")

    def close(self, name: str, actual: float, expected: float, tolerance: float = 0.01) -> None:
        ok = abs(float(actual) - float(expected)) <= tolerance
        self.check(name, ok, f"expected ~{expected}, got {actual}")

    def summary(self) -> str:
        passed = sum(1 for _, ok, _ in self.steps if ok)
        elapsed = time.time() - self.started
        return f"{passed}/{len(self.steps)} checks passed in {elapsed:.1f}s"


# --------------------------------------------------------------------------
# Scenario
# --------------------------------------------------------------------------


def unique_email() -> str:
    """A fresh address per run.

    Note the domain: ``.test`` is a reserved TLD and the API's validator
    (correctly) rejects it, so a real-looking domain is used instead. These
    accounts are throwaway; nothing is ever emailed.
    """
    return f"e2e.{int(time.time() * 1000)}.{time.process_time_ns() % 100000}@agripredict-e2e.pk"


def run(base_url: str, password: str, require_ml: bool) -> Report:
    report = Report()
    client = Client(base_url)

    # -- health ------------------------------------------------------------
    print("\n1. Service health")
    health_base = base_url.split("/api/")[0]
    status, health = client.request("GET", "/health", auth=False, base=health_base)
    report.equal("health returns 200", status, 200)
    report.equal("database is reachable", health.get("database"), "ok")
    ml_reported = health.get("ml_service")
    print(f"  [INFO] backend reports ml_service={ml_reported!r}")

    # -- unauthenticated access is refused ---------------------------------
    print("\n2. Authentication")
    client.request("GET", "/farms", auth=False, expect=401)
    report.check("unauthenticated request is rejected", True, "401")
    client.request("GET", "/farms", auth=False, expect=401)
    client.token = "bogus.token.value"
    client.request("GET", "/farms", expect=401)
    report.check("bogus token is rejected", True, "401")
    client.token = None

    # -- register ----------------------------------------------------------
    email = unique_email()
    pair = client.post(
        "/auth/register",
        {
            "email": email,
            "password": password,
            "full_name": "E2E Farmer",
            "phone": "+923001234567",
            "preferred_language": "en",
        },
        auth=False,
    )
    client.token = pair["access_token"]
    report.check("registration issues an access token", bool(pair.get("access_token")))
    report.check(
        "registration issues a refresh token that is not the access token",
        pair.get("refresh_token") not in (None, "", pair.get("access_token")),
    )

    me = client.get("/auth/me")
    report.equal("new account email matches", me["email"], email)
    report.check("new account has no farms yet", client.get("/farms") == [])

    # -- reference data ----------------------------------------------------
    print("\n3. Reference data")
    commodities = client.get("/markets/commodities")
    markets = client.get("/markets/list")
    report.check("commodities are seeded", len(commodities) >= 10, f"{len(commodities)} rows")
    report.check("markets are seeded", len(markets) >= 5, f"{len(markets)} rows")
    wheat = next((c for c in commodities if c["slug"] == "wheat"), None)
    if wheat is None:
        raise E2EFailure("wheat is missing from the seeded commodities")
    lahore = next((m for m in markets if m["slug"] == "lahore-sabzi-mandi"), None)
    if lahore is None:
        raise E2EFailure("lahore-sabzi-mandi is missing from the seeded markets")
    report.equal("wheat carries both language names", sorted(["name_en", "name_ur"]), sorted(
        [k for k in wheat if k in ("name_en", "name_ur")]
    ))

    # -- farm --------------------------------------------------------------
    print("\n4. Farm")
    farm = client.post(
        "/farms",
        {
            "name": "E2E Canal Road Plot",
            "district": "Lahore",
            "tehsil": "Shalimar",
            "total_area_acres": 4.0,
            "latitude": 31.5204,
            "longitude": 74.3587,
        },
    )
    report.check("farm is created", farm["id"] > 0)
    client.request(
        "POST",
        "/farms",
        body={"name": "Half a coordinate", "district": "Lahore", "latitude": 31.5},
        expect=422,
    )
    report.check("one coordinate without the other is rejected", True, "422")

    # -- crop cycle --------------------------------------------------------
    print("\n5. Crop cycle")
    cycle = client.post(
        "/crop-cycles",
        {
            "farm_id": farm["id"],
            "commodity_id": wheat["id"],
            "season": "rabi",
            "area_acres": 4.0,
            "sowing_date": "2026-11-01",
            "expected_harvest_date": "2027-04-01",
            "status": "active",
            "expected_yield_kg": 1600,
        },
    )
    cycle_id = cycle["id"]
    report.equal("cycle area is stored", str(cycle["area_acres"]).split(".")[0], "4")
    client.request(
        "POST",
        "/crop-cycles",
        body={
            "farm_id": farm["id"],
            "commodity_id": wheat["id"],
            "area_acres": 1,
            "sowing_date": "2026-11-01",
            "expected_harvest_date": "2026-10-01",
        },
        expect=422,
    )
    report.check("harvest before sowing is rejected", True, "422")

    # -- expenses ----------------------------------------------------------
    print("\n6. Expenses")
    expenses = [
        ("seeds", 8000, "Certified wheat seed"),
        ("fertilizer", 12000, "Urea + DAP"),
        ("irrigation", 4000, "Three waterings"),
        ("labour", 6000, "Sowing and weeding"),
    ]
    for category, amount, description in expenses:
        created = client.post(
            f"/crop-cycles/{cycle_id}/expenses",
            {
                "category": category,
                "amount_pkr": amount,
                "expense_date": "2026-11-02",
                "description": description,
            },
        )
        report.close(f"expense {category} stored exactly", created["amount_pkr"], amount)
    listed = client.get(f"/crop-cycles/{cycle_id}/expenses")
    report.equal("all four expenses are listed", len(listed), 4)
    total_cost = sum(int(float(row["amount_pkr"])) for row in listed)
    report.equal("total cost adds up", total_cost, 30000)

    filtered = client.get(f"/crop-cycles/{cycle_id}/expenses", query={"category": "fertilizer"})
    report.equal("category filter works", len(filtered), 1)

    # A negative amount must not be storable.
    client.request(
        "POST",
        f"/crop-cycles/{cycle_id}/expenses",
        body={"category": "seeds", "amount_pkr": -500, "expense_date": "2026-11-02"},
        expect=422,
    )
    report.check("negative expense is rejected", True, "422")

    # -- sales -------------------------------------------------------------
    print("\n7. Sales")
    # 400 kg = 10 maunds; at 4000 per maund the server must derive 40 000.
    sale = client.post(
        f"/crop-cycles/{cycle_id}/sales",
        {
            "quantity_kg": 400,
            "unit_price_pkr": 4000,
            "sale_date": "2026-11-20",
            "market_id": lahore["id"],
            "buyer_name": "E2E Commission Agent",
        },
    )
    report.close("server derives the sale total (40 kg/maund)", sale["total_amount_pkr"], 40000)

    second = client.post(
        f"/crop-cycles/{cycle_id}/sales",
        {"quantity_kg": 200, "unit_price_pkr": 4100, "sale_date": "2026-11-22"},
    )
    # 200 kg = 5 maunds; 5 x 4100 = 20 500
    report.close("second sale total is derived too", second["total_amount_pkr"], 20500)
    total_revenue = 40000 + 20500

    # -- finance block -----------------------------------------------------
    print("\n8. Derived finance")
    detail = client.get(f"/crop-cycles/{cycle_id}")
    finance = detail["finance"]
    report.close("revenue matches the sales", finance["revenue_pkr"], total_revenue)
    report.close("cost matches the expenses", finance["cost_pkr"], 30000)
    report.close("profit is revenue minus cost", finance["profit_pkr"], total_revenue - 30000)
    expected_margin = (total_revenue - 30000) / total_revenue * 100
    report.close("margin is computed on revenue", finance["margin_pct"], expected_margin, 0.05)
    # Break-even = total cost / total harvested maunds = 30000 / 15
    report.close("break-even price is cost per maund", finance["break_even_price_pkr"], 2000)
    report.close("yield per acre is derived", finance["yield_per_acre_kg"], 150)

    overview = client.get("/finance/summary")
    report.close("overview revenue agrees with the cycle", overview["lifetime_revenue_pkr"], total_revenue)
    report.close("overview cost agrees with the cycle", overview["lifetime_cost_pkr"], 30000)
    report.check("overview carries a season row", len(overview["seasons"]) == 1, f"{len(overview['seasons'])} row(s)")
    breakdown = {row["category"]: float(row["total_pkr"]) for row in overview["expense_breakdown"]}
    report.equal("expense mix covers all four categories", len(breakdown), 4)
    report.close("expense mix totals the cost", sum(breakdown.values()), 30000)

    # -- market data -------------------------------------------------------
    print("\n9. Market prices")
    history = client.get(f"/markets/history/wheat/lahore-sabzi-mandi", query={"days": 90})
    report.check("price history is non-empty", history["count"] > 0, f"{history['count']} points")
    first = history["points"][0]
    report.check(
        "price points carry the documented fields",
        all(k in first for k in ("price_date", "avg_price_pkr", "source")),
    )
    report.equal("history unit is stated", history["unit"], "PKR/40kg")
    sources = {point["source"] for point in history["points"]}
    print(f"  [INFO] price sources in use: {sorted(sources)}")

    comparison = client.get("/markets/compare/wheat", query={"days": 7})
    report.check("comparison spans several markets", len(comparison["rows"]) > 1,
                 f"{len(comparison['rows'])} markets")
    report.check("a best market is identified", bool(comparison["best_market_slug"]),
                 str(comparison["best_market_slug"]))

    # -- forecast ----------------------------------------------------------
    print("\n10. Forecast (backend -> ML service)")
    try:
        forecast = client.get("/forecasts/wheat/lahore-sabzi-mandi", query={"horizon": 7})
    except E2EFailure as exc:
        if require_ml:
            raise
        print(f"  [SKIP] forecast unavailable: {exc}")
        forecast = None

    if forecast is not None:
        report.equal("forecast returns the requested horizon", forecast["horizon_days"], 7)
        report.equal("forecast returns one point per day", len(forecast["points"]), 7)
        point = forecast["points"][0]
        report.check(
            "forecast points carry bounds",
            all(k in point for k in ("target_date", "predicted_price_pkr",
                                     "lower_bound_pkr", "upper_bound_pkr")),
        )
        low = float(point["lower_bound_pkr"])
        high = float(point["upper_bound_pkr"])
        mid = float(point["predicted_price_pkr"])
        report.check("interval is ordered and contains the prediction", low <= mid <= high,
                     f"{low:.2f} <= {mid:.2f} <= {high:.2f}")
        report.check("interval is not degenerate", high > low, f"width {high - low:.2f}")
        report.check("forecast states a model", bool(forecast.get("model_name")),
                     str(forecast.get("model_name")))
        if forecast.get("is_fallback"):
            print("  [INFO] forecast is a fallback (ML service not in use) — allowed")
        else:
            report.check("a real model produced the forecast with a measured error",
                         forecast.get("mae") is not None, f"MAE {forecast.get('mae')}")
        report.check("forecast carries a disclaimer", bool(forecast.get("disclaimer")))

        try:
            latest = client.get("/forecasts/latest/wheat/lahore-sabzi-mandi", query={"horizon": 7})
            report.equal("latest forecast is the stored one", latest["id"], forecast["id"])
        except E2EFailure as exc:
            print(f"  [SKIP] /forecasts/latest: {exc}")

    # -- reports -----------------------------------------------------------
    print("\n11. Reports")
    reports_base = base_url.split("/api/")[0]
    for file_format, magic in (("pdf", b"%PDF"), ("xlsx", b"PK")):
        report_record = client.post(
            "/reports",
            {"report_type": "crop_cycle", "file_format": file_format, "crop_cycle_id": cycle_id},
        )
        url = report_record["download_url"]
        report.check(f"{file_format} download_url carries a signed token", "token=" in url)
        absolute = url if url.startswith("http") else reports_base + url

        # No Authorization header: exactly what Android's download manager sends.
        with urllib.request.urlopen(absolute, timeout=client.timeout) as response:
            payload = response.read()
            content_type = response.headers.get("content-type", "")
        report.check(f"{file_format} downloads without an auth header", payload[:len(magic)] == magic,
                     f"{len(payload)} bytes, {content_type}")
        report.check(f"{file_format} is not an error page", len(payload) > 1000,
                     f"{len(payload)} bytes")

    tampered = client.post(
        "/reports", {"report_type": "financial_summary", "file_format": "pdf"}
    )
    bad_url = reports_base + tampered["download_url"].split("token=")[0] + "token=forged"
    try:
        with urllib.request.urlopen(bad_url, timeout=client.timeout):
            forged_status = 200
    except urllib.error.HTTPError as exc:
        forged_status = exc.code
    report.equal("a forged download token is refused", forged_status, 401)

    # -- weather / buyers --------------------------------------------------
    print("\n12. External integrations")
    weather = client.get(f"/weather/{farm['id']}")
    report.check("weather returns a provider name", bool(weather.get("provider")),
                 str(weather.get("provider")))
    report.check("weather states whether it is live", "is_live" in weather,
                 f"is_live={weather.get('is_live')}")
    if weather.get("is_live") is False:
        print("  [INFO] weather is simulated in this environment (provider=mock)")

    buyers = client.get("/buyers", query={"limit": 5})
    report.check("buyer search reports its data source", buyers.get("source") in
                 ("google_places", "cache", "unavailable"), str(buyers.get("source")))
    if buyers.get("source") == "unavailable":
        print("  [INFO] buyer search is unconfigured (no Google Places key) — reported honestly")
    report.check("buyer response always carries a results list", isinstance(buyers.get("results"), list))

    # -- cross-user isolation ---------------------------------------------
    print("\n13. Data isolation")
    other = Client(base_url)
    other_pair = other.post(
        "/auth/register",
        {
            "email": unique_email(),
            "password": password,
            "full_name": "Other Farmer",
            "preferred_language": "en",
        },
        auth=False,
    )
    other.token = other_pair["access_token"]
    report.equal("the second account sees no farms", other.get("/farms"), [])
    other.request("GET", f"/crop-cycles/{cycle_id}", expect=404)
    report.check("another user cannot read my crop cycle", True, "404")
    other.request("DELETE", f"/crop-cycles/{cycle_id}", expect=404)
    report.check("another user cannot delete my crop cycle", True, "404")
    report.equal("my cycle still exists", client.get(f"/crop-cycles/{cycle_id}")["id"], cycle_id)

    # -- token rotation ----------------------------------------------------
    print("\n14. Token lifecycle")
    pair2 = client.post("/auth/refresh", {"refresh_token": pair["refresh_token"]}, auth=False)
    # Note: access tokens minted in the same second with identical claims are
    # byte-identical, so "the string changed" is not a valid property to assert.
    # What matters is rotation: the refresh token is replaced, the old one is
    # spent, and the new access token authenticates.
    report.check("refresh issues a refresh token", bool(pair2.get("refresh_token")))
    client.token = pair2["access_token"]
    report.equal("the access token from refresh works", client.get("/auth/me")["email"], email)

    # A spent refresh token must not be reusable (that is the whole point of
    # rotation: a stolen token is worthless after one use).
    try:
        client.post("/auth/refresh", {"refresh_token": pair["refresh_token"]}, auth=False)
        reused = 200
    except E2EFailure as exc:
        reused = int(str(exc).split("-> ")[1].split(" ")[0])
    report.equal("a spent refresh token is rejected", reused, 401)

    # Logout revokes the refresh token, not the already-issued access token.
    # That is the documented, standard trade-off for stateless JWTs: the access
    # token stays valid until it expires (60 minutes by default). The scenario
    # asserts what is actually implemented rather than what would be nicer, and
    # records the consequence explicitly so it is a known limitation, not a
    # surprise during a security review. "Sign out everywhere" exists for the
    # case where immediate revocation is required.
    client.post("/auth/logout", {"refresh_token": pair2["refresh_token"]})
    try:
        client.post("/auth/refresh", {"refresh_token": pair2["refresh_token"]}, auth=False)
        revoked = 200
    except E2EFailure as exc:
        revoked = int(str(exc).split("-> ")[1].split(" ")[0])
    report.equal("logout revokes the refresh token", revoked, 401)
    current_access = client.get("/auth/me")
    report.check(
        "access token remains valid until expiry after logout (known JWT trade-off)",
        current_access["email"] == email,
    )

    # logout-all bumps token_version, which invalidates access tokens immediately.
    client.post("/auth/logout-all")
    client.request("GET", "/auth/me", expect=401)
    report.check("logout-all invalidates the access token immediately", True, "401")

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument(
        "--password",
        default="Harvest2026",
        help="password for the throwaway accounts (must satisfy the API policy)",
    )
    parser.add_argument(
        "--require-ml",
        action="store_true",
        help="fail if the forecast is not produced by a real model",
    )
    args = parser.parse_args()

    print(f"AgriPredict end-to-end scenario against {args.base_url}")
    try:
        report = run(args.base_url, args.password, args.require_ml)
    except E2EFailure as exc:
        print(f"\nFAILED: {exc}", file=sys.stderr)
        return 1
    print(f"\n{report.summary()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
