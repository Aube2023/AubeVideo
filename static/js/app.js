/* AubeVideo — interactions client (prod) */

function getCsrf() {
  const m = document.querySelector('meta[name="csrf-token"]');
  return m ? m.content : '';
}
function jsonHeaders() {
  return {'Content-Type': 'application/json', 'X-CSRF-Token': getCsrf()};
}

/* ========= UI TOGGLES ========= */
function toggleSidebar() { document.getElementById('sidebar').classList.toggle('open'); }
function toggleUserMenu() { const el = document.getElementById('userDropdown'); if (el) el.classList.toggle('open'); }
function toggleNotifs() {
  const el = document.getElementById('notifDropdown');
  if (!el) return;
  el.classList.toggle('open');
  if (el.classList.contains('open')) loadNotifications();
}

document.addEventListener('click', (e) => {
  const menu = document.querySelector('.user-menu');
  const dd = document.getElementById('userDropdown');
  if (dd && menu && !menu.contains(e.target)) dd.classList.remove('open');
  const nw = document.querySelector('.notif-wrap');
  const nd = document.getElementById('notifDropdown');
  if (nd && nw && !nw.contains(e.target)) nd.classList.remove('open');
});

/* ========= NOTIFICATIONS ========= */
async function loadNotifications() {
  const list = document.getElementById('notifList');
  if (!list) return;
  list.innerHTML = '<div class="notif-empty">Chargement...</div>';
  try {
    const r = await fetch('/api/notifications');
    const data = await r.json();
    if (!data.length) { list.innerHTML = '<div class="notif-empty">Aucune notification</div>'; return; }
    list.innerHTML = data.map(n => `
      <a href="${escapeAttr(n.link || '#')}" class="notif-item ${n.is_read ? '' : 'unread'}" onclick="markAllRead()">
        <div><strong>${escapeHtml(n.title)}</strong></div>
        <div class="notif-sub">${escapeHtml(n.body || '')}</div>
        <div class="notif-time">${timeAgo(n.created_at)}</div>
      </a>
    `).join('');
  } catch (e) {
    list.innerHTML = '<div class="notif-empty">Erreur de chargement</div>';
  }
}
async function markAllRead() {
  await fetch('/api/notifications/read', {method: 'POST', headers: jsonHeaders()});
  const badge = document.querySelector('.notif-btn .badge');
  if (badge) badge.remove();
  document.querySelectorAll('.notif-item.unread').forEach(i => i.classList.remove('unread'));
}

/* ========= LIKES / DISLIKES ========= */
document.querySelectorAll('.like-btn, .dislike-btn').forEach(btn => {
  btn.addEventListener('click', async () => {
    const videoId = btn.dataset.video;
    const reaction = btn.dataset.reaction;
    const r = await fetch(`/api/video/${videoId}/react`, {
      method: 'POST', headers: jsonHeaders(),
      body: JSON.stringify({reaction})
    });
    if (r.status === 401) { window.location = '/login'; return; }
    if (!r.ok) return;
    const data = await r.json();
    document.querySelector('.like-btn').classList.toggle('active', data.reaction === 'like');
    document.querySelector('.dislike-btn').classList.toggle('active', data.reaction === 'dislike');
    document.getElementById('likeCount').textContent = formatCount(data.likes);
    const dc = document.getElementById('dislikeCount');
    if (dc) dc.textContent = formatCount(data.dislikes);
  });
});

/* ========= SUBSCRIBE ========= */
const subBtn = document.getElementById('subBtn');
if (subBtn) {
  subBtn.addEventListener('click', async () => {
    const cid = subBtn.dataset.channel;
    const r = await fetch(`/api/subscribe/${cid}`, {method: 'POST', headers: jsonHeaders()});
    if (r.status === 401) { window.location = '/login'; return; }
    if (!r.ok) return;
    const data = await r.json();
    subBtn.classList.toggle('subscribed', data.subscribed);
    subBtn.textContent = data.subscribed ? 'Abonné' : "S'abonner";
    const count = document.getElementById('channelSubCount');
    if (count) count.textContent = `${formatCount(data.count)} abonné${data.count > 1 ? 's' : ''}`;
    const subsCount = document.querySelector('.subs-count');
    if (subsCount) subsCount.textContent = `${formatCount(data.count)} abonné${data.count > 1 ? 's' : ''}`;
  });
}

/* ========= WATCH LATER ========= */
const wlBtn = document.getElementById('watchLaterBtn');
if (wlBtn) {
  wlBtn.addEventListener('click', async () => {
    const vid = wlBtn.dataset.video;
    const r = await fetch('/api/watch-later/' + vid, {method: 'POST', headers: jsonHeaders()});
    if (!r.ok) return;
    const data = await r.json();
    wlBtn.classList.toggle('active', data.saved);
    wlBtn.querySelector('span').textContent = data.saved ? 'Enregistrée' : 'Regarder plus tard';
  });
}

/* ========= COMMENTS ========= */
async function postComment(videoId, parentId) {
  const taId = parentId ? 'reply-ta-' + parentId : 'commentContent';
  const ta = document.getElementById(taId);
  const content = ta.value.trim();
  if (!content) return;
  const r = await fetch(`/api/video/${videoId}/comment`, {
    method: 'POST', headers: jsonHeaders(),
    body: JSON.stringify({content, parent_id: parentId || null})
  });
  if (!r.ok) { uiToast('Erreur lors de l\'envoi du commentaire.'); return; }
  const c = await r.json();
  if (parentId) {
    const box = document.getElementById('replies-' + parentId);
    box.insertAdjacentHTML('beforeend', renderReply(c, videoId));
    document.getElementById('reply-form-' + parentId).style.display = 'none';
  } else {
    document.getElementById('commentsList').insertAdjacentHTML('afterbegin', renderComment(c, videoId));
    ta.value = '';
    const h = document.getElementById('commentsHeader');
    if (h) h.textContent = h.textContent.replace(/^\d+/, (parseInt(h.textContent) || 0) + 1);
  }
}

function renderComment(c, videoId) {
  return `<div class="comment" data-id="${c.id}">
    <a href="/c/${encodeURIComponent(c.username)}"><img class="avatar-sm" src="/avatar/${encodeURIComponent(c.username)}" alt=""></a>
    <div class="c-body">
      <div class="c-head">
        <a href="/c/${encodeURIComponent(c.username)}" class="c-name">${escapeHtml(c.display_name)}</a>
        <span class="c-time">à l'instant</span>
      </div>
      <div class="c-content">${escapeHtml(c.content)}</div>
      <div class="c-foot">
        <button class="c-like" onclick="likeComment(${c.id}, this)"><span>0</span></button>
        <button class="c-reply" onclick="toggleReply(${c.id})">Répondre</button>
        <button class="c-delete" onclick="deleteComment(${videoId}, ${c.id})">Supprimer</button>
      </div>
      <div class="reply-form" id="reply-form-${c.id}" style="display:none"></div>
      <div class="replies" id="replies-${c.id}"></div>
    </div>
  </div>`;
}

function renderReply(c, videoId) {
  return `<div class="comment reply" data-id="${c.id}">
    <a href="/c/${encodeURIComponent(c.username)}"><img class="avatar-sm" src="/avatar/${encodeURIComponent(c.username)}" alt=""></a>
    <div class="c-body">
      <div class="c-head">
        <a href="/c/${encodeURIComponent(c.username)}" class="c-name">${escapeHtml(c.display_name)}</a>
        <span class="c-time">à l'instant</span>
      </div>
      <div class="c-content">${escapeHtml(c.content)}</div>
      <div class="c-foot">
        <button class="c-like" onclick="likeComment(${c.id}, this)"><span>${c.likes_count || 0}</span></button>
      </div>
    </div>
  </div>`;
}

function toggleReply(parentId) {
  const box = document.getElementById('reply-form-' + parentId);
  if (box.style.display === 'none') {
    box.innerHTML = `
      <textarea id="reply-ta-${parentId}" placeholder="Répondre..." rows="1"></textarea>
      <div class="comment-actions">
        <button class="btn-ghost" onclick="document.getElementById('reply-form-${parentId}').style.display='none'">Annuler</button>
        <button class="btn btn-primary" onclick="postComment(${window.AUBE_VIDEO_ID || 0}, ${parentId})">Répondre</button>
      </div>`;
    box.style.display = 'block';
    document.getElementById('reply-ta-' + parentId).focus();
  } else box.style.display = 'none';
}

async function loadReplies(parentId) {
  const box = document.getElementById('replies-' + parentId);
  if (box.dataset.loaded === '1') { box.innerHTML = ''; box.dataset.loaded = '0'; return; }
  const r = await fetch('/api/comment/' + parentId + '/replies');
  const replies = await r.json();
  box.innerHTML = replies.map(c => renderReply(c, window.AUBE_VIDEO_ID || 0)).join('');
  box.dataset.loaded = '1';
}

async function likeComment(commentId, btn) {
  const r = await fetch('/api/comment/' + commentId + '/like', {method: 'POST', headers: jsonHeaders()});
  if (r.status === 401) { window.location = '/login'; return; }
  if (!r.ok) return;
  const data = await r.json();
  btn.querySelector('span').textContent = data.count;
  btn.classList.toggle('active', data.liked);
}

async function deleteComment(videoId, commentId) {
  if (!await uiConfirm('Supprimer ce commentaire ?', {danger: true, okLabel: 'Supprimer'})) return;
  const r = await fetch(`/api/video/${videoId}/comment/${commentId}`, {
    method: 'DELETE', headers: jsonHeaders()
  });
  if (r.ok) {
    const el = document.querySelector(`.comment[data-id="${commentId}"]`);
    if (el) el.remove();
  }
}

/* ========= PLAYER ENHANCEMENTS ========= */
const player = document.getElementById('player');
if (player) {
  document.addEventListener('keydown', (e) => {
    if (['INPUT','TEXTAREA'].includes(e.target.tagName)) return;
    switch (e.key.toLowerCase()) {
      case ' ':
      case 'k':
        e.preventDefault();
        player.paused ? player.play() : player.pause();
        flashOverlay(player.paused ? '⏸' : '▶');
        break;
      case 'arrowright':
      case 'l':
        player.currentTime = Math.min(player.duration, player.currentTime + 5);
        flashOverlay('+5s');
        break;
      case 'arrowleft':
      case 'j':
        player.currentTime = Math.max(0, player.currentTime - 5);
        flashOverlay('-5s');
        break;
      case 'arrowup':
        player.volume = Math.min(1, player.volume + 0.1);
        flashOverlay('Volume ' + Math.round(player.volume * 100) + '%');
        break;
      case 'arrowdown':
        player.volume = Math.max(0, player.volume - 0.1);
        flashOverlay('Volume ' + Math.round(player.volume * 100) + '%');
        break;
      case 'm':
        player.muted = !player.muted;
        flashOverlay(player.muted ? 'Muet' : 'Son');
        break;
      case 'f':
        if (document.fullscreenElement) document.exitFullscreen();
        else player.requestFullscreen();
        break;
      case 't':
        toggleTheater();
        break;
    }
  });

  try {
    const saved = parseFloat(localStorage.getItem('vol'));
    if (!isNaN(saved)) player.volume = saved;
  } catch(e){}
  player.addEventListener('volumechange', () => {
    try { localStorage.setItem('vol', player.volume); } catch(e){}
  });

  player.addEventListener('ended', () => {
    const first = document.querySelector('.sug-card');
    if (first && localStorage.getItem('autoplay') !== '0') {
      setTimeout(() => { window.location = first.href; }, 1500);
    }
  });
}

function flashOverlay(text) {
  const o = document.getElementById('playerOverlay');
  if (!o) return;
  o.textContent = text;
  o.classList.remove('show'); void o.offsetWidth; o.classList.add('show');
}

function toggleTheater() {
  const layout = document.getElementById('watchLayout');
  if (layout) layout.classList.toggle('theater');
}

/* ========= SHARE ========= */
function shareVideo(id) {
  const t = Math.floor(player ? player.currentTime : 0);
  const url = location.origin + '/watch/' + id + (t > 0 ? '?t=' + t : '');
  if (navigator.share) navigator.share({title: document.title, url});
  else { navigator.clipboard.writeText(url); uiToast('Lien copié dans le presse-papiers'); }
}

// Seek on load if ?t=
const urlParams = new URLSearchParams(location.search);
const tParam = parseInt(urlParams.get('t'));
if (player && !isNaN(tParam) && tParam > 0) {
  player.addEventListener('loadedmetadata', () => { player.currentTime = tParam; }, {once: true});
}

/* ========= PLAYLIST MODAL ========= */
function openSaveToPlaylist(videoId) {
  const pls = window.AUBE_PLAYLISTS || [];
  const root = document.getElementById('modalRoot');
  const list = pls.map(p => `
    <label class="pl-check">
      <input type="checkbox" data-playlist="${p.id}" ${p.has_video ? 'checked' : ''}>
      ${escapeHtml(p.title)}
    </label>`).join('');
  root.innerHTML = `
    <div class="modal-bg" onclick="if(event.target===this)closeModal()">
      <div class="modal">
        <h3>Enregistrer dans une playlist</h3>
        ${pls.length ? list : '<p class="empty">Aucune playlist. Créez-en une dans "Mes playlists".</p>'}
        <div class="form-actions">
          <button class="btn-ghost" onclick="closeModal()">Fermer</button>
        </div>
      </div>
    </div>`;
  root.querySelectorAll('input[data-playlist]').forEach(inp => {
    inp.addEventListener('change', async () => {
      const pid = inp.dataset.playlist;
      await fetch(`/api/playlist/${pid}/video/${videoId}`, {method: 'POST', headers: jsonHeaders()});
    });
  });
}
function closeModal() { document.getElementById('modalRoot').innerHTML = ''; }

/* ========= DIALOGUES & TOASTS (remplacent alert/confirm/prompt natifs) ========= */
function uiDialog(opts) {
  return new Promise(resolve => {
    const root = document.getElementById('modalRoot');
    if (!root) { resolve(null); return; }
    const wrap = document.createElement('div');
    wrap.className = 'modal-bg';
    wrap.innerHTML = `
      <div class="modal dialog" role="dialog" aria-modal="true">
        ${opts.title ? `<h3>${escapeHtml(opts.title)}</h3>` : ''}
        ${opts.message ? `<p class="dialog-msg">${escapeHtml(opts.message)}</p>` : ''}
        ${opts.bodyHtml || ''}
        <div class="form-actions">
          ${opts.cancelLabel ? `<button type="button" class="btn-ghost" data-act="cancel">${escapeHtml(opts.cancelLabel)}</button>` : ''}
          <button type="button" class="btn ${opts.danger ? 'btn-danger-solid' : 'btn-primary'}" data-act="ok">${escapeHtml(opts.okLabel || 'OK')}</button>
        </div>
      </div>`;
    root.innerHTML = '';
    root.appendChild(wrap);
    const dlg = wrap.querySelector('.dialog');
    const done = val => { root.innerHTML = ''; document.removeEventListener('keydown', onKey); resolve(val); };
    const ok = () => done(opts.collect ? opts.collect(dlg) : true);
    const cancel = () => done(null);
    function onKey(e) {
      if (e.key === 'Escape') cancel();
      else if (e.key === 'Enter' && e.target.tagName !== 'TEXTAREA') { e.preventDefault(); ok(); }
    }
    wrap.addEventListener('click', e => { if (e.target === wrap) cancel(); });
    wrap.querySelector('[data-act="ok"]').addEventListener('click', ok);
    const cb = wrap.querySelector('[data-act="cancel"]');
    if (cb) cb.addEventListener('click', cancel);
    document.addEventListener('keydown', onKey);
    const first = dlg.querySelector('input:not([type=hidden]), select, textarea') || wrap.querySelector('[data-act="ok"]');
    first.focus();
    if (first.select) first.select();
  });
}
function uiAlert(message, title) {
  return uiDialog({title: title || '', message, okLabel: 'OK'});
}
function uiConfirm(message, opts = {}) {
  return uiDialog({
    title: opts.title || 'Confirmation', message,
    okLabel: opts.okLabel || 'Confirmer',
    cancelLabel: opts.cancelLabel || 'Annuler',
    danger: opts.danger,
  }).then(v => v !== null);
}
function uiPrompt(title, opts = {}) {
  return uiDialog({
    title,
    bodyHtml: `<label class="field">
        ${opts.label ? `<span>${escapeHtml(opts.label)}</span>` : ''}
        <input type="text" data-dlg-input value="${escapeAttr(opts.value || '')}"
               placeholder="${escapeAttr(opts.placeholder || '')}" maxlength="${opts.maxlength || 200}">
      </label>`,
    okLabel: opts.okLabel || 'OK', cancelLabel: 'Annuler',
    collect: el => el.querySelector('[data-dlg-input]').value.trim(),
  });
}
const VISIBILITY_LABELS = [
  ['public', 'Publique — visible par tout le monde'],
  ['unlisted', 'Non répertoriée — accessible par lien seulement'],
  ['private', 'Privée — visible par vous seul'],
];
function uiVisibilityField(current) {
  return `<label class="field"><span>Visibilité</span>
    <select data-dlg-vis>${VISIBILITY_LABELS.map(([v, l]) =>
      `<option value="${v}" ${v === current ? 'selected' : ''}>${l}</option>`).join('')}
    </select></label>`;
}
function uiToast(message, ms = 2600) {
  document.querySelectorAll('.toast').forEach(t => t.remove());
  const el = document.createElement('div');
  el.className = 'toast';
  el.textContent = message;
  document.body.appendChild(el);
  requestAnimationFrame(() => el.classList.add('show'));
  setTimeout(() => { el.classList.remove('show'); setTimeout(() => el.remove(), 300); }, ms);
}

function openEmbed(videoId) {
  const code = `<iframe src="${location.origin}/embed/${videoId}" width="640" height="360" frameborder="0" allowfullscreen></iframe>`;
  const link = `${location.origin}/watch/${videoId}`;
  const root = document.getElementById('modalRoot');
  root.innerHTML = `
    <div class="modal-bg" onclick="if(event.target===this)closeModal()">
      <div class="modal">
        <h3>Intégrer cette vidéo</h3>
        <label class="field">
          <span>Code iframe (copier-coller)</span>
          <textarea rows="3" readonly id="embedTA">${code}</textarea>
        </label>
        <label class="field">
          <span>Lien direct</span>
          <input type="text" readonly value="${link}">
        </label>
        <div class="form-actions">
          <button class="btn-ghost" onclick="closeModal()">Fermer</button>
          <button class="btn btn-primary" onclick="navigator.clipboard.writeText(document.getElementById('embedTA').value); this.textContent='✓ Copié'">Copier le code</button>
        </div>
      </div>
    </div>`;
}

/* ========= REPORT MODAL ========= */
const REPORT_REASONS = [
  "Contenu inapproprié", "Discours haineux", "Violence",
  "Spam / arnaque", "Fausses informations", "Harcèlement",
  "Atteinte aux droits d'auteur", "Autre"
];
function openReport(target_type, target_id) {
  const root = document.getElementById('modalRoot');
  root.innerHTML = `
    <div class="modal-bg" onclick="if(event.target===this)closeModal()">
      <div class="modal">
        <h3>Signaler</h3>
        <label class="field">
          <span>Motif</span>
          <select id="reportReason">
            ${REPORT_REASONS.map(r => `<option>${r}</option>`).join('')}
          </select>
        </label>
        <label class="field">
          <span>Détails (optionnel)</span>
          <textarea id="reportDetails" rows="3" maxlength="2000"></textarea>
        </label>
        <div class="form-actions">
          <button class="btn-ghost" onclick="closeModal()">Annuler</button>
          <button class="btn btn-primary" onclick="submitReport('${target_type}', ${target_id})">Envoyer</button>
        </div>
      </div>
    </div>`;
}
async function submitReport(type, id) {
  const reason = document.getElementById('reportReason').value;
  const details = document.getElementById('reportDetails').value;
  const r = await fetch('/api/report', {
    method: 'POST', headers: jsonHeaders(),
    body: JSON.stringify({target_type: type, target_id: id, reason, details})
  });
  if (r.ok) { closeModal(); uiToast('Merci — votre signalement a été transmis.'); }
  else uiToast('Erreur lors de l\'envoi.');
}

/* ========= UTILS ========= */
function formatCount(n) {
  n = Number(n);
  if (n < 1000) return String(n);
  if (n < 1e6) return (n/1000).toFixed(1).replace('.0','') + ' k';
  if (n < 1e9) return (n/1e6).toFixed(1).replace('.0','') + ' M';
  return (n/1e9).toFixed(1).replace('.0','') + ' Md';
}
function timeAgo(iso) {
  const dt = new Date(iso); const s = (Date.now() - dt) / 1000;
  if (s < 60) return "à l'instant";
  if (s < 3600) return "il y a " + Math.floor(s/60) + " min";
  if (s < 86400) return "il y a " + Math.floor(s/3600) + " h";
  return "il y a " + Math.floor(s/86400) + " j";
}
function escapeHtml(s) {
  return String(s || '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function escapeAttr(s) { return escapeHtml(s).replace(/"/g, '&quot;'); }

document.querySelectorAll('.comment-input textarea, .reply-form textarea').forEach(ta => {
  ta.addEventListener('input', () => { ta.style.height = 'auto'; ta.style.height = ta.scrollHeight + 'px'; });
});

setTimeout(() => {
  document.querySelectorAll('.flash').forEach(f => {
    f.style.transition = 'opacity .3s'; f.style.opacity = '0';
    setTimeout(() => f.remove(), 300);
  });
}, 4000);

/* ========= AUTO-RESUME VIDEO POSITION ========= */
if (player) {
  const videoId = window.AUBE_VIDEO_ID;
  const key = 'resume_' + videoId;
  player.addEventListener('loadedmetadata', () => {
    if (!isNaN(tParam) && tParam > 0) return;
    try {
      const saved = parseFloat(localStorage.getItem(key));
      if (!isNaN(saved) && saved > 5 && saved < player.duration - 10) {
        player.currentTime = saved;
        flashOverlay('Reprise à ' + fmtTime(saved));
      }
    } catch(e) {}
  });
  let saveT = 0;
  player.addEventListener('timeupdate', () => {
    const now = Date.now();
    if (now - saveT > 3000) {
      saveT = now;
      try { localStorage.setItem(key, player.currentTime); } catch(e){}
    }
  });
  player.addEventListener('ended', () => {
    try { localStorage.removeItem(key); } catch(e){}
  });
}
function fmtTime(s) {
  s = Math.floor(s);
  const m = Math.floor(s/60), r = s%60;
  return m + ':' + (r < 10 ? '0' : '') + r;
}

/* ========= SEARCH AUTOCOMPLETE ========= */
const searchInput = document.getElementById('searchInput');
const searchSuggest = document.getElementById('searchSuggest');
let searchTimer;
if (searchInput && searchSuggest) {
  searchInput.addEventListener('input', () => {
    clearTimeout(searchTimer);
    const q = searchInput.value.trim();
    if (q.length < 2) { searchSuggest.innerHTML = ''; searchSuggest.classList.remove('open'); return; }
    searchTimer = setTimeout(async () => {
      const r = await fetch('/api/suggest?q=' + encodeURIComponent(q));
      if (!r.ok) return;
      const items = await r.json();
      if (!items.length) { searchSuggest.innerHTML = ''; searchSuggest.classList.remove('open'); return; }
      searchSuggest.innerHTML = items.map(it => {
        const link = it.kind === 'channel'
          ? `/c/${encodeURIComponent(it.username)}`
          : `/watch/${encodeURIComponent(it.id)}`;
        const icon = it.kind === 'channel' ? '<svg viewBox="0 0 24 24" width="16" height="16"><path fill="currentColor" d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/></svg>' : '<svg viewBox="0 0 24 24" width="16" height="16"><path fill="currentColor" d="M8 5v14l11-7z"/></svg>';
        return `<a href="${link}" class="ss-item"><span class="ss-icon">${icon}</span><span>${escapeHtml(it.text)}</span></a>`;
      }).join('');
      searchSuggest.classList.add('open');
    }, 150);
  });
  searchInput.addEventListener('blur', () => setTimeout(() => searchSuggest.classList.remove('open'), 200));
  searchInput.addEventListener('focus', () => { if (searchSuggest.innerHTML) searchSuggest.classList.add('open'); });
}

/* ========= CHAPTERS (timestamps dans description) ========= */
const desc = document.getElementById('videoDescription');
const chaptersList = document.getElementById('chaptersList');
if (desc && chaptersList && player) {
  const text = desc.textContent;
  const re = /(?:^|\n)\s*(\d{1,2}(?::\d{2}){1,2})\s+([^\n]+)/g;
  const chapters = [];
  let m;
  while ((m = re.exec(text)) !== null) {
    chapters.push({ts: parseTs(m[1]), label: m[2].trim(), raw: m[1]});
  }
  if (chapters.length >= 2) {
    desc.innerHTML = desc.innerHTML.replace(/(\d{1,2}(?::\d{2}){1,2})/g, (ts) => {
      return `<a href="#" class="ts-link" data-t="${parseTs(ts)}">${ts}</a>`;
    });
    desc.querySelectorAll('.ts-link').forEach(a => {
      a.addEventListener('click', e => { e.preventDefault(); player.currentTime = +a.dataset.t; player.play(); });
    });
    chaptersList.innerHTML = '<h4>Chapitres</h4>' + chapters.map(c => `
      <button class="chapter" data-t="${c.ts}">
        <span class="ch-time">${c.raw}</span>
        <span class="ch-label">${escapeHtml(c.label)}</span>
      </button>
    `).join('');
    chaptersList.querySelectorAll('.chapter').forEach(b => {
      b.addEventListener('click', () => { player.currentTime = +b.dataset.t; player.play(); });
    });
  }
}
function parseTs(s) {
  const parts = s.split(':').map(Number);
  if (parts.length === 3) return parts[0]*3600 + parts[1]*60 + parts[2];
  return parts[0]*60 + parts[1];
}

/* ========= QUALITY SELECTOR ========= */
const qs = document.getElementById('qualitySelector');
if (qs && window.AUBE_VIDEO_QUALITIES) {
  const quals = window.AUBE_VIDEO_QUALITIES.split(',').filter(Boolean);
  if (quals.length) {
    qs.innerHTML = '<button class="q-btn">Auto ▾</button><div class="q-menu">' +
      ['auto', ...quals].map(q => `<button data-q="${q}">${q}</button>`).join('') + '</div>';
    qs.querySelector('.q-btn').addEventListener('click', () => qs.classList.toggle('open'));
    qs.querySelectorAll('.q-menu button').forEach(b => {
      b.addEventListener('click', () => {
        const q = b.dataset.q;
        const src = document.getElementById('playerSource');
        const t = player.currentTime;
        const wasPlaying = !player.paused;
        const base = src.src.split('?')[0];
        src.src = q === 'auto' ? base : base + '?q=' + q;
        player.load();
        player.addEventListener('loadedmetadata', () => {
          player.currentTime = t;
          if (wasPlaying) player.play().catch(()=>{});
        }, {once: true});
        qs.querySelector('.q-btn').textContent = q + ' ▾';
        qs.classList.remove('open');
      });
    });
  }
}

/* ========= CAPTIONS UPLOAD MODAL ========= */
function openCaptionsUpload(videoId) {
  const root = document.getElementById('modalRoot');
  root.innerHTML = `
    <div class="modal-bg" onclick="if(event.target===this)closeModal()">
      <div class="modal">
        <h3>Ajouter des sous-titres</h3>
        <form id="capForm" enctype="multipart/form-data">
          <label class="field">
            <span>Langue (code)</span>
            <input type="text" name="lang" value="fr" maxlength="10">
          </label>
          <label class="field">
            <span>Libellé</span>
            <input type="text" name="label" value="Français" maxlength="64">
          </label>
          <label class="field">
            <span>Fichier .vtt ou .srt</span>
            <input type="file" name="file" accept=".vtt,.srt" required>
          </label>
          <div class="form-actions">
            <button type="button" class="btn-ghost" onclick="closeModal()">Annuler</button>
            <button type="submit" class="btn btn-primary">Téléverser</button>
          </div>
        </form>
      </div>
    </div>`;
  document.getElementById('capForm').addEventListener('submit', async e => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const r = await fetch('/api/video/' + videoId + '/captions',
      {method: 'POST', headers: {'X-CSRF-Token': getCsrf()}, body: fd});
    if (r.ok) { closeModal(); location.reload(); }
    else uiToast('Erreur lors du téléversement des sous-titres.');
  });
}

/* ========= PIN / HEART COMMENTS ========= */
async function pinComment(commentId) {
  const r = await fetch('/api/comment/' + commentId + '/pin',
    {method: 'POST', headers: jsonHeaders()});
  if (r.ok) location.reload();
}
async function heartComment(commentId) {
  const r = await fetch('/api/comment/' + commentId + '/heart',
    {method: 'POST', headers: jsonHeaders()});
  if (r.ok) location.reload();
}

/* ========= WEB PUSH ========= */
async function enablePushNotifications() {
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) return;
  const reg = await navigator.serviceWorker.ready;
  const r = await fetch('/api/push/key');
  const {key} = await r.json();
  if (!key) return;
  const sub = await reg.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlB64ToUint8Array(key),
  });
  await fetch('/api/push/subscribe',
    {method: 'POST', headers: jsonHeaders(), body: JSON.stringify(sub)});
}
function urlB64ToUint8Array(b64) {
  const pad = '='.repeat((4 - b64.length % 4) % 4);
  const b = (b64 + pad).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(b);
  return new Uint8Array([...raw].map(c => c.charCodeAt(0)));
}
