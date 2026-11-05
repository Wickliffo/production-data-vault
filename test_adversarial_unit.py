import json
from decimal import Decimal
from pathlib import Path

import pytest

from dv_ingest.hash import HASH_CONTRACT_VERSION, hash_components, hub_hash
from dv_ingest.models import OrderItemRecord

FIXTURE = Path(__file__).parent / "fixtures" / "adversarial_records.json"


def test_adversarial_fixture_contains_required_cases() -> None:
    records = json.loads(FIXTURE.read_text())
    cases = {record["payload"]["case"] for record in records}
    assert {
        "normal",
        "replay",
        "correction",
        "same_business_key_different_source",
        "null_and_whitespace",
        "late_arriving_unicode",
    } <= cases


def test_same_business_key_is_source_qualified() -> None:
    assert hub_hash("CUSTOMER", "C-100", "CRM_A") != hub_hash("CUSTOMER", "C-100", "ERP_B")


def test_delimiter_values_are_still_deterministic() -> None:
    assert hash_components("A||B", "C") == hash_components("A||B", "C")


def test_hash_contract_is_versioned_and_length_prefixed() -> None:
    assert HASH_CONTRACT_VERSION == "sha256-length-prefixed-v1"
    assert hash_components("A", "BC") != hash_components("AB", "C")


def test_order_item_validation_rejects_invalid_quantity_and_price() -> None:
    with pytest.raises(ValueError, match="quantity"):
        OrderItemRecord("C-1", "O-1", "I-1", "P-1", quantity=0).validate()
    with pytest.raises(ValueError, match="unit_price"):
        OrderItemRecord("C-1", "O-1", "I-1", "P-1", unit_price=Decimal("-1")).validate()
