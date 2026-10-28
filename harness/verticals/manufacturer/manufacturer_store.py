"""Owned manufacturer drafts and a read-only adapter for the public CompanyStore schema.

No import of the public order writer: constructing CompanyStore would migrate its database.
The operator binds one existing source in this workspace's private manufacturer-source.json.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import sqlite3
import uuid
import xml.etree.ElementTree as ET
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from origin_config import configured_origin
ORIGIN = configured_origin()
DEFAULT_SLUG = 'sample-hardware'
SCHEMA = 'rocoto.manufacturer.configurator.v1'


class Invalid(ValueError):
    pass


class Conflict(ValueError):
    pass


class SourceUnavailable(ValueError):
    pass


class Missing(ValueError):
    pass


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def plain(value, maximum=200, *, empty=False):
    if (not isinstance(value, str) or len(value) > maximum or (not empty and not value.strip())
            or any(ord(c) < 32 and c not in '\n\t' for c in value) or re.search(r'<\s*/?\s*[a-zA-Z!]', value)):
        raise Invalid('Use plain text within the field length.')
    return value.strip()


def website(value):
    if not isinstance(value, str) or len(value) > 2048 or re.search(r'''[\s<>"'`\\]''', value):
        raise Invalid('Use an HTTPS website address.')
    parsed = urlparse(value)
    local_origin = parsed.scheme == 'http' and parsed.netloc == urlparse(ORIGIN).netloc and ORIGIN.startswith('http://')
    if (parsed.scheme != 'https' and not local_origin) or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise Invalid('Use an HTTPS website address.')
    return value


def default_configuration():
    return {'slug': DEFAULT_SLUG, 'name': {'en': 'Sample Hardware', 'bg': 'Sample Hardware'},
            'source': 'https://sample-hardware.example.test/', 'accent': '#12356d',
            'logo': '', 'currency': 'EUR', 'vat': .2,
            'headline': 'Order hardware', 'description': 'Choose products and send your requirements.',
            'button_label': 'Start order', 'questionnaire': {}, 'turnaround': {}, 'theme': {},
            'texts': {}, 'assets': []}


def default_document():
    return {'schema': SCHEMA, 'configuration': default_configuration(), 'catalogue': {'cats': []}, 'attachments': []}


def settings_of(document):
    config = document['configuration']
    slug = config['slug']
    language = config.get('defaultLanguage', 'en')
    spec_first = config.get('picker', {}).get('start', {}).get('spec')
    headline = ('Имате ли спецификация?' if language == 'bg' else 'Do you have a specification to upload or paste?') if spec_first else 'Instant quote'
    description = ('Качете списъка си или изберете обкова за вашия проект.' if language == 'bg' else 'Upload your list, or choose the hardware for your project.') if spec_first else 'Choose products and send your requirements.'
    button = config.get('strings', {}).get(language, {}).get('go') or ('Започни поръчка' if language == 'bg' else 'Start order')
    return {'accent': config.get('accent', '#12356d'), 'headline': config.get('headline', headline),
            'description': config.get('description', description),
            'button_label': config.get('button_label', button), 'company_slug': slug,
            'embed_url': f'{ORIGIN}/{slug}/rocoto/configurator.js', 'preview_url': f'{ORIGIN}/{slug}/#order'}


def drawing(value):
    if not isinstance(value, str) or len(value) > 30000 or '<!' in value:
        raise Invalid('Use a bounded SVG drawing.')
    try:
        root = ET.fromstring(value)
    except ET.ParseError as exc:
        raise Invalid('Use a valid SVG drawing.') from exc
    tags = {'svg', 'g', 'path', 'circle', 'ellipse', 'rect', 'line', 'polyline', 'polygon', 'text', 'tspan', 'title', 'desc', 'defs', 'marker', 'linearGradient', 'radialGradient', 'stop'}
    attributes = {'viewBox', 'width', 'height', 'x', 'y', 'x1', 'x2', 'y1', 'y2', 'cx', 'cy', 'rx', 'ry', 'r',
                  'd', 'points', 'fill', 'fill-opacity', 'stroke', 'stroke-width', 'stroke-linecap', 'stroke-linejoin',
                  'stroke-dasharray', 'opacity', 'transform', 'font-size', 'font-family', 'font-weight', 'text-anchor',
                  'dominant-baseline', 'aria-hidden', 'role', 'class', 'id', 'markerWidth', 'markerHeight', 'refX',
                  'refY', 'orient', 'markerUnits', 'marker-start', 'marker-end', 'preserveAspectRatio',
                  'offset', 'stop-color', 'stop-opacity', 'gradientUnits', 'gradientTransform', 'fx', 'fy', 'fr', 'spreadMethod'}
    if root.tag.rsplit('}', 1)[-1] != 'svg':
        raise Invalid('Use an SVG drawing.')
    for node in root.iter():
        if node.tag.rsplit('}', 1)[-1] not in tags:
            raise Invalid('Use geometric SVG drawing elements.')
        for key, item in node.attrib.items():
            if key not in attributes or re.search(r'(?:https?:|data:|javascript:|[<>;])', item, re.I):
                raise Invalid('Use geometric SVG attributes.')
            if 'url(' in item and not re.fullmatch(r'url\(#[A-Za-z0-9_-]+\)', item):
                raise Invalid('Use local drawing markers.')
    return value



def validate_document(value, slug):
    """Data-only, bounded snapshots. Source configuration and catalogue stay together."""
    if (not isinstance(value, dict) or set(value) != {'schema', 'configuration', 'catalogue', 'attachments'}
            or value.get('schema') != SCHEMA or not isinstance(value['configuration'], dict)
            or value['configuration'].get('slug') != slug or not isinstance(value['catalogue'], dict)
            or not isinstance(value['attachments'], list)):
        raise Invalid('Use this company’s complete configurator document.')
    try:
        encoded = dump(value)
    except (ValueError, TypeError):
        raise Invalid('Use finite JSON values in the configuration.') from None
    if len(encoded.encode()) > 8_000_000:
        raise Invalid('Keep the configurator document within 8 MB.')
    count = 0
    blocked = {'__proto__', 'prototype', 'constructor', 'javascript', 'script', 'scripts', 'code', 'eval', 'onclick', 'onload', 'html', 'css', 'filesystem_path', 'database', 'command', 'commands', 'tool_families', 'host_module'}
    # `code` is a published product/type identifier in the catalogue, not executable text.
    blocked.remove('code')
    def walk(item, key='', depth=0):
        nonlocal count
        count += 1
        if count > 250000 or depth > 24:
            raise Invalid('Keep the configuration structure within its limits.')
        if item is None or type(item) is bool:
            return
        if type(item) in {int, float}:
            if not math.isfinite(item) or abs(item) > 1e12 or (key.lower() in {'price', 'amount', 'p', 'net', 'gross', 'vat', 'delivery'} and item < 0):
                raise Invalid('Use finite, non-negative prices and bounded numbers.')
            return
        if isinstance(item, str):
            plain(item, 16000, empty=True)
            if re.search(r'(?:javascript|vbscript|data|file):', item, re.I):
                raise Invalid('Use data and HTTPS assets in the configurator.')
            if key.lower() in {'url', 'src', 'href', 'source_url', 'image_url', 'website', 'logo', 'img', 'picture'} and item:
                if item.startswith('/') and not item.startswith('//') and '..' not in item.split('/') and not re.search(r'''[\s<>"'`\\]''', item):
                    return
                website(item)
            return
        if isinstance(item, list):
            if len(item) > 20000:
                raise Invalid('Use bounded configuration lists.')
            for child in item:
                walk(child, key, depth + 1)
            return
        if isinstance(item, dict):
            for child_key, child in item.items():
                if not isinstance(child_key, str) or len(child_key) > 160 or child_key.lower() in blocked:
                    raise Invalid('Use declared data fields in the configurator.')
                if child_key == 'drawings':
                    if not isinstance(child, dict) or len(child) > 300:
                        raise Invalid('Use a bounded drawing dictionary.')
                    for identifier, svg in child.items():
                        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', identifier):
                            raise Invalid('Use drawing identifiers.')
                        drawing(svg)
                else:
                    walk(child, child_key, depth + 1)
            return
        raise Invalid('Use JSON data in the configurator.')
    walk(value)
    config = value['configuration']
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', config.get('accent', '#12356d')):
        raise Invalid('Use a six-digit hexadecimal accent colour.')
    for key, maximum in [('headline', 160), ('description', 1000), ('button_label', 80)]:
        if key in config:
            plain(config[key], maximum, empty=key == 'description')
            if '\n' in config[key] or '\t' in config[key]:
                raise Invalid('Keep these labels on one line.')
    questionnaire = config.get('questionnaire', {})
    if not isinstance(questionnaire, dict):
        raise Invalid('Use a questionnaire object.')
    questions = questionnaire.get('questions', [])
    if not isinstance(questions, list) or len(questions) > 100:
        raise Invalid('Use up to 100 questionnaire sections.')
    ids = set()
    for question in questions:
        if (not isinstance(question, dict) or not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_-]{0,79}', str(question.get('id', '')))
                or question['id'] in ids or question.get('kind', 'single') not in {'single', 'multiple', 'text', 'number', 'file'}):
            raise Invalid('Give each question a unique identifier and supported choice type.')
        ids.add(question['id'])
        options = question.get('options', [])
        if not isinstance(options, list) or len(options) > 100:
            raise Invalid('Use up to 100 choices per question.')
        option_ids = set()
        for option in options:
            if (not isinstance(option, dict) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}', str(option.get('id', '')))
                    or option['id'] in option_ids or not isinstance(option.get('label'), (dict, str))):
                raise Invalid('Give each choice a unique identifier and label.')
            option_ids.add(option['id'])
    if len(value['attachments']) > 100:
        raise Invalid('Keep up to 100 source attachments per revision.')
    for attachment in value['attachments']:
        if (not isinstance(attachment, dict) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}', str(attachment.get('file_id', '')))
                or set(attachment) - {'file_id', 'name', 'content_type', 'purpose', 'sha256'}):
            raise Invalid('Reference a native saved file by its identifier.')
    return copy.deepcopy(value)


class CompanySource:
    """A workspace-scoped, read-only view of a bound orders CompanyStore database."""
    def __init__(self, state, company_id):
        self.state = Path(state).absolute()
        self.company_id = company_id

    def binding(self):
        path = self.state / 'manufacturer-source.json'
        if not path.exists():
            return None
        try:
            if path.is_symlink() or path.stat().st_size > 8192:
                raise ValueError()
            value = json.loads(path.read_text())
            database = Path(value['database'])
            if (value.get('company_id') != self.company_id or not re.fullmatch(r'[a-z][a-z0-9-]{1,40}', value.get('company_slug', ''))
                    or not database.is_absolute() or not database.is_file() or database.is_symlink()):
                raise ValueError()
            return value
        except (OSError, KeyError, ValueError, TypeError):
            raise SourceUnavailable('Connect this workspace’s company order source.') from None

    @contextmanager
    def connect(self):
        binding = self.binding()
        if binding is None:
            yield None
            return
        try:
            with closing(sqlite3.connect(Path(binding['database']).as_uri() + '?mode=ro', uri=True, timeout=3)) as db:
                db.row_factory = sqlite3.Row
                db.execute('PRAGMA query_only=ON')
                db.execute('BEGIN')
                identities = db.execute('SELECT id,config FROM company LIMIT 2').fetchall()
                if (len(identities) != 1 or identities[0]['id'] != binding['company_slug']
                        or json.loads(identities[0]['config']).get('slug') != binding['company_slug']):
                    raise SourceUnavailable('Connect this workspace’s company order source.')
                yield db
        except (sqlite3.Error, OSError) as error:
            raise SourceUnavailable('The company order source is temporarily unavailable.') from error

    def status(self):
        try:
            with self.connect() as db:
                return {'status': 'connected' if db is not None else 'unbound',
                        'label': 'Company order database' if db is not None else 'Connect the company order database', 'read_only': True}
        except SourceUnavailable:
            return {'status': 'unavailable', 'label': 'Company order source needs attention', 'read_only': True}

    def company(self):
        config = default_configuration()
        try:
            with self.connect() as db:
                if db is not None:
                    config = json.loads(db.execute('SELECT config FROM company').fetchone()['config'])
        except SourceUnavailable:
            pass
        name = config.get('name', {})
        name = name.get('en') or name.get('bg') or 'Sample Hardware' if isinstance(name, dict) else str(name)
        source = config.get('source') or 'https://sample-hardware.example.test/'
        try:
            source = website(source)
        except Invalid:
            source = 'https://sample-hardware.example.test/'
        slug = config.get('slug', DEFAULT_SLUG)
        return {'id': self.company_id, 'slug': slug, 'name': name, 'website': source, 'domain': urlparse(source).hostname,
                'logo': f"{ORIGIN}/{slug}{config.get('logo', '')}" if str(config.get('logo', '')).startswith('/') else '',
                'configurator_url': f'{ORIGIN}/{slug}/#order',
                'capabilities': {'customer_research': config.get('checkout', {}).get('customerResearch', True) is not False,
                                 'agent_editing': config.get('checkout', {}).get('agentEditing', True) is not False},
                'warehouses': config.get('checkout', {}).get('warehouses', [])}

    def document(self):
        with self.connect() as db:
            if db is None:
                return default_document()
            company = db.execute('SELECT config,catalog_meta FROM company').fetchone()
            config, catalogue = json.loads(company['config']), json.loads(company['catalog_meta'])
            cats = []
            for record in db.execute('SELECT id,data FROM product_types WHERE active=1 ORDER BY position,id'):
                cat = json.loads(record['data'])
                cat['items'] = [json.loads(item['data']) for item in db.execute('SELECT data FROM items WHERE active=1 AND type_id=? ORDER BY position,id', (record['id'],))]
                cats.append(cat)
            catalogue['cats'] = cats
            # Preserve current source price overrides as their own complete, source-backed records.
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'price_overrides' in tables:
                catalogue['price_overrides'] = [dict(row) for row in db.execute('SELECT p.item_id,p.basis,p.amount,p.actor,p.evidence,p.created_at FROM price_overrides o JOIN prices p ON p.id=o.price_id ORDER BY p.item_id,p.basis')]
            return {'schema': SCHEMA, 'configuration': config, 'catalogue': catalogue, 'attachments': []}

    @staticmethod
    def _order(db, record):
        from manufacturer_order import project_order
        return project_order(db, record)

    def orders(self, limit=100, offset=0):
        if type(limit) is not int or not 1 <= limit <= 200 or type(offset) is not int or not 0 <= offset <= 1_000_000:
            raise Invalid('Choose a bounded order page.')
        with self.connect() as db:
            if db is None:
                return []
            return [self._order(db, row) for row in db.execute('SELECT * FROM orders ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?', (limit, offset)).fetchall()]

    def order(self, order_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone() if db is not None else None
            if row is None:
                raise Missing('Choose an order in this company.')
            return self._order(db, row)


class ManufacturerStore:
    def __init__(self, state, company_id, original=None):
        self.state = Path(state).absolute()
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.state / 'manufacturer-platform.sqlite'
        self.company_id = company_id
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS manufacturer_versions(
                    company_id TEXT NOT NULL,id TEXT NOT NULL,revision INTEGER NOT NULL,document TEXT NOT NULL,
                    sha256 TEXT NOT NULL,actor TEXT NOT NULL,actor_name TEXT NOT NULL,actor_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,label TEXT NOT NULL,summary TEXT NOT NULL,restored_from TEXT,
                    PRIMARY KEY(company_id,id),UNIQUE(company_id,revision));
                CREATE TABLE IF NOT EXISTS manufacturer_current(company_id TEXT PRIMARY KEY,version_id TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS manufacturer_demo_research(company_id TEXT NOT NULL,order_id TEXT NOT NULL,data TEXT NOT NULL,PRIMARY KEY(company_id,order_id));
                CREATE TABLE IF NOT EXISTS manufacturer_team(company_id TEXT PRIMARY KEY,revision INTEGER NOT NULL,data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS manufacturer_audit(id INTEGER PRIMARY KEY,company_id TEXT NOT NULL,action TEXT NOT NULL,
                    actor TEXT NOT NULL,evidence TEXT NOT NULL,created_at TEXT NOT NULL,data TEXT NOT NULL);
            ''')
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM manufacturer_current WHERE company_id=?', (company_id,)).fetchone() is None:
                document = original if original is not None else default_document()
                # Imported source bytes are a preserved baseline. Future edits pass data validation.
                identifier = uuid.uuid4().hex
                encoded = dump(document)
                db.execute('INSERT INTO manufacturer_versions VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                           (company_id, identifier, 0, encoded, hashlib.sha256(encoded.encode()).hexdigest(), 'source', 'Original configuration', 'source', stamp(), 'Original configuration', 'Initial company configuration and catalogue snapshot.', None))
                db.execute('INSERT INTO manufacturer_current VALUES(?,?)', (company_id, identifier))
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        with closing(sqlite3.connect(self.path, timeout=10)) as db:
            db.row_factory = sqlite3.Row
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def _current(self, db):
        return db.execute('SELECT v.* FROM manufacturer_versions v JOIN manufacturer_current c ON c.company_id=v.company_id AND c.version_id=v.id WHERE v.company_id=?', (self.company_id,)).fetchone()

    def configurator(self):
        with self.connect() as db:
            current = self._current(db)
            document = json.loads(current['document'])
            return {'settings': settings_of(document), 'document': document, 'revision': current['revision'],
                    'version_id': current['id'], 'state': 'draft', 'published': False, 'updated_at': current['created_at'],
                    'last_edit': {'created_at': current['created_at'], 'author': {'id': current['actor'], 'name': current['actor_name'], 'type': current['actor_type']}}}

    def _version(self, row, current_id, full=False):
        version = {'id': row['id'], 'revision': row['revision'], 'created_at': row['created_at'],
                   'author': {'id': row['actor'], 'name': row['actor_name'], 'type': row['actor_type']},
                   'name': row['label'], 'summary': row['summary'], 'sha256': row['sha256'], 'is_current': row['id'] == current_id,
                   'restored_from': row['restored_from']}
        if full:
            document = json.loads(row['document'])
            settings = settings_of(document)
            version.update(document=document, settings=settings, questionnaire=document['configuration'].get('questionnaire', {}),
                           catalogue=document['catalogue'], preview_url=settings['preview_url'])
        return version

    def versions(self):
        with self.connect() as db:
            current = self._current(db)
            return {'versions': [self._version(row, current['id']) for row in db.execute('SELECT * FROM manufacturer_versions WHERE company_id=? ORDER BY revision DESC', (self.company_id,))], 'revision': current['revision']}

    def version(self, version_id):
        with self.connect() as db:
            current = self._current(db)
            row = db.execute('SELECT * FROM manufacturer_versions WHERE company_id=? AND id=?', (self.company_id, version_id)).fetchone()
            if row is None:
                raise Missing('Choose a version in this company.')
            return {'version': self._version(row, current['id'], True), 'revision': current['revision']}

    def save_configurator(self, settings, expected_revision, actor, evidence, current, **metadata):
        if not isinstance(settings, dict) or not settings or set(settings) - {'accent', 'headline', 'description', 'button_label'}:
            raise Invalid('Edit the displayed configurator fields or save a full document.')
        value = self.configurator()
        document = value['document']
        document['configuration'].update(settings)
        return self.save_document(document, expected_revision, actor, evidence, current, **metadata)

    def save_document(self, document, expected_revision, actor, evidence, current, *, actor_name='', actor_type='user', label='', summary='', restored_from=None):
        if type(expected_revision) is not int or expected_revision < 0:
            raise Invalid('Supply the revision you are editing.')
        if actor_type not in {'user', 'agent'}:
            raise Invalid('Use an authenticated author type.')
        evidence = plain(evidence, 2000)
        actor_name = plain(actor_name or actor, 200)
        label = plain(label, 160, empty=True)
        summary = plain(summary, 1000, empty=True)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            previous = self._current(db)
            if previous['revision'] != expected_revision:
                raise Conflict('This configuration changed. Review the latest version and save again.')
            if not current():
                raise ValueError('Continue with current company editing access.')
            slug = json.loads(previous['document'])['configuration']['slug']
            # Restore reuses the exact stored canonical content, including its original source fields.
            if restored_from:
                chosen = db.execute('SELECT document FROM manufacturer_versions WHERE company_id=? AND id=?', (self.company_id, restored_from)).fetchone()
                if chosen is None:
                    raise Missing('Choose a version in this company.')
                encoded = chosen['document']
            else:
                encoded = dump(validate_document(document, slug))
            revision = previous['revision'] + 1
            identifier, now = uuid.uuid4().hex, stamp()
            db.execute('INSERT INTO manufacturer_versions VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', (self.company_id, identifier, revision, encoded,
                       hashlib.sha256(encoded.encode()).hexdigest(), actor, actor_name, actor_type, now, label or f'Version {revision}', summary, restored_from))
            db.execute('UPDATE manufacturer_current SET version_id=? WHERE company_id=?', (identifier, self.company_id))
            db.execute('INSERT INTO manufacturer_audit(company_id,action,actor,evidence,created_at,data) VALUES(?,?,?,?,?,?)',
                       (self.company_id, 'configurator.restore' if restored_from else 'configurator.save', actor, evidence, now,
                        dump({'version_id': identifier, 'revision': revision, 'restored_from': restored_from})))
            if not current():
                raise ValueError('Continue with current company editing access.')
        return self.configurator()

    def restore(self, version_id, expected_revision, actor, evidence, current, **metadata):
        if not isinstance(version_id, str) or not re.fullmatch(r'[a-f0-9]{32}', version_id):
            raise Invalid('Choose a saved version identifier.')
        return self.save_document(None, expected_revision, actor, evidence, current, restored_from=version_id,
                                  label='Restored version', **metadata)

    def demo_research(self, order_id):
        with self.connect() as db:
            row = db.execute('SELECT data FROM manufacturer_demo_research WHERE company_id=? AND order_id=?', (self.company_id, order_id)).fetchone()
        return json.loads(row['data']) if row else None

    def import_demo_research(self, company_id, order, findings, *, actor, as_of, evidence, current):
        """Explicit operator fixture import, separate from agent jobs and original orders."""
        from research_queue import validate_findings
        if company_id != self.company_id or not isinstance(order, dict) or order.get('customer', {}).get('is_demo') is not True:
            raise Invalid('Choose an explicitly marked demonstration order in this company.')
        identifier = plain(order.get('id'), 200)
        if not isinstance(as_of, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', as_of):
            raise Invalid('Record the research source date.')
        datetime.strptime(as_of, '%Y-%m-%d')
        value = {**validate_findings(findings), 'basis': 'operator_demo_research', 'as_of': as_of,
                 'updated_at': stamp(), 'order_id': identifier, 'company_id': self.company_id,
                 'coverage': {'source': 'operator_demo_research', 'as_of': as_of}}
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if not current():
                raise Invalid('Use current owner access for demonstration research.')
            db.execute('INSERT INTO manufacturer_demo_research VALUES(?,?,?) ON CONFLICT(company_id,order_id) DO UPDATE SET data=excluded.data', (self.company_id, identifier, dump(value)))
            db.execute('INSERT INTO manufacturer_audit(company_id,action,actor,evidence,created_at,data) VALUES(?,?,?,?,?,?)',
                       (self.company_id, 'demo.research', actor, plain(evidence, 2000), stamp(), dump({'order_id': identifier, 'as_of': as_of, 'sources': value['sources']})))
            if not current():
                raise Invalid('Use current owner access for demonstration research.')
        return value

    def team(self, domain='sample-hardware.example.test'):
        with self.connect() as db:
            row = db.execute('SELECT revision,data FROM manufacturer_team WHERE company_id=?', (self.company_id,)).fetchone()
            value = json.loads(row['data']) if row else {'invitations': [], 'policy': {'domain': domain, 'allow_domain_join': False, 'state': 'draft', 'verified_login_required': True}}
            return {**value, 'revision': row['revision'] if row else 0}

    def update_team(self, arguments, actor, evidence, current, domain):
        if not isinstance(arguments, dict) or type(arguments.get('expected_revision')) is not int:
            raise Invalid('Supply the team revision you are editing.')
        action = arguments.get('action')
        if action not in {'invite', 'policy'}:
            raise Invalid('Choose an invitation or company access policy.')
        allowed = {'action', 'expected_revision', 'email', 'role'} if action == 'invite' else {'action', 'expected_revision', 'domain', 'allow_domain_join'}
        if set(arguments) - allowed:
            raise Invalid('Use the fields of this team action.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT revision,data FROM manufacturer_team WHERE company_id=?', (self.company_id,)).fetchone()
            revision = row['revision'] if row else 0
            if revision != arguments['expected_revision']:
                raise Conflict('Company settings changed. Review the latest settings and save again.')
            if not current():
                raise ValueError('Use current owner access for company membership settings.')
            value = json.loads(row['data']) if row else {'invitations': [], 'policy': {'domain': domain, 'allow_domain_join': False, 'state': 'draft', 'verified_login_required': True}}
            if action == 'invite':
                email = arguments.get('email', '')
                if not isinstance(email, str):
                    raise Invalid('Enter a company email address.')
                email = email.strip().lower()
                role = arguments.get('role', 'operator')
                if not re.fullmatch(r'[^\s@<>]{1,64}@[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?\.[a-z]{2,63}', email) or role not in {'operator', 'browse'}:
                    raise Invalid('Enter a company email address and supported role.')
                if any(invite['email'] == email for invite in value['invitations']):
                    raise Invalid('This email already has an invitation draft.')
                if len(value['invitations']) >= 100:
                    raise Invalid('Review the existing invitation drafts.')
                value['invitations'].append({'id': uuid.uuid4().hex, 'email': email, 'role': role, 'state': 'draft', 'created_at': stamp(), 'created_by': actor})
            else:
                if arguments.get('domain') != domain or type(arguments.get('allow_domain_join')) is not bool:
                    raise Invalid('Use the company website domain and a domain-join preference.')
                value['policy'] = {'domain': domain, 'allow_domain_join': arguments['allow_domain_join'], 'state': 'draft', 'verified_login_required': True}
            db.execute('INSERT INTO manufacturer_team VALUES(?,?,?) ON CONFLICT(company_id) DO UPDATE SET revision=excluded.revision,data=excluded.data', (self.company_id, revision + 1, dump(value)))
            db.execute('INSERT INTO manufacturer_audit(company_id,action,actor,evidence,created_at,data) VALUES(?,?,?,?,?,?)', (self.company_id, f'team.{action}', actor, plain(evidence, 2000), stamp(), dump(arguments)))
            if not current():
                raise ValueError('Use current owner access for company membership settings.')
        return self.team(domain)
