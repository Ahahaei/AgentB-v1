from enum import Enum


class Intent(str, Enum):
    REORDER = "reorder"
    UNKNOWN = "unknown"
