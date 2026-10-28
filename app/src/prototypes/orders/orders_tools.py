"""Manufacturer family in the native harness's specs/read/call contract.

The HTTP/CLI registry in tools.py keeps its own read/write selector and schema shape.
This adapter translates those contracts and accepts a capability fixed by the host.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

try:
    from . import tools as business
except ImportError:
    from app.src.prototypes.orders import tools as business

# These operations consume a host-computed quote or verified identity. A model's
# assertion is not that evidence; the order API and reviewed claim path own them.
HOST_ONLY = frozenset({"orders_submit", "claim_grant"})
READ_NAMES = tuple(business.READ_NAMES)
WRITE_NAMES = tuple(name for name in business.WRITE_NAMES if name not in HOST_ONLY)


@dataclass(frozen=True)
class CompanyContext:
    """Host capability. Build from authenticated membership or explicit local startup.

    Never construct this from model tool arguments, a query string or request JSON.
    The database handle and company are fixed for the lifetime of this capability.
    """

    store: object
    company: str
    actor: str
    role: str = "public"
    evidence: str = ""
    writes: bool = False

    def checked(self):
        if self.role not in {"public", "operator", "owner", "admin"} or not self.actor:
            raise PermissionError("Use a host-authenticated company principal.")
        company = self.store.one("SELECT id FROM company")
        if not company or company["id"] != self.company:
            raise PermissionError("The database belongs to another company.")
        return {"store": self.store, "actor": self.actor, "role": self.role, "evidence": self.evidence}


def specs(write=True):
    """Native harness: False means reads; True means reads plus writes."""
    rows = business.specs(False) + (business.specs(True) if write else [])
    return [
        {
            "type": "function",
            "name": row["name"],
            "description": row["description"],
            "inputSchema": deepcopy(row["parameters"]),
        }
        for row in rows
        if row["name"] not in HOST_ONLY
    ]


def available(context):
    context.checked()
    return [row for row in specs(context.writes) if context.role in business.REGISTRY[row["name"]]["roles"]]


def _context(context):
    if not isinstance(context, CompanyContext):
        raise PermissionError("The host must supply an authenticated manufacturer CompanyContext.")
    return context.checked()


def read(context, name, args):
    return business.read(_context(context), name, args)


def call(context, name, args):
    trusted = _context(context)
    if not context.writes or name not in WRITE_NAMES:
        raise PermissionError("This host capability permits declared manufacturer writes only.")
    return business.call(trusted, name, args)
