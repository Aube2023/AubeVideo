/* AubeVideo — interactions client */

function toggleSidebar() {
  document.getElementById('sidebar').classList.toggle('open');
}

function toggleUserMenu() {
  const el = document.getElementById('userDropdown');
  if (el) el.classList.toggle('open');
}

document.addEventListener('click', (e) => {
  const menu = document.querySelector('.user-menu');
  const dd = document.getElementById('userDropdown');
  if (dd && menu && !menu.contains(e.target)) dd.classList.remove('open');
});

/* ========= LIKES / DISLIKES ========= */
document.querySelectorAll('.like-btn, .dislike-btn').forEach(btn => {
  btn.addEventListener('click', async () => {
    const videoId = btn.dataset.video;
    const reaction = btn.dataset.reaction;
    const r = await fetch(`/api/video/${videoId}/react`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({reaction})
    });
    if (r.status === 401) { window.location = '/login'; return; }
    if (!r.ok) return;
    const data = await r.json();
    const likeBtn = document.querySelector('.like-btn');
    const dislikeBtn = document.querySelector('.dislike-btn');
    document.getElementById('likeCount').textContent = formatCount(data.likes);
    likeBtn.classList.toggle('active', data.reaction === 'like');
    dislikeBtn.classList.toggle('active', data.reaction === 'dislike');
  });
});

/* ========= SUBSCRIBE ========= */
const subBtn = document.getElementById('subBtn');
if (subBtn) {
  subBtn.addEventListener('click', async () => {
    const cid = subBtn.dataset.channel;
    const r = await fetch(`/api/subscribe/${cid}`, {method: 'POST'});
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

/* ========= COMMENTS ========= */
async function postComment(videoId) {
  const ta = document.getElementById('commentContent');
  const content = ta.value.trim();
  if (!content) return;
  const r = await fetch(`/api/video/${videoId}/comment`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({content})
  });
  if (!r.ok) { alert('Erreur lors de la publication.'); return; }
  const c = await r.json();
  const html = `
    <div class="comment" data-id="${c.id}">
      <a href="/c/${c.username}"><img class="avatar-sm" src="/avatar/${c.username}" alt=""></a>
      <div class="c-body">
        <div class="c-head">
          <a href="/c/${c.username}" class="c-name">${escapeHtml(c.display_name)}</a>
          <span class="c-time">à l'instant</span>
        </div>
        <div class="c-content">${escapeHtml(c.content)}</div>
        <button class="c-delete" onclick="deleteComment(${videoId}, ${c.id})">Supprimer</button>
      </div>
    </div>`;
  document.getElementById('commentsList').insertAdjacentHTML('afterbegin', html);
  ta.value = '';
}

async function deleteComment(videoId, commentId) {
  if (!confirm('Supprimer ce commentaire ?')) return;
  const r = await fetch(`/api/video/${videoId}/comment/${commentId}`, {method: 'DELETE'});
  if (r.ok) {
    const el = document.querySelector(`.comment[data-id="${commentId}"]`);
    if (el) el.remove();
  }
}

/* ========= UTILS ========= */
function formatCount(n) {
  n = Number(n);
  if (n < 1000) return String(n);
  if (n < 1e6) return (n/1000).toFixed(1).replace('.0','') + ' k';
  if (n < 1e9) return (n/1e6).toFixed(1).replace('.0','') + ' M';
  return (n/1e9).toFixed(1).replace('.0','') + ' Md';
}
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

/* ========= COMMENT TEXTAREA AUTO-GROW ========= */
document.querySelectorAll('.comment-input textarea').forEach(ta => {
  ta.addEventListener('input', () => {
    ta.style.height = 'auto';
    ta.style.height = ta.scrollHeight + 'px';
  });
});

/* ========= AUTO-DISMISS FLASH ========= */
setTimeout(() => {
  document.querySelectorAll('.flash').forEach(f => {
    f.style.transition = 'opacity .3s';
    f.style.opacity = '0';
    setTimeout(() => f.remove(), 300);
  });
}, 4000);
