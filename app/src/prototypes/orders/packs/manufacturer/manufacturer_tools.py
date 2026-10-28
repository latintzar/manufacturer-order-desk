"""Manufacturer tools exported through the native vertical-owned family contract."""

from app.src.prototypes.orders import orders_tools as source


class NativeOrdersFamily:
    """Set-shaped names required by the native registry, delegating the orders contract."""

    READ_NAMES = frozenset(source.READ_NAMES)
    WRITE_NAMES = frozenset(source.WRITE_NAMES)
    HOST_ONLY = source.HOST_ONLY
    specs = staticmethod(source.specs)
    read = staticmethod(source.read)
    call = staticmethod(source.call)


family = NativeOrdersFamily()

__all__ = ["family"]
