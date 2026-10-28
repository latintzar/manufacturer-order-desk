"""Deliver a saved company version to its commissioned Orders receiver and retain its receipt."""
from __future__ import annotations

import fcntl
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from manufacturer_source_http import TOKEN_ENV, NoRedirect
from manufacturer_store import ORIGIN, dump, stamp


class Publisher:
    def __init__(self, platform, source, *, transport=None):
        self.platform, self.source = platform, source
        self.transport = transport or self._post
        with platform.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS manufacturer_publications(
                company_id TEXT NOT NULL,version_id TEXT NOT NULL,state TEXT NOT NULL,receipt TEXT NOT NULL,
                updated_at TEXT NOT NULL,PRIMARY KEY(company_id,version_id))''')

    def configured(self):
        binding = self.source.binding()
        return bool(binding and binding.get('transport') == 'orders-api' and len(os.environ.get(TOKEN_ENV, '')) >= 32)

    def _post(self, value):
        slug = self.source.binding()['company_slug']
        request = urllib.request.Request(f'{ORIGIN}/{slug}/rocoto/api/configurator-version',
            data=dump(value).encode(), headers={'Authorization': 'Bearer ' + os.environ.get(TOKEN_ENV, ''),
            'X-Rocoto-Company': self.platform.company_id, 'Content-Type': 'application/json'}, method='POST')
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=20) as response:
            body = response.read(20000)
        return json.loads(body)

    def status(self, version_id):
        with self.platform.connect() as db:
            row = db.execute('SELECT state,receipt,updated_at FROM manufacturer_publications WHERE company_id=? AND version_id=?',
                             (self.platform.company_id, version_id)).fetchone()
            if row:
                return {'state': row['state'], 'published': row['state'] == 'published',
                        'receipt': json.loads(row['receipt']), 'updated_at': row['updated_at']}
        return {'state': 'draft', 'published': False}

    def publish(self, authorized):
        if not self.configured():
            return self.status(self.platform.configurator()['version_id'])
        lock = Path(self.platform.state) / 'manufacturer-publication.lock'
        with open(os.open(lock, os.O_CREAT | os.O_RDWR, 0o600), 'r+b') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            if not authorized():
                raise ValueError('Continue with current company editing access.')
            current = self.platform.configurator()
            version = self.platform.version(current['version_id'])['version']
            prior = self.status(version['id'])
            if prior['published']:
                return prior
            payload = {'company_id': self.platform.company_id, 'company_slug': version['document']['configuration']['slug'],
                       'version': {key: version[key] for key in ('id', 'revision', 'sha256', 'document')}}
            state, receipt = 'pending', {'message': 'Saved version is waiting for the company configurator connection.'}
            try:
                answer = self.transport(payload)
                if (answer.get('ok') is True and answer.get('published') is True
                        and answer.get('version_id') == version['id'] and answer.get('revision') == version['revision']
                        and answer.get('sha256') == version['sha256']):
                    state, receipt = 'published', answer
            except (OSError, ValueError, TypeError, KeyError):
                pass
            with self.platform.connect() as db:
                db.execute('INSERT INTO manufacturer_publications VALUES(?,?,?,?,?) ON CONFLICT(company_id,version_id) DO UPDATE SET state=excluded.state,receipt=excluded.receipt,updated_at=excluded.updated_at',
                           (self.platform.company_id, version['id'], state, dump(receipt), stamp()))
                db.execute('INSERT INTO manufacturer_audit(company_id,action,actor,evidence,created_at,data) VALUES(?,?,?,?,?,?)',
                           (self.platform.company_id, 'configurator.publication', version['author']['id'],
                            'Automatic application of the authenticated saved company version.', stamp(),
                            dump({'version_id': version['id'], 'state': state, 'sha256': version['sha256']})))
            if not authorized():
                raise ValueError('Continue with current company access.')
            return self.status(version['id'])
