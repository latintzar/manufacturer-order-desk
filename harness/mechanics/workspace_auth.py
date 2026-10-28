"""Hosted WorkOS identity admission into the harness's existing workspace sessions.

WorkOS owns authentication and verified organization membership. Native environment
bindings, principal IDs, session cookies and tool authority remain harness-owned.
Provider configuration is optional; existing demo-code sessions are unchanged.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
import hashlib
import json
import os
import re
import secrets
import time
from urllib.parse import urlencode, urlsplit

import httpx

from access import DAY, digest

API = 'https://api.workos.com'
STATE_TTL = 600
MEMBERSHIP_TTL = 60
FLOW_COOKIE = 'rocoto_auth_flow'
PUBLIC_ROUTES = frozenset({('GET', '/auth/login'), ('GET', '/auth/callback'),
                           ('GET', '/api/auth/config')})
ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$')
ENV = re.compile(r'^[a-z0-9][a-z0-9-]{0,63}$')


class AuthError(ValueError):
    def __init__(self, code='access_denied'):
        self.code = code
        super().__init__(code)


class ProviderUnavailable(AuthError):
    def __init__(self):
        super().__init__('provider_unavailable')


def _identifier(value, prefix=None):
    return isinstance(value, str) and bool(ID.fullmatch(value)) and (prefix is None or value.startswith(prefix))


def _return_path(value):
    if not isinstance(value, str) or len(value) > 2048 or not value.startswith('/') or value.startswith('//'):
        raise AuthError('invalid_return')
    if '\\' in value or any(ord(c) < 32 for c in value) or urlsplit(value).netloc:
        raise AuthError('invalid_return')
    return value


@dataclass(frozen=True)
class AuthConfig:
    client_id: str = ''
    api_key: str = field(default='', repr=False)
    organizations: dict[str, str] = field(default_factory=dict)
    redirect_uri: str = ''
    public_workspace: dict = field(default_factory=dict)
    admin_roles: tuple[str, ...] = ('admin',)

    @property
    def enabled(self):
        return bool(self.client_id and self.api_key and self.organizations and self.redirect_uri)

    @classmethod
    def from_env(cls, public_origin, environ=None):
        env = os.environ if environ is None else environ
        client = env.get('WORKOS_CLIENT_ID', '').strip()
        key = env.get('WORKOS_API_KEY', '').strip()
        raw = env.get('ROCOTO_WORKOS_ORGANIZATIONS', '').strip()
        organizations = {}
        if any((client, key, raw)):
            if not all((client, key, raw)) or not _identifier(client, 'client_'):
                raise ValueError('Configure the WorkOS client, API key and workspace bindings together.')
            try:
                organizations = json.loads(raw)
            except (ValueError, TypeError):
                raise ValueError('Configure the WorkOS organization bindings as a JSON object.') from None
            if (not isinstance(organizations, dict) or not organizations or len(organizations) > 100
                    or any(not isinstance(k, str) or not ENV.fullmatch(k) or not _identifier(v, 'org_') for k, v in organizations.items())
                    or len(set(organizations.values())) != len(organizations)):
                raise ValueError('Bind each existing workspace to one distinct WorkOS organization.')
            origin = urlsplit(public_origin)
            if (origin.scheme != 'https' or not origin.netloc or origin.username or origin.password
                    or origin.path not in {'', '/'} or origin.query or origin.fragment):
                raise ValueError('Configure the exact HTTPS origin for WorkOS callbacks.')
        public = {}
        name = env.get('ROCOTO_WORKSPACE_NAME', '').strip()
        if name:
            environment = env.get('ROCOTO_WORKSPACE_ENVIRONMENT', 'demo').strip()
            slug = env.get('ROCOTO_WORKSPACE_SLUG', '').strip()
            logo = env.get('ROCOTO_WORKSPACE_LOGO', '').strip()
            if len(name) > 100 or any(ord(c) < 32 for c in name) or not ENV.fullmatch(environment):
                raise ValueError('Configure a short public workspace name and environment.')
            if slug and not ENV.fullmatch(slug):
                raise ValueError('Configure a short public workspace slug.')
            if logo:
                parts = urlsplit(logo)
                relative = logo.startswith('/') and not logo.startswith('//')
                if (len(logo) > 2048 or '\\' in logo or any(ord(c) < 32 for c in logo)
                        or not (relative or parts.scheme == 'https' and parts.hostname and not parts.username and not parts.password)):
                    raise ValueError('Configure an HTTPS or same-origin workspace logo.')
            public = {'id': environment, 'name': name, 'slug': slug, 'logo': logo}
        admin_roles = tuple(env.get('ROCOTO_WORKOS_ADMIN_ROLES', 'admin').split(','))
        if not admin_roles or len(admin_roles) > 8 or any(not _identifier(role) for role in admin_roles):
            raise ValueError('Configure exact WorkOS workspace-admin role slugs.')
        return cls(client, key, organizations, public_origin.rstrip('/') + '/auth/callback' if client else '', public, admin_roles)


class WorkspaceAuth:
    def __init__(self, access, config=None, *, transport=None):
        self.access = access
        self.config = config or AuthConfig()
        self.transport = transport
        with access.connect() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS workspace_auth_flows (
                state_hash TEXT PRIMARY KEY, browser_hash TEXT NOT NULL,
                client_id TEXT NOT NULL, verifier TEXT NOT NULL, environment TEXT,
                organization_id TEXT, invitation_token TEXT, invited_email TEXT,
                return_to TEXT NOT NULL, expires REAL NOT NULL, used REAL);
              CREATE TABLE IF NOT EXISTS workspace_auth_identities (
                client_id TEXT NOT NULL, subject TEXT NOT NULL, principal_id TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL, PRIMARY KEY(client_id,subject));
              CREATE TABLE IF NOT EXISTS workspace_auth_memberships (
                principal_id TEXT NOT NULL, environment TEXT NOT NULL,
                organization_id TEXT NOT NULL, role_slug TEXT NOT NULL,
                checked_at REAL NOT NULL, PRIMARY KEY(principal_id,environment));
              CREATE TABLE IF NOT EXISTS workspace_auth_sessions (
                session_hash TEXT PRIMARY KEY, client_id TEXT NOT NULL,
                subject TEXT NOT NULL, checked_at REAL NOT NULL);
            ''')
            existing = {row['id'] for row in db.execute('SELECT id FROM environments')}
            if set(self.config.organizations) - existing:
                raise ValueError('Create native workspaces before binding WorkOS organizations.')

    @classmethod
    def from_env(cls, access, public_origin, environ=None):
        return cls(access, AuthConfig.from_env(public_origin, environ))

    @property
    def enabled(self):
        return self.config.enabled

    def public_config(self):
        return {'enabled': self.enabled, 'provider': 'workos', 'login_url': '/auth/login',
                'demo_code_label': 'Demo code',
                'workspaces': [dict(self.config.public_workspace)] if self.config.public_workspace else []}

    async def _request(self, method, path, *, params=None, body=None):
        if not self.enabled:
            raise AuthError('auth_unconfigured')
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=10, follow_redirects=False) as client:
                response = await client.request(method, API + path, params=params, json=body,
                    headers={'Authorization': 'Bearer ' + self.config.api_key})
            if response.status_code >= 500 or response.status_code in {401, 403, 429}:
                raise ProviderUnavailable()
            if response.status_code != 200 and response.status_code != 201:
                raise AuthError('access_denied')
            if len(response.content) > 1024 * 1024:
                raise ProviderUnavailable()
            data = response.json()
            if not isinstance(data, dict):
                raise ProviderUnavailable()
            return data
        except (httpx.HTTPError, ValueError) as error:
            if isinstance(error, AuthError):
                raise
            raise ProviderUnavailable() from None

    async def begin(self, *, workspace=None, return_to='/', invitation_token=None, now=None):
        if not self.enabled:
            raise AuthError('auth_unconfigured')
        now = time.time() if now is None else now
        if workspace is not None and workspace not in self.config.organizations:
            raise AuthError('workspace_unknown')
        organization = self.config.organizations.get(workspace)
        email = None
        if invitation_token:
            if not _identifier(invitation_token):
                raise AuthError('invitation_invalid')
            invitation = await self._request('GET', '/user_management/invitations/by_token/' + invitation_token)
            target = invitation.get('organization_id')
            target_workspace = next((key for key, value in self.config.organizations.items() if value == target), None)
            if (not target_workspace or invitation.get('state') != 'pending'
                    or workspace is not None and target_workspace != workspace):
                raise AuthError('invitation_invalid')
            workspace, organization = target_workspace, target
            email = self._email(invitation.get('email'))
        destination = _return_path(return_to)
        state, browser, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(32), secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        with self.access.connect() as db:
            db.execute('DELETE FROM workspace_auth_flows WHERE expires<?', (now,))
            db.execute('INSERT INTO workspace_auth_flows VALUES(?,?,?,?,?,?,?,?,?,?,NULL)',
                (digest(state), digest(browser), self.config.client_id, verifier, workspace, organization,
                 invitation_token, email, destination, now + STATE_TTL))
        params = {'client_id': self.config.client_id, 'provider': 'authkit', 'response_type': 'code',
                  'redirect_uri': self.config.redirect_uri, 'state': state,
                  'code_challenge': challenge, 'code_challenge_method': 'S256'}
        if organization:
            params['organization_id'] = organization
        if invitation_token:
            params['invitation_token'] = invitation_token
        return {'url': API + '/user_management/authorize?' + urlencode(params), 'browser_nonce': browser}

    def _consume(self, state, browser, now):
        if not isinstance(state, str) or not isinstance(browser, str) or not (20 <= len(state) <= 128 and 20 <= len(browser) <= 128):
            raise AuthError('state_invalid')
        with self.access.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM workspace_auth_flows WHERE state_hash=?', (digest(state),)).fetchone()
            if (row is None or row['used'] is not None or row['expires'] <= now
                    or row['client_id'] != self.config.client_id or not secrets.compare_digest(row['browser_hash'], digest(browser))):
                raise AuthError('state_invalid')
            flow = dict(row)
            # Burn state before any external I/O; a failed exchange starts a fresh login.
            db.execute('UPDATE workspace_auth_flows SET used=?,verifier=?,invitation_token=NULL WHERE state_hash=?',
                       (now, '', digest(state)))
        return flow

    @staticmethod
    def _email(value):
        if not isinstance(value, str) or len(value) > 254 or not re.fullmatch(r'[^\s@<>]{1,64}@[^\s@<>]+\.[^\s@<>]+', value):
            raise AuthError('identity_invalid')
        return value.strip().lower()

    def _user(self, user, subject=None):
        if (not isinstance(user, dict) or not _identifier(user.get('id'), 'user_')
                or subject is not None and user['id'] != subject or user.get('email_verified') is not True):
            raise AuthError('identity_unverified')
        email = self._email(user.get('email'))
        name = ' '.join(str(user.get(key) or '').strip() for key in ('first_name', 'last_name')).strip() or email
        name = ''.join(c for c in name if ord(c) >= 32)[:80]
        return user['id'], email, name

    async def _memberships(self, subject):
        records, cursor, seen = [], None, set()
        for _ in range(10):
            params = {'user_id': subject, 'limit': 100, 'statuses': 'active'}
            if cursor:
                params['after'] = cursor
            data = await self._request('GET', '/user_management/organization_memberships', params=params)
            rows = data.get('data')
            if not isinstance(rows, list) or any(not isinstance(row, dict) or row.get('user_id') != subject for row in rows):
                raise AuthError('membership_invalid')
            records.extend(row for row in rows if row.get('status') == 'active')
            cursor = (data.get('list_metadata') or {}).get('after')
            if not cursor:
                return records
            if not _identifier(cursor) or cursor in seen:
                raise AuthError('membership_invalid')
            seen.add(cursor)
        raise AuthError('membership_invalid')

    def _admitted(self, records):
        bindings = {organization: environment for environment, organization in self.config.organizations.items()}
        result = {}
        for row in records:
            organization = row.get('organization_id')
            if organization in bindings:
                role = row.get('role') or {}
                role = role.get('slug', 'member') if isinstance(role, dict) else 'member'
                if not isinstance(role, str) or not _identifier(role):
                    raise AuthError('membership_invalid')
                result[bindings[organization]] = {'organization_id': organization, 'role_slug': role}
        return result

    def _sync(self, db, subject, email, name, admitted, now):
        principal = 'workos-' + digest(self.config.client_id + ':' + subject)[:48]
        previous = db.execute('SELECT principal_id FROM workspace_auth_identities WHERE client_id=? AND subject=?',
                              (self.config.client_id, subject)).fetchone()
        if previous and previous['principal_id'] != principal:
            raise AuthError('identity_invalid')
        db.execute('INSERT INTO workspace_auth_identities VALUES(?,?,?,?) ON CONFLICT(client_id,subject) DO UPDATE SET email=excluded.email',
                   (self.config.client_id, subject, principal, email))
        db.execute('INSERT INTO principals VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET display_name=excluded.display_name',
                   (principal, name, now))
        previous_envs = {row['environment'] for row in db.execute('SELECT environment FROM workspace_auth_memberships WHERE principal_id=?', (principal,))}
        for environment in previous_envs - set(admitted):
            db.execute('DELETE FROM principal_environments WHERE principal_id=? AND environment=?', (principal, environment))
        db.execute('DELETE FROM workspace_auth_memberships WHERE principal_id=?', (principal,))
        for environment, row in admitted.items():
            # Client admin/owner are provider metadata, never native service-owner authority.
            db.execute('INSERT INTO principal_environments VALUES(?,?,?) ON CONFLICT(principal_id,environment) DO UPDATE SET role=excluded.role',
                       (principal, environment, 'operator'))
            db.execute('INSERT INTO workspace_auth_memberships VALUES(?,?,?,?,?)',
                       (principal, environment, row['organization_id'], row['role_slug'], now))
        return principal

    async def complete(self, *, code, state, browser_nonce, now=None):
        if not self.enabled:
            raise AuthError('auth_unconfigured')
        now = time.time() if now is None else now
        flow = self._consume(state, browser_nonce, now)
        if not isinstance(code, str) or not (1 <= len(code) <= 2048) or any(ord(c) < 32 for c in code):
            raise AuthError('code_invalid')
        body = {'client_id': self.config.client_id, 'client_secret': self.config.api_key,
                'grant_type': 'authorization_code', 'code': code, 'code_verifier': flow['verifier']}
        if flow['invitation_token']:
            body['invitation_token'] = flow['invitation_token']
        data = await self._request('POST', '/user_management/authenticate', body=body)
        subject, email, name = self._user(data.get('user'))
        if data.get('impersonator') or flow['invited_email'] and email != flow['invited_email']:
            raise AuthError('identity_invalid')
        organization = data.get('organization_id')
        if flow['organization_id'] and organization != flow['organization_id']:
            raise AuthError('workspace_mismatch')
        admitted = self._admitted(await self._memberships(subject))
        environment = next((env for env, row in admitted.items() if row['organization_id'] == organization), None)
        choosing = organization is None and flow['environment'] is None and len(admitted) > 1
        if organization is None and flow['environment'] is None and admitted:
            environment = sorted(admitted)[0]
        if not environment:
            raise AuthError('workspace_membership_required')
        token = secrets.token_urlsafe(32)
        with self.access.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            principal = self._sync(db, subject, email, name, admitted, now)
            db.execute('INSERT INTO sessions(hash,environment,grants,expires,can_query,principal_id,role) VALUES(?,?,?,?,?,?,?)',
                       (digest(token), environment, json.dumps(sorted(admitted)), now + DAY, 1, principal, 'operator'))
            db.execute('INSERT INTO workspace_auth_sessions VALUES(?,?,?,?)', (digest(token), self.config.client_id, subject, now))
        return {'token': token, 'session': self.decorate(self.access.session(token, now)),
                'return_to': '/?workspaces=1' if choosing else flow['return_to']}

    def decorate(self, session):
        """Workspace admin is separate from the native service-owner role."""
        if not session:
            return session
        with self.access.connect() as db:
            membership = db.execute('SELECT m.role_slug FROM workspace_auth_memberships m '
                'JOIN principal_environments p ON p.principal_id=m.principal_id AND p.environment=m.environment '
                'WHERE m.principal_id=? AND m.environment=?',
                (session['principal']['id'], session['environment']['id'])).fetchone()
        return {**session, 'workspace_admin': bool(not session.get('viewing_as') and
                (session['role'] == 'owner' or membership and membership['role_slug'] in self.config.admin_roles))}

    def _withdraw(self, subject):
        """A withdrawn identity also loses its standing native membership authority."""
        with self.access.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT principal_id FROM workspace_auth_identities WHERE client_id=? AND subject=?',
                             (self.config.client_id, subject)).fetchone()
            if row:
                principal = row['principal_id']
                db.execute('DELETE FROM principal_environments WHERE principal_id=? AND environment IN '
                           '(SELECT environment FROM workspace_auth_memberships WHERE principal_id=?)', (principal, principal))
                db.execute('DELETE FROM workspace_auth_memberships WHERE principal_id=?', (principal,))
                db.execute('DELETE FROM sessions WHERE principal_id=? AND hash IN '
                           '(SELECT session_hash FROM workspace_auth_sessions)', (principal,))

    async def validate_session(self, token, session=None, *, force=False, now=None):
        now = time.time() if now is None else now
        session = self.access.session(token, now) if session is None else session
        if not session:
            return None
        with self.access.connect() as db:
            row = db.execute('SELECT * FROM workspace_auth_sessions WHERE session_hash=?', (digest(token),)).fetchone()
        if not row:
            return self.decorate(session)
        if not self.enabled or row['client_id'] != self.config.client_id:
            return None
        principal = session['principal']['id']
        with self.access.connect() as db:
            local = db.execute('SELECT * FROM workspace_auth_memberships WHERE principal_id=? AND environment=?',
                               (principal, session['environment']['id'])).fetchone()
        if not local or self.config.organizations.get(local['environment']) != local['organization_id']:
            return None
        if not force and row['checked_at'] + MEMBERSHIP_TTL > now:
            return self.decorate(session)
        try:
            user = await self._request('GET', '/user_management/users/' + row['subject'])
            subject, email, name = self._user(user, row['subject'])
            admitted = self._admitted(await self._memberships(subject))
        except ProviderUnavailable:
            raise
        except AuthError:
            self._withdraw(row['subject'])
            return None
        with self.access.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._sync(db, subject, email, name, admitted, now)
            db.execute('UPDATE sessions SET grants=? WHERE principal_id=? AND hash IN (SELECT session_hash FROM workspace_auth_sessions)',
                       (json.dumps(sorted(admitted)), principal))
            db.execute('DELETE FROM sessions WHERE principal_id=? AND hash IN (SELECT session_hash FROM workspace_auth_sessions) '
                       'AND environment NOT IN (SELECT environment FROM workspace_auth_memberships WHERE principal_id=?)', (principal, principal))
            db.execute('UPDATE workspace_auth_sessions SET checked_at=? WHERE client_id=? AND subject=?', (now, self.config.client_id, subject))
        return self.decorate(self.access.session(token, now))

    async def select(self, token, environment):
        session = await self.validate_session(token, force=True)
        if not session or not isinstance(environment, str) or environment not in {row['id'] for row in session['environments']}:
            raise AuthError('workspace_membership_required')
        return self.decorate(self.access.switch(token, environment))

    def workspaces(self, session):
        if not session or not session.get('authenticated'):
            raise AuthError('sign_in_required')
        with self.access.connect() as db:
            roles = {row['environment']: row['role_slug'] for row in db.execute(
                'SELECT environment,role_slug FROM workspace_auth_memberships WHERE principal_id=?', (session['principal']['id'],))}
        return {'workspaces': [{**row, 'selected': row['id'] == session['environment']['id'],
                 'role': roles.get(row['id'], session['role'])} for row in session['environments']]}

    async def invite(self, token, environment, email):
        session = await self.validate_session(token, force=True)
        if (not session or session.get('viewing_as')
                or not isinstance(environment, str) or environment not in {row['id'] for row in session['environments']}):
            raise AuthError('workspace_owner_required')
        if session['role'] != 'owner' and not (session.get('workspace_admin') and session['environment']['id'] == environment):
            raise AuthError('workspace_owner_required')
        organization = self.config.organizations.get(environment)
        if not organization:
            raise AuthError('workspace_unknown')
        email = self._email(email)
        data = await self._request('POST', '/user_management/invitations', body={
            'email': email, 'organization_id': organization, 'role_slug': 'member', 'expires_in_days': 7})
        if data.get('organization_id') != organization or self._email(data.get('email')) != email or not _identifier(data.get('id')):
            raise AuthError('invitation_invalid')
        return {'id': data['id'], 'email': email, 'environment_id': environment,
                'state': data.get('state', 'pending'), 'expires_at': data.get('expires_at')}
