"""Product configuration CRUD + JSON seeding.

Products are the multi-product reuse surface: everything product-specific lives
in a `products` row. Non-engineers manage these via /admin/products; seeding
from products.example.json is only a bootstrap convenience.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Product

log = logging.getLogger(__name__)


def _parse_date(value) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    # Accept "YYYY-MM-DD" or full ISO strings.
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        log.warning("Could not parse launch_date=%r; storing NULL", value)
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def list_products(session: Session, only_active: bool = False) -> list[Product]:
    stmt = select(Product).order_by(Product.name)
    if only_active:
        stmt = stmt.where(Product.active.is_(True))
    return list(session.scalars(stmt))


def get_product(session: Session, product_id: int) -> Optional[Product]:
    return session.get(Product, product_id)


def upsert_product(session: Session, data: dict) -> Product:
    """Create or update a product by name."""
    name = data["name"].strip()
    product = session.scalar(select(Product).where(Product.name == name))
    if product is None:
        product = Product(name=name)
        session.add(product)

    product.keywords = data.get("keywords", []) or []
    product.official_accounts = data.get("official_accounts", []) or []
    product.seed_kols = data.get("seed_kols", []) or []
    product.launch_date = _parse_date(data.get("launch_date"))
    product.active = bool(data.get("active", True))
    session.commit()
    session.refresh(product)
    return product


def delete_product(session: Session, product_id: int) -> None:
    product = session.get(Product, product_id)
    if product:
        session.delete(product)
        session.commit()


def seed_from_file(session: Session, path: str) -> int:
    """Seed products from a JSON file when the table is empty. Returns count added."""
    existing = session.scalar(select(Product).limit(1))
    if existing is not None:
        log.info("Products table not empty; skipping seed from %s", path)
        return 0
    with open(path, "r", encoding="utf-8") as fh:
        rows = json.load(fh)
    added = 0
    for row in rows:
        # Ignore documentation-only keys like "_comment".
        clean = {k: v for k, v in row.items() if not k.startswith("_")}
        if not clean.get("name"):
            continue
        upsert_product(session, clean)
        added += 1
    log.info("Seeded %d products from %s", added, path)
    return added
