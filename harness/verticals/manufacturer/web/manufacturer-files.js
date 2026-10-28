/* Company documents use native ChatFiles and the existing organization conversation. */
(() => {
  'use strict';
  const LIMIT = 8, MAX_BYTES = 16 * 1024 * 1024;
  const ACCEPT = '.pdf,.csv,.tsv,.xlsx,.docx,.txt,.md,.json';
  const OPEN = '\n\n<manufacturer-files>\n', CLOSE = '\n</manufacturer-files>';
  const fileId = value => typeof value === 'string' && /^file-[a-f0-9]{32}$/.test(value);
  function normalize(values) {
    if (!Array.isArray(values)) return [];
    const seen = new Set();
    return values.filter(value => value && fileId(value.id) && fileId(value.read_file_id) && !seen.has(value.id) && seen.add(value.id)).slice(0, LIMIT).map(value => ({
      id: value.id, read_file_id: value.read_file_id, name: String(value.name || 'Company document').slice(0, 240),
      size_bytes: Math.max(0, Number(value.size_bytes) || 0), extraction: value.extraction === 'needs_review' ? 'needs_review' : 'ready',
    }));
  }
  function unpack(message) {
    const text = typeof message.content === 'string' ? message.content : message.text || message.query || '';
    if (message.role && message.role !== 'user') return {};
    const start = text.lastIndexOf(OPEN);
    if (start < 0 || !text.endsWith(CLOSE)) return {};
    try {
      const data = JSON.parse(text.slice(start + OPEN.length, -CLOSE.length)), files = normalize(data.files);
      if (data.version !== 1 || !files.length || files.length !== data.files.length) return {};
      return {text: text.slice(0, start), manufacturer_query: text.slice(0, start), manufacturer_files: files};
    } catch { return {}; }
  }
  function requestData(message) {
    const files = normalize(message.manufacturer_files);
    if (!files.length) return {};
    const query = message.query ?? message.manufacturer_query ?? message.text ?? '';
    return {message: (query.trim() || 'Review the attached files.') + OPEN + JSON.stringify({version: 1, files}) + CLOSE};
  }
  window.RocotoManufacturerFiles = host => {
    const drafts = new Map(), pending = new Map();
    let readOnly = false, storageKey = '';
    const section = host.node('section', 'mf-file-drafts');
    section.id = 'manufacturer-file-drafts'; section.hidden = true; section.setAttribute('aria-label', 'Attachments');
    section.setAttribute('aria-live', 'polite');
    document.querySelector('[data-workspace-slot="source-attachments"]').replaceWith(section);
    const action = host.node('button', '', 'Files'); action.type = 'button'; action.id = 'manufacturer-attach-files';
    action.prepend(host.icon('document'));
    document.querySelector('[data-workspace-slot="source-attachment-action"]').replaceWith(action);
    const input = host.node('input'); input.type = 'file'; input.accept = ACCEPT; input.multiple = true; input.hidden = true;
    input.id = 'manufacturer-file-input'; host.$('composer').append(input);
    const organization = () => host.activeChat()?.kind === 'organization_chat';
    const writable = () => organization() && host.session?.can_query && !readOnly && !host.activeChat()?.read_only;
    const current = () => drafts.get(host.activeId) || [];
    const blocked = () => current().some(file => file.uploading || file.error);
    function saveDrafts() {
      if (!storageKey) return;
      try { localStorage.setItem(storageKey, JSON.stringify([...drafts].map(([id, files]) => [id, normalize(files.filter(file => !file.uploading && !file.error))]).filter(([, files]) => files.length))); }
      catch { host.notice('Keep this page open to save attachments.'); }
    }
    function changed(id = host.activeId) {
      saveDrafts(); host.persistDraft(id, false);
      if (id === host.activeId) { render(); host.updateMode(); }
    }
    function chip(file, removable = false) {
      const card = host.node('div', 'mf-file-chip');
      card.append(host.icon('document'));
      const content = host.node('div', 'mf-file-info');
      const title = host.node(file.id ? 'a' : 'span', 'mf-file-name', file.name);
      title.title = file.name;
      if (file.id) { title.href = `/api/files/${encodeURIComponent(file.id)}/download`; title.setAttribute('download', file.name); }
      const type = file.name.split('.').pop().toUpperCase();
      const detail = file.uploading ? 'Reading file…' : file.error || (file.extraction === 'needs_review' ? 'Saved · ready to review' : `${type} · ${host.fileSize(file.size_bytes)}`);
      content.append(title, host.node('small', '', detail)); card.append(content);
      if (removable) {
        const remove = host.node('button', 'icon-button'); remove.type = 'button'; remove.setAttribute('aria-label', `Remove ${file.name}`);
        remove.title = `Remove ${file.name}`; remove.append(host.icon('close')); remove.disabled = readOnly;
        remove.addEventListener('click', () => {
          if (readOnly) return;
          pending.get(file.localId)?.abort(); pending.delete(file.localId);
          drafts.set(host.activeId, current().filter(value => value !== file)); changed();
        }); card.append(remove);
      }
      return card;
    }
    function render() {
      action.hidden = !organization(); action.disabled = !writable();
      host.$('attach-images').hidden = organization();
      section.replaceChildren(); section.hidden = !organization() || !current().length;
      if (!section.hidden) for (const file of current()) section.append(chip(file, true));
    }
    const uploadErrors = {
      'Choose a file saved in this workspace.':'Choose a file from this workspace.',
      'Choose a file from your current company conversation.':'Choose a file from the current company chat.',
      'Upload a PDF, spreadsheet or text document up to 16 MiB.':'Upload a PDF, spreadsheet or text document up to 16 MiB.',
      'Try this upload again when the current document finishes processing.':'Upload the file after the current document finishes processing.',
      'Export this source as a text PDF, CSV or XLSX and upload it again.':'Save the source as a text PDF, CSV or XLSX and upload it again.',
      'Upload sources in your current company conversation.':'Upload the file to the current company chat.',
    };
    async function upload(files) {
      if (!writable()) return;
      const chatId = host.activeId, generation = host.sessionGeneration;
      host.toggleAttachmentMenu(false);
      for (const file of files) {
        if (generation !== host.sessionGeneration || !writable() || host.activeId !== chatId) break;
        const values = drafts.get(chatId) || [];
        if (values.length >= LIMIT) { host.notice('Attach up to eight files to a message.'); break; }
        if (!ACCEPT.split(',').includes('.' + file.name.split('.').pop().toLowerCase()) || !file.size || file.size > MAX_BYTES) {
          host.notice('Choose a PDF, CSV, TSV, XLSX, DOCX, TXT, Markdown or JSON file up to 16 MiB.'); continue;
        }
        const item = {localId: crypto.randomUUID(), name: file.name, size_bytes: file.size, uploading: true};
        const controller = new AbortController(); pending.set(item.localId, controller); drafts.set(chatId, [...values, item]); changed(chatId);
        try {
          const body = new FormData(); body.append('file', file);
          const response = await fetch('/api/manufacturer/files', {method: 'POST', credentials: 'same-origin', headers: {'X-Rocoto-Page': '1'}, body, signal: controller.signal});
          const result = await response.json();
          if (!response.ok) throw new Error(response.status === 401 || response.status === 403 ? 'Sign in to your company workspace and upload the file again.' : response.status === 413 ? 'Choose a file up to 16 MiB.' : uploadErrors[result.detail] || (typeof result.detail === 'string' && /[A-Za-z][^]*\s/.test(result.detail) ? result.detail : 'Upload the file again.'));
          if (generation !== host.sessionGeneration || controller.signal.aborted) continue;
          const valid = normalize([{...result.file, read_file_id: result.read_file?.id, extraction: result.extraction?.status}])[0];
          if (!valid || result.chat_id !== chatId) throw new Error('Open company chat and attach the file again.');
          Object.assign(item, valid, {uploading: false});
        } catch (error) {
          if (generation !== host.sessionGeneration || controller.signal.aborted) continue;
          item.uploading = false; item.error = error instanceof Error ? error.message : 'Upload the file again.';
        } finally {
          pending.delete(item.localId);
          if (generation === host.sessionGeneration) changed(chatId);
        }
      }
      if (generation === host.sessionGeneration && host.activeId === chatId) host.elements.message.focus();
    }
    action.addEventListener('click', () => { if (writable()) input.click(); });
    input.addEventListener('change', () => { const files = Array.from(input.files || []); input.value = ''; upload(files); });
    host.$('composer').addEventListener('dragover', event => {
      if (writable() && Array.from(event.dataTransfer?.types || []).includes('Files')) { event.preventDefault(); event.stopImmediatePropagation(); }
    }, true);
    host.$('composer').addEventListener('drop', event => {
      if (!writable() || !event.dataTransfer?.files.length) return;
      event.preventDefault(); event.stopImmediatePropagation(); upload(Array.from(event.dataTransfer.files));
    }, true);
    host.$('composer').addEventListener('submit', event => {
      if (!organization()) return;
      const value = requestData({manufacturer_files: current(), manufacturer_query: host.elements.message.value});
      if (blocked() || (value.message?.length || 0) > 8000) {
        event.preventDefault(); event.stopImmediatePropagation();
        host.notice(blocked() ? 'Wait for the upload or remove the selected file.' : 'Shorten the message to send it with attachments.');
      }
    }, true);
    return {
      draftData(id) { return {manufacturer_files: normalize((drafts.get(id) || []).filter(file => !file.uploading && !file.error))}; },
      restoreDraft(id, value) { if (!drafts.has(id)) drafts.set(id, normalize(value.manufacturer_files)); },
      loadDrafts(suffix, read) { storageKey = `rocoto-manufacturer-file-drafts-v1${suffix}`; for (const row of read(storageKey)) if (Array.isArray(row) && typeof row[0] === 'string') drafts.set(row[0], normalize(row[1])); },
      saveDrafts,
      hasDraft(id) { return Boolean(drafts.get(id)?.length); },
      clearDraft(id) { drafts.delete(id); saveDrafts(); render(); },
      moveDraft(from, to) { if (drafts.has(from)) { drafts.set(to, drafts.get(from)); drafts.delete(from); saveDrafts(); } },
      editQueued(id, item) { drafts.set(id, normalize(item.manufacturer_files)); saveDrafts(); },
      composerData(id) { return {manufacturer_files: normalize(drafts.get(id)), manufacturer_query: host.elements.message.value.trim()}; },
      messageData(message) { return Array.isArray(message.manufacturer_files) ? {manufacturer_files: normalize(message.manufacturer_files), manufacturer_query: message.query ?? message.manufacturer_query ?? message.text ?? ''} : unpack(message); },
      requestData,
      hasMessageContent(message) { return Boolean(normalize(message.manufacturer_files).length); },
      defaultMessage(message) { return message.manufacturer_files?.length ? 'Review the attached files.' : null; },
      renderComposerAttachments: render,
      setComposerReadOnly(value) { readOnly = value; render(); },
      updateAlternateComposer() {
        if (!organization() || !blocked()) return false;
        host.$('composer-note').textContent = current().some(file => file.uploading) ? 'Reading files…' : 'Remove the selected file to continue.';
        host.elements.send.disabled = true; host.elements.send.setAttribute('aria-label', 'Send message'); host.elements.send.replaceChildren(host.icon('arrow')); return true;
      },
      renderUserAttachments(bubble, message) {
        const files = normalize(message.manufacturer_files); if (!files.length) return;
        const box = host.node('div', 'mf-message-files'); for (const file of files) box.append(chip(file)); bubble.append(box);
      },
      renderChatSources(sources, chat) {
        const files = [...new Map(chat.messages.flatMap(message => normalize(message.manufacturer_files)).map(file => [file.id, file])).values()];
        for (const file of files) sources.append(chip(file)); return files.length;
      },
      resetWorkspace() { for (const controller of pending.values()) controller.abort(); pending.clear(); drafts.clear(); storageKey = ''; section.replaceChildren(); section.hidden = true; },
    };
  };
})();
