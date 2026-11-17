(function () {
  const sessionKey = "esg_demo_authenticated";
  const destinationKey = "esg_demo_destination";
  const loginUrl = new URL("login.html", window.location.href);
  const isLoginPage = window.location.pathname === loginUrl.pathname;

  if (!isLoginPage && sessionStorage.getItem(sessionKey) !== "1") {
    sessionStorage.setItem(destinationKey, `${window.location.pathname}${window.location.search}${window.location.hash}`);
    window.location.replace(loginUrl.href);
    return;
  }

  if (!isLoginPage) return;

  document.addEventListener("DOMContentLoaded", function () {
    if (sessionStorage.getItem(sessionKey) === "1") {
      window.location.replace("documents.html");
      return;
    }

    const form = document.getElementById("login-form");
    const error = document.getElementById("login-error");
    form.addEventListener("submit", async function (event) {
      event.preventDefault();
      const username = form.elements.username.value.trim();
      const password = form.elements.password.value;
      const apiBase = (
        (window.ESGApi && typeof window.ESGApi.platformBase === "function" ? window.ESGApi.platformBase() : null) ||
        localStorage.getItem("esg_platform_api_base") ||
        localStorage.getItem("esg_doc_api_base") ||
        "http://localhost:8001"
      ).replace(/\/$/, "");

      try {
        const resp = await fetch(apiBase + "/api/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username, password }),
        });

        if (resp.ok) {
          const data = await resp.json();
          if (data && data.access_token) {
            localStorage.setItem("esg_access_token", data.access_token);
            sessionStorage.setItem("esg_access_token", data.access_token);
            if (data.user) {
              sessionStorage.setItem("esg_user_role", data.user.role);
              sessionStorage.setItem("esg_user_name", data.user.full_name || data.user.username);
            }
            sessionStorage.setItem(sessionKey, "1");
            const destination = sessionStorage.getItem(destinationKey) || "documents.html";
            sessionStorage.removeItem(destinationKey);
            const target = new URL(destination, window.location.origin);
            const isTargetForbidden = target.pathname.endsWith("index.html") || target.pathname.endsWith("risks.html") || target.pathname.endsWith("insights.html") || target.pathname === "/" || target.pathname === "";
            window.location.replace(target.origin === window.location.origin && !isTargetForbidden ? target.href : "documents.html");
            return;
          }
        } else {
          const errData = await resp.json().catch(() => null);
          error.textContent = (errData && (errData.detail || errData.message)) || "Invalid credentials.";
          return;
        }
      } catch (_netErr) {
        // Fallback for offline or standalone demo mode
        if ((username === "admin" || username === "auditor" || username === "developer" || username === "viewer") && password === "esg2026") {
          sessionStorage.setItem(sessionKey, "1");
          sessionStorage.setItem("esg_user_role", username);
          const destination = sessionStorage.getItem(destinationKey) || "documents.html";
          sessionStorage.removeItem(destinationKey);
          const target = new URL(destination, window.location.origin);
          const isTargetForbidden = target.pathname.endsWith("index.html") || target.pathname.endsWith("risks.html") || target.pathname.endsWith("insights.html") || target.pathname === "/" || target.pathname === "";
          window.location.replace(target.origin === window.location.origin && !isTargetForbidden ? target.href : "documents.html");
          return;
        }
        error.textContent = "Username or password is incorrect.";
      }
    });
  });
})();