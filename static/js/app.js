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
      <a href="${escapeAttr(n.link || '#')}" class="notif-item ${n.is_read ? '' : 'unread'}">
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
  if (!r.ok) { alert('Erreur.'); return; }
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
  if (!confirm('Supprimer ce commentaire ?')) return;
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
        flashOverlay('🔊 ' + Math.round(player.volume * 100) + '%');
        break;
      case 'arrowdown':
        player.volume = Math.max(0, player.volume - 0.1);
        flashOverlay('🔉 ' + Math.round(player.volume * 100) + '%');
        break;
      case 'm':
        player.muted = !player.muted;
        flashOverlay(player.muted ? '🔇' : '🔊');
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
  else { navigator.clipboard.writeText(url); alert('Lien copié : ' + url); }
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
  if (r.ok) { alert('Merci — votre signalement a été transmis.'); closeModal(); }
  else alert('Erreur lors de l\'envoi.');
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

/* ========= INFINITE SCROLL (feed) ========= */
const grid = document.querySelector('.video-grid');
if (grid && document.body.dataset.infinite === '1') {
  let loading = false, page = 1, hasMore = true;
  window.addEventListener('scroll', async () => {
    if (loading || !hasMore) return;
    if (window.innerHeight + window.scrollY >= document.body.offsetHeight - 800) {
      loading = true; page++;
      const url = new URL(location.href); url.searchParams.set('page', page); url.searchParams.set('partial', '1');
      const r = await fetch(url.pathname + '?' + url.searchParams);
      if (!r.ok) { loading = false; return; }
      const html = await r.text();
      if (html.trim()) grid.insertAdjacentHTML('beforeend', html);
      else hasMore = false;
      loading = false;
    }
  });
}
