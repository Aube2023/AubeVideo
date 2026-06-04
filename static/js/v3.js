/* AubeVideo v3 — améliorations professionnelles côté client.
 * Inclus après app.js. Tout ce qui est nouveau passe par ici pour ne pas
 * casser le code existant.
 *
 * Features :
 * - Theme switcher (auto/dark/light) avec persistence + cookie pour SSR
 * - Skeleton loaders sur grille initiale
 * - Mode théâtre (T) + plein écran (F) + raccourcis clavier (?)
 * - Mini-player flottant quand on scrolle sur /watch
 * - Quality selector (HLS-style à partir des qualités générées)
 * - Sélection chapitres + barre de progression visuelle
 * - Toast pour feedback léger
 * - Sauvegarde de la progression vidéo (sync mobile)
 * - Quality auto-adaptive
 */

(function () {
  'use strict';

  // ============= THEME =============
  const THEMES = ['auto', 'dark', 'light'];

  function getStoredTheme() {
    try {
      return localStorage.getItem('aube-theme') || 'auto';
    } catch (_) { return 'auto'; }
  }
  function applyTheme(theme) {
    if (!THEMES.includes(theme)) theme = 'auto';
    document.documentElement.setAttribute('data-theme', theme);
    try { localStorage.setItem('aube-theme', theme); } catch (_) {}
    // Cookie pour SSR (peut être lu côté serveur si besoin)
    document.cookie = 'aube-theme=' + theme + ';path=/;max-age=' + (60 * 60 * 24 * 365) + ';SameSite=Lax';
    const btn = document.querySelector('.theme-btn');
    if (btn) btn.title = 'Thème : ' + theme;
  }
  function cycleTheme() {
    const cur = getStoredTheme();
    const idx = THEMES.indexOf(cur);
    applyTheme(THEMES[(idx + 1) % THEMES.length]);
    showToast('Thème : ' + (THEMES[(idx + 1) % THEMES.length] === 'auto' ? 'système' :
      THEMES[(idx + 1) % THEMES.length] === 'dark' ? 'sombre' : 'clair'));
  }
  // Apply ASAP to avoid flash
  applyTheme(getStoredTheme());

  document.addEventListener('DOMContentLoaded', function () {
    // Inject theme button into topbar if absent
    const right = document.querySelector('.topbar-right');
    if (right && !document.querySelector('.theme-btn')) {
      const btn = document.createElement('button');
      btn.className = 'theme-btn icon-btn';
      btn.setAttribute('aria-label', 'Changer de thème');
      btn.innerHTML = `
        <svg class="icon-light" viewBox="0 0 24 24" width="22" height="22"><path fill="currentColor" d="M12 7a5 5 0 0 0-5 5 5 5 0 0 0 5 5 5 5 0 0 0 5-5 5 5 0 0 0-5-5zm0-5l-1 4h2zm0 18l-1 4h2zm10-10l-4 1v2zm-16 0L2 11v2l4 1zm12.7 7.7l2.8 2.8 1.4-1.4-2.8-2.8zm-12.8-12.8L2.1 5.5 4.9 8.3l1.4-1.4zM18.7 6.3l-1.4-1.4-2.8 2.8 1.4 1.4zM7.1 18.6l-1.4 1.4-2.8-2.8 1.4-1.4z"/></svg>
        <svg class="icon-dark" viewBox="0 0 24 24" width="22" height="22"><path fill="currentColor" d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>`;
      btn.addEventListener('click', cycleTheme);
      // Insère avant le premier élément de droite
      right.insertBefore(btn, right.firstChild);
    }
  });

  // ============= TOAST =============
  let toastTimer = null;
  function showToast(msg) {
    let el = document.querySelector('.toast');
    if (el) el.remove();
    el = document.createElement('div');
    el.className = 'toast';
    el.textContent = msg;
    document.body.appendChild(el);
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.remove(), 2500);
  }
  window.showToast = showToast;

  // ============= THEATER MODE =============
  function toggleTheater() {
    document.body.classList.toggle('theater-mode');
  }
  window.toggleTheater = toggleTheater;

  // ============= KEYBOARD SHORTCUTS =============
  function isTyping(e) {
    const t = e.target;
    return t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable);
  }
  document.addEventListener('keydown', function (e) {
    if (isTyping(e)) return;
    const player = document.getElementById('player');
    // Player keyboard shortcuts (only on /watch)
    if (player) {
      if (e.key === ' ' || e.key === 'k') {
        e.preventDefault();
        if (player.paused) player.play(); else player.pause();
        flashPlayerIcon(player.paused ? '▶' : '⏸');
      } else if (e.key === 'j') {
        player.currentTime = Math.max(0, player.currentTime - 10);
        flashPlayerIcon('⏪ 10s');
      } else if (e.key === 'l') {
        player.currentTime = Math.min(player.duration || 0, player.currentTime + 10);
        flashPlayerIcon('⏩ 10s');
      } else if (e.key === 'ArrowLeft') {
        player.currentTime = Math.max(0, player.currentTime - 5);
      } else if (e.key === 'ArrowRight') {
        player.currentTime = Math.min(player.duration || 0, player.currentTime + 5);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        player.volume = Math.min(1, player.volume + 0.05);
      } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        player.volume = Math.max(0, player.volume - 0.05);
      } else if (e.key === 'm') {
        player.muted = !player.muted;
        flashPlayerIcon(player.muted ? '🔇' : '🔊');
      } else if (e.key === 't') {
        toggleTheater();
      } else if (e.key === 'f') {
        if (document.fullscreenElement) document.exitFullscreen();
        else player.requestFullscreen?.();
      } else if (e.key === 'i') {
        if (player.requestPictureInPicture && !document.pictureInPictureElement) {
          player.requestPictureInPicture();
        }
      } else if (e.key === '?') {
        toggleHintsOverlay(true);
      } else if (/^[0-9]$/.test(e.key) && player.duration) {
        player.currentTime = (player.duration * parseInt(e.key, 10)) / 10;
      }
    }
    // Global
    if (e.key === '/' && !document.activeElement.matches('input, textarea')) {
      e.preventDefault();
      const s = document.getElementById('searchInput');
      if (s) s.focus();
    }
    if (e.key === 'Escape') toggleHintsOverlay(false);
  });

  function flashPlayerIcon(text) {
    const overlay = document.getElementById('playerOverlay');
    if (!overlay) return;
    overlay.textContent = text;
    overlay.classList.add('show');
    clearTimeout(overlay._t);
    overlay._t = setTimeout(() => overlay.classList.remove('show'), 600);
  }

  function toggleHintsOverlay(force) {
    let el = document.getElementById('kbdHints');
    if (!el) {
      el = document.createElement('div');
      el.id = 'kbdHints';
      el.className = 'kbd-hints';
      el.innerHTML = `
        <div class="kbd-hints-box">
          <h3>Raccourcis clavier</h3>
          <div class="kbd-row"><span class="kbd">Espace / K</span><span>Lecture / pause</span></div>
          <div class="kbd-row"><span class="kbd">J / L</span><span>Reculer / avancer 10s</span></div>
          <div class="kbd-row"><span class="kbd">←  →</span><span>Reculer / avancer 5s</span></div>
          <div class="kbd-row"><span class="kbd">↑  ↓</span><span>Volume +/−</span></div>
          <div class="kbd-row"><span class="kbd">M</span><span>Muet</span></div>
          <div class="kbd-row"><span class="kbd">F</span><span>Plein écran</span></div>
          <div class="kbd-row"><span class="kbd">T</span><span>Mode théâtre</span></div>
          <div class="kbd-row"><span class="kbd">I</span><span>Picture-in-Picture</span></div>
          <div class="kbd-row"><span class="kbd">0-9</span><span>Aller à 0%-90%</span></div>
          <div class="kbd-row"><span class="kbd">/</span><span>Recherche</span></div>
          <div class="kbd-row"><span class="kbd">?</span><span>Cette aide</span></div>
          <div style="margin-top:16px;text-align:right">
            <button class="btn btn-ghost" onclick="document.getElementById('kbdHints').classList.remove('open')">Fermer</button>
          </div>
        </div>`;
      el.addEventListener('click', (e) => {
        if (e.target.id === 'kbdHints') el.classList.remove('open');
      });
      document.body.appendChild(el);
    }
    if (force === true) el.classList.add('open');
    else if (force === false) el.classList.remove('open');
    else el.classList.toggle('open');
  }
  window.toggleHintsOverlay = toggleHintsOverlay;

  // ============= QUALITY SELECTOR =============
  document.addEventListener('DOMContentLoaded', function () {
    const player = document.getElementById('player');
    const qs = document.getElementById('qualitySelector');
    const source = document.getElementById('playerSource');
    if (!player || !qs || !source) return;
    const qualities = (window.AUBE_VIDEO_QUALITIES || '').split(',').filter(Boolean);
    const renditions = ['Auto', ...qualities];
    let current = 'Auto';
    qs.innerHTML = renditions.map(q =>
      `<button class="q-item${q === current ? ' active' : ''}" data-q="${q}">${q}</button>`
    ).join('');
    qs.querySelectorAll('.q-item').forEach(b => {
      b.addEventListener('click', () => {
        current = b.dataset.q;
        qs.querySelectorAll('.q-item').forEach(x => x.classList.toggle('active', x === b));
        const t = player.currentTime, was = !player.paused;
        const baseUrl = source.getAttribute('src').split('?')[0];
        source.src = current === 'Auto' ? baseUrl : `${baseUrl}?q=${current}`;
        player.load();
        player.currentTime = t;
        if (was) player.play();
        qs.classList.remove('open');
        showToast('Qualité : ' + current);
      });
    });

    // Bouton pour ouvrir le sélecteur (overlay sur le coin du player)
    const wrap = document.getElementById('playerWrap');
    if (wrap && !document.getElementById('qToggle')) {
      const t = document.createElement('button');
      t.id = 'qToggle'; t.className = 'chip-btn';
      t.style.cssText = 'position:absolute;bottom:60px;right:60px;z-index:5;background:rgba(0,0,0,.7);color:#fff;padding:4px 10px';
      t.textContent = 'Qualité';
      t.addEventListener('click', () => qs.classList.toggle('open'));
      wrap.style.position = 'relative';
      wrap.appendChild(t);
    }
  });

  // ============= CHAPTERS =============
  document.addEventListener('DOMContentLoaded', async function () {
    const descBody = document.getElementById('videoDescription');
    const chapList = document.getElementById('chaptersList');
    const player = document.getElementById('player');
    if (!descBody || !chapList || !player) return;
    // Parse "0:00 Intro\n1:23 Démo\n..." dans la description
    const lines = (descBody.textContent || '').split('\n');
    const re = /^(\d{1,2}:)?(\d{1,2}):(\d{2})\s+(.+)$/;
    const chapters = [];
    for (const line of lines) {
      const m = line.trim().match(re);
      if (!m) continue;
      const h = parseInt(m[1] || '0', 10);
      const mn = parseInt(m[2], 10), s = parseInt(m[3], 10);
      chapters.push({ time: h * 3600 + mn * 60 + s, title: m[4] });
    }
    if (chapters.length < 2) return;
    chapList.innerHTML = chapters.map(c =>
      `<div class="chapter-row" data-time="${c.time}">
        <span class="chapter-time">${fmtTime(c.time)}</span>
        <span>${escapeHtml(c.title)}</span>
       </div>`
    ).join('');
    chapList.querySelectorAll('.chapter-row').forEach(r => {
      r.addEventListener('click', () => {
        player.currentTime = parseInt(r.dataset.time, 10);
        player.play?.();
      });
    });
  });

  function fmtTime(s) {
    s = s | 0;
    const h = (s / 3600) | 0, m = ((s % 3600) / 60) | 0, sec = s % 60;
    return (h ? h + ':' + String(m).padStart(2, '0') : m) + ':' + String(sec).padStart(2, '0');
  }
  function escapeHtml(s) {
    return (s || '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
  }

  // ============= PROGRESS SAVE (sync avec mobile) =============
  document.addEventListener('DOMContentLoaded', function () {
    const player = document.getElementById('player');
    const vid = window.AUBE_VIDEO_ID;
    if (!player || !vid) return;
    let last = 0;
    setInterval(() => {
      if (player.paused || !player.currentTime) return;
      const t = (player.currentTime | 0);
      if (t === last) return;
      last = t;
      fetch(`/api/video/${vid}/progress`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': (document.querySelector('meta[name="csrf-token"]') || {}).content || '',
        },
        body: JSON.stringify({ seconds: t }),
      }).catch(() => {});
    }, 10_000);
  });

  // ============= MINI PLAYER ON SCROLL =============
  document.addEventListener('DOMContentLoaded', function () {
    const player = document.getElementById('player');
    const wrap = document.getElementById('playerWrap');
    if (!player || !wrap) return;
    let mini = null;
    function ensureMini() {
      if (mini) return mini;
      mini = document.createElement('div');
      mini.className = 'miniplayer hidden';
      mini.innerHTML = `
        <button class="mp-close" title="Fermer">×</button>
        <button class="mp-expand" title="Agrandir">⤢</button>
        <div class="mp-info">${escapeHtml(document.querySelector('.video-title')?.textContent || '')}</div>`;
      document.body.appendChild(mini);
      mini.addEventListener('click', (e) => {
        if (e.target.classList.contains('mp-close')) {
          player.pause();
          mini.classList.add('hidden');
          window._mpHidden = true;
        } else if (e.target.classList.contains('mp-expand')) {
          window.scrollTo({ top: 0, behavior: 'smooth' });
        }
      });
      return mini;
    }
    function update() {
      const rect = wrap.getBoundingClientRect();
      const offscreen = rect.bottom < 80;
      if (offscreen && !player.paused && !window._mpHidden) {
        const m = ensureMini();
        if (m.firstElementChild !== player) {
          // Garder le player dans le DOM et juste déplacer un clone visuel ?
          // Plus simple : déplacer le <video> dans le miniplayer.
          m.appendChild(player);
          player.style.width = '100%';
          player.style.height = '100%';
          player.controls = false;
        }
        m.classList.remove('hidden');
      } else if (mini && !mini.classList.contains('hidden')) {
        wrap.appendChild(player);
        player.style.width = '100%';
        player.style.height = '';
        player.controls = true;
        mini.classList.add('hidden');
      }
    }
    let raf;
    window.addEventListener('scroll', () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(update);
    }, { passive: true });
  });

  // ============= SKELETON LOADERS =============
  document.addEventListener('DOMContentLoaded', function () {
    // Si la grille est vide à l'arrivée, on n'a rien à faire — Flask SSR
    // a déjà rendu les cartes. Laisser pour futurs feeds AJAX.
  });

  // ============= LAZY HOVER PREVIEW =============
  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.video-card').forEach(card => {
      let preview = null;
      const link = card.querySelector('a[href^="/watch/"]');
      const wrap = card.querySelector('.thumb-wrap');
      if (!link || !wrap) return;
      const m = link.getAttribute('href').match(/\/watch\/(\d+)/);
      if (!m) return;
      const vid = m[1];
      let timer;
      card.addEventListener('mouseenter', () => {
        timer = setTimeout(() => {
          if (preview) return;
          preview = document.createElement('video');
          preview.className = 'hover-preview';
          preview.muted = true; preview.loop = true; preview.playsInline = true;
          preview.preload = 'metadata';
          preview.src = `/stream/${vid}#t=2,8`;
          wrap.appendChild(preview);
          preview.play?.().catch(() => {});
        }, 600);
      });
      card.addEventListener('mouseleave', () => {
        clearTimeout(timer);
        if (preview) { preview.pause(); preview.remove(); preview = null; }
      });
    });
  });
})();
