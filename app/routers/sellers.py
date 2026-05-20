import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import store
from app.models.seller import Seller, SellerPolicies, SellerStatus

router = APIRouter(prefix="/sellers", tags=["sellers"])


class SellerCreate(BaseModel):
    name: str
    slack_channel_id: str
    slack_user_id: Optional[str] = None
    policies: SellerPolicies


class SellerUpdate(BaseModel):
    name: Optional[str] = None
    slack_channel_id: Optional[str] = None
    slack_user_id: Optional[str] = None
    status: Optional[SellerStatus] = None
    policies: Optional[SellerPolicies] = None


@router.get("")
def list_sellers() -> list[Seller]:
    return store.list_sellers()


@router.post("", status_code=201)
def create_seller(body: SellerCreate) -> Seller:
    seller = Seller(
        id=str(uuid.uuid4()),
        name=body.name,
        status=SellerStatus.ACTIVE,
        slack_channel_id=body.slack_channel_id,
        slack_user_id=body.slack_user_id,
        policies=body.policies,
    )
    store.create_seller(seller)
    return seller


@router.get("/{seller_id}")
def get_seller(seller_id: str) -> Seller:
    seller = store.get_seller(seller_id)
    if seller is None:
        raise HTTPException(status_code=404, detail=f"Seller '{seller_id}' not found")
    return seller


@router.patch("/{seller_id}")
def update_seller(seller_id: str, body: SellerUpdate) -> Seller:
    seller = store.get_seller(seller_id)
    if seller is None:
        raise HTTPException(status_code=404, detail=f"Seller '{seller_id}' not found")

    updates: dict = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.slack_channel_id is not None:
        updates["slack_channel_id"] = body.slack_channel_id
    if body.slack_user_id is not None:
        updates["slack_user_id"] = body.slack_user_id
    if body.status is not None:
        updates["status"] = body.status.value
    if body.policies is not None:
        updates["policies"] = body.policies.model_dump(mode="json")

    if not updates:
        return seller

    updated = store.update_seller(seller_id, updates)
    return updated
