import { login, register, saveToken, isLoggedIn } from "./api.js";

// Redireciona usuário já logado
if (isLoggedIn() && window.location.pathname.includes("login")) {
  window.location.href = "/index.html";
}

// ---------- Formulário de login ----------

const loginForm = document.getElementById("login-form");
if (loginForm) {
  loginForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const email = document.getElementById("email").value.trim();
    const password = document.getElementById("password").value;
    const alertEl = document.getElementById("alert");
    const btn = loginForm.querySelector("button[type=submit]");

    alertEl.className = "alert";
    alertEl.textContent = "";
    btn.disabled = true;
    btn.textContent = "Entrando...";

    try {
      const data = await login(email, password);
      saveToken(data.access_token);
      window.location.href = "/index.html";
    } catch (err) {
      alertEl.className = "alert alert-error";
      alertEl.textContent = err.message;
    } finally {
      btn.disabled = false;
      btn.textContent = "Entrar";
    }
  });
}

// ---------- Formulário de registro ----------

const registerForm = document.getElementById("register-form");
if (registerForm) {
  registerForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = document.getElementById("name").value.trim();
    const email = document.getElementById("email").value.trim();
    const password = document.getElementById("password").value;
    const alertEl = document.getElementById("alert");
    const btn = registerForm.querySelector("button[type=submit]");

    alertEl.className = "alert";
    alertEl.textContent = "";
    btn.disabled = true;
    btn.textContent = "Cadastrando...";

    try {
      await register(name, email, password);
      alertEl.className = "alert alert-success";
      alertEl.textContent = "Conta criada! Redirecionando para o login...";
      setTimeout(() => (window.location.href = "/login.html"), 1500);
    } catch (err) {
      alertEl.className = "alert alert-error";
      alertEl.textContent = err.message;
    } finally {
      btn.disabled = false;
      btn.textContent = "Criar conta";
    }
  });
}
