/* Manufacturer navigation composes the shared harness; its chat and settings stay native. */
(() => {
  'use strict';
  // Credits stay in the native content flow, outside the icon rail.
  window.RocotoManufacturerFooter = root => queueMicrotask(() => {
    if (!root.isConnected || root.querySelector(':scope > .mf-atelier-credit')) return;
    const credit = document.createElement('a'); credit.className = 'mf-atelier-credit';
    credit.textContent = 'made by atelier neyra'; credit.href = 'https://atelierneyra.com';
    credit.target = '_blank'; credit.rel = 'noopener noreferrer'; root.append(credit);
  });
  window.RocotoWorkspaceExtensions.register('manufacturer', host => {
    document.body.classList.add('manufacturer-workspace');
    const signIn = host.$('session-form'), signInTitle = signIn.querySelector('h1');
    signIn.querySelector(':scope > img')?.remove();
    const signInBrand = host.node('div', 'mf-signin-brand'); signInBrand.append(host.icon('building'));
    signInTitle.before(signInBrand); signInTitle.textContent = 'Workspace';
    signInTitle.id = 'manufacturer-signin-title'; signIn.setAttribute('aria-labelledby', signInTitle.id);
    host.$('session-code').placeholder = 'Enter access code';
    host.$('session-submit').textContent = 'Continue';
    const returnToWorkspace = host.node('button', 'mf-signin-return', 'Back to workspace');
    returnToWorkspace.type = 'button'; returnToWorkspace.hidden = true;
    returnToWorkspace.addEventListener('click', () => location.reload()); signIn.append(returnToWorkspace);
    document.addEventListener('manufacturer:signin', event => {
      if (!host.session) return;
      const name = event.detail?.company;
      signInTitle.textContent = typeof name === 'string' && name.trim() ? name : 'Workspace';
      // The native access-code screen keeps the current cookie until another code is accepted.
      host.showSession(''); returnToWorkspace.hidden = false; host.$('session-code').focus();
    });
    const humanChat = window.RocotoManufacturerConversations.install(host);
    const nav = host.node('nav', 'manufacturer-navigation');
    nav.setAttribute('aria-label', 'Workspace');
    const controls = new Map();
    let agentEditing = true;
    function openSurface(id) {
      if (!host.session) { host.showSession('Sign in with your company access code.'); return; }
      closeContext(false); humanChat.close(); host.persistDraft();
      host.currentView = `vertical:${id}`;
      const url = new URL(location.href);
      for (const key of ['chat', 'agents', 'agent', 'settings', 'customize', 'tab', 'order', 'customer', 'product', 'history']) url.searchParams.delete(key);
      url.searchParams.set('view', id);
      history.replaceState({}, '', url);
      host.render();
      host.setSidebar(false);
    }
    window.addEventListener('popstate', () => {
      const view = new URL(location.href).searchParams.get('view');
      if (!['orders', 'customers', 'products', 'configurator', 'company', 'service'].includes(view) || host.currentView === `vertical:${view}`) return;
      host.persistDraft(); host.currentView = `vertical:${view}`; host.render(); host.setSidebar(false);
    });
    for (const [id, label, symbol] of [['orders', 'Orders', 'list'], ['customers', 'Customers', 'people'], ['products', 'Products', 'package'], ['service', 'Team chat', 'chat'], ['configurator', 'Configurator', 'sliders']]) {
      const button = host.node('button', 'agents-nav');
      button.type = 'button'; button.dataset.manufacturerNav = id; button.title = label; button.setAttribute('aria-label', label);
      button.append(host.icon(symbol), host.node('span', '', label));
      button.addEventListener('click', () => {
        if (id === 'chat') {
          if (!host.session?.can_query) host.showSession('Sign in with your company code to open chat.');
          else if (contextChat && contextReady) fullChat(); else host.openOrganizationChat('organization', 'company');
        } else openSurface(id);
      });
      controls.set(id, button); nav.append(button);
    }
    host.$('vertical-navigation').before(nav);
    document.addEventListener('click', event => {
      const anchor = event.target.closest?.('a[data-manufacturer-route]');
      if (!anchor || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const url = new URL(anchor.href, location.href), view = url.searchParams.get('view');
      if (url.origin !== location.origin || !['orders', 'customers', 'products', 'configurator'].includes(view)) return;
      event.preventDefault(); host.persistDraft(); history.pushState({}, '', url);
      if (host.currentView === `vertical:${view}`) window.dispatchEvent(new PopStateEvent('popstate'));
      else { host.currentView = `vertical:${view}`; host.render(); host.setSidebar(false); }
    });
    const company = host.node('button', '', 'Company and team');
    company.id = 'settings-company'; company.type = 'button';
    Object.assign(company.dataset, {settingsGroup: 'Organization', settingsAfter: 'business', settingsIcon: 'building'});
    company.addEventListener('click', () => openSurface('company'));
    host.$('settings-nav').append(company);
    // This event carries only display metadata; company authority remains in the native session.
    document.addEventListener('manufacturer:company', event => {
      const value = event.detail;
      if (value?.session !== host.session?.environment?.id) return;
      applyCompany(value);
      if (typeof value.name === 'string') {
        signInTitle.textContent = value.name;
        host.$('workspace-owner').textContent = value.name;
        host.$('workspace-avatar').textContent = value.name.trim().slice(0, 1);
      }
    });
    document.querySelectorAll('.referral-stub').forEach(element => element.remove());
    const preview = host.node('button', 'icon-button manufacturer-chat-preview');
    preview.type = 'button'; preview.title = 'Preview configurator'; preview.setAttribute('aria-label', 'Preview configurator');
    preview.append(host.icon('eye')); preview.addEventListener('click', () => openSurface('configurator'));
    const files = host.$('chat-files-toggle');
    files.classList.add('icon-button'); files.replaceChildren(host.icon('folder'));
    files.title = 'Chat files'; files.setAttribute('aria-label', 'Chat files');
    const tools = host.node('div', 'mf-chat-tools'); tools.setAttribute('role', 'group'); tools.setAttribute('aria-label', 'Chat tools');
    tools.append(files, preview); document.querySelector('.attachment-menu-anchor').after(tools);
    host.$('chat-context-toggle').title = 'Chat details';
    const documents = window.RocotoManufacturerFiles(host);
    const embedded = new URL(location.href).searchParams.get('manufacturer_embed') === '1' && window.parent !== window;
    document.documentElement.lang = 'en';
    document.body.classList.toggle('mf-chat-embedded', embedded);
    const symbols = document.querySelector('svg defs');
    for (const [name, paths] of [['package', ['m12 3 9 5v8l-9 5-9-5V8Z', 'm3 8 9 5 9-5M12 13v8M7.5 5.5l9 5v4']], ['sliders', ['M4 3v7m0 4v7M12 3v3m0 4v11M20 3v11m0 4v3', 'M1 10h6v4H1ZM9 6h6v4H9ZM17 14h6v4h-6Z']]]) {
      if (document.getElementById(`i-${name}`)) continue;
      const symbol = document.createElementNS('http://www.w3.org/2000/svg', 'symbol'); symbol.id = `i-${name}`; symbol.setAttribute('viewBox', '0 0 24 24');
      for (const value of paths) { const path = document.createElementNS(symbol.namespaceURI, 'path'); path.setAttribute('d', value); symbol.append(path); } symbols.append(symbol);
    }
    const chromeCopy = new Map(Object.entries({
      'Message':'Message', 'Send message':'Send message', 'Queue message':'Queue message', 'Stop response':'Stop response',
      'Stop':'Stop', 'Add attachment':'Add attachment', 'Chat details':'Chat details', 'Chat files':'Chat files',
      'Files':'Files', 'Choose file':'Choose file', 'Refresh files':'Refresh files', 'Close files':'Close files',
      'File preview':'File preview', 'Ask about this file':'Ask about this file', 'Images':'Images', 'Skills':'Skills',
      'Add New Skill':'Add skill', 'Browse Skills':'Browse skills', 'Context and usage':'Context and usage',
      'Usage':'Usage', 'See detailed breakdown':'Usage details', 'Available after a response':'Available after a response',
      'Queued messages':'Queued messages', 'Selected skills':'Selected skills', 'Image attachments':'Image attachments',
      'Account and usage':'Account and usage', 'Profile':'Profile', 'Settings':'Settings', 'Log out':'Log out',
      'Demo code':'Access code', 'Company access code':'Access code', 'Open your workspace with an access code.':'Open your workspace with an access code.',
      'Connecting…':'Connecting…', 'Checking server':'Checking server', 'Company workspace':'Workspace',
      'Conversation':'Conversation', 'Workspace pages':'Pages', 'Open chats':'Open navigation', 'Close chats':'Close navigation',
      'Company & people':'Company and team', 'Organization':'Organization', 'Your workspace':'Your workspace',
      'View workspace as':'View as', 'Company':'Company', 'New chat':'Chat', 'Ask anything…':'Write a message…',
      'Ask a question or describe a task.':'Ask a question or describe a task.', 'Preview configurator':'Preview configurator',
      'Open chats':'Open navigation', 'Return to parent':'Back to conversation', 'Your Business':'Company',
      'Appearance':'Appearance', 'Notifications':'Notifications', 'Team':'Team', 'Messaging':'Messaging', 'Billing':'Billing',
      'Your available credit has been used. Your draft is saved.':'Your available budget is used. Your draft is saved.',
      'Write a follow-up while Rocoto works.':'Add a follow-up while the agent works.',
      'Business':'Company', 'Search settings':'Search settings', 'Personal':'Personal', 'Workspace':'Workspace',
    }));
    const chromeRoots = ['session-screen', 'chat-title', 'notice', 'funding-notice', 'agent-setup-notice', 'profile-menu', 'settings-nav', 'account-button', 'composer', 'message-queue', 'chat-context-popup', 'chat-files-panel', 'composer-note', 'context-tooltip', 'usage-popover', 'attachment-previews'];
    let translating = false;
    function translateChrome() {
      if (translating) return; translating = true;
      for (const id of chromeRoots) {
        const root = host.$(id); if (!root) continue;
        const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
        let text;
        while ((text = walker.nextNode())) { if (text.parentElement.closest('#messages, #file-preview, textarea, pre, code, .profile-menu-heading')) continue; const value = text.nodeValue.trim(), translated = chromeCopy.get(value); if (translated && translated !== value) text.nodeValue = text.nodeValue.replace(value, translated); }
        for (const el of [root, ...root.querySelectorAll('[aria-label], [title], [placeholder]')]) {
          for (const attr of ['aria-label', 'title', 'placeholder']) { const translated = chromeCopy.get(el.getAttribute(attr)); if (translated && translated !== el.getAttribute(attr)) el.setAttribute(attr, translated); }
        }
      }
      for (const el of host.elements.messages.querySelectorAll('.work-timing, .completed-turn > summary > span')) {
        const value = el.textContent;
        if (/^Work(?:ing|ed)(?: for |$)/.test(value)) el.textContent = value.replace(/^Working/, 'Working').replace(/^Worked/, 'Completed').replace(' for ', ' · ').replace(/(\d+)m/g, '$1m').replace(/(\d+)s/g, '$1s');
      }
      translating = false;
    }
    const chromeObserver = new MutationObserver(translateChrome);
    queueMicrotask(() => { for (const id of chromeRoots) { const root = host.$(id); if (root) chromeObserver.observe(root, {childList:true, subtree:true, characterData:true, attributes:true, attributeFilter:['aria-label','title','placeholder']}); } chromeObserver.observe(host.elements.messages, {childList:true, subtree:true, characterData:true}); translateChrome(); });
    let metadataIdentity = '', companyName = 'Sample Hardware';
    const brand = document.querySelector('#sidebar > .brand');
    brand.classList.add('mf-company-brand'); brand.setAttribute('aria-label', 'Sample Hardware · Orders');
    brand.href = '?view=orders'; brand.replaceChildren(host.node('span', 'mf-brand-fallback', 'S'));
    brand.addEventListener('click', event => { if (event.button || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return; event.preventDefault(); closeContext(false); openSurface('orders'); });
    function applyCompany(value) {
      agentEditing = value?.capabilities?.agent_editing !== false;
      document.body.classList.toggle('mf-manual-workspace', !agentEditing);
      if (!agentEditing && host.currentView === 'chat') { closeContext(false); openSurface('service'); }
      if (typeof value?.name === 'string' && value.name.trim()) companyName = value.name;
      brand.setAttribute('aria-label', `${companyName} · Orders`); brand.title = companyName;
      if (typeof value?.logo === 'string') {
        try { const logo = new URL(value.logo, location.href); if (!['https:', 'http:'].includes(logo.protocol) || logo.username || logo.password) return;
          const img = host.node('img', 'mf-brand-logo'); img.alt = companyName; img.src = logo.href;
          img.addEventListener('load', () => { brand.replaceChildren(img); const mark = img.cloneNode(); mark.alt = companyName; signInBrand.replaceChildren(mark); });
        } catch {}
      }
      host.$('workspace-owner').textContent = companyName;
    }
    function loadCompanyMetadata() {
      const identity = host.storageIdentity; if (!host.session || !identity || metadataIdentity === identity) return;
      metadataIdentity = identity; const generation = host.sessionGeneration;
      fetch('/api/manufacturer/team', {credentials:'same-origin', cache:'no-store'}).then(async response => { if (!response.ok) throw Error('metadata'); const data = await response.json(); if (generation !== host.sessionGeneration || identity !== host.storageIdentity) return; applyCompany(data.company); }).catch(() => { if (identity === host.storageIdentity) metadataIdentity = ''; });
    }
    const panel = host.node('aside', 'mf-context-chat'); panel.id = 'manufacturer-context-chat'; panel.hidden = true; panel.setAttribute('role', 'complementary'); panel.setAttribute('aria-label', 'Agent chat');
    const panelHeader = host.node('header', 'mf-context-header'), panelIdentity = host.node('div', 'mf-context-identity');
    const panelTitle = host.node('strong', '', 'Agent chat'), panelContext = host.node('span', 'mf-context-label'); panelContext.hidden = true; panelIdentity.append(panelTitle, panelContext);
    const expandChat = host.node('button', 'icon-button'); expandChat.type = 'button'; expandChat.title = 'Open full chat'; expandChat.setAttribute('aria-label', expandChat.title); expandChat.append(host.icon('fullscreen'));
    const closeChat = host.node('button', 'icon-button'); closeChat.type = 'button'; closeChat.title = 'Close chat'; closeChat.setAttribute('aria-label', closeChat.title); closeChat.append(host.icon('close'));
    panelHeader.append(panelIdentity, expandChat, closeChat); panel.append(panelHeader);
    const panelStatus = host.node('div', 'mf-context-loading'); panelStatus.setAttribute('role', 'status');
    const loadingText = host.node('span', 'mo-sr-only', 'Loading chat'); panelStatus.append(loadingText);
    for (const width of ['70%', '92%', '50%']) { const line = host.node('span', 'mf-context-skeleton'); line.style.width = width; line.setAttribute('aria-hidden', 'true'); panelStatus.append(line); }
    const frame = host.node('iframe', 'mf-context-frame'); frame.title = 'Company agent chat'; frame.hidden = true; panel.append(panelStatus, frame);
    const scrim = host.node('button', 'mf-context-scrim'); scrim.type = 'button'; scrim.hidden = true; scrim.setAttribute('aria-label', 'Close chat'); document.body.append(scrim, panel);
    const narrowContext = matchMedia('(max-width: 1100px)');
    let contextEpoch = 0, contextIdentity = '', contextChat = '', contextReady = false, pendingContext = null, returnFocus = null, contextView = '', contextOpen = false, openingContext = false;
    function syncContextLayout() {
      const modal = contextOpen && narrowContext.matches;
      panel.setAttribute('role', modal ? 'dialog' : 'complementary');
      if (modal) panel.setAttribute('aria-modal', 'true'); else panel.removeAttribute('aria-modal');
      const blocked = modal || Boolean(document.querySelector('.mh-panel:not([hidden])[aria-modal="true"]'));
      scrim.hidden = !modal; document.querySelector('.workspace').inert = blocked; host.$('sidebar').inert = blocked;
      document.body.classList.toggle('mf-context-open', contextOpen);
    }
    narrowContext.addEventListener('change', syncContextLayout);
    function closeContext(restore = true) {
      contextOpen = false; panel.hidden = true; syncContextLayout();
      if (restore && returnFocus?.isConnected) returnFocus.focus({preventScroll:true});
    }
    function resetContext() {
      closeContext(false); contextEpoch++; contextIdentity = ''; contextChat = ''; contextReady = false; pendingContext = null; frame.removeAttribute('src');
    }
    closeChat.addEventListener('click', () => closeContext()); scrim.addEventListener('click', () => closeContext());
    document.addEventListener('focusin', event => { if (contextOpen && narrowContext.matches && !panel.contains(event.target)) closeChat.focus(); });
    document.addEventListener('keydown', event => { if (event.key === 'Escape' && contextOpen && !event.defaultPrevented && !document.querySelector('dialog[open]')) { event.preventDefault(); closeContext(); } });
    function sendContext() {
      if (!contextReady || !pendingContext || !contextOpen) return;
      frame.contentWindow.postMessage({type:'manufacturer:context-prefill', chatId:contextChat, identity:contextIdentity, ...pendingContext}, location.origin);
    }
    function fullChat() {
      if (!contextChat) return;
      if (contextReady) frame.contentWindow.postMessage({type:'manufacturer:context-expand', chatId:contextChat, identity:contextIdentity}, location.origin);
    }
    expandChat.addEventListener('click', fullChat);
    async function openContext(detail = {}) {
      if (!host.session?.can_query) { host.showSession('Sign in with your company access code.'); return; }
      if (embedded) { startChat(detail.message || ''); return; }
      returnFocus = document.activeElement; contextView = host.currentView; contextOpen = true; panel.hidden = false; syncContextLayout(); closeChat.focus({preventScroll:true});
      panelContext.textContent = String(detail.label || detail.context?.title || detail.orderNumber || (new URL(location.href).searchParams.has('order') ? document.querySelector('.mo-detail-heading h1')?.textContent : '') || ''); panelContext.hidden = !panelContext.textContent;
      pendingContext = {requestId:crypto.randomUUID(), message:String(detail.message || '').slice(0,8000)};
      if (contextChat && contextIdentity === host.storageIdentity) { sendContext(); return; }
      const epoch = ++contextEpoch, identity = host.storageIdentity; openingContext = true;
      try {
        const response = await host.request('/api/organization/chats', {purpose:'organization', collection:'company'}); const data = await response.json();
        if (epoch !== contextEpoch || identity !== host.storageIdentity) return;
        const chat = host.mergeRemoteChat(data.chat || data); if (!chat || chat.kind !== 'organization_chat') throw Error('Open company chat again.');
        contextChat = chat.id; contextIdentity = identity; contextReady = false; panelStatus.hidden = false; frame.hidden = true;
        const url = new URL('/', location.href); url.searchParams.set('chat', chat.id); url.searchParams.set('manufacturer_embed', '1'); frame.src = url.href;
      } catch (error) { if (epoch !== contextEpoch) return; panelStatus.replaceChildren(host.node('p', '', 'Reconnecting chat.')); const retry = host.node('button', 'mf-button', 'Try again'); retry.type = 'button'; retry.addEventListener('click', () => openContext(detail)); panelStatus.append(retry); }
      finally { if (epoch === contextEpoch) openingContext = false; }
    }
    let handoffRestoring = false;
    function restoreChatHandoff() {
      if (embedded || handoffRestoring || !host.session || host.currentView !== 'chat' || host.activeChat()?.kind !== 'organization_chat') return;
      let saved; try { saved = JSON.parse(sessionStorage.getItem('manufacturer-chat-handoff') || 'null'); } catch { return; }
      if (!saved || saved.identity !== host.storageIdentity || saved.chatId !== host.activeId || typeof saved.text !== 'string' || saved.text.length > 8000 || Date.now() - saved.createdAt > 60000) return;
      handoffRestoring = true;
      queueMicrotask(() => {
        try {
          if (saved.identity !== host.storageIdentity || saved.chatId !== host.activeId) return;
          host.elements.message.value = saved.text; host.textDrafts.set(saved.chatId, saved.text); documents.editQueued(saved.chatId, {manufacturer_files:saved.files});
          host.resizeComposer(); documents.renderComposerAttachments(); host.updateMode(); sessionStorage.removeItem('manufacturer-chat-handoff');
        } finally { handoffRestoring = false; }
      });
    }
    let embeddedReady = '', lastPrefill = '', embeddedInitialized = false, initialPanelScroll = false;
    function embeddedState() {
      if (!embedded || !embeddedInitialized || host.currentView !== 'chat' || host.activeChat()?.kind !== 'organization_chat' || !host.session) return;
      const identity = host.storageIdentity, chatId = host.activeId, key = `${identity}:${chatId}`;
      if (embeddedReady !== key) { embeddedReady = key; window.parent.postMessage({type:'manufacturer:context-ready', identity, chatId}, location.origin); }
      window.parent.postMessage({type:'manufacturer:context-draft', identity, chatId, text:host.elements.message.value, files:documents.draftData(chatId).manufacturer_files}, location.origin);
    }
    window.addEventListener('message', event => {
      if (event.origin !== location.origin || !event.data || typeof event.data.type !== 'string') return;
      const data = event.data;
      if (embedded) {
        if (event.source !== window.parent || data.identity !== host.storageIdentity || data.chatId !== host.activeId || host.activeChat()?.kind !== 'organization_chat') return;
        if (data.type === 'manufacturer:context-prefill' && typeof data.message === 'string' && data.requestId !== lastPrefill) {
          lastPrefill = data.requestId; const prior = host.elements.message.value.trim(), message = data.message.trim();
          const combined = message && !prior.includes(message) ? (prior ? `${prior}\n\n${message}` : message) : prior;
          if (combined.length <= 8000) { host.elements.message.value = combined; host.textDrafts.set(host.activeId, combined); host.resizeComposer(); host.updateMode(); host.elements.message.focus(); }
          else host.notice('Save or send your current draft to add order context.');
          embeddedState(); window.parent.postMessage({type:'manufacturer:context-prefilled', identity:host.storageIdentity, chatId:host.activeId, requestId:data.requestId}, location.origin);
        } else if (data.type === 'manufacturer:context-focus') {
          requestAnimationFrame(() => {
            host.resizeComposer();
            if (!initialPanelScroll) {
              const latest = host.elements.messages.querySelector('.message-assistant:last-child') || host.elements.messages.lastElementChild;
              if (latest) host.elements.conversation.scrollTop += latest.getBoundingClientRect().top - host.elements.conversation.getBoundingClientRect().top - 12;
              initialPanelScroll = true;
            }
            host.elements.message.focus({preventScroll:true});
          });
        } else if (data.type === 'manufacturer:context-expand') {
          if (host.draftAdmitting() || documents.updateAlternateComposer()) { host.notice('Wait for files to finish processing before opening full chat.'); return; }
          host.persistDraft(); documents.saveDrafts(); window.parent.postMessage({type:'manufacturer:context-expand-ready', identity:host.storageIdentity, chatId:host.activeId, text:host.elements.message.value, files:documents.draftData(host.activeId).manufacturer_files}, location.origin);
        }
        return;
      }
      if (event.source !== frame.contentWindow || data.identity !== contextIdentity || data.chatId !== contextChat) return;
      if (data.type === 'manufacturer:context-ready') { contextReady = true; if (pendingContext) sendContext(); else { panelStatus.hidden = true; frame.hidden = false; } }
      else if (data.type === 'manufacturer:context-prefilled' && data.requestId === pendingContext?.requestId) { pendingContext = null; panelStatus.hidden = true; frame.hidden = false; frame.contentWindow.postMessage({type:'manufacturer:context-focus', identity:contextIdentity, chatId:contextChat}, location.origin); }
      else if (data.type === 'manufacturer:context-close') closeContext();
      else if (data.type === 'manufacturer:context-expand-ready' && typeof data.text === 'string' && data.text.length <= 8000) {
        try { sessionStorage.setItem('manufacturer-chat-handoff', JSON.stringify({identity:contextIdentity, chatId:contextChat, text:data.text, files:data.files, createdAt:Date.now()})); }
        catch { frame.contentWindow.postMessage({type:'manufacturer:context-prefill', identity:contextIdentity, chatId:contextChat, requestId:crypto.randomUUID(), message:''}, location.origin); return; }
        closeContext(false); location.assign(`/?chat=${encodeURIComponent(contextChat)}`);
      }
      else if (data.type === 'manufacturer:context-draft' && typeof data.text === 'string' && data.text.length <= 8000) {
        host.textDrafts.set(contextChat, data.text); if (host.activeId === contextChat) host.elements.message.value = data.text;
        documents.editQueued(contextChat, {manufacturer_files:data.files});
      }
    });
    host.elements.message.addEventListener('input', () => {
      if (host.activeChat()?.kind === 'organization_chat') host.textDrafts.set(host.activeId, host.elements.message.value);
      if (embedded) queueMicrotask(embeddedState);
    });
    if (embedded) {
      new MutationObserver(() => queueMicrotask(embeddedState)).observe(host.$('manufacturer-file-drafts'), {childList:true, subtree:true, characterData:true});
      document.addEventListener('keydown', event => { if (event.key !== 'Escape' || event.defaultPrevented || document.querySelector('dialog[open], #attachment-menu:not([hidden]), #chat-context-popup:not([hidden]), #chat-files-panel:not([hidden])')) return; window.parent.postMessage({type:'manufacturer:context-close', identity:host.storageIdentity, chatId:host.activeId}, location.origin); });
    }
    const tray = host.node('section', 'mf-composer-tray'); tray.id = 'manufacturer-composer-tray';
    tray.setAttribute('aria-label', 'Files and status'); tray.hidden = true;
    host.$('composer').before(tray);
    const attachments = host.$('manufacturer-file-drafts'); tray.append(attachments);
    const globalNotice = host.$('notice'), noticeHome = document.createComment('manufacturer notice origin');
    globalNotice.before(noticeHome);
    const notices = [];
    for (const [id, symbol, label] of [['notice', 'bell', 'Workspace'], ['funding-notice', 'chart', 'Usage'], ['agent-setup-notice', 'clock', 'Agent status']]) {
      const original = host.$(id), drawer = host.node('details', 'mf-composer-status'), summary = host.node('summary');
      drawer.dataset.notice = id; drawer.hidden = true; drawer.setAttribute('aria-label', label);
      const line = host.node('span', 'mf-composer-status-copy'); line.setAttribute('aria-live', 'polite');
      summary.append(host.icon(symbol), line, host.icon('chevron'));
      const body = host.node('div', 'mf-composer-status-body'); body.append(original); drawer.append(summary, body); tray.append(drawer);
      notices.push({original, drawer, line, body});
      new MutationObserver(syncTray).observe(original, {attributes: true, attributeFilter: ['hidden'], childList: true, characterData: true, subtree: true});
    }
    new MutationObserver(syncTray).observe(attachments, {attributes: true, attributeFilter: ['hidden'], childList: true});
    function syncTray() {
      const chat = host.currentView === 'chat';
      for (const {original, drawer, line} of notices) {
        const text = (original.querySelector(':scope > span')?.textContent || original.textContent || '').trim();
        const shown = chat && !original.hidden && Boolean(text);
        drawer.hidden = !shown;
        if (line.textContent !== text) { line.textContent = text; drawer.open = false; }
        line.title = text;
      }
      tray.hidden = !chat || (attachments.hidden && notices.every(({drawer}) => drawer.hidden));
      host.$('composer').classList.toggle('mf-has-tray', !tray.hidden);
    }
    function renderChatChrome() {
      const chat = host.currentView === 'chat';
      document.body.classList.toggle('manufacturer-chat-active', chat);
      const noticeBody = notices[0].body;
      if (chat && globalNotice.parentElement !== noticeBody) noticeBody.append(globalNotice);
      else if (!chat && globalNotice.parentNode !== noticeHome.parentNode) noticeHome.after(globalNotice);
      tools.hidden = !chat;
      syncTray();
    }
    function startChat(message) {
      host.openOrganizationChat('organization', 'company').then(chat => {
        if (!chat || !message) return;
        host.elements.message.value = message; host.textDrafts.set(chat.id, message); host.resizeComposer(); host.elements.message.focus();
      });
    }
    document.addEventListener('manufacturer:service', () => openSurface('service'));
    document.addEventListener('manufacturer:chat', event => { if(host.session?.role !== 'owner' || !agentEditing){openSurface('service');return;} if (host.currentView.startsWith('vertical:') && !embedded) openContext(event.detail || {}); else startChat(event.detail?.message || ''); });
    return {
      ...documents,
      // The native initial chat route runs after workspace hydration and may replace the composer.
      openInitialRoute() { embeddedInitialized = true; restoreChatHandoff(); embeddedState(); },
      composerPlaceholder() { return 'Write a message…'; },
      sessionIntroduction: 'Open your workspace with an access code.',
      resetScope() { agentEditing = true; document.body.classList.remove('mf-manual-workspace'); resetContext(); humanChat.reset(); },
      resetWorkspace() { agentEditing = true; document.body.classList.remove('mf-manual-workspace'); resetContext(); humanChat.reset(); documents.resetWorkspace(); },
      applyHarness(shell) {
        if (shell.vertical?.id === 'manufacturer' && host.currentView === 'home') host.currentView = 'vertical:orders';
      },
      beforeRender() {
        if(host.session && (host.session.role !== 'owner' || !agentEditing) && host.currentView === 'chat') host.currentView = 'vertical:service';
        if (host.harness.vertical?.id === 'manufacturer' && host.currentView === 'home') host.currentView = 'vertical:orders';
      },
      renderNavigation() {
        renderChatChrome(); loadCompanyMetadata(); translateChrome();
        if (contextOpen && host.currentView !== contextView && !openingContext) closeContext(false);
        if (embedded) queueMicrotask(embeddedState);
        preview.hidden = host.currentView !== 'chat';
        host.$('sidebar-toggle').setAttribute('aria-label', host.currentView.startsWith('vertical:') ? 'Open navigation' : 'Open navigation');
        document.body.classList.toggle('manufacturer-surface', host.currentView.startsWith('vertical:'));
        for (const [id, button] of controls) button.setAttribute('aria-current', (id === 'chat' ? host.currentView === 'chat' : host.currentView === `vertical:${id}`) ? 'page' : 'false');
        company.setAttribute('aria-current', host.currentView === 'vertical:company' ? 'page' : 'false');
      },
      renderWelcomeExamples(chat) {
        if (chat?.kind !== 'organization_chat') return;
        host.elements.welcome.querySelector('h1').textContent = 'Catalogue and configurator';
        host.elements.welcome.querySelector('p').textContent = 'Products, questions and configurator.';
        const suggestions = host.elements.welcome.querySelector('.suggestions');
        suggestions.replaceChildren(); suggestions.hidden = false;
        for (const text of ['Update prices from a file', 'Edit the configurator', 'Change delivery lead times']) {
          const choice = host.node('button', '', text); choice.type = 'button'; choice.append(host.icon('chevron'));
          choice.addEventListener('click', () => { host.elements.message.value = text; host.textDrafts.set(chat.id, text); host.resizeComposer(); host.elements.message.focus(); });
          suggestions.append(choice);
        }
      },
      surfaceLayout() { return {settings: host.currentView === 'vertical:company', hideTopbar:embedded}; },
    };
  });
})();
