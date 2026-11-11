"""Pydantic schemas for catalog API payloads. Decimals are serialised as strings."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ProductCostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    unit_cost: Decimal
    variable_cost_per_unit: Decimal | None
    currency: str
    label: str
    effective_from: datetime


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str
    title: str
    description: str | None
    image_url: str | None
    selling_price: Decimal
    currency: str
    source: str
    channel3_id: str | None
    cost: ProductCostOut | None = None


class CostIn(BaseModel):
    unit_cost: Decimal = Field(ge=0)
    variable_cost_per_unit: Decimal | None = Field(default=None, ge=0)


class PriceIn(BaseModel):
    selling_price: Decimal = Field(ge=0)


class ProductIn(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=300)
    selling_price: Decimal = Field(ge=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    description: str | None = None
    image_url: str | None = None
    source: str = "manual"
    channel3_id: str | None = None
    unit_cost: Decimal | None = Field(default=None, ge=0)
