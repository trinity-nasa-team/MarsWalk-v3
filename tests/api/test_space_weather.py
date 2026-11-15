"""Clima espacial (DONKI) servido por el backend: sin red, con respuestas falsas de CCMC."""

import http.client
import json
import threading
import time
import urllib.error
from datetime import UTC, datetime

import pytest

from marsmap.data import space_weather
from marsmap.data.space_weather import SpaceWeather, from_snapshot, mars_impacts, summarize
from tests.api.conftest import make_client

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)


def _cme(cid, start, arrival, glancing, accurate=True, loc="Mars"):
    return {"activityID": cid, "startTime": start, "cmeAnalyses": [
        {"isMostAccurate": accurate, "enlilList": [{"impactList": [
            {"location": loc, "arrivalTime": arrival, "isGlancingBlow": glancing}]}]}]}  # fmt: skip


CMES = [
    _cme("A", "2026-11-01T00:00Z", "2026-11-04T00:00Z", False),
    _cme("B", "2026-11-09T18:15Z", "2026-11-13T12:00Z", True),
    _cme("T", "2026-11-10T00:00Z", "2026-11-12T00:00Z", False, loc="Earth"),  # solo Tierra
    _cme("OLD", "2026-09-01T00:00Z", "2026-09-05T00:00Z", False),  # fuera de 30 días
]
SEPS = [
    {"sepID": "s1", "eventTime": "2026-11-13T05:00Z"},
    {"sepID": "s0", "eventTime": "2026-11-01T00:00Z"},
]


def test_mars_impacts_only_mars_and_sorted():
    m = mars_impacts(CMES)
    assert [c["id"] for c in m] == ["OLD", "A", "B"]
    assert m[-1] == {
        "id": "B",
        "start": "2026-11-09T18:15Z",
        "arrival": "2026-11-13T12:00Z",
        "glancing": True,
    }


def test_mars_impacts_prefers_most_accurate_analysis():
    c = _cme("X", "2026-11-05T00:00Z", "2026-11-08T00:00Z", False, accurate=False)
    c["cmeAnalyses"].append({"isMostAccurate": True, "enlilList": [{"impactList": []}]})
    assert mars_impacts([c]) == []  # el análisis más preciso no predice llegada a Marte


def test_summarize_windows():
    s = summarize(SEPS, mars_impacts(CMES), NOW)
    assert [e["id"] for e in s["sep"]] == ["s1"]  # solo 72 h
    assert s["mars_cme"]["id"] == "B" and s["mars_cme_30d"] == 2
    assert s["as_of"] == "2026-11-14T12:00Z"


def test_live_then_cached():
    calls = []

    def fake(url):
        calls.append(url)
        return json.dumps(SEPS if "/SEP?" in url else CMES).encode()

    sw = SpaceWeather(fetch=fake, clock=lambda: NOW.timestamp())
    v = sw.get()
    assert v["status"] == "live" and v["mars_cme"]["id"] == "B"
    assert all(u.startswith("https://ccmc.gsfc.nasa.gov/DONKI-API/get/") for u in calls)
    sw.get()
    assert len(calls) == 2  # caché de 1 h


def test_falls_back_to_snapshot_when_ccmc_down():
    def down(_):
        raise TimeoutError("sin red")

    v = SpaceWeather(fetch=down, clock=lambda: NOW.timestamp()).get()
    assert v["status"] == "snapshot"
    assert v == from_snapshot()
    assert v["as_of"].startswith("2026-11-14")


def test_endpoint(data_dir, tmp_path):
    c = make_client(tmp_path / "processed")
    c.app.state.space_weather = SpaceWeather(fetch=lambda u: json.dumps(SEPS if "/SEP?" in u else CMES).encode(),
                                             clock=lambda: NOW.timestamp())  # fmt: skip
    r = c.get("/api/mars/space-weather")
    assert r.status_code == 200
    body = r.json()
    assert (
        body["status"] == "live"
        and body["sep_window_h"] == 72
        and body["mars_cme"]["glancing"] is True
    )


# --- Propuestos en la revisión de código: el endpoint nunca debe fallar, pase lo que pase con CCMC ---


def _http_error(_):
    raise urllib.error.HTTPError("https://ccmc.gsfc.nasa.gov", 503, "Service Unavailable", {}, None)


def _truncated(_):
    raise http.client.IncompleteRead(b"")  # NO es OSError ni ValueError


@pytest.mark.parametrize(
    "fetch",
    [
        _http_error,
        _truncated,
        lambda _: b"<html><body>CCMC maintenance</body></html>",  # HTML en vez de JSON
        lambda _: b'{"error": "Date range cannot exceed 60 days"}',  # dict en vez de lista
        lambda _: b"",  # cuerpo vacío
    ],
    ids=["http-503", "incomplete-read", "html", "dict", "empty"],
)
def test_any_ccmc_failure_falls_back_to_snapshot(fetch):
    v = SpaceWeather(fetch=fetch, clock=lambda: NOW.timestamp()).get()
    assert v["status"] in {"live", "snapshot"}  # cuerpo vacío == lista vacía == en vivo sin eventos
    assert v["mars_cme_30d"] >= 0


def test_endpoint_200_even_if_ccmc_and_snapshot_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(space_weather, "SNAPSHOT", tmp_path / "missing.json")
    c = make_client(tmp_path / "processed")
    c.app.state.space_weather = SpaceWeather(fetch=_truncated, clock=lambda: NOW.timestamp())
    r = c.get("/api/mars/space-weather")
    assert r.status_code == 200
    assert r.json()["status"] == "down" and r.json()["mars_cme"] is None


def test_retries_live_after_fail_ttl():
    calls = []
    clock = {"t": NOW.timestamp()}

    def flaky(url):
        calls.append(url)
        if clock["t"] < NOW.timestamp() + space_weather.TTL_FAIL_S:  # CCMC caído los primeros 5 min
            raise TimeoutError("sin red")
        return json.dumps(SEPS if "/SEP?" in url else CMES).encode()

    sw = SpaceWeather(fetch=flaky, clock=lambda: clock["t"])
    assert sw.get()["status"] == "snapshot"
    n = len(calls)
    clock["t"] += 60
    assert sw.get()["status"] == "snapshot" and len(calls) == n  # no reintenta antes de 5 min
    clock["t"] += space_weather.TTL_FAIL_S
    assert sw.get()["status"] == "live" and len(calls) == n + 2


def test_naive_timestamp_is_utc():
    assert space_weather._parse_time("2026-11-09T18:15") == datetime(
        2026, 11, 9, 18, 15, tzinfo=UTC
    )
    assert space_weather._parse_time("2026-11-09T18:15:00Z") == datetime(
        2026, 11, 9, 18, 15, tzinfo=UTC
    )
    assert space_weather._parse_time(1234) is None


def test_concurrent_cold_requests_hit_ccmc_once():
    calls = []
    lock = threading.Lock()

    def slow(url):
        with lock:
            calls.append(url)
        time.sleep(0.05)
        return b"[]"

    sw = SpaceWeather(fetch=slow, clock=lambda: NOW.timestamp())
    threads = [threading.Thread(target=sw.get) for _ in range(8)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert len(calls) == 2  # SEP + CME una sola vez, no 16
