"""Explicit synthetic QA source for a fresh, isolated manufacturer workspace.

Run: python3 manufacturer_seed.py --state /tmp/private-qa --company-id <native-scope> --confirm-synthetic
"""
import argparse
import json
import sqlite3
from pathlib import Path

from manufacturer_store import default_configuration, stamp


def seed(state, company_id):
    state = Path(state).absolute()
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    source = state / 'manufacturer-qa-source.sqlite'
    binding = state / 'manufacturer-source.json'
    if source.exists() or binding.exists() or (state / 'manufacturer-platform.sqlite').exists():
        raise ValueError('Choose a fresh isolated QA workspace.')
    config = default_configuration()
    config['name'] = {'en': 'Sample Hardware · synthetic QA', 'bg': 'Sample Hardware · синтетичен тест'}
    meta = {'company': config['name'], 'currency': 'EUR', 'vat': .2, 'source': config['source'], 'forms': [], 'metals': [], 'services': []}
    with sqlite3.connect(source) as db:
        db.executescript('''CREATE TABLE company(id TEXT PRIMARY KEY,config TEXT,catalog_meta TEXT);
            CREATE TABLE product_types(id TEXT PRIMARY KEY,position INTEGER,data TEXT,active INTEGER);
            CREATE TABLE items(id TEXT PRIMARY KEY,type_id TEXT,position INTEGER,data TEXT,active INTEGER);
            CREATE TABLE customers(id TEXT PRIMARY KEY,data TEXT);
            CREATE TABLE orders(id TEXT PRIMARY KEY,customer_id TEXT,state TEXT,quote TEXT,created_at TEXT);
            CREATE TABLE order_lines(id INTEGER PRIMARY KEY,order_id TEXT,item_id TEXT,quantity REAL,data TEXT);''')
        db.execute('INSERT INTO company VALUES(?,?,?)', ('sample-hardware', json.dumps(config), json.dumps(meta)))
        for index, (company, status, total) in enumerate([('Example Construction · synthetic', 'requested', 1420), ('Example Facilities · synthetic', 'quoted', 780), ('Example Joinery · synthetic', 'accepted', 360)], 1):
            customer = {'name': f'QA buyer {index}', 'company': company, 'email': f'buyer{index}@example.com', 'website': 'https://example.com', 'work_type': 'Synthetic door hardware requirements'}
            oid = f'QA-{index:03}'
            db.execute('INSERT INTO customers VALUES(?,?)', (oid, json.dumps(customer)))
            db.execute('INSERT INTO orders VALUES(?,?,?,?,?)', (oid, oid, status, json.dumps({'gross': total, 'currency': 'EUR', 'fulfilment': 'delivery'}), stamp()))
            line = {'item_id': None, 'quantity': index * 10, 'custom': 'Synthetic QA door hardware request'}
            db.execute('INSERT INTO order_lines(order_id,item_id,quantity,data) VALUES(?,?,?,?)', (oid, None, index * 10, json.dumps(line)))
    source.chmod(0o600)
    binding.write_text(json.dumps({'company_id': company_id, 'company_slug': 'sample-hardware', 'database': str(source)}, indent=2) + '\n')
    binding.chmod(0o600)
    return {'synthetic': True, 'state': str(state), 'source': str(source), 'orders': 3}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', required=True)
    parser.add_argument('--company-id', required=True)
    parser.add_argument('--confirm-synthetic', required=True, action='store_true')
    args = parser.parse_args()
    print(json.dumps(seed(args.state, args.company_id)))
