import uuid

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from app import store
from app.models.seller import (
    InventoryPolicy,
    OrderSpikePolicy,
    RefundRatePolicy,
    Seller,
    SellerPolicies,
    SellerStatus,
)

router = APIRouter(tags=["onboard"])

_DEFAULT_POLICIES = SellerPolicies(
    inventory_low=InventoryPolicy(
        reorder_point=10,
        reorder_quantity=50,
        auto_approve_max_units=20,
        auto_approve_max_spend=500.0,
        unit_cost=10.0,
    ),
    order_spike=OrderSpikePolicy(auto_approve_max_multiplier=2.0),
    high_refund_rate=RefundRatePolicy(auto_approve_max_rate=0.10),
)

_FORM_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Get started with SellerOps</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 480px; margin: 80px auto; padding: 0 24px; color: #111; }
    h1 { font-size: 1.6rem; margin-bottom: 8px; }
    p { color: #555; margin-bottom: 32px; }
    label { display: block; font-weight: 600; margin-bottom: 6px; }
    input[type=text] { width: 100%; padding: 10px 12px; font-size: 1rem; border: 1px solid #ccc; border-radius: 6px; box-sizing: border-box; }
    button { margin-top: 20px; width: 100%; padding: 12px; font-size: 1rem; font-weight: 600; background: #4A154B; color: #fff; border: none; border-radius: 6px; cursor: pointer; }
    button:hover { background: #611f69; }
  </style>
</head>
<body>
  <h1>Get started with SellerOps</h1>
  <p>Connect your Slack workspace to manage Amazon operations from any channel.</p>
  <form method="POST" action="/onboard">
    <label for="name">Store name</label>
    <input type="text" id="name" name="name" placeholder="e.g. Acme Gadgets" required autofocus>
    <button type="submit">Connect Slack</button>
  </form>
</body>
</html>"""

_SUCCESS_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>You're all set — SellerOps</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 480px; margin: 80px auto; padding: 0 24px; color: #111; text-align: center; }
    h1 { font-size: 1.8rem; margin-bottom: 12px; }
    p { color: #555; font-size: 1.05rem; }
  </style>
</head>
<body>
  <h1>You're all set.</h1>
  <p>Your bot is live in your chosen channel.<br>Check your Slack DMs to get started.</p>
</body>
</html>"""


@router.get("/onboard", response_class=HTMLResponse)
def onboard_form():
    return _FORM_HTML


@router.post("/onboard")
def onboard_submit(name: str = Form(...)):
    seller = Seller(
        id=str(uuid.uuid4()),
        name=name,
        status=SellerStatus.ACTIVE,
        policies=_DEFAULT_POLICIES,
    )
    store.create_seller(seller)
    return RedirectResponse(url=f"/slack/authorize?seller_id={seller.id}", status_code=303)


@router.get("/success", response_class=HTMLResponse)
def success():
    return _SUCCESS_HTML
