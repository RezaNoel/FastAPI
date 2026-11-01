/* Grove HTTP client. Tokens stay in the browser; the API remains the authority. */
const api = (() => {
  const base = "/api/v1";
  let access = sessionStorage.getItem("grove.access") || "";
  let refreshToken = localStorage.getItem("grove.refresh") || "";
  let refreshing = null;

  function setSession(pair) {
    access = pair.access_token;
    refreshToken = pair.refresh_token;
    sessionStorage.setItem("grove.access", access);
    localStorage.setItem("grove.refresh", refreshToken);
  }

  function clear() {
    access = "";
    refreshToken = "";
    sessionStorage.removeItem("grove.access");
    localStorage.removeItem("grove.refresh");
  }

  async function parse(response) {
    if (response.status === 204) return null;
    const text = await response.text();
    if (!text) return null;
    try {
      return JSON.parse(text);
    } catch {
      return { detail: text };
    }
  }

  function fail(response, data) {
    const error = new Error((data && data.detail) || "Request failed");
    error.status = response.status;
    error.payload = data;
    return error;
  }

  async function refresh() {
    if (!refreshToken) return false;
    if (!refreshing) {
      const token = refreshToken;
      refreshing = fetch(`${base}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: token }),
      })
        .then(async (response) => {
          const data = await parse(response);
          if (!response.ok) {
            clear();
            return false;
          }
          setSession(data);
          return true;
        })
        .catch(() => {
          clear();
          return false;
        })
        .finally(() => {
          refreshing = null;
        });
    }
    return refreshing;
  }

  async function raw(path, options = {}, retry = true) {
    const headers = new Headers(options.headers || {});
    if (access && !headers.has("Authorization") && !headers.has("X-API-Key")) {
      headers.set("Authorization", `Bearer ${access}`);
    }
    let body = options.body;
    if (options.json !== undefined) {
      headers.set("Content-Type", "application/json");
      body = JSON.stringify(options.json);
    }
    const response = await fetch(base + path, {
      method: options.method || "GET",
      headers,
      body,
    });
    if (response.status === 401 && retry && refreshToken && !path.startsWith("/auth/")) {
      const ok = await refresh();
      if (ok) return raw(path, options, false);
    }
    const data = await parse(response);
    if (!response.ok) throw fail(response, data);
    return data;
  }

  return {
    get: (path) => raw(path),
    post: (path, json, headers) => raw(path, { method: "POST", json, headers }),
    patch: (path, json, headers) => raw(path, { method: "PATCH", json, headers }),
    del: (path) => raw(path, { method: "DELETE" }),
    upload(path, formData) {
      return raw(path, { method: "POST", body: formData });
    },
    token: () => access,
    clear,
    async login(email, password) {
      const body = new URLSearchParams();
      body.set("username", email);
      body.set("password", password);
      const response = await fetch(`${base}/auth/token`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body,
      });
      const data = await parse(response);
      if (!response.ok) throw fail(response, data);
      setSession(data);
      return raw("/auth/me");
    },
    async logout() {
      if (refreshToken) {
        await raw("/auth/logout", { method: "POST", json: { refresh_token: refreshToken } }, false).catch(
          () => {},
        );
      }
      clear();
    },
    async restore() {
      if (!access && refreshToken) {
        const ok = await refresh();
        if (!ok) return null;
      }
      if (!access) return null;
      try {
        return await raw("/auth/me");
      } catch {
        clear();
        return null;
      }
    },
  };
})();
