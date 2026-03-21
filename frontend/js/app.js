// --- Toast notifications ---
function showToast(msg, type = 'success', duration = 3500) {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    document.body.appendChild(container);
  }
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = msg;
  container.appendChild(toast);
  requestAnimationFrame(() => { requestAnimationFrame(() => toast.classList.add('show')); });
  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => toast.remove(), 350);
  }, duration);
}

// --- Button loading state ---
function btnLoading(btn, loading, text = 'Salvando...') {
  if (loading) {
    btn.dataset.orig = btn.innerHTML;
    btn.innerHTML = `<span class="spinner"></span> ${text}`;
    btn.disabled = true;
  } else {
    btn.innerHTML = btn.dataset.orig || btn.textContent;
    btn.disabled = false;
  }
}

// --- Modal helpers ---
function openModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.add('open');
}
function closeModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.remove('open');
}

// Close modal on overlay click
document.addEventListener('click', (e) => {
  if (e.target.classList.contains('modal-overlay')) {
    e.target.classList.remove('open');
  }
});

// --- Sidebar ---
function initSidebar() {
  const toggle = document.getElementById('sidebar-toggle');
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebar-overlay');
  if (!toggle || !sidebar) return;
  toggle.addEventListener('click', () => {
    sidebar.classList.toggle('open');
    overlay?.classList.toggle('show');
  });
  overlay?.addEventListener('click', () => {
    sidebar.classList.remove('open');
    overlay?.classList.remove('show');
  });
}

// Highlight active nav item
function setActiveNav() {
  const page = window.location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('.nav-item').forEach(a => {
    const href = a.getAttribute('href') || '';
    a.classList.toggle('active', href === page || href.endsWith(page));
  });
}

// --- User info in sidebar ---
function loadUserInfo() {
  const user = getUser();
  if (!user) return;
  const nameEl = document.getElementById('user-name');
  const roleEl = document.getElementById('user-role');
  const avatarEl = document.getElementById('user-avatar');
  if (nameEl) nameEl.textContent = user.name || user.email || 'Usuário';
  if (roleEl) roleEl.textContent = user.role === 'admin' ? 'Administrador' : user.role === 'organizer' ? 'Organizador' : 'Usuário';
  if (avatarEl) avatarEl.textContent = (user.name || user.email || 'U')[0].toUpperCase();
}

// --- Formatters ---
function fmtDate(d) {
  if (!d) return '—';
  return new Date(d).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric' });
}
function fmtDatetime(d) {
  if (!d) return '—';
  return new Date(d).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

// --- Status badge ---
function statusBadge(status) {
  const map = {
    draft: '<span class="badge badge-draft">Rascunho</span>',
    active: '<span class="badge badge-active">Ativo</span>',
    finished: '<span class="badge badge-finished">Encerrado</span>',
    scheduled: '<span class="badge badge-info">Agendado</span>',
    live: '<span class="badge badge-live">Ao Vivo</span>',
    completed: '<span class="badge badge-finished">Concluído</span>',
    round_robin: '<span class="badge badge-info">Pontos Corridos</span>',
    elimination: '<span class="badge badge-draft">Eliminatório</span>',
    hybrid: '<span class="badge badge-live">Híbrido</span>',
  };
  return map[status] || `<span class="badge">${status || '—'}</span>`;
}

// --- Empty state ---
function emptyState(message, icon = '📭') {
  return `<div class="empty-state"><span class="empty-icon">${icon}</span><p>${message}</p></div>`;
}

// --- Pagination ---
function paginate(allItems, page, perPage = 10) {
  const total = allItems.length;
  const pages = Math.ceil(total / perPage) || 1;
  const current = Math.max(1, Math.min(page, pages));
  return {
    items: allItems.slice((current - 1) * perPage, current * perPage),
    total, pages, current,
  };
}
function renderPagination(containerId, state, onPage) {
  const el = document.getElementById(containerId);
  if (!el) return;
  if (state.pages <= 1) { el.innerHTML = ''; return; }
  let html = '<div class="pagination">';
  html += `<button class="btn btn-sm btn-secondary" ${state.current === 1 ? 'disabled' : ''} data-page="${state.current - 1}">&#8249;</button>`;
  for (let i = 1; i <= state.pages; i++) {
    html += `<button class="btn btn-sm btn-secondary ${i === state.current ? 'active' : ''}" data-page="${i}">${i}</button>`;
  }
  html += `<button class="btn btn-sm btn-secondary" ${state.current === state.pages ? 'disabled' : ''} data-page="${state.current + 1}">&#8250;</button>`;
  html += '</div>';
  el.innerHTML = html;
  el.querySelectorAll('[data-page]').forEach(btn => {
    btn.addEventListener('click', () => onPage(Number(btn.dataset.page)));
  });
}

// --- Google Drive image URL converter ---
function driveImageUrl(url) {
  if (!url) return null;
  const m1 = url.match(/\/d\/([a-zA-Z0-9_-]+)/);
  if (m1) return `https://lh3.googleusercontent.com/d/${m1[1]}`;
  const m2 = url.match(/[?&]id=([a-zA-Z0-9_-]+)/);
  if (m2) return `https://lh3.googleusercontent.com/d/${m2[1]}`;
  const m3 = url.match(/uc\?.*id=([a-zA-Z0-9_-]+)/);
  if (m3) return `https://lh3.googleusercontent.com/d/${m3[1]}`;
  return url;
}

function teamAvatar(team, size = 36) {
  const url = driveImageUrl(team?.logo_url);
  const initials = (team?.name || '?').split(' ').map(w => w[0]).join('').substring(0, 2).toUpperCase();
  const colors = ['#6c63ff', '#00d4aa', '#ff6b6b', '#ffa500', '#4ecdc4', '#45b7d1'];
  const color = colors[(team?.id || 0) % colors.length];
  if (url) {
    return `<img src="${url}" style="width:${size}px;height:${size}px;border-radius:50%;object-fit:cover;flex-shrink:0;" onerror="this.outerHTML='<div style=width:${size}px;height:${size}px;border-radius:50%;background:${color};display:flex;align-items:center;justify-content:center;font-size:${Math.round(size * 0.35)}px;font-weight:700;color:#fff;flex-shrink:0>${initials}</div>'" alt="${team?.name || ''}">`;
  }
  return `<div style="width:${size}px;height:${size}px;border-radius:50%;background:${color};display:flex;align-items:center;justify-content:center;font-size:${Math.round(size * 0.35)}px;font-weight:700;color:#fff;flex-shrink:0;">${initials}</div>`;
}

function athleteAvatar(athlete, size = 36) {
  const url = driveImageUrl(athlete?.photo_url);
  const initials = (athlete?.name || '?').split(' ').map(w => w[0]).join('').substring(0, 2).toUpperCase();
  const colors = ['#6c63ff', '#00d4aa', '#ff6b6b', '#ffa500', '#4ecdc4'];
  const color = colors[(athlete?.id || 0) % colors.length];
  if (url) {
    return `<img src="${url}" style="width:${size}px;height:${size}px;border-radius:50%;object-fit:cover;flex-shrink:0;" onerror="this.outerHTML='<div style=width:${size}px;height:${size}px;border-radius:50%;background:${color};display:flex;align-items:center;justify-content:center;font-size:${Math.round(size * 0.35)}px;font-weight:700;color:#fff;flex-shrink:0>${initials}</div>'" alt="${athlete?.name || ''}">`;
  }
  return `<div style="width:${size}px;height:${size}px;border-radius:50%;background:${color};display:flex;align-items:center;justify-content:center;font-size:${Math.round(size * 0.35)}px;font-weight:700;color:#fff;flex-shrink:0;">${initials}</div>`;
}

// --- Sport icon ---
function sportIcon(slug, size = 20) {
  const map = {
    'futsal':     'img/futsal.png',
    'volleyball': 'img/volei.png',
    'basketball': 'img/basquete.png',
    'running':    'img/corrida.png',
    'domino':     'img/domino.png',
    'dama':       'img/dama.png',
    'xadrez':     'img/xadrez.png',
  };
  const src = map[slug];
  if (!src) return '';
  return `<img src="${src}" style="width:${size}px;height:${size}px;object-fit:contain;vertical-align:middle;margin-right:4px;" alt="${slug}">`;
}

// --- URL params ---
function getParam(key) { return new URLSearchParams(window.location.search).get(key); }

// --- Init ---
document.addEventListener('DOMContentLoaded', () => {
  initSidebar();
  setActiveNav();
  loadUserInfo();
  document.getElementById('logout-btn')?.addEventListener('click', logout);
});
