"""The recipient's exact Orders origin; plain HTTP is limited to loopback development."""
import os
from urllib.parse import urlsplit


def configured_origin():
    value=os.environ.get('MANUFACTURER_ORDERS_ORIGIN','https://orders.example.test').strip().rstrip('/')
    if any(c.isspace() or c in "<>\"'\\;," for c in value):
        raise ValueError('Use one exact Orders origin.')
    p=urlsplit(value)
    try:
        _ = p.port
    except ValueError:
        raise ValueError('Use a valid Orders origin port.') from None
    local=p.scheme=='http' and p.hostname in {'localhost','127.0.0.1','::1'}
    if not p.hostname or p.username or p.password or p.query or p.fragment or p.path or (p.scheme!='https' and not local):
        raise ValueError('Set MANUFACTURER_ORDERS_ORIGIN to an HTTPS origin or a loopback development origin.')
    return value
