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

function isAdmin()       { return getUserRole() === 'admin'; }
function isOrganizer()   { var r = getUserRole(); return r === 'organizer'  || r === 'admin'; }
function isCantina()     { var r = getUserRole(); return r === 'cantina'    || r === 'admin'; }
function isSecretaria()  { var r = getUserRole(); return r === 'secretaria' || r === 'admin'; }

function requireAuth() {
  if (!isAuthenticated()) {
    window.location.href = 'login.html';
    return false;
  }
  return true;
}

function requireOrganizerAccess() {
  if (!requireAuth()) return false;
  var r = getUserRole();
  if (r === 'secretaria') {
    window.location.href = 'secretaria.html';
    return false;
  }
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

function requireAdminAccess() {
  if (!requireAuth()) return false;
  if (getUserRole() !== 'admin') {
    window.location.href = 'dashboard.html';
    return false;
  }
  return true;
}

function requireSecretariaAccess() {
  if (!requireAuth()) return false;
  if (!isSecretaria()) {
    window.location.href = 'dashboard.html';
    return false;
  }
  return true;
}

function redirectIfAuth() {
  if (!isAuthenticated()) return;
  var r = getUserRole();
  if (r === 'cantina') {
    window.location.href = 'cantina-select.html';
  } else if (r === 'secretaria') {
    window.location.href = 'secretaria.html';
  } else {
    window.location.href = 'dashboard.html';
  }
}

function logout() {
  clearAuth();
  window.location.href = 'login.html';
}

// Oculta automaticamente itens de navegação com data-role="admin" para não-admins
document.addEventListener('DOMContentLoaded', function() {
  if (!isAdmin()) {
    document.querySelectorAll('[data-role="admin"]').forEach(function(el) {
      el.style.display = 'none';
    });
  }
});
