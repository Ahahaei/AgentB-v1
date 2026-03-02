from app.models.seller import (
    InventoryPolicy,
    OrderSpikePolicy,
    RefundRatePolicy,
    Seller,
    SellerPolicies,
    SellerStatus,
)

MOCK_SELLERS: list[Seller] = [
    Seller(
        id="S001",
        name="Gadget Galaxy",
        status=SellerStatus.ACTIVE,
        policies=SellerPolicies(
            inventory_low=InventoryPolicy(
                reorder_point=5,
                reorder_quantity=40,
                auto_approve_max_units=50,
                auto_approve_max_spend=500.0,
                unit_cost=8.00,
            ),
            # spike up to 2x baseline → LOW; above 2x → HIGH
            order_spike=OrderSpikePolicy(auto_approve_max_multiplier=2.0),
            # refund rate up to 10% → LOW; above 10% → HIGH
            high_refund_rate=RefundRatePolicy(auto_approve_max_rate=0.10),
        ),
    ),
    # reorder 40 * $8.00 = $320 < $500, 40 < 50 → LOW risk by default
    Seller(
        id="S002",
        name="Bulk Barn",
        status=SellerStatus.ACTIVE,
        policies=SellerPolicies(
            inventory_low=InventoryPolicy(
                reorder_point=10,
                reorder_quantity=200,
                auto_approve_max_units=100,
                auto_approve_max_spend=800.0,
                unit_cost=5.00,
            ),
            # tighter threshold — spike above 1.5x baseline → HIGH
            order_spike=OrderSpikePolicy(auto_approve_max_multiplier=1.5),
            # tighter threshold — refund rate above 5% → HIGH
            high_refund_rate=RefundRatePolicy(auto_approve_max_rate=0.05),
        ),
    ),
    # reorder 200 * $5.00 = $1000 > $800, 200 > 100 → HIGH risk by default
    Seller(
        id="S003",
        name="Dormant Shop",
        status=SellerStatus.INACTIVE,
        policies=SellerPolicies(
            inventory_low=InventoryPolicy(
                reorder_point=5,
                reorder_quantity=20,
                auto_approve_max_units=50,
                auto_approve_max_spend=500.0,
                unit_cost=10.00,
            ),
            order_spike=OrderSpikePolicy(auto_approve_max_multiplier=2.0),
            high_refund_rate=RefundRatePolicy(auto_approve_max_rate=0.10),
        ),
    ),
]
