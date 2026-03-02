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


class OrderSpikePolicy(BaseModel):
    auto_approve_max_multiplier: float  # spike above this ratio → HIGH risk


class SellerPolicies(BaseModel):
    inventory_low: InventoryPolicy
    order_spike: OrderSpikePolicy


class Seller(BaseModel):
    id: str
    name: str
    status: SellerStatus
    policies: SellerPolicies
