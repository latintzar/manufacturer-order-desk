#!/usr/bin/env python3
"""Address search for the order page's delivery step, with hard ceilings on what it may cost.

    python3 places.py commission --state <directory>     make the call ledger, once per host
    python3 places.py used --state <directory>           today's and this month's counts

Two calls to Google Maps Platform, made by the preview server and never by the page:
  suggestions  Places API (New) Autocomplete, one call per typed query
  place        Places API (New) Place Details, fields `formattedAddress,location,addressComponents`
               (all in the Essentials price), one call per chosen suggestion; it closes the session
               the suggestions opened and gives the street line, the postcode and the town
  here         Geocoding API, the address at the customer's own position, one call when they ask
               for it. It is counted against the `place` ceiling. While the product is switched
               off on the Google project it answers `off` for ten minutes at a time, without
               counting and without resting the address search
The request shapes follow the kit's adapter, mock-api/app/places.py; this preview is a consumer of
its own with its own key, ledger and switch.

What it costs (Google's price list, https://developers.google.com/maps/billing-and-pricing/pricing,
read 11 October 2026): "Autocomplete Requests" and "Places API Place Details Essentials" each carry
10,000 free events a month across the whole billing account, then 2.83 USD and 5.00 USD per
thousand. In a session that ends in Place Details, Google bills the first twelve suggestion calls
and one Place Details call.

The ceilings, counted for the whole server before a call leaves and kept across restarts:
  suggestions  1,000 a UTC day, 10,000 a UTC month
  place          500 a UTC day, 10,000 a UTC month (chosen places and position lookups together)
The month ceiling is Google's free allowance for each product (Peter, 12 October 2026: «servrwise
10k per month cap»); the day ceiling stops a script error within one day. The allowance belongs to
the billing account, so another Rocoto service on the same products draws on the same 10,000.
Every counted call stays counted, answered or lost. A missing, unreadable or damaged ledger admits
no call; so does a clock that reads earlier than a day already counted. The commissioning command
makes the ledger; serving never does. On top: 30 calls a minute per client, a query of three
characters at least, four seconds per call, and a rest after an upstream failure.

Stop switch: ROCOTO_ORDERS_PLACES=off ends every outside call. The key is read once from
ROCOTO_ORDERS_GOOGLE_MAPS_API_KEY, leaves the process environment, and travels to Google only: in
the request header for Places, in the query for Geocoding. Without it the service answers `key` and the page shows its address fields.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from collections import OrderedDict, deque
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

AUTOCOMPLETE = "https://places.googleapis.com/v1/places:autocomplete"
DETAILS = "https://places.googleapis.com/v1/places/{}"
SUGGESTION_FIELDS = ("suggestions.placePrediction.placeId,suggestions.placePrediction.text.text,"
                     "suggestions.placePrediction.structuredFormat.mainText.text,"
                     "suggestions.placePrediction.structuredFormat.secondaryText.text")
PLACE_FIELDS = "formattedAddress,location,addressComponents"
GEOCODE = "https://maps.googleapis.com/maps/api/geocode/json"
GEOCODE_OFF = 600.0                                                   # seconds the position lookup stays off after a refusal
CEILINGS = {"autocomplete": (1000, 10000), "details": (500, 10000)}      # per UTC day, per UTC month
KEY_ENV, SWITCH_ENV = "ROCOTO_ORDERS_GOOGLE_MAPS_API_KEY", "ROCOTO_ORDERS_PLACES"
LEDGER_NAME = "places-ledger.json"
MIN_QUERY, MAX_QUERY, MAX_ITEMS = 3, 120, 5
TIMEOUT = 4.0
RATE_CALLS, RATE_SECONDS, RATE_CLIENTS = 30, 60.0, 4096
REST = {401: 6 * 3600.0, 403: 6 * 3600.0, 429: 3600.0}               # seconds; any other failure rests 60
STATUS = {"cap": 429, "off": 503, "key": 503, "rate": 429, "short": 400, "upstream": 502}
SESSION = re.compile(r"[A-Za-z0-9_-]{1,36}")
PLACE_ID = re.compile(r"[A-Za-z0-9_-]{1,300}")
LANGUAGE = re.compile(r"[a-z]{2}")


class Refusal(Exception):
    """The service answers without calling out. `reason` is one of STATUS."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason, self.status = reason, STATUS[reason]


class Ledger:
    """Outside calls counted before they leave: per product, per UTC day and per UTC month."""

    DAYS, MONTHS = 62, 14                                             # periods kept in the file

    def __init__(self, path: Path | None, ceilings: dict | None = None, *, clock=time.time):
        self.path = Path(path).absolute() if path else None
        self.ceilings, self.clock = dict(ceilings or CEILINGS), clock

    def _now(self) -> tuple[str, str]:
        day = datetime.fromtimestamp(self.clock(), timezone.utc).strftime("%Y-%m-%d")
        return day, day[:7]

    def exists(self) -> bool:
        return bool(self.path) and self.path.is_file() and not self.path.is_symlink()

    def _write(self, ledger: dict) -> None:
        handle, temporary = tempfile.mkstemp(dir=self.path.parent, prefix=".ledger-")
        with os.fdopen(handle, "w") as stream:
            json.dump(ledger, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.path)

    @staticmethod
    def _counts(table: object, stamp: str) -> dict:
        if not isinstance(table, dict) or any(
                not isinstance(period, str) or not re.fullmatch(stamp, period)
                or type(count) is not int or count < 0 for period, count in table.items()):
            raise ValueError("the call ledger is damaged")
        return table

    @contextmanager
    def _open(self, write: bool):
        if not self.exists():
            raise ValueError("the call ledger has yet to be commissioned")
        lock_path = self.path.with_name(self.path.name + ".lock")
        with open(os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600), "r+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            ledger = json.loads(self.path.read_text())
            if not isinstance(ledger, dict) or set(ledger) != set(self.ceilings):
                raise ValueError("the call ledger is damaged")
            for product in ledger.values():
                if not isinstance(product, dict) or set(product) != {"days", "months"}:
                    raise ValueError("the call ledger is damaged")
                self._counts(product["days"], r"\d{4}-\d{2}-\d{2}")
                self._counts(product["months"], r"\d{4}-\d{2}")
            before = json.dumps(ledger, sort_keys=True)
            yield ledger
            if write and json.dumps(ledger, sort_keys=True) != before:
                for product in ledger.values():
                    for table, kept in ((product["days"], self.DAYS), (product["months"], self.MONTHS)):
                        for period in sorted(table)[:-kept]:
                            del table[period]
                self._write(ledger)

    def commission(self) -> bool:
        """Make the ledger where none stands. A standing ledger is left exactly as it is."""
        if self.path is None:
            raise ValueError("the call ledger has no place")
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock_path = self.path.with_name(self.path.name + ".lock")
        with open(os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600), "r+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if self.path.exists() or self.path.is_symlink():
                return False
            self._write({product: {"days": {}, "months": {}} for product in self.ceilings})
            return True

    def reserve(self, product: str) -> bool:
        """Count one call against its day and month before it leaves. False admits no call."""
        daily, monthly = self.ceilings[product]
        try:
            with self._open(True) as ledger:
                day, month = self._now()
                days, months = ledger[product]["days"], ledger[product]["months"]
                if any(period > day for period in days) or any(period > month for period in months):
                    return False                                      # the clock reads earlier than a counted period
                if days.get(day, 0) + 1 > daily or months.get(month, 0) + 1 > monthly:
                    return False
                days[day], months[month] = days.get(day, 0) + 1, months.get(month, 0) + 1
                return True
        except (OSError, ValueError):
            return False

    def used(self, product: str) -> tuple[int, int]:
        """Today's and this month's counts. A ledger that cannot be read reads as full."""
        try:
            with self._open(False) as ledger:
                day, month = self._now()
                return ledger[product]["days"].get(day, 0), ledger[product]["months"].get(month, 0)
        except (OSError, ValueError):
            return self.ceilings[product]


class RateLimit:
    """At most `calls` per client in any window of `seconds`, for a bounded number of clients."""

    def __init__(self, calls: int = RATE_CALLS, seconds: float = RATE_SECONDS, *, clock=time.monotonic):
        self.calls, self.seconds, self.clock = calls, seconds, clock
        self.seen: OrderedDict[str, deque] = OrderedDict()
        self.lock = threading.Lock()

    def admit(self, client: str) -> bool:
        with self.lock:
            now = self.clock()
            window = self.seen.setdefault(client, deque())
            self.seen.move_to_end(client)
            while window and now - window[0] >= self.seconds:
                window.popleft()
            if len(window) >= self.calls:
                return False
            window.append(now)
            while len(self.seen) > RATE_CLIENTS:
                self.seen.popitem(last=False)
            return True


def send(method: str, url: str, headers: dict, body: bytes | None, timeout: float) -> tuple[int, bytes]:
    """One HTTPS call. Returns the status and the body; raises OSError when no answer came."""
    request = urllib.request.Request(url, data=body, headers=headers, method=method)  # noqa: S310 - fixed https hosts
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return response.status, response.read(1_000_000)
    except urllib.error.HTTPError as error:
        return error.code, b""


class Places:
    """The two calls, each behind the switch, the key, the client's rate, the ledger and a rest."""

    def __init__(self, state: Path | None, *, key: str = "", enabled: bool = True, transport=send,
                 clock=time.time, ceilings: dict | None = None, rate: RateLimit | None = None):
        self.key, self.enabled, self.transport, self.clock = key, enabled, transport, clock
        self.ledger = Ledger(Path(state) / LEDGER_NAME if state else None, ceilings, clock=clock)
        self.rate = rate or RateLimit()
        self.resting_until = 0.0
        self.here_off_until = 0.0
        self.lock = threading.Lock()

    def _admit(self, product: str, client: str) -> None:
        if not self.enabled or not self.ledger.exists():
            raise Refusal("off")
        if not self.key:
            raise Refusal("key")
        with self.lock:
            if self.clock() < self.resting_until:
                raise Refusal("upstream")
        if not self.rate.admit(client):
            raise Refusal("rate")
        if not self.ledger.reserve(product):
            raise Refusal("cap")

    def _call(self, method: str, url: str, headers: dict, body: bytes | None) -> dict:
        headers = {"X-Goog-Api-Key": self.key, **headers}
        try:
            status, raw = self.transport(method, url, headers, body, TIMEOUT)
            if status != 200:
                raise ValueError(status)
            answer = json.loads(raw)
            if not isinstance(answer, dict) or answer.get("error"):
                raise ValueError(0)
            return answer
        except (OSError, ValueError) as failure:
            status = failure.args[0] if isinstance(failure, ValueError) and failure.args else 0
            with self.lock:
                self.resting_until = self.clock() + REST.get(status if isinstance(status, int) else 0, 60.0)
            print(f"places: upstream gave no usable answer ({status or type(failure).__name__})", file=sys.stderr)
            raise Refusal("upstream") from None

    def suggestions(self, query: str, session: str, language: str, client: str, geo: dict | None = None) -> dict:
        query = " ".join((query or "").split())
        if not MIN_QUERY <= len(query) <= MAX_QUERY or not SESSION.fullmatch(session or ""):
            raise Refusal("short")
        self._admit("autocomplete", client)
        ask: dict = {"input": query, "sessionToken": session,
                     "languageCode": language if LANGUAGE.fullmatch(language or "") else "en"}
        regions = [code for code in (geo or {}).get("regions") or [] if re.fullmatch(r"[a-z]{2}", str(code))][:15]
        if regions:
            ask["includedRegionCodes"] = regions
        origin = (geo or {}).get("origin") or {}
        if isinstance(origin.get("lat"), (int, float)) and isinstance(origin.get("lng"), (int, float)):
            ask["locationBias"] = {"circle": {"center": {"latitude": origin["lat"], "longitude": origin["lng"]},
                                              "radius": 50000.0}}
        answer = self._call("POST", AUTOCOMPLETE, {"Content-Type": "application/json",
                                                   "X-Goog-FieldMask": SUGGESTION_FIELDS},
                            json.dumps(ask).encode())
        items = []
        try:
            for suggestion in (answer.get("suggestions") or [])[:MAX_ITEMS]:
                prediction = suggestion.get("placePrediction")
                if not prediction:
                    continue
                text = prediction.get("text", {}).get("text", "")
                structure = prediction.get("structuredFormat") or {}
                main = structure.get("mainText", {}).get("text") or text
                secondary = structure.get("secondaryText", {}).get("text") or ""
                place_id = prediction["placeId"]
                if not PLACE_ID.fullmatch(place_id) or not main or len(main) > 300 or len(secondary) > 300:
                    raise ValueError
                items.append({"id": place_id, "main": main, "secondary": secondary})
        except (KeyError, TypeError, ValueError, AttributeError):
            raise Refusal("upstream") from None
        return {"ok": True, "items": items}

    def place(self, place_id: str, session: str, language: str, client: str) -> dict:
        if not PLACE_ID.fullmatch(place_id or "") or not SESSION.fullmatch(session or ""):
            raise Refusal("short")
        self._admit("details", client)
        chosen = language if LANGUAGE.fullmatch(language or "") else "en"
        answer = self._call("GET", DETAILS.format(place_id) + f"?sessionToken={session}&languageCode={chosen}",
                            {"X-Goog-FieldMask": PLACE_FIELDS}, None)
        try:
            latitude, longitude = float(answer["location"]["latitude"]), float(answer["location"]["longitude"])
            address = str(answer.get("formattedAddress") or "")
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180) or not address or len(address) > 500:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise Refusal("upstream") from None
        return {"ok": True, "address": address, "lat": latitude, "lng": longitude, **parts(answer.get("addressComponents"))}

    def here(self, latitude: float, longitude: float, language: str, client: str) -> dict:
        """The address at a position the customer shared. Never rests the address search."""
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise Refusal("short")
        with self.lock:
            if self.clock() < self.here_off_until:
                raise Refusal("off")
        self._admit("details", client)
        chosen = language if LANGUAGE.fullmatch(language or "") else "en"
        url = (f"{GEOCODE}?latlng={latitude:.6f},{longitude:.6f}&language={chosen}"
               f"&result_type=street_address%7Cpremise%7Croute&key={self.key}")
        try:
            status, raw = self.transport("GET", url, {}, None, TIMEOUT)
            answer = json.loads(raw) if status == 200 else {}
            first = (answer.get("results") or [{}])[0] if answer.get("status") == "OK" else None
            found = parts(first.get("address_components"), long="long_name") if first else {}
            address = str(first.get("formatted_address") or "") if first else ""
        except (OSError, ValueError, AttributeError, TypeError):
            first, found, address = None, {}, ""
        if not first or not found.get("line1") or len(address) > 500:
            with self.lock:
                self.here_off_until = self.clock() + GEOCODE_OFF
            raise Refusal("off")
        return {"ok": True, "address": address, "lat": latitude, "lng": longitude, **found}


def parts(components: object, long: str = "longText") -> dict:
    """Street line, postcode and town from Google's address components; empty where it names none."""
    def one(*kinds: str) -> str:
        for kind in kinds:
            for part in components if isinstance(components, list) else []:
                if isinstance(part, dict) and kind in (part.get("types") or []):
                    return str(part.get(long) or "")[:200]
        return ""

    street, number = one("route"), one("street_number")
    line = f"{street} {number}".strip() or one("premise", "neighborhood", "sublocality")
    return {"line1": line, "zip": one("postal_code"),
            "city": one("locality", "postal_town", "administrative_area_level_2", "administrative_area_level_1")}


def from_environment(state: Path | None, environ=None) -> Places:
    """The service as this process is configured. The key leaves the environment once read."""
    environ = os.environ if environ is None else environ
    switch = environ.get(SWITCH_ENV, "on").strip().lower()
    if switch not in ("on", "off"):
        raise SystemExit(f"Set {SWITCH_ENV} to on or off.")
    key = environ.pop(KEY_ENV, "").strip()
    if key and not re.fullmatch(r"[A-Za-z0-9._-]{20,400}", key):
        raise SystemExit(f"Set {KEY_ENV} to the server key.")
    return Places(state, key=key, enabled=switch == "on")


def main(argv: list[str]) -> int:
    if len(argv) != 4 or argv[1] not in ("commission", "used") or argv[2] != "--state":
        print("\n".join(line.strip() for line in __doc__.strip().splitlines()[2:4]))
        return 2
    ledger = Ledger(Path(argv[3]) / LEDGER_NAME)
    if argv[1] == "commission":
        print("ledger made" if ledger.commission() else "ledger stands; left as it is", ledger.path)
        return 0
    for product, (daily, monthly) in CEILINGS.items():
        day, month = ledger.used(product)
        print(f"{product}: {day} of {daily} today, {month} of {monthly} this month")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
