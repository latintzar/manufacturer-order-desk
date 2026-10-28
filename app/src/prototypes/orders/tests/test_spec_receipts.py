"""Allocation confirmation must refer to the exact retained server reading."""

import customer_details
import pytest
import spec_receipts
from store import CompanyStore
from test_order_api import upload
from test_platform_files import PDF

import serve

pytest_plugins = ["test_order_api"]


@pytest.fixture(autouse=True)
def fresh_request_budget():
    serve.Handler.requests.clear()
    yield
    serve.Handler.requests.clear()


def example(store, upload_id):
    review = {
        "schema": "rocoto.orders.allocations.v1",
        "destinations": [{"id": "1602", "label": "Варна"}],
        "allocations": [
            {"line": 0, "sku": "A", "destination_id": "1602", "quantity": 2, "source_cell": "sheet1!B2"}
        ],
        "issues": [],
        "totals": {"declared": 2, "calculated": 2, "status": "matched"},
    }
    parsed = {"lines": [{"source": "A | 2", "qty": 2, "matches": ["A"]}], "review": review}
    receipt = spec_receipts.record(store, {"upload": upload_id}, parsed)
    customer = {
        "name": "Buyer",
        "email": "buyer@example.test",
        "specification_file": upload_id,
        "capture": {
            "schema": "rocoto.orders.capture.v1",
            "entry_path": "specification",
            "language": "bg",
            "specification": {
                "text": "",
                "file_id": upload_id,
                "reading_id": receipt["reading_id"],
                "allocations_confirmed": True,
                "lines": [{"source": "A | 2", "quantity": 2, "selected_code": "A", "status": "exact"}],
            },
        },
    }
    return customer, parsed


def test_confirmation_embeds_server_allocation_and_keeps_input_immutable(order_api):
    _, uploaded = upload(order_api, "Order.pdf", PDF)
    store = CompanyStore(order_api[1])
    customer, _ = example(store, uploaded["upload"]["id"])
    valid = customer_details.validate(customer, {})
    result = spec_receipts.validate(store, valid, [{"item_id": "A", "quantity": 2}])
    assert result["capture"]["specification"]["allocation_review"]["allocations"][0]["selected_code"] == "A"
    assert "allocation_review" not in customer["capture"]["specification"]
    with pytest.raises(ValueError):
        customer_details.validate(result, {})
    store.close()


@pytest.mark.parametrize("change", ["omitted", "unconfirmed", "file", "quantity", "source", "code", "short", "extra", "unallocated"])
def test_confirmation_cannot_omit_or_change_extraction(order_api, change):
    _, uploaded = upload(order_api, "Order.pdf", PDF)
    store = CompanyStore(order_api[1])
    customer, _ = example(store, uploaded["upload"]["id"])
    cap = customer["capture"]["specification"]
    lines = [{"item_id": "A", "quantity": 2}]
    if change == "omitted":
        del cap["reading_id"]
    elif change == "unconfirmed":
        cap["allocations_confirmed"] = False
    elif change == "file":
        customer["specification_file"] = "b" * 32
    elif change == "quantity":
        cap["lines"][0]["quantity"] = 3
    elif change == "source":
        cap["lines"][0]["source"] = "B | 2"
    elif change == "code":
        cap["lines"][0]["selected_code"] = "B"
    elif change == "short":
        lines[0]["quantity"] = 1
    elif change == "extra":
        lines[0]["quantity"] = 5
    elif change == "unallocated":
        lines.append({"item_id": "B", "quantity": 1})
    with pytest.raises(ValueError):
        spec_receipts.validate(store, customer, lines)
    store.close()


def test_text_table_review_cannot_be_bypassed_by_omitting_reading(order_api):
    store=CompanyStore(order_api[1])
    source='Артикул | Варна | София\nA | 2 | 3'
    spec_receipts.record(store, {'text':source}, {'lines':[], 'review':{
        'schema':'rocoto.orders.allocations.v1','issues':[{'code':'document_table_review'}]}})
    customer={'capture':{'specification':{'text':source,'lines':[]}}}
    with pytest.raises(ValueError):
        spec_receipts.validate(store,customer,[{'item_id':'A','quantity':5}])
    store.close()
