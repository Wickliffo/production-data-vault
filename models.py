"""Input contracts for the reference ingestion pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any


@dataclass(frozen=True, slots=True)
class CustomerOrderRecord:
    customer_id: str
    order_id: str
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    order_status: str | None = None
    order_total: Decimal | None = None
    source_updated_at: datetime | None = None
    payload: dict[str, Any] | None = None

    def validate(self) -> None:
        if not self.customer_id or not self.customer_id.strip():
            raise ValueError("customer_id must be non-empty")
        if not self.order_id or not self.order_id.strip():
            raise ValueError("order_id must be non-empty")
        if self.order_total is not None and self.order_total < 0:
            raise ValueError("order_total must not be negative")


@dataclass(frozen=True, slots=True)
class OrderItemRecord:
    customer_id: str
    order_id: str
    order_item_id: str
    product_code: str
    product_name: str | None = None
    category: str | None = None
    quantity: int = 1
    unit_price: Decimal = Decimal("0")
    source_updated_at: datetime | None = None
    payload: dict[str, Any] | None = None

    def validate(self) -> None:
        for field_name, value in (
            ("customer_id", self.customer_id),
            ("order_id", self.order_id),
            ("order_item_id", self.order_item_id),
            ("product_code", self.product_code),
        ):
            if not value or not value.strip():
                raise ValueError(f"{field_name} must be non-empty")
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.unit_price < 0:
            raise ValueError("unit_price must not be negative")
