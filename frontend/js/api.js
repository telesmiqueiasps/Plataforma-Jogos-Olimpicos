const API_BASE = 'https://sports-platform-api.onrender.com';

async function apiFetch(path, options = {}) {
  const token = localStorage.getItem('sp_token');
  const isForm = options.body instanceof URLSearchParams;
  const headers = {};
  if (!isForm) headers['Content-Type'] = 'application/json';
  if (token) headers['Authorization'] = `Bearer ${token}`;
  Object.assign(headers, options.headers || {});

  let res;
  try {
    res = await fetch(API_BASE + path, { ...options, headers });
  } catch (e) {
    throw new Error('Sem conexão com o servidor. Verifique sua internet.');
  }

  if (res.status === 401) {
    localStorage.removeItem('sp_token');
    localStorage.removeItem('sp_user');
    if (!window.location.pathname.endsWith('login.html')) {
      window.location.href = 'login.html';
    }
    throw new Error('Sessão expirada. Faça login novamente.');
  }

  if (!res.ok) {
    let detail = `Erro ${res.status}`;
    try {
      const err = await res.json();
      if (typeof err.detail === 'string') {
        detail = err.detail;
      } else if (Array.isArray(err.detail)) {
        detail = err.detail.map(d => d.msg || JSON.stringify(d)).join('; ');
      } else {
        detail = JSON.stringify(err.detail) || detail;
      }
    } catch {}
    throw new Error(detail);
  }

  if (res.status === 204) return null;
  return res.json();
}

// --- Auth ---
const AuthAPI = {
  async login(email, password) {
    const body = new URLSearchParams({ username: email, password });
    let res;
    try {
      res = await fetch(API_BASE + '/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body,
      });
    } catch {
      throw new Error('Sem conexão com o servidor.');
    }
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Credenciais inválidas');
    }
    return res.json();
  },
  register: (data) => apiFetch('/api/auth/register', { method: 'POST', body: JSON.stringify(data) }),
  me: () => apiFetch('/api/users/me'),
};

// --- Sports ---
const SportsAPI = {
  list: () => apiFetch('/api/sports/'),
  create: (data) => apiFetch('/api/sports/', { method: 'POST', body: JSON.stringify(data) }),
};

// --- Championships ---
const ChampAPI = {
  list: () => apiFetch('/api/championships/'),
  get: (id) => apiFetch(`/api/championships/${id}`),
  create: (data) => apiFetch('/api/championships/', { method: 'POST', body: JSON.stringify(data) }),
  update: (id, data) => apiFetch(`/api/championships/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  delete: (id) => apiFetch(`/api/championships/${id}`, { method: 'DELETE' }),
  // Equipes
  teams: (id) => apiFetch(`/api/championships/${id}/teams`),
  addTeam: (id, teamId) => apiFetch(`/api/championships/${id}/teams`, { method: 'POST', body: JSON.stringify({ team_id: teamId }) }),
  removeTeam: (id, teamId) => apiFetch(`/api/championships/${id}/teams/${teamId}`, { method: 'DELETE' }),
  // Configuração
  config: (id) => apiFetch(`/api/championships/${id}/config`),
  updateConfig: (id, data) => apiFetch(`/api/championships/${id}/config`, { method: 'PUT', body: JSON.stringify(data) }),
  // Jogos
  games: (id) => apiFetch(`/api/championships/${id}/games`),
  createGame: (id, data) => apiFetch(`/api/championships/${id}/games`, { method: 'POST', body: JSON.stringify(data) }),
  // Grupos
  groups: (id) => apiFetch(`/api/championships/${id}/groups`),
  drawGroups: (id, data) => apiFetch(`/api/championships/${id}/groups/draw`, { method: 'POST', body: JSON.stringify(data) }),
  generateGroupGames: (id, group) => apiFetch(`/api/championships/${id}/groups/${group}/games/generate`, { method: 'POST' }),
  // Classificação
  standings: (id, group, phase) => {
    const params = new URLSearchParams();
    if (group) params.append('group', group);
    if (phase) params.append('phase', phase);
    const qs = params.toString();
    return apiFetch(`/api/championships/${id}/standings${qs ? '?' + qs : ''}`);
  },
  // Mata-mata
  knockout: (id) => apiFetch(`/api/championships/${id}/knockout`),
  setupKnockout: (id, data) => apiFetch(`/api/championships/${id}/knockout/setup`, { method: 'POST', body: JSON.stringify(data) }),
  generateKnockout: (id) => apiFetch(`/api/championships/${id}/knockout/generate`, { method: 'POST' }),
  // Estatísticas
  stats: (id) => apiFetch(`/api/championships/${id}/stats`),
  // Mata-mata automático
  advanceKnockout: (id) => apiFetch(`/api/championships/${id}/knockout/advance`, { method: 'POST' }),
  champion: (id) => apiFetch(`/api/championships/${id}/champion`),
};

// --- Athletes ---
const AthletesAPI = {
  list: (params = {}) => {
    const qs = new URLSearchParams(
      Object.fromEntries(Object.entries(params).filter(([, v]) => v != null && v !== ''))
    ).toString();
    return apiFetch('/api/athletes/' + (qs ? '?' + qs : ''));
  },
  create: (data) => apiFetch('/api/athletes/', { method: 'POST', body: JSON.stringify(data) }),
  get: (id) => apiFetch(`/api/athletes/${id}`),
  update: (id, data) => apiFetch(`/api/athletes/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  delete: (id) => apiFetch(`/api/athletes/${id}`, { method: 'DELETE' }),
};

// --- Teams ---
const TeamsAPI = {
  list: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return apiFetch('/api/teams/' + (qs ? '?' + qs : ''));
  },
  get: (id) => apiFetch(`/api/teams/${id}`),
  create: (data) => apiFetch('/api/teams/', { method: 'POST', body: JSON.stringify(data) }),
  update: (id, data) => apiFetch(`/api/teams/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  delete: (id) => apiFetch(`/api/teams/${id}`, { method: 'DELETE' }),
  athletes: (teamId) => apiFetch(`/api/teams/${teamId}/athletes/`),
  createAthlete: (teamId, data) => apiFetch(`/api/teams/${teamId}/athletes/`, { method: 'POST', body: JSON.stringify(data) }),
};

// --- Games ---
const GamesAPI = {
  get: (id) => apiFetch(`/api/games/${id}`),
  update: (id, data) => apiFetch(`/api/games/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  delete: (id) => apiFetch(`/api/games/${id}`, { method: 'DELETE' }),
  result: (id, data) => apiFetch(`/api/games/${id}/result`, { method: 'PUT', body: JSON.stringify(data) }),
  setResult: (id, data) => apiFetch(`/api/games/${id}/result`, { method: 'PUT', body: JSON.stringify(data) }),
  events: (id) => apiFetch(`/api/games/${id}/events`),
  createEvent: (id, data) => apiFetch(`/api/games/${id}/events`, { method: 'POST', body: JSON.stringify(data) }),
  addEvent: (id, data) => apiFetch(`/api/games/${id}/events`, { method: 'POST', body: JSON.stringify(data) }),
};
