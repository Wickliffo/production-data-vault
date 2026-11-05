import os

import psycopg
import pytest

DATABASE_URL = os.getenv("DATABASE_URL")


@pytest.fixture
def connection():
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL is not set")
    with psycopg.connect(DATABASE_URL) as conn:
        yield conn
        conn.execute("TRUNCATE staging.customer_order_batch CASCADE")
        conn.commit()
