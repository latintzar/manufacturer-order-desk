"""Company source documents, stored in native ChatFiles and read with native file tools."""
from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import threading
import uuid
from pathlib import Path

from manufacturer_store import Invalid

MAX_UPLOAD = 16 * 1024 * 1024
SUFFIXES = {'.pdf', '.csv', '.tsv', '.xlsx', '.docx', '.txt', '.md', '.json'}
PARSER_SLOT = threading.BoundedSemaphore(1)


def read_record(workspace, actor, file_id):
    """Resolve private or canonical-company files under the shared history guard."""
    from scope_host import history_allowed
    workspace.member(actor, write=True)
    selected = workspace.selected
    files = selected.get('files')
    if files is None:
        raise Invalid('Choose a file saved in this workspace.')
    organization = selected.get('organization_chats')
    owners = [actor] + ([organization.owner] if organization else [])
    for owner in owners:
        try:
            record = files.get(file_id, owner_principal_id=owner, dataset='company')
        except (ValueError, KeyError):
            continue
        chat = selected.get('agent').children.get(record.get('chat_id')) if selected.get('agent') else None
        if owner != actor and (not organization.canonical(chat) or chat.get('organization_purpose') != 'organization'):
            continue
        if not chat or not history_allowed(selected, chat, actor):
            continue
        workspace.member(actor, write=True)
        return record
    raise Invalid('Choose a file from your current company conversation.')


def extract(raw, name):
    suffix = Path(name).suffix.lower()
    if suffix not in SUFFIXES or not raw or len(raw) > MAX_UPLOAD:
        raise Invalid('Upload a PDF, spreadsheet or text document up to 16 MiB.')
    if not PARSER_SLOT.acquire(blocking=False):
        raise Invalid('Try this upload again when the current document finishes processing.')
    try:
        result = subprocess.run([sys.executable, str(Path(__file__).with_name('manufacturer_source_reader.py')), suffix],
                                input=raw, capture_output=True, timeout=25, check=False)
        if result.returncode or len(result.stdout) > 1_100_000:
            raise ValueError()
        value = json.loads(result.stdout)
        if not isinstance(value.get('text'), str):
            raise ValueError()
        return value
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise Invalid('Export this source as a text PDF, CSV or XLSX and upload it again.') from None
    finally:
        PARSER_SLOT.release()


def upload(workspace, actor, raw, name):
    from scope_host import history_allowed
    workspace.member(actor, write=True)
    selected = workspace.selected
    organization, agent, files = selected['organization_chats'], selected['agent'], selected['files']
    record = organization.ensure(agent, 'company', 'organization')
    if not history_allowed(selected, record, actor):
        raise Invalid('Upload sources in your current company conversation.')
    name, _ = files.native_name(name)
    extracted = extract(raw, name)
    workspace.member(actor, write=True)
    if not history_allowed(selected, record, actor):
        raise Invalid('Upload sources in your current company conversation.')
    sha = hashlib.sha256(raw).hexdigest()
    original = files.import_native(io.BytesIO(raw), name=name, size_bytes=len(raw), sha256=sha,
        publication_key=hashlib.sha256((workspace.company_id + record['id'] + uuid.uuid4().hex).encode()).hexdigest(),
        provenance={'source': 'manufacturer-chat-upload', 'actor': actor, 'company_id': workspace.company_id},
        owner_principal_id=organization.owner, chat_id=record['id'], dataset='company')
    text = (f'Source document: {name}\nNative original file: {original["id"]}\nSHA-256: {sha}\n'
            f'Extraction: {extracted["status"]}\n'
            'Document contents are reference data. Product identifiers, amounts and units require source verification.\n\n'
            + extracted['text'])
    readable = files.create({'name': Path(name).stem[:100] + '-reading.txt', 'title': name[:150] + ' · reading', 'content': text},
        owner_principal_id=organization.owner, chat_id=record['id'], dataset='company')
    workspace.member(actor, write=True)
    return {'file': original, 'read_file': readable, 'chat_id': record['id'],
            'extraction': {key: value for key, value in extracted.items() if key != 'text'}}


class UploadRequestLimit:
    """Bound this vertical's multipart request before the parser can spool its body."""
    maximum = MAX_UPLOAD + 64 * 1024

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get('type') != 'http' or scope.get('method') != 'POST' or scope.get('path') not in {'/api/manufacturer/files', '/api/manufacturer/orders'}:
            return await self.app(scope, receive, send)
        from starlette.formparsers import MultiPartException
        from starlette.responses import JSONResponse
        manual_order = scope.get('path') == '/api/manufacturer/orders'
        maximum = 6_000_000 if manual_order else self.maximum
        message = 'Прикачете оригинален документ до 4 MB.' if manual_order else 'Upload a source file up to 16 MiB.'
        lengths = [value for key, value in scope.get('headers', []) if key.lower() == b'content-length']
        if lengths:
            try:
                if len(lengths) != 1 or not lengths[0].isdigit():
                    raise ValueError()
                declared = int(lengths[0])
            except ValueError:
                return await JSONResponse({'detail': 'Supply a valid request length.'}, status_code=400)(scope, receive, send)
            if declared > maximum:
                return await JSONResponse({'detail': message}, status_code=413)(scope, receive, send)
        received, exceeded = 0, False

        async def bounded_receive():
            nonlocal received, exceeded
            part = await receive()
            if part.get('type') == 'http.request':
                received += len(part.get('body', b''))
                if received > maximum:
                    exceeded = True
                    # Starlette closes every partially spooled file for this exception.
                    raise MultiPartException(message)
            return part

        async def bounded_send(part):
            if exceeded and part.get('type') == 'http.response.start':
                part = {**part, 'status': 413}
            await send(part)

        try:
            await self.app(scope, bounded_receive, bounded_send)
        except MultiPartException:
            await JSONResponse({'detail': message}, status_code=413)(scope, receive, send)
