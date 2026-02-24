from app.models.seller import InventoryPolicy, Seller, SellerPolicies, SellerStatus

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
            )
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
            )
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
            )
        ),
    ),
]
