"""Authenticated, company-bound immutable configuration publication for the native platform.

The source CompanyStore remains intact. The active saved document supplies both the public
catalogue and server pricing. Repeated delivery is idempotent; stale deliveries cannot roll back.
"""
from __future__ import annotations

import copy
import hashlib
import hmac
import json
import math
import os
import re
import sqlite3
import xml.etree.ElementTree as ET
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

MAX_BYTES = 8_000_000
SCHEMA = 'rocoto.manufacturer.configurator.v1'


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def drawing(value):
    if not isinstance(value, str) or len(value) > 30000 or '<!' in value:
        raise ValueError('Use a bounded SVG drawing.')
    try:
        root = ET.fromstring(value)
    except ET.ParseError as exc:
        raise ValueError('Use a valid SVG drawing.') from exc
    tags = {'svg', 'g', 'path', 'circle', 'ellipse', 'rect', 'line', 'polyline', 'polygon', 'text', 'tspan', 'title', 'desc', 'defs', 'marker', 'linearGradient', 'radialGradient', 'stop'}
    attributes = {'viewBox', 'width', 'height', 'x', 'y', 'x1', 'x2', 'y1', 'y2', 'cx', 'cy', 'rx', 'ry', 'r',
                  'd', 'points', 'fill', 'fill-opacity', 'stroke', 'stroke-width', 'stroke-linecap', 'stroke-linejoin',
                  'stroke-dasharray', 'opacity', 'transform', 'font-size', 'font-family', 'font-weight', 'text-anchor',
                  'dominant-baseline', 'aria-hidden', 'role', 'class', 'id', 'markerWidth', 'markerHeight', 'refX',
                  'refY', 'orient', 'markerUnits', 'marker-start', 'marker-end', 'preserveAspectRatio',
                  'offset', 'stop-color', 'stop-opacity', 'gradientUnits', 'gradientTransform', 'fx', 'fy', 'fr', 'spreadMethod'}
    if root.tag.rsplit('}', 1)[-1] != 'svg':
        raise ValueError('Use an SVG drawing.')
    for node in root.iter():
        if node.tag.rsplit('}', 1)[-1] not in tags:
            raise ValueError('Use geometric SVG drawing elements.')
        for key, item in node.attrib.items():
            if key not in attributes or re.search(r'(?:https?:|data:|javascript:|[<>;])', item, re.I):
                raise ValueError('Use geometric SVG attributes.')
            if 'url(' in item and not re.fullmatch(r'url\(#[A-Za-z0-9_-]+\)', item):
                raise ValueError('Use local drawing markers.')
    return value


def validate(document, slug):
    if (not isinstance(document, dict) or set(document) != {'schema', 'configuration', 'catalogue', 'attachments'}
            or document.get('schema') != SCHEMA or not isinstance(document['configuration'], dict)
            or document['configuration'].get('slug') != slug or not isinstance(document['catalogue'], dict)
            or not isinstance(document['attachments'], list)):
        raise ValueError('Publish this company’s complete configuration.')
    encoded = dump(document)
    if len(encoded.encode()) > MAX_BYTES:
        raise ValueError('Keep configuration snapshots within 8 MB.')
    count = 0
    blocked = {'__proto__', 'prototype', 'constructor', 'script', 'scripts', 'eval', 'html', 'css',
               'filesystem_path', 'database', 'command', 'commands', 'tool_families', 'host_module'}
    def walk(value, key='', depth=0):
        nonlocal count
        count += 1
        if count > 250000 or depth > 24:
            raise ValueError('Keep configuration structure bounded.')
        if value is None or type(value) is bool:
            return
        if type(value) in (int, float):
            if not math.isfinite(value) or abs(value) > 1e12 or (key in {'p', 'price', 'amount', 'vat', 'delivery'} and value < 0):
                raise ValueError('Use finite non-negative prices.')
        elif isinstance(value, str):
            if (len(value) > 16000 or re.search(r'<\s*/?\s*[a-zA-Z!]|(?:javascript|vbscript|data|file):', value, re.I)
                    or any(ord(c) < 32 and c not in '\n\t' for c in value)):
                raise ValueError('Use plain configuration text.')
            if key.lower() in {'url', 'src', 'href', 'source_url', 'image_url', 'website', 'logo', 'img', 'picture'} and value:
                relative = value.startswith('/') and not value.startswith('//') and '..' not in value.split('/')
                parsed = urlsplit(value)
                if re.search(r'''[\s<>"'`\\]''', value) or not relative and (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password):
                    raise ValueError('Use HTTPS or relative company assets.')
        elif isinstance(value, list):
            if len(value) > 20000:
                raise ValueError('Use bounded configuration lists.')
            for item in value:
                walk(item, key, depth + 1)
        elif isinstance(value, dict):
            for name, item in value.items():
                if not isinstance(name, str) or len(name) > 160 or name.lower() in blocked or name.lower().startswith('onload'):
                    raise ValueError('Use data configuration fields.')
                if name == 'drawings':
                    if not isinstance(item, dict) or len(item) > 300:
                        raise ValueError('Use a bounded drawing dictionary.')
                    for identifier, svg in item.items():
                        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', identifier):
                            raise ValueError('Use drawing identifiers.')
                        drawing(svg)
                else:
                    walk(item, name, depth + 1)
        else:
            raise ValueError('Use JSON configuration data.')
    walk(document)
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', document['configuration'].get('accent', '#12356d')):
        raise ValueError('Use a hexadecimal accent colour.')
    seen = set()
    cats = document['catalogue'].get('cats', [])
    if not isinstance(cats, list):
        raise ValueError('Use catalogue categories.')
    for category in cats:
        if not isinstance(category, dict) or not isinstance(category.get('code'), str) or not isinstance(category.get('items'), list):
            raise ValueError('Use complete catalogue categories.')
        for item in category['items']:
            if not isinstance(item, dict) or not isinstance(item.get('c'), str) or item['c'] in seen:
                raise ValueError('Use unique catalogue article identifiers.')
            seen.add(item['c'])
    return encoded


class Conflict(ValueError):
    pass


class Bridge:
    def __init__(self, state, *, token='', company='', scope=''):
        self.state = Path(state) if state else None
        self._token, self.company, self.scope = token, company, scope

    def authorized(self, company, authorization, scope):
        return bool(self.state and len(self._token) >= 32 and self.company == company and self.scope
                    and hmac.compare_digest(scope.encode(), self.scope.encode())
                    and hmac.compare_digest(authorization.encode(), ('Bearer ' + self._token).encode()))

    def _path(self, company):
        if company != self.company or not self.state or not re.fullmatch(r'[a-z][a-z0-9-]{1,40}', company):
            raise ValueError('Choose the connected company.')
        return self.state / 'companies' / company / 'configurator-versions.sqlite'

    def active(self, company):
        if company != self.company or not self.state:
            return None
        path = self._path(company)
        if not path.is_file():
            return None
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=3)) as db:
            db.row_factory = sqlite3.Row
            row = db.execute('SELECT v.* FROM versions v JOIN active a ON a.id=v.id').fetchone()
            if row is None:
                return None
            return {**dict(row), 'document': json.loads(row['document'])}

    def publish(self, company, value):
        if not isinstance(value, dict):
            raise ValueError('Publish a saved configuration object.')
        if value.get('company_id') != self.scope or value.get('company_slug') != company:
            raise ValueError('Publish to the connected company.')
        version = value.get('version')
        if (not isinstance(version, dict) or not re.fullmatch(r'[a-f0-9]{32}', str(version.get('id', '')))
                or type(version.get('revision')) is not int or not 0 <= version['revision'] < 1_000_000):
            raise ValueError('Publish an immutable saved version.')
        encoded = validate(version.get('document'), company)
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        if not hmac.compare_digest(digest, str(version.get('sha256', ''))):
            raise ValueError('Publish the complete saved snapshot hash.')
        path = self._path(company)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with closing(sqlite3.connect(path, timeout=10)) as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS versions(id TEXT PRIMARY KEY,revision INTEGER UNIQUE NOT NULL,
                sha256 TEXT NOT NULL,document TEXT NOT NULL,published_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS active(singleton INTEGER PRIMARY KEY CHECK(singleton=1),id TEXT NOT NULL);
                CREATE TRIGGER IF NOT EXISTS immutable_versions_update BEFORE UPDATE ON versions
                  BEGIN SELECT RAISE(ABORT,'immutable snapshot'); END;
                CREATE TRIGGER IF NOT EXISTS immutable_versions_delete BEFORE DELETE ON versions
                  BEGIN SELECT RAISE(ABORT,'immutable snapshot'); END;''')
            db.execute('BEGIN IMMEDIATE')
            previous = db.execute('SELECT v.id,v.revision,v.sha256,v.published_at FROM versions v JOIN active a ON a.id=v.id').fetchone()
            existing = db.execute('SELECT revision,sha256,published_at FROM versions WHERE id=?', (version['id'],)).fetchone()
            if existing:
                if existing[:2] != (version['revision'], digest):
                    raise Conflict('This version identifier already has different content.')
                if not previous or previous[0] != version['id']:
                    raise Conflict('A newer configuration is already published.')
                published_at = existing[2]
            else:
                if previous and previous[1] >= version['revision']:
                    raise Conflict('A newer configuration is already published.')
                published_at = datetime.now(timezone.utc).isoformat()
                db.execute('INSERT INTO versions VALUES(?,?,?,?,?)', (version['id'], version['revision'], digest, encoded, published_at))
                db.execute('INSERT INTO active VALUES(1,?) ON CONFLICT(singleton) DO UPDATE SET id=excluded.id', (version['id'],))
            db.commit()
        path.chmod(0o600)
        return {'ok': True, 'published': True, 'version_id': version['id'], 'revision': version['revision'],
                'sha256': digest, 'published_at': published_at}


def from_environment(state):
    return Bridge(state, token=os.environ.pop('ROCOTO_ORDERS_CONFIGURATOR_TOKEN', ''),
                  company=os.environ.get('ROCOTO_ORDERS_CONFIGURATOR_COMPANY', ''),
                  scope=os.environ.get('ROCOTO_ORDERS_CONFIGURATOR_SCOPE', ''))


def catalogue(document):
    result = copy.deepcopy(document['catalogue'])
    overrides = result.pop('price_overrides', [])
    if isinstance(overrides, list):
        for override in overrides:
            for category in result.get('cats', []):
                for item in category.get('items', []):
                    if item['c'] == override.get('item_id'):
                        basis, amount = override.get('basis'), override.get('amount')
                        if basis not in {'p', 'cut'} or type(amount) not in {int, float} or not math.isfinite(amount) or amount < 0:
                            raise ValueError('Use a finite price override with its p or cut basis.')
                        item[basis] = amount
                        if basis == 'p':
                            item.pop('q', None)
    return result


def script(source, document):
    """Replace the single build-generated data assignment; keep executable renderer bytes."""
    marker = 'window.RocotoConfig='
    start = source.find(marker)
    if start < 0:
        raise ValueError('Use a built company configurator.')
    begin = start + len(marker)
    original, consumed = json.JSONDecoder().raw_decode(source[begin:])
    config = document['configuration']
    widget = copy.deepcopy(original)
    for key in ('accent', 'hours', 'shop', 'strings', 'geo', 'turnaround', 'checkout', 'questionnaire', 'picker',
                'drawings', 'headline', 'description', 'button_label', 'theme', 'texts', 'assets', 'delivery'):
        if key in config:
            widget[key] = copy.deepcopy(config[key])
        elif key in ('questionnaire', 'picker', 'turnaround', 'theme', 'texts', 'assets'):
            widget.pop(key, None)
    if config.get('logo'):
        widget['logo'] = config['logo'] if config['logo'].startswith('https://') else '/' + config['slug'] + config['logo']
    if config.get('button_label'):
        for words in widget.get('strings', {}).values():
            words['go'] = config['button_label']
    return source[:begin] + dump(widget) + source[begin + consumed:]
