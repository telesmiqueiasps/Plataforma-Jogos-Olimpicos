/**
 * Módulo de comunicação com a API do backend.
 * Centraliza todas as chamadas HTTP e gerencia o token JWT.
 */

const API_BASE = "http://localhost:8000/api";

// ---------- Token helpers ----------

export function saveToken(token) {
  localStorage.setItem("access_token", token);
}

export function getToken() {
  return localStorage.getItem("access_token");
}

export function removeToken() {
  localStorage.removeItem("access_token");
}

export function isLoggedIn() {
  return !!getToken();
}

// ---------- Fetch wrapper ----------

async function request(method, path, body = null, auth = true) {
  const headers = { "Content-Type": "application/json" };

  if (auth) {
    const token = getToken();
    if (!token) throw new Error("Não autenticado");
    headers["Authorization"] = `Bearer ${token}`;
  }

  const options = { method, headers };
  if (body) options.body = JSON.stringify(body);

  const res = await fetch(`${API_BASE}${path}`, options);

  if (res.status === 401) {
    removeToken();
    window.location.href = "/login.html";
    return;
  }

  const data = res.status === 204 ? null : await res.json();

  if (!res.ok) {
    const msg = data?.detail || `Erro ${res.status}`;
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }

  return data;
}

// ---------- Auth ----------

export async function login(email, password) {
  const form = new URLSearchParams();
  form.append("username", email);
  form.append("password", password);

  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: form.toString(),
  });

  const data = await res.json();
  if (!res.ok) throw new Error(data?.detail || "Erro ao fazer login");
  return data;
}

export async function register(name, email, password) {
  return request("POST", "/auth/register", { name, email, password }, false);
}

// ---------- Usuários ----------

export async function getMe() {
  return request("GET", "/users/me");
}

// ---------- Modalidades ----------

export async function getSports() {
  return request("GET", "/sports", null, false);
}

export async function createSport(data) {
  return request("POST", "/sports", data);
}

export async function deleteSport(id) {
  return request("DELETE", `/sports/${id}`);
}
