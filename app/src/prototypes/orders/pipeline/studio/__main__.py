"""Company-scoped CLI for immutable plans, stage gates and native transport receipts."""

import argparse
import json
from pathlib import Path

from . import queue, schema


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--company", required=True)
    parser.add_argument(
        "command",
        choices=["init", "import", "gate", "authorize", "native-request", "native-result", "review", "audit"],
    )
    parser.add_argument("--input", type=Path, help="JSON command arguments or manifest")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output and args.output.exists():
        raise ValueError("Use a new evidence output path")
    data = json.loads(args.input.read_text()) if args.input else {}
    with schema.connect(args.db, args.company) as connection:
        if args.command == "init":
            schema.initialize(connection, args.company, **data)
            result = queue.usage(connection)
        elif args.command == "import":
            result = schema.import_manifest(connection, data)
        elif args.command == "gate":
            result = schema.record_gate(connection, **data)
        elif args.command == "authorize":
            result = queue.authorize(connection, **data)
        elif args.command == "native-request":
            result = queue.native_handoff(connection, **data)
        elif args.command == "native-result":
            result = queue.import_native(connection, data)
        elif args.command == "review":
            result = queue.review(connection, **data)
        else:
            result = queue.delivery_audit(connection)
    rendered = json.dumps(result, indent=2)
    if args.output:
        if args.output.exists():
            raise ValueError("Use a new evidence output path")
        args.output.write_text(rendered + "\n")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
