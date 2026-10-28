"""Reviewed catalogue growth keeps existing orders, prices and operational records."""
import copy
import sqlite3

import pytest
from refresh import source_catalog
from release_catalogue import apply, checked
from test_store import store as store
from test_store import submit


def growth(store):
    candidate = source_catalog(store)
    original = candidate['cats'][0]['items'][0]
    candidate['cats'][0]['items'].extend({**copy.deepcopy(original), 'c': f'new-{index}'} for index in range(30))
    return candidate


def test_reviewed_growth_retains_orders_and_price_overrides(store, tmp_path):
    store.set_price('A', 17, 'owner', 'contract')
    submit(store)
    tables = ('customers', 'orders', 'order_lines', 'order_events', 'messages', 'price_overrides', 'stock_events')
    before = {table: store.rows(f'SELECT * FROM {table}') for table in tables}
    result = apply(store, growth(store), {'slug': 'example'}, tmp_path / 'backup.db',
                   reviewed_growth=True, evidence='approved complete catalogue')
    assert result['added'] == 30
    assert store.item('A')['item']['p'] == 17
    for table in tables:
        assert store.rows(f'SELECT * FROM {table}') == before[table]
    with sqlite3.connect(tmp_path / 'backup.db') as db:
        assert db.execute('SELECT COUNT(*) FROM orders').fetchone()[0] == 1
        assert db.execute('SELECT COUNT(*) FROM items').fetchone()[0] == 1


def test_growth_permission_cannot_remove_existing_items_or_change_basis(store, tmp_path):
    candidate = growth(store)
    candidate['cats'][0]['items'].pop(0)
    with pytest.raises(ValueError, match='disappeared'):
        apply(store, candidate, {'slug': 'example'}, tmp_path / 'backup.db',
              reviewed_growth=True, evidence='review')
    assert not (tmp_path / 'backup.db').exists()
    with pytest.raises(ValueError, match='threshold'):
        apply(store, growth(store), {'slug': 'example'}, tmp_path / 'backup.db', evidence='review')


def test_release_digest_must_match_exact_file(tmp_path):
    source = tmp_path / 'catalog.json'
    source.write_text('{}')
    with pytest.raises(ValueError, match='digest'):
        checked(source, '0' * 64)



def test_public_reviewed_subset_only_updates_configuration(store, tmp_path):
    before = source_catalog(store)
    submit(store)
    result = apply(store, {'cats': []}, {'slug': 'example', 'catalogueScope': 'reviewed_images'},
                   tmp_path / 'configuration-backup.db', configuration_only=True, evidence='reviewed public selection')
    assert result['added'] == 0
    assert source_catalog(store) == before
    assert store.one('SELECT count(*) n FROM orders')['n'] == 1
