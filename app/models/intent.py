from enum import Enum


class Intent(str, Enum):
    REORDER = "reorder"
    FLAG_ORDER_SPIKE = "flag_order_spike"
    UNKNOWN = "unknown"
