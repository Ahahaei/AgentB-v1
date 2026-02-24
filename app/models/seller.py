from enum import Enum

from pydantic import BaseModel


class SellerStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class InventoryPolicy(BaseModel):
    reorder_point: int
    reorder_quantity: int
    auto_approve_max_units: int
    auto_approve_max_spend: float
    unit_cost: float


class SellerPolicies(BaseModel):
    inventory_low: InventoryPolicy


class Seller(BaseModel):
    id: str
    name: str
    status: SellerStatus
    policies: SellerPolicies
