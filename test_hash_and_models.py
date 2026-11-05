from decimal import Decimal

import pytest

from dv_ingest.hash import hash_components, hash_diff, hub_hash
from dv_ingest.models import CustomerOrderRecord


def test_hash_is_stable_across_case_and_whitespace() -> None:
    assert hash_components(" customer-1 ") == hash_components("CUSTOMER-1")


def test_null_is_distinct_from_empty_string() -> None:
    assert hash_diff([None]) != hash_diff([""])


def test_entity_namespace_prevents_hub_collisions() -> None:
    assert hub_hash("CUSTOMER", "100") != hub_hash("ORDER", "100")


def test_record_validation_rejects_missing_keys() -> None:
    with pytest.raises(ValueError, match="customer_id"):
        CustomerOrderRecord("", "order-1").validate()


def test_record_validation_rejects_negative_amount() -> None:
    with pytest.raises(ValueError, match="negative"):
        CustomerOrderRecord("customer-1", "order-1", order_total=Decimal("-1")).validate()
