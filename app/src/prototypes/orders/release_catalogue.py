"""Apply one reviewed built catalogue while retaining the existing company's order store.

Growth beyond the unattended refresh threshold requires --reviewed-growth. All other
refresh checks remain active. A private SQLite backup precedes the transactional ingest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from pathlib import Path

from refresh import check_candidate, digest, locked, source_catalog
from store import CompanyStore

GROWTH = 'item growth exceeds the bounded automatic acceptance threshold'


def checked(path, expected):
    body = Path(path).read_bytes()
    if hashlib.sha256(body).hexdigest() != expected:
        raise ValueError('The reviewed release file changed. Check its exact digest.')
    return json.loads(body)


def apply(store, catalogue, config, backup, *, reviewed_growth=False, configuration_only=False, evidence):
    if store.one('SELECT id FROM company')['id'] != config.get('slug'):
        raise ValueError('Apply this release to its own company store.')
    # A reviewed public selection is a subset, not the company's source catalogue.
    if configuration_only:
        catalogue = source_catalog(store)
    items = [item for cat in catalogue['cats'] for item in cat['items']]
    counts = {'rows': len(items), 'priced items': sum(not item.get('q') for item in items),
              'price on request': sum(bool(item.get('q')) for item in items)}
    check = check_candidate(source_catalog(store), catalogue, counts)
    errors = [reason for reason in check['errors'] if not (reviewed_growth and reason == GROWTH)]
    if errors:
        raise ValueError('Review the catalogue release: ' + '; '.join(errors))
    backup = Path(backup)
    backup.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    fd = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    try:
        with sqlite3.connect(backup) as destination:
            store.db.backup(destination)
    except BaseException:
        backup.unlink(missing_ok=True)
        raise
    result = store.ingest_catalog(catalogue, config, actor='reviewed-release', evidence=evidence,
                                 idempotency_key='reviewed-release:' + digest([catalogue, config]))
    return {**result, 'added': len(check['added']), 'backup': str(backup), 'preserves_orders': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True, type=Path)
    parser.add_argument('--catalogue', required=True, type=Path)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--catalogue-sha256', required=True)
    parser.add_argument('--config-sha256', required=True)
    parser.add_argument('--backup', required=True, type=Path)
    parser.add_argument('--evidence', required=True)
    parser.add_argument('--reviewed-growth', action='store_true')
    parser.add_argument('--configuration-only', action='store_true')
    args = parser.parse_args()
    catalogue = checked(args.catalogue, args.catalogue_sha256)
    config = checked(args.config, args.config_sha256)
    if not args.database.is_file() or args.database.is_symlink():
        raise ValueError('Use the existing commissioned company database.')
    with locked(args.database.with_suffix('.refresh.lock')) as acquired:
        if not acquired:
            raise ValueError('A catalogue update is active. Retry this release afterward.')
        store = CompanyStore(args.database)
        try:
            print(json.dumps(apply(store, catalogue, config, args.backup,
                                   reviewed_growth=args.reviewed_growth,
                                   configuration_only=args.configuration_only or config.get('catalogueScope') == 'reviewed_images',
                                   evidence=args.evidence)))
        finally:
            store.close()


if __name__ == '__main__':
    main()
