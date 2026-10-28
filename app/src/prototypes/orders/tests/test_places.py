"""The address search holds its ceilings whatever a browser does, and makes no call it has not counted."""
from __future__ import annotations

import json

import pytest

import places

SUGGESTIONS = {"suggestions": [{"placePrediction": {
    "placeId": "ChIJ_example-1", "text": {"text": "bul. Vitosha 12, Sofia"},
    "structuredFormat": {"mainText": {"text": "bul. Vitosha 12"}, "secondaryText": {"text": "Sofia, Bulgaria"}}}}]}
PLACE = {"formattedAddress": "bul. Vitosha 12, 1000 Sofia, Bulgaria", "location": {"latitude": 42.69, "longitude": 23.32}}


class Upstream:
    """Stands in for Google: records each call and answers from a script."""

    def __init__(self, answers=None):
        self.calls, self.answers = [], list(answers or [])

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append({"method": method, "url": url, "headers": headers, "body": body, "timeout": timeout})
        if self.answers:
            answer = self.answers.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer
        return 200, json.dumps(SUGGESTIONS if method == "POST" else PLACE).encode()


class Clock:
    def __init__(self, now=1791720000.0):          # 11 October 2026, UTC
        self.now = now

    def __call__(self):
        return self.now


def service(tmp_path, *, upstream=None, clock=None, commission=True, **options):
    clock = clock or Clock()
    upstream = upstream if upstream is not None else Upstream()
    options.setdefault("key", "A" * 39)
    made = places.Places(tmp_path, transport=upstream, clock=clock,
                         rate=options.pop("rate", places.RateLimit(clock=clock)), **options)
    if commission:
        made.ledger.commission()
    return made, upstream, clock


def reason(call):
    with pytest.raises(places.Refusal) as refused:
        call()
    return refused.value.reason, refused.value.status


def test_a_query_becomes_one_counted_call_with_the_key_in_its_header_only(tmp_path):
    made, upstream, _ = service(tmp_path)
    answer = made.suggestions("bul. Vitosha 12", "session-1", "bg", "client", {"regions": ["bg"]})
    assert answer == {"ok": True, "items": [{"id": "ChIJ_example-1", "main": "bul. Vitosha 12",
                                             "secondary": "Sofia, Bulgaria"}]}
    call = upstream.calls[0]
    assert call["url"] == places.AUTOCOMPLETE and call["headers"]["X-Goog-Api-Key"] == "A" * 39
    assert "A" * 39 not in call["url"] and call["timeout"] == 4.0
    sent = json.loads(call["body"])
    assert sent == {"input": "bul. Vitosha 12", "sessionToken": "session-1", "languageCode": "bg",
                    "includedRegionCodes": ["bg"]}
    assert made.ledger.used("autocomplete") == (1, 1) and made.ledger.used("details") == (0, 0)


def test_a_chosen_place_closes_the_session_with_the_essentials_fields(tmp_path):
    made, upstream, _ = service(tmp_path)
    answer = made.place("ChIJ_example-1", "session-1", "en", "client")
    assert answer == {"ok": True, "address": "bul. Vitosha 12, 1000 Sofia, Bulgaria", "lat": 42.69, "lng": 23.32,
                      "line1": "", "zip": "", "city": ""}
    call = upstream.calls[0]
    assert call["method"] == "GET" and "sessionToken=session-1" in call["url"]
    assert call["headers"]["X-Goog-FieldMask"] == "formattedAddress,location,addressComponents"
    assert made.ledger.used("details") == (1, 1)


def test_the_daily_ceiling_holds_and_the_next_day_opens_again(tmp_path):
    made, upstream, clock = service(tmp_path, ceilings={"autocomplete": (3, 100), "details": (1, 100)},
                                    rate=places.RateLimit(calls=1000))
    for _ in range(3):
        made.suggestions("sofia centre", "s", "bg", "client")
    assert reason(lambda: made.suggestions("sofia centre", "s", "bg", "client")) == ("cap", 429)
    assert len(upstream.calls) == 3
    clock.now += 86400
    made.suggestions("sofia centre", "s", "bg", "client")
    assert len(upstream.calls) == 4


def test_the_monthly_ceiling_holds_across_days(tmp_path):
    made, upstream, clock = service(tmp_path, ceilings={"autocomplete": (2, 3), "details": (1, 1)},
                                    rate=places.RateLimit(calls=1000))
    made.suggestions("sofia centre", "s", "bg", "c")
    made.suggestions("sofia centre", "s", "bg", "c")
    clock.now += 86400
    made.suggestions("sofia centre", "s", "bg", "c")
    assert reason(lambda: made.suggestions("sofia centre", "s", "bg", "c")) == ("cap", 429)
    made.place("ChIJ_example-1", "s", "bg", "c")
    assert reason(lambda: made.place("ChIJ_example-1", "s", "bg", "c")) == ("cap", 429)
    assert len(upstream.calls) == 4


def test_the_ledger_survives_a_restart(tmp_path):
    first, upstream, clock = service(tmp_path, ceilings={"autocomplete": (2, 2), "details": (1, 1)})
    first.suggestions("sofia centre", "s", "bg", "c")
    first.suggestions("sofia centre", "s", "bg", "c")
    again, upstream, _ = service(tmp_path, clock=clock, ceilings={"autocomplete": (2, 2), "details": (1, 1)},
                                 commission=False)
    assert again.ledger.used("autocomplete") == (2, 2)
    assert reason(lambda: again.suggestions("sofia centre", "s", "bg", "c")) == ("cap", 429)
    assert upstream.calls == []
    assert again.ledger.commission() is False          # commissioning again leaves the counts standing
    assert again.ledger.used("autocomplete") == (2, 2)


def test_serving_never_makes_a_ledger_and_answers_off_without_one(tmp_path):
    made, upstream, _ = service(tmp_path, commission=False)
    assert reason(lambda: made.suggestions("sofia centre", "s", "bg", "c")) == ("off", 503)
    assert upstream.calls == [] and not (tmp_path / places.LEDGER_NAME).exists()
    stateless, upstream, _ = service(None, commission=False)
    assert reason(lambda: stateless.place("ChIJ_example-1", "s", "bg", "c")) == ("off", 503)


def test_the_switch_and_a_missing_key_each_end_every_outside_call(tmp_path):
    off, upstream, _ = service(tmp_path, enabled=False)
    assert reason(lambda: off.suggestions("sofia centre", "s", "bg", "c")) == ("off", 503)
    keyless, other, _ = service(tmp_path, key="", commission=False)
    assert reason(lambda: keyless.suggestions("sofia centre", "s", "bg", "c")) == ("key", 503)
    assert upstream.calls == [] and other.calls == []
    assert keyless.ledger.used("autocomplete") == (0, 0)


def test_the_environment_supplies_switch_and_key_and_the_key_leaves_it(tmp_path):
    environ = {places.SWITCH_ENV: "off", places.KEY_ENV: "B" * 39}
    made = places.from_environment(tmp_path, environ)
    assert made.enabled is False and made.key == "B" * 39 and places.KEY_ENV not in environ
    assert places.from_environment(tmp_path, {}).enabled is True
    with pytest.raises(SystemExit):
        places.from_environment(tmp_path, {places.SWITCH_ENV: "maybe"})
    with pytest.raises(SystemExit):
        places.from_environment(tmp_path, {places.KEY_ENV: "short key"})


def test_one_client_is_slowed_while_another_goes_on(tmp_path):
    made, upstream, clock = service(tmp_path)
    for _ in range(places.RATE_CALLS):
        made.suggestions("sofia centre", "s", "bg", "203.0.113.5")
    assert reason(lambda: made.suggestions("sofia centre", "s", "bg", "203.0.113.5")) == ("rate", 429)
    made.suggestions("sofia centre", "s", "bg", "203.0.113.6")
    assert len(upstream.calls) == places.RATE_CALLS + 1
    assert made.ledger.used("autocomplete")[0] == places.RATE_CALLS + 1     # a slowed call is never counted
    clock.now += places.RATE_SECONDS
    made.suggestions("sofia centre", "s", "bg", "203.0.113.5")


def test_a_short_query_or_a_malformed_token_makes_no_call(tmp_path):
    made, upstream, _ = service(tmp_path)
    assert reason(lambda: made.suggestions("so", "s", "bg", "c")) == ("short", 400)
    assert reason(lambda: made.suggestions("  a      ", "s", "bg", "c")) == ("short", 400)
    assert reason(lambda: made.suggestions("sofia centre", "bad token!", "bg", "c")) == ("short", 400)
    assert reason(lambda: made.suggestions("x" * 121, "s", "bg", "c")) == ("short", 400)
    assert reason(lambda: made.place("../admin", "s", "bg", "c")) == ("short", 400)
    assert upstream.calls == [] and made.ledger.used("autocomplete") == (0, 0)


@pytest.mark.parametrize("answer", [
    (500, b""), (403, b""), (200, b"not json"), (200, b'{"error": {"code": 400}}'),
    (200, b'{"suggestions": [{"placePrediction": {"text": {"text": "x"}}}]}'),
    OSError("no route"), TimeoutError("timed out"),
])
def test_an_upstream_failure_is_answered_as_upstream_and_stays_counted(tmp_path, answer):
    made, upstream, _ = service(tmp_path, upstream=Upstream([answer]))
    assert reason(lambda: made.suggestions("sofia centre", "s", "bg", "c")) == ("upstream", 502)
    assert made.ledger.used("autocomplete") == (1, 1)


def test_after_a_failure_the_service_rests_before_it_calls_again(tmp_path):
    made, upstream, clock = service(tmp_path, upstream=Upstream([(403, b"")]))
    assert reason(lambda: made.suggestions("sofia centre", "s", "bg", "c")) == ("upstream", 502)
    assert reason(lambda: made.suggestions("sofia centre", "s", "bg", "c")) == ("upstream", 502)
    assert len(upstream.calls) == 1 and made.ledger.used("autocomplete") == (1, 1)
    clock.now += 6 * 3600 + 1
    assert made.suggestions("sofia centre", "s", "bg", "c")["ok"] is True


@pytest.mark.parametrize("content", ["", "{", '{"autocomplete": {"days": {}, "months": {}}}',
                                     '{"autocomplete": {"days": {"2026-10-11": -1}, "months": {}}, '
                                     '"details": {"days": {}, "months": {}}}'])
def test_a_damaged_ledger_admits_no_call(tmp_path, content):
    made, upstream, _ = service(tmp_path)
    (tmp_path / places.LEDGER_NAME).write_text(content)
    assert reason(lambda: made.suggestions("sofia centre", "s", "bg", "c")) == ("cap", 429)
    assert upstream.calls == [] and made.ledger.used("autocomplete") == places.CEILINGS["autocomplete"]


def test_a_clock_that_reads_earlier_than_a_counted_day_admits_no_call(tmp_path):
    made, upstream, clock = service(tmp_path)
    made.suggestions("sofia centre", "s", "bg", "c")
    clock.now -= 3 * 86400
    assert reason(lambda: made.suggestions("sofia centre", "s", "bg", "c")) == ("cap", 429)
    assert len(upstream.calls) == 1


def test_the_shipped_ceilings_stay_inside_the_free_monthly_allowance():
    free_events_a_month = 10_000                    # Google's price list, read 11 October 2026
    for product, (daily, monthly) in places.CEILINGS.items():
        assert monthly <= free_events_a_month, product
        assert daily <= monthly * 0.1, product      # a script error is stopped within the day


def test_a_chosen_place_gives_its_street_line_postcode_and_town(tmp_path):
    place = dict(PLACE, addressComponents=[
        {"longText": "12", "types": ["street_number"]}, {"longText": "bul. Vitosha", "types": ["route"]},
        {"longText": "Sofia", "types": ["locality", "political"]}, {"longText": "1000", "types": ["postal_code"]}])
    made, _, _ = service(tmp_path, upstream=Upstream([(200, json.dumps(place).encode())]))
    answer = made.place("ChIJ-place_1", "s1", "en", "client")
    assert (answer["line1"], answer["zip"], answer["city"]) == ("bul. Vitosha 12", "1000", "Sofia")


def test_the_address_at_a_position_counts_as_one_place_call(tmp_path):
    found = {"status": "OK", "results": [{"formatted_address": "ul. Pirotska 5, 1000 Sofia", "address_components": [
        {"long_name": "5", "types": ["street_number"]}, {"long_name": "ul. Pirotska", "types": ["route"]},
        {"long_name": "Sofia", "types": ["locality"]}, {"long_name": "1000", "types": ["postal_code"]}]}]}
    made, upstream, _ = service(tmp_path, upstream=Upstream([(200, json.dumps(found).encode())]))
    answer = made.here(42.6977, 23.3219, "bg", "client")
    assert (answer["line1"], answer["zip"], answer["city"], answer["lat"]) == ("ul. Pirotska 5", "1000", "Sofia", 42.6977)
    assert "latlng=42.697700,23.321900" in upstream.calls[0]["url"] and made.ledger.used("details")[0] == 1


def test_a_switched_off_position_lookup_stays_off_and_leaves_the_search_working(tmp_path):
    denied = (200, json.dumps({"status": "REQUEST_DENIED", "results": []}).encode())
    made, upstream, clock = service(tmp_path, upstream=Upstream([denied]))
    assert reason(lambda: made.here(42.6977, 23.3219, "bg", "client"))[0] == "off"
    assert reason(lambda: made.here(42.6977, 23.3219, "bg", "client"))[0] == "off"
    assert len(upstream.calls) == 1 and made.ledger.used("details")[0] == 1
    assert made.suggestions("Vitosha 12", "s1", "en", "client")["ok"] is True
    clock.now += places.GEOCODE_OFF + 1
    upstream.answers.append(denied)
    assert reason(lambda: made.here(42.6977, 23.3219, "bg", "client"))[0] == "off"
    assert len(upstream.calls) == 3
