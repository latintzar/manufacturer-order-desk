"""Real Agents SDK loop with an offline model; no provider requests or external messages."""

import asyncio
import json
import os
import time

import pytest

pytest.importorskip("agents")
from agents import Model
from agents.exceptions import UserError
from agents.items import ModelResponse
from agents.usage import Usage
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText

from app.src.prototypes.orders import agent_host as host_module
from app.src.prototypes.orders import harness_launcher as bridge
from app.src.prototypes.orders import orders_tools as family

pytest_plugins = ["test_store"]


class FakeModel(Model):
    def __init__(self, malicious=False, failure=False):
        self.inputs = []
        self.malicious, self.failure = malicious, failure

    async def get_response(self, **kwargs):
        self.inputs.append(kwargs["input"])
        if self.failure:
            raise ConnectionError("offline provider failure")
        if len(self.inputs) == 1:
            arguments = {"item_id": "A"}
            if self.malicious:
                arguments["role"] = "admin"
            output = [
                ResponseFunctionToolCall(
                    id="fc_1",
                    call_id="call_1",
                    name="catalog_read",
                    arguments=json.dumps(arguments),
                    type="function_call",
                )
            ]
        else:
            output = [
                ResponseOutputMessage(
                    id="msg_1",
                    role="assistant",
                    status="completed",
                    type="message",
                    content=[
                        ResponseOutputText(type="output_text", text="Read the company item.", annotations=[])
                    ],
                )
            ]
        return ModelResponse(
            output=output,
            usage=Usage(requests=1, input_tokens=20, output_tokens=10, total_tokens=30),
            response_id="offline",
        )

    async def stream_response(self, *args, **kwargs):
        raise NotImplementedError
        yield


def grant():
    return {
        "company": "example",
        "openai_project": "proj_offline",
        "account_evidence": "offline fixture",
        "grant_id": "offline-test",
        "approval_evidence": "test, no API calls",
        "api_key_env": "ROCOTO_ORDERS_OPENAI_API_KEY",
        "expires_at": time.time() + 3600,
        "maximum_usd": 1,
        "maximum_run_usd": 1,
        "maximum_requests": 4,
        "maximum_output_tokens": 128,
        "profiles": {
            "judge": {
                "model": "offline-fake",
                "pricing_evidence": "test only",
                "input_usd_per_million": 1,
                "output_usd_per_million": 1,
                "input_token_bound": 65536,
            }
        },
    }


@pytest.fixture
def host(store, tmp_path):
    source = os.environ.get("ORDERS_HARNESS_SOURCE")
    if not source:
        pytest.skip("Set ORDERS_HARNESS_SOURCE for the actual native pack integration.")
    _, template, monitoring = bridge.check_pack(source)
    journal = host_module.Journal(tmp_path / "agent", "example")
    model = FakeModel()
    context = family.CompanyContext(store, "example", "local:test", "operator")
    value = host_module.Host(context, template, monitoring, journal, grant(), lambda profile: model)
    value.fake = model
    yield value
    journal.db.close()


def test_real_sdk_dispatch_history_and_profile(host):
    first = asyncio.run(host.turn("office", "Read A", stage="catalogue"))
    assert first["output"] == "Read the company item."
    assert len(host.fake.inputs) == 2
    tool_notes = host.journal.db.execute("SELECT data FROM notes WHERE kind='tool'").fetchall()
    assert json.loads(tool_notes[0][0])["result"]["item"]["p"] == 12.345
    assert host.journal.db.execute("SELECT COUNT(*) FROM requests WHERE state='settled'").fetchone()[0] == 2
    asyncio.run(host.turn("office", "What did we read?"))
    assert any(item.get("type") == "function_call_output" for item in host.fake.inputs[-1])
    assert first["profile"] == "judge"
    assert host.journal.db.execute("SELECT COUNT(*) FROM runs WHERE state='completed'").fetchone()[0] == 2


def test_failed_tool_authority_is_recorded(host):
    host.fake.malicious = True
    with pytest.raises(UserError, match="declared fields"):
        asyncio.run(host.turn("office", "Read A"))
    assert host.journal.db.execute("SELECT COUNT(*) FROM notes WHERE kind='guard'").fetchone()[0] == 1
    assert host.journal.db.execute("SELECT state FROM runs").fetchone()[0] == "failed"
    saved_input = host.journal.db.execute("SELECT data FROM notes WHERE kind='input'").fetchone()[0]
    assert json.loads(saved_input)["message"] == "Read A"
    with pytest.raises(PermissionError, match="failed turn"):
        asyncio.run(host.turn("office", "Retry"))


def test_budget_admission_and_uncertain_usage(host):
    host.config["maximum_usd"] = 0.000001
    with pytest.raises(PermissionError, match="allowance"):
        asyncio.run(host.turn("office", "Read A"))
    assert not host.fake.inputs
    host.config["maximum_usd"] = 1
    host.fake.failure = True
    with pytest.raises(ConnectionError):
        asyncio.run(host.turn("fresh", "Read A"))
    assert host.journal.db.execute("SELECT state FROM requests").fetchone()[0] == "reserved"
    host.fake.failure = False
    with pytest.raises(PermissionError, match="Uncertain"):
        asyncio.run(host.turn("fresh-2", "Read A"))


def test_company_principal_and_readonly_authority(host, tmp_path):
    with pytest.raises(PermissionError, match="another company"):
        host_module.Journal(host.journal.workspace, "foreign")
    asyncio.run(host.turn("office", "Read A"))
    host.context = family.CompanyContext(host.context.store, "example", "another-user", "owner", "test", True)
    with pytest.raises(PermissionError, match="principal"):
        asyncio.run(host.turn("office", "Read A"))


def test_scheduled_template_executes_bounded_runs(host):
    schedule = host.schedule("ready-time", "judge", 1)
    result = asyncio.run(host.tick())
    assert len(result) == 1
    state, remaining = host.journal.db.execute(
        "SELECT state,remaining FROM schedules WHERE id=?", (schedule,)
    ).fetchone()
    assert (state, remaining) == ("completed", 0)
    assert asyncio.run(host.tick()) == []
    with pytest.raises(ValueError, match="scheduled"):
        host.schedule("manufacturer-onboarding", "judge", 1)


def test_grant_file_requires_company_private_permissions_and_expiry(tmp_path):
    path = tmp_path / "grant.json"
    path.write_text(json.dumps(grant()))
    path.chmod(0o644)
    with pytest.raises(PermissionError, match="private"):
        host_module.configuration(path, "example")
    path.chmod(0o600)
    assert host_module.configuration(path, "example")["profiles"]["judge"]["model"] == "offline-fake"
    with pytest.raises(PermissionError, match="another company"):
        host_module.configuration(path, "foreign")
    expired = grant()
    expired["expires_at"] = time.time() - 1
    path.write_text(json.dumps(expired))
    with pytest.raises(PermissionError, match="expired"):
        host_module.configuration(path, "example")


def test_schedule_keeps_original_authority(host):
    host.schedule("ready-time", "judge", 1)
    host.context = family.CompanyContext(host.context.store, "example", "different", "owner", "test", True)
    with pytest.raises(PermissionError, match="principal"):
        asyncio.run(host.tick())


def test_changed_grant_and_expiry_block_new_requests(host):
    asyncio.run(host.turn("office", "Read A"))
    host.config["maximum_usd"] = 2
    with pytest.raises(PermissionError, match="changed grant"):
        asyncio.run(host.turn("new", "Read A"))
    host.config["expires_at"] = time.time() - 1
    with pytest.raises(PermissionError, match="expired"):
        asyncio.run(host.turn("newer", "Read A"))


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    import socket

    def forbidden(*args, **kwargs):
        raise AssertionError("Offline host proof must never open a network connection")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
