"""Local operator CLI. Filesystem access to the private DB is the trust boundary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from . import tools
    from .store import CompanyStore
except ImportError:
    from store import CompanyStore

    import tools


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path)
    parser.add_argument("--actor", default="local-operator")
    parser.add_argument("--role", choices=["operator", "owner", "admin"], default="operator")
    parser.add_argument("--evidence", default="")
    parser.add_argument(
        "command", choices=["specs", "ingest", "export", *tools.READ_NAMES, *tools.WRITE_NAMES]
    )
    parser.add_argument("--args", default="{}", help="JSON object; prefix @ to read a local JSON file")
    args = parser.parse_args()
    if args.command == "specs":
        result = tools.openai_specs(False) + tools.openai_specs(True)
    else:
        if not args.db:
            parser.error("--db is required")
        payload = json.loads(Path(args.args[1:]).read_text() if args.args.startswith("@") else args.args)
        store = CompanyStore(args.db)
        try:
            context = {"store": store, "actor": args.actor, "role": args.role, "evidence": args.evidence}
            if args.command == "ingest":
                if not args.evidence:
                    parser.error("--evidence is required for ingest")
                result = store.ingest_catalog(
                    json.loads(Path(payload["catalog"]).read_text()),
                    json.loads(Path(payload["config"]).read_text()),
                    args.actor,
                    args.evidence,
                )
            elif args.command == "export":
                result = store.export_catalog()
            else:
                result = (tools.call if args.command in tools.WRITE_NAMES else tools.read)(
                    context, args.command, payload
                )
        finally:
            store.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
