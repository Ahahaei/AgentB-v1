TOOLS: list[dict] = [
    {
        "name": "reorder_sku",
        "description": (
            "Place a reorder for a specific product SKU. "
            "The quantity you specify is validated against the seller's policy thresholds "
            "and will either be auto-executed or escalated for the seller's approval."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sku": {
                    "type": "string",
                    "description": "The product SKU to reorder, e.g. WIDGET-42",
                },
                "quantity": {
                    "type": "integer",
                    "description": "Number of units to reorder",
                },
            },
            "required": ["sku", "quantity"],
        },
    },
    {
        "name": "list_approvals",
        "description": "List all pending approvals waiting for the seller's decision.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_refund_rate",
        "description": "Return the seller's most recently recorded refund rate.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
]
