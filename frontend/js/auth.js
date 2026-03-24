const TOKEN_KEY = 'sp_token';
const USER_KEY = 'sp_user';

function getToken() { return localStorage.getItem(TOKEN_KEY); }

function getUser() {
  try { return JSON.parse(localStorage.getItem(USER_KEY) || 'null'); } catch { return null; }
}

function setAuth(token, user) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
  if (user && user.name) localStorage.setItem('sp_user_name', user.name);
  if (user && user.role) localStorage.setItem('sp_role', user.role);
}

function clearAuth() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  localStorage.removeItem('sp_user_name');
  localStorage.removeItem('sp_role');
}

function isAuthenticated() { return !!getToken(); }

function getUserRole() {
  return localStorage.getItem('sp_role') || (getUser() || {}).role || 'organizer';
}

function isAdmin()     { return getUserRole() === 'admin'; }
function isOrganizer() { var r = getUserRole(); return r === 'organizer' || r === 'admin'; }
function isCantina()   { var r = getUserRole(); return r === 'cantina'   || r === 'admin'; }

function requireAuth() {
  if (!isAuthenticated()) {
    window.location.href = 'login.html';
    return false;
  }
  return true;
}

function requireOrganizerAccess() {
  if (!requireAuth()) return false;
  if (!isOrganizer()) {
    window.location.href = 'cantina.html';
    return false;
  }
  return true;
}

function requireCantinaAccess() {
  if (!requireAuth()) return false;
  if (!isCantina()) {
    window.location.href = 'dashboard.html';
    return false;
  }
  return true;
}

function redirectIfAuth() {
  if (!isAuthenticated()) return;
  if (getUserRole() === 'cantina') {
    window.location.href = 'cantina.html';
  } else {
    window.location.href = 'dashboard.html';
  }
}

function logout() {
  clearAuth();
  window.location.href = 'login.html';
}
