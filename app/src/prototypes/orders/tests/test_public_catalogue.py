import copy
import json

import pytest
from public_catalogue import for_site, select


def fixture():
    catalogue = {
        "currency": "EUR", "metals": {"steel": "Steel", "copper": "Copper"},
        "cats": [
            {"code": "a", "metal": "steel", "items": [{"c": "A", "p": 3}, {"c": "B", "p": 5}]},
            {"code": "b", "metal": "copper", "items": [{"c": "C", "p": 8}]},
        ],
    }
    index = {"sets": {"a": ["a.webp"]}, "items": {"A": "a", "B": None}}
    return catalogue, index


def test_sales_collection_preserves_full_source_and_exact_prices():
    catalogue, index = fixture()
    original = copy.deepcopy(catalogue)
    public = select(catalogue, index)
    assert public["cats"] == [{"code": "a", "metal": "steel", "items": [{"c": "A", "p": 3}]}]
    assert public["metals"] == {"steel": "Steel"}
    assert catalogue == original


def test_live_prices_use_release_scope_without_revealing_new_items(tmp_path):
    catalogue, index = fixture()
    (tmp_path / "g").mkdir()
    (tmp_path / "g/index.json").write_text(json.dumps(index))
    (tmp_path / "site.json").write_text(json.dumps({"catalogueScope": "reviewed_images"}))
    catalogue["cats"][0]["items"][0]["p"] = 4
    catalogue["cats"][0]["items"].append({"c": "NEW", "p": 20})
    public = for_site(catalogue, tmp_path)
    assert public["cats"][0]["items"] == [{"c": "A", "p": 4}]


def test_missing_or_wrong_shot_selection_is_held(tmp_path):
    catalogue, index = fixture()
    index["sets"]["a"] = ["whole.webp", "front.webp"]
    with pytest.raises(ValueError, match="empty"):
        select(catalogue, index)
    (tmp_path / "site.json").write_text(json.dumps({"catalogueScope": "reviewed_images"}))
    with pytest.raises(ValueError, match="being prepared"):
        for_site(catalogue, tmp_path)


def test_list_filters_include_only_published_materials():
    catalogue, index = fixture()
    catalogue["metals"] = [{"id": "steel", "en": "Steel"}, {"id": "copper", "en": "Copper"}]
    assert select(catalogue, index)["metals"] == [{"id": "steel", "en": "Steel"}]
