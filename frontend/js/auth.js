const TOKEN_KEY = 'sp_token';
const USER_KEY = 'sp_user';

function getToken() { return localStorage.getItem(TOKEN_KEY); }

function getUser() {
  try { return JSON.parse(localStorage.getItem(USER_KEY) || 'null'); } catch { return null; }
}

function setAuth(token, user) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
  if (user?.name) localStorage.setItem('sp_user_name', user.name);
}

function clearAuth() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  localStorage.removeItem('sp_user_name');
}

function isAuthenticated() { return !!getToken(); }

function requireAuth() {
  if (!isAuthenticated()) {
    window.location.href = 'login.html';
    return false;
  }
  return true;
}

function redirectIfAuth() {
  if (isAuthenticated()) window.location.href = 'dashboard.html';
}

function logout() {
  clearAuth();
  window.location.href = 'login.html';
}
