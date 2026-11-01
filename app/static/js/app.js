/* Grove floor. The API is the source of truth; this file only renders it. */
(function () {
  const CATEGORIES = [
    ["citrus", "Citrus"],
    ["berry", "Berry"],
    ["tropical", "Tropical"],
    ["stone", "Stone fruit"],
    ["pome", "Pome"],
    ["melon", "Melon"],
    ["other", "Other"],
  ];
  const PUBLIC = new Set(["landing", "login"]);
  const NAV = [
    ["floor", "Floor"],
    ["catalog", "Catalog"],
    ["stock", "Stock"],
    ["orders", "Orders"],
    ["growers", "Growers"],
    ["wire", "Wire"],
    ["house", "House"],
  ];

  const state = {
    user: null,
    route: { name: "landing", parts: [] },
    loading: false,
    error: "",
    data: {},
    modal: null,
    authMode: "login",
    filters: { q: "", category: "", seasonal: "", sort: "name" },
    socket: null,
  };

  const $ = (sel) => document.querySelector(sel);

  function esc(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function money(value) {
    return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(Number(value || 0));
  }

  function kg(value) {
    return `${Number(value || 0).toLocaleString("en-US", { maximumFractionDigits: 3 })} kg`;
  }

  function when(value) {
    if (!value) return "";
    return new Date(value).toLocaleString("en-GB", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function label(value) {
    const found = CATEGORIES.find(([key]) => key === value);
    if (found) return found[1];
    return value ? value.charAt(0).toUpperCase() + value.slice(1) : "";
  }

  function can(scope) {
    return Boolean(state.user && state.user.scopes && state.user.scopes.includes(scope));
  }

  function mark() {
    return `<svg class="brand-mark" viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="8" fill="currentColor"></rect><path d="M16 5.5c1.8 5.2-1.6 7.4-1.6 12.2 3.4-3.4 7-3.6 8.8-2.2-5.2 7-14 7.2-14.6.4 1.6-3.6 5-5.4 7.4-10.4z" fill="#f4f0e6"></path></svg>`;
  }

  function parseRoute() {
    const raw = (location.hash || "#/").replace(/^#/, "");
    const path = raw.split("?")[0];
    const parts = path.split("/").filter(Boolean);
    return { name: parts[0] || "landing", parts };
  }

  function toast(message, kind) {
    const node = document.createElement("div");
    node.className = `toast ${kind || "ok"}`;
    node.textContent = message;
    $("#toasts").appendChild(node);
    setTimeout(() => node.remove(), 3400);
  }

  function pill(status) {
    return `<span class="pill ${esc(status)}">${esc(label(status))}</span>`;
  }

  function options(pairs, selected) {
    return pairs
      .map(([value, text]) => `<option value="${esc(value)}" ${value === selected ? "selected" : ""}>${esc(text)}</option>`)
      .join("");
  }

  function fruitChoices(selected) {
    const items = (state.data.catalog && state.data.catalog.items) || [];
    return items
      .map(
        (fruit) =>
          `<option value="${esc(fruit.id)}" ${fruit.id === selected ? "selected" : ""}>${esc(fruit.name)} · ${esc(fruit.sku)} · ${esc(kg(fruit.quantity_on_hand))}</option>`,
      )
      .join("");
  }

  function supplierChoices(selected) {
    const items = (state.data.suppliers && state.data.suppliers.items) || [];
    const head = `<option value="">No grower</option>`;
    return (
      head +
      items
        .map(
          (row) =>
            `<option value="${esc(row.id)}" ${row.id === selected ? "selected" : ""}>${esc(row.name)}</option>`,
        )
        .join("")
    );
  }

  function viewLanding() {
    const items = (state.data.highlights && state.data.highlights.items) || [];
    const rows = items.length
      ? items
          .map(
            (fruit) => `<div class="board-row">
              <div><strong>${esc(fruit.name)}</strong><div class="board-meta">${esc(fruit.origin)} · ${esc(label(fruit.category))}</div></div>
              <div class="board-price">${esc(money(fruit.price_per_kg))}</div>
            </div>`,
          )
          .join("")
      : `<p class="board-note">${state.loading ? "Reading the board…" : "The board is empty."}</p>`;
    return `<main class="landing">
      <header class="topbar">
        <a class="brand" href="#/">${mark()} Grove</a>
        <div class="top-actions">
          <a class="btn-ghost" href="/docs">API docs</a>
          <a class="btn" href="#/login">Sign in</a>
        </div>
      </header>
      <section class="hero">
        <div>
          <p class="kicker">Produce house</p>
          <h1>Know what is on the floor.</h1>
          <p class="lede">Grove is the ledger for one house: the catalog, the cold room, the orders, and a wire of what just moved.</p>
          <div class="hero-actions">
            <a class="btn" href="#/login">Open the floor</a>
            <a class="btn-ghost" href="/redoc">Read the contract</a>
          </div>
        </div>
        <aside class="board">
          <header><h2>Today's board</h2><p class="board-note">per kilogram</p></header>
          ${state.error ? `<p class="board-note">${esc(state.error)}</p>` : rows}
        </aside>
      </section>
      <section class="principles">
        <article><h3>Stock is a promise.</h3><p>An order draws the oldest lot first. Cancelling puts the weight back in Returns.</p></article>
        <article><h3>Price is a snapshot.</h3><p>The line keeps the price from the moment of sale. A later edit does not rewrite the ticket.</p></article>
        <article><h3>The wire is the room.</h3><p>Receipts, sales, and cancellations show up as they happen. No one refreshes the clipboard.</p></article>
      </section>
    </main>`;
  }

  function viewLogin() {
    const register = state.authMode === "register";
    const form = register
      ? `<form class="stack" data-form="register">
          <label>Name <input name="full_name" required minlength="2" data-autofocus /></label>
          <label>Email <input name="email" type="email" required /></label>
          <label>Password <input name="password" type="password" required minlength="10" /></label>
          <p class="form-error" id="form-error" hidden></p>
          <button class="btn" type="submit">Create the account</button>
        </form>
        <p class="muted">Already on the floor? <button type="button" class="text-btn" data-action="show-login">Sign in</button></p>`
      : `<form class="stack" id="login-form" data-form="login">
          <label>Email <input name="email" type="email" required data-autofocus /></label>
          <label>Password <input name="password" type="password" required /></label>
          <p class="form-error" id="form-error" hidden></p>
          <button class="btn" type="submit">Sign in</button>
        </form>
        <div class="stack">
          <p class="muted">Demo desk, password Harvest2026</p>
          <div class="demo-row">
            <button type="button" data-demo="admin@grove.example">Iris · admin</button>
            <button type="button" data-demo="manager@grove.example">Mira · manager</button>
            <button type="button" data-demo="clerk@grove.example">Leo · clerk</button>
          </div>
          <p class="muted">New clerk? <button type="button" class="text-btn" data-action="show-register">Open an account</button></p>
        </div>`;
    return `<main class="auth-screen">
      <section class="auth-story">
        <a class="brand" href="#/" style="color:#f4f0e6">${mark()} Grove</a>
        <div>
          <p class="kicker">The house ledger</p>
          <h1>Come in through the side door.</h1>
          <p>Clerks sell. Managers price and receive. Admins keep the keys. The board out front stays public.</p>
        </div>
        <p>Local books. Short-lived access. Refresh tokens rotate.</p>
      </section>
      <section class="auth-panel"><div class="card stack"><h2>${register ? "Open an account" : "Sign in"}</h2>${form}</div></section>
    </main>`;
  }

  function skeleton() {
    return `<div class="skeleton"><i></i><i></i><i></i></div>`;
  }

  function head(kicker, title, actions) {
    return `<header class="page-head"><div><p class="kicker">${esc(kicker)}</p><h1>${esc(title)}</h1></div><div class="toolbar">${actions || ""}</div></header>${
      state.error ? `<div class="banner">${esc(state.error)}</div>` : ""
    }`;
  }

  function viewFloor() {
    const summary = state.data.summary;
    if (!summary) return head("Floor", "This morning") + `<p class="empty">No summary yet.</p>`;
    const max = Math.max(...summary.categories.map((row) => Number(row.quantity_kg)), 1);
    const bars = summary.categories
      .map((row) => {
        const width = Math.max(4, Math.round((Number(row.quantity_kg) / max) * 100));
        return `<div class="bar-row"><span>${esc(label(row.category))}</span><div class="bar"><i style="width:${width}%"></i></div><strong>${esc(kg(row.quantity_kg))}</strong></div>`;
      })
      .join("");
    const low = summary.low_stock.length
      ? `<div class="table-wrap"><table><tbody>${summary.low_stock
          .map(
            (row) =>
              `<tr><td>${esc(row.name)}<div class="muted">${esc(row.sku)}</div></td><td class="num">${esc(kg(row.quantity_kg))}</td></tr>`,
          )
          .join("")}</tbody></table></div>`
      : `<p class="empty">Nothing under ${esc(kg(15))}.</p>`;
    const orders = summary.recent_orders.length
      ? `<div class="table-wrap"><table><thead><tr><th>Order</th><th>Customer</th><th>Status</th><th class="num">Total</th></tr></thead><tbody>${summary.recent_orders
          .map(
            (order) =>
              `<tr><td>${esc(order.number)}</td><td>${esc(order.customer_name)}</td><td>${pill(order.status)}</td><td class="num">${esc(money(order.total))}</td></tr>`,
          )
          .join("")}</tbody></table></div>`
      : `<p class="empty">No tickets yet.</p>`;
    return `${head("Floor", "This morning", `<a class="btn-ghost" href="#/orders">Orders</a>`)}
      <section class="stats">
        <article class="stat"><span>SKUs</span><strong>${esc(summary.sku_count)}</strong></article>
        <article class="stat"><span>On hand</span><strong>${esc(kg(summary.stock_kg))}</strong></article>
        <article class="stat"><span>Open orders</span><strong>${esc(summary.open_orders)}</strong></article>
        <article class="stat"><span>Today</span><strong>${esc(money(summary.revenue_today))}</strong></article>
      </section>
      <section class="split">
        <article class="panel"><h2>By kind</h2>${bars || `<p class="empty">No stock.</p>`}</article>
        <article class="panel"><h2>Running low</h2>${low}</article>
      </section>
      <section class="panel" style="margin-top:12px"><h2>Latest tickets</h2>${orders}</section>`;
  }

  function viewCatalog() {
    const items = (state.data.catalog && state.data.catalog.items) || [];
    const filters = state.filters;
    const rows = items
      .map(
        (fruit) => `<tr>
          <td><strong>${esc(fruit.name)}</strong><div class="muted">${esc(fruit.sku)} · ${esc(fruit.origin)}</div></td>
          <td>${esc(label(fruit.category))}</td>
          <td class="num">${esc(money(fruit.price_per_kg))}</td>
          <td class="num">${esc(kg(fruit.quantity_on_hand))}</td>
          <td>${pill(fruit.stock_status)}</td>
          <td class="row-actions">${
            can("catalog:write")
              ? `<button type="button" class="btn-ghost btn-small" data-action="edit-fruit" data-id="${esc(fruit.id)}">Edit</button>
                 <button type="button" class="text-btn" data-action="archive-fruit" data-id="${esc(fruit.id)}" data-name="${esc(fruit.name)}">Archive</button>`
              : ""
          }</td>
        </tr>`,
      )
      .join("");
    return `${head(
      "Catalog",
      "The book",
      `${can("catalog:read") ? `<button type="button" class="btn-ghost" data-action="export">Export</button>` : ""}
       ${can("catalog:write") ? `<button type="button" class="btn" data-action="new-fruit">New fruit</button>` : ""}`,
    )}
      <form class="filters" data-form="filter">
        <input name="q" placeholder="Search name, SKU, origin" value="${esc(filters.q || "")}" />
        <select name="category"><option value="">All kinds</option>${options(CATEGORIES, filters.category || "")}</select>
        <select name="seasonal">
          <option value="" ${!filters.seasonal ? "selected" : ""}>Any season</option>
          <option value="yes" ${filters.seasonal === "yes" ? "selected" : ""}>Seasonal</option>
          <option value="no" ${filters.seasonal === "no" ? "selected" : ""}>Year round</option>
        </select>
        <select name="sort">
          ${options([["name", "Name"], ["-name", "Name, Z–A"], ["price", "Price"], ["-price", "Price, high"], ["newest", "Newest"]], filters.sort || "name")}
        </select>
        <button class="btn-ghost" type="submit">Apply</button>
      </form>
      <div class="panel table-wrap">
        ${
          rows
            ? `<table><thead><tr><th>Fruit</th><th>Kind</th><th class="num">Price</th><th class="num">On hand</th><th>State</th><th></th></tr></thead><tbody>${rows}</tbody></table>`
            : `<p class="empty">Nothing matches.</p>`
        }
      </div>`;
  }

  function viewStock() {
    const lots = state.data.lots || [];
    const rows = lots
      .map(
        (lot) => `<tr>
          <td><strong>${esc(lot.fruit_name || "Fruit")}</strong><div class="muted">${esc(lot.sku || "")}</div></td>
          <td>${esc(lot.warehouse)}</td>
          <td class="num">${esc(kg(lot.quantity_kg))}</td>
          <td class="num">${esc(money(lot.unit_cost))}</td>
          <td>${esc(when(lot.received_at))}</td>
          <td class="muted">${esc(lot.note || "")}</td>
        </tr>`,
      )
      .join("");
    return `${head(
      "Stock",
      "Cold room",
      can("inventory:write")
        ? `<button type="button" class="btn-ghost" data-action="adjust">Adjust</button><button type="button" class="btn" data-action="receive">Receive</button>`
        : "",
    )}
      <div class="panel table-wrap">
        ${
          rows
            ? `<table><thead><tr><th>Fruit</th><th>Room</th><th class="num">Weight</th><th class="num">Cost</th><th>Received</th><th>Note</th></tr></thead><tbody>${rows}</tbody></table>`
            : `<p class="empty">No open lots.</p>`
        }
      </div>`;
  }

  function viewOrders() {
    const items = (state.data.orders && state.data.orders.items) || [];
    const rows = items
      .map((order) => {
        const actions = [];
        if (order.status === "confirmed" && can("orders:write")) {
          actions.push(`<button type="button" class="text-btn" data-action="cancel-order" data-id="${esc(order.id)}">Cancel</button>`);
        }
        if (order.status === "confirmed" && can("orders:fulfill")) {
          actions.push(`<button type="button" class="btn-ghost btn-small" data-action="fulfill" data-id="${esc(order.id)}">Fulfill</button>`);
        }
        return `<tr>
          <td><strong>${esc(order.number)}</strong><div class="muted">${esc(when(order.created_at))}</div></td>
          <td>${esc(order.customer_name)}</td>
          <td>${order.lines.map((line) => `${esc(line.fruit_name)} · ${esc(kg(line.quantity_kg))}`).join("<br>")}</td>
          <td>${pill(order.status)}</td>
          <td class="num">${esc(money(order.total))}</td>
          <td class="row-actions">${actions.join(" ")}</td>
        </tr>`;
      })
      .join("");
    return `${head(
      "Orders",
      "Tickets",
      can("orders:write") ? `<button type="button" class="btn" data-action="new-order">New order</button>` : "",
    )}
      <div class="panel table-wrap">
        ${
          rows
            ? `<table><thead><tr><th>Ticket</th><th>Customer</th><th>Lines</th><th>Status</th><th class="num">Total</th><th></th></tr></thead><tbody>${rows}</tbody></table>`
            : `<p class="empty">No tickets yet.</p>`
        }
      </div>`;
  }

  function viewGrowers() {
    const items = (state.data.suppliers && state.data.suppliers.items) || [];
    const rows = items
      .map(
        (row) => `<tr>
          <td><strong>${esc(row.name)}</strong><div class="muted">${esc(row.region)}</div></td>
          <td>${esc(row.contact_email || "—")}</td>
          <td>${esc(row.phone || "—")}</td>
          <td class="num">${esc(row.fruit_count)}</td>
          <td>${row.is_active ? pill("ok") : pill("out")}</td>
        </tr>`,
      )
      .join("");
    return `${head(
      "Growers",
      "Who grows it",
      can("suppliers:write") ? `<button type="button" class="btn" data-action="new-supplier">New grower</button>` : "",
    )}
      <div class="panel table-wrap">
        ${
          rows
            ? `<table><thead><tr><th>Grower</th><th>Email</th><th>Phone</th><th class="num">SKUs</th><th></th></tr></thead><tbody>${rows}</tbody></table>`
            : `<p class="empty">No growers yet.</p>`
        }
      </div>`;
  }

  function wireItem(event) {
    const payload = event.payload || {};
    const bits = Object.entries(payload)
      .filter(([, value]) => value !== null && value !== "")
      .map(([key, value]) => `${label(key)}: ${value}`)
      .join(" · ");
    return `<article><time>${esc(when(event.at))}</time><div><strong>${esc(label((event.type || "").replaceAll(".", " ")))}</strong><div class="muted">${esc(bits)}</div></div></article>`;
  }

  function viewWire() {
    const events = state.data.events || [];
    return `${head("Wire", "What just moved")}
      <div class="panel"><div class="wire" id="wire">${
        events.length ? events.map(wireItem).join("") : `<p class="empty">The wire is quiet.</p>`
      }</div></div>`;
  }

  function viewHouse() {
    const user = state.user;
    const profile = `<article class="panel stack">
      <h2>${esc(user.full_name)}</h2>
      <p class="muted">${esc(user.email)} · ${esc(label(user.role))}</p>
      <form class="stack" data-form="password">
        <label>Current password <input name="current_password" type="password" required /></label>
        <label>New password <input name="new_password" type="password" required minlength="10" /></label>
        <p class="form-error" id="form-error" hidden></p>
        <button class="btn" type="submit">Change password</button>
      </form>
    </article>`;
    let extra = "";
    if (can("admin")) {
      const people = ((state.data.users && state.data.users.items) || [])
        .map(
          (person) => `<tr>
            <td><strong>${esc(person.full_name)}</strong><div class="muted">${esc(person.email)}</div></td>
            <td><select data-role="${esc(person.id)}" ${person.id === user.id ? "disabled" : ""}>
              ${options([["clerk", "Clerk"], ["manager", "Manager"], ["admin", "Admin"]], person.role)}
            </select></td>
            <td>${person.is_active ? pill("ok") : pill("out")}</td>
          </tr>`,
        )
        .join("");
      const keys = (state.data.keys || [])
        .map(
          (key) => `<tr>
            <td><strong>${esc(key.name)}</strong><div class="muted">${esc(key.prefix)}…</div></td>
            <td>${key.revoked_at ? pill("out") : pill("ok")}</td>
            <td class="row-actions">${
              key.revoked_at
                ? ""
                : `<button type="button" class="text-btn" data-action="revoke-key" data-id="${esc(key.id)}">Revoke</button>`
            }</td>
          </tr>`,
        )
        .join("");
      extra += `<article class="panel"><h2>People</h2><div class="table-wrap"><table><tbody>${people}</tbody></table></div></article>
        <article class="panel"><header class="page-head"><h2>Keys</h2><button type="button" class="btn btn-small" data-action="new-key">New key</button></header>
          <p class="muted">A key can read the floor. It cannot sell, price, or change a role.</p>
          <div class="table-wrap">${keys ? `<table><tbody>${keys}</tbody></table>` : `<p class="empty">No keys.</p>`}</div>
        </article>`;
    }
    if (can("audit:read")) {
      const rows = ((state.data.audit && state.data.audit.items) || [])
        .map(
          (row) =>
            `<tr><td>${esc(when(row.created_at))}</td><td>${esc(row.actor_name || "House")}</td><td>${esc(row.action)}</td></tr>`,
        )
        .join("");
      extra += `<article class="panel"><h2>Audit</h2><div class="table-wrap">${
        rows ? `<table><tbody>${rows}</tbody></table>` : `<p class="empty">Nothing recorded.</p>`
      }</div></article>`;
    }
    return `${head("House", "The desk")}<div class="house-grid">${profile}<div class="stack">${extra}</div></div>`;
  }

  function lineRow() {
    return `<div class="line-row" data-line>
      <select name="fruit_id" required><option value="">Fruit</option>${fruitChoices("")}</select>
      <input name="quantity_kg" type="number" min="0.001" step="0.001" placeholder="kg" required />
      <button type="button" class="text-btn" data-action="remove-line">Remove</button>
    </div>`;
  }

  function modal() {
    const modalState = state.modal;
    if (!modalState) return "";
    let body = "";
    if (modalState.type === "fruit") {
      const fruit = modalState.fruit;
      body = `<form class="stack" data-form="fruit">
        ${fruit ? "" : `<label>SKU <input name="sku" required data-autofocus placeholder="FIG-001" /></label>`}
        <label>Name <input name="name" required value="${esc(fruit ? fruit.name : "")}" ${fruit ? "data-autofocus" : ""} /></label>
        <div class="two">
          <label>Kind <select name="category">${options(CATEGORIES, fruit ? fruit.category : "pome")}</select></label>
          <label>Price / kg <input name="price_per_kg" type="number" min="0.01" step="0.01" required value="${fruit ? esc(fruit.price_per_kg) : ""}" /></label>
        </div>
        <label>Origin <input name="origin" required value="${esc(fruit ? fruit.origin : "")}" /></label>
        <label>Grower <select name="supplier_id">${supplierChoices(fruit ? fruit.supplier_id : "")}</select></label>
        <label>Description <textarea name="description">${esc(fruit ? fruit.description : "")}</textarea></label>
        <div class="two">
          <label class="check"><input type="checkbox" name="is_seasonal" ${fruit && fruit.is_seasonal ? "checked" : ""} /> Seasonal</label>
          <label>Season <input name="season_label" value="${esc(fruit ? fruit.season_label || "" : "")}" /></label>
        </div>
        <p class="form-error" id="form-error" hidden></p>
        <button class="btn" type="submit">${fruit ? "Save" : "Add to the book"}</button>
      </form>`;
    } else if (modalState.type === "receive" || modalState.type === "adjust") {
      const adjust = modalState.type === "adjust";
      body = `<form class="stack" data-form="${adjust ? "adjust" : "receive"}">
        <label>Fruit <select name="fruit_id" required data-autofocus><option value="">Choose</option>${fruitChoices("")}</select></label>
        <label>${adjust ? "Weight change, kg" : "Weight, kg"} <input name="quantity_kg" type="number" step="0.001" required ${adjust ? "" : 'min="0.001"'} /></label>
        ${
          adjust
            ? `<label>Reason <input name="reason" required minlength="3" /></label>`
            : `<div class="two"><label>Unit cost <input name="unit_cost" type="number" min="0" step="0.01" required value="0" /></label><label>Room <input name="warehouse" value="Cold room A" required /></label></div>
               <label>Note <input name="note" /></label>`
        }
        <p class="form-error" id="form-error" hidden></p>
        <button class="btn" type="submit">${adjust ? "Adjust" : "Receive"}</button>
      </form>`;
    } else if (modalState.type === "order") {
      body = `<form class="stack" data-form="order">
        <label>Customer <input name="customer_name" required data-autofocus /></label>
        <label>Email <input name="customer_email" type="email" /></label>
        <label>Notes <input name="notes" /></label>
        <div class="stack" id="lines">${lineRow()}</div>
        <button type="button" class="text-btn" data-action="add-line">Add a line</button>
        <p class="form-error" id="form-error" hidden></p>
        <button class="btn" type="submit">Commit the order</button>
      </form>`;
    } else if (modalState.type === "supplier") {
      body = `<form class="stack" data-form="supplier">
        <label>Name <input name="name" required data-autofocus /></label>
        <label>Region <input name="region" required /></label>
        <div class="two"><label>Email <input name="contact_email" type="email" /></label><label>Phone <input name="phone" /></label></div>
        <label>Notes <textarea name="notes"></textarea></label>
        <p class="form-error" id="form-error" hidden></p>
        <button class="btn" type="submit">Save grower</button>
      </form>`;
    } else if (modalState.type === "key") {
      body = `<form class="stack" data-form="key">
        <label>Name <input name="name" required data-autofocus placeholder="Front board" /></label>
        <p class="form-error" id="form-error" hidden></p>
        <button class="btn" type="submit">Create key</button>
      </form>`;
    } else if (modalState.type === "secret") {
      body = `<p>Copy this now. Grove will not show it again.</p><p class="secret">${esc(modalState.secret)}</p><button type="button" class="btn" data-action="modal-close">Done</button>`;
    } else if (modalState.type === "confirm") {
      body = `<p>${esc(modalState.body)}</p><div class="toolbar"><button type="button" class="btn-ghost" data-action="modal-close">Keep it</button><button type="button" class="btn-danger" data-action="confirm-yes">${esc(modalState.confirm || "Confirm")}</button></div>`;
    }
    return `<div class="modal-back" data-action="modal-back"><div class="modal" role="dialog" aria-modal="true" data-stop>
      <header><h2>${esc(modalState.title || "Grove")}</h2><button type="button" class="text-btn" data-action="modal-close">Close</button></header>
      ${body}
    </div></div>`;
  }

  function titles(name) {
    return (
      {
        floor: ["Floor", "This morning"],
        catalog: ["Catalog", "The book"],
        stock: ["Stock", "Cold room"],
        orders: ["Orders", "Tickets"],
        growers: ["Growers", "Who grows it"],
        wire: ["Wire", "What just moved"],
        house: ["House", "The desk"],
      }[name] || ["Grove", "Grove"]
    );
  }

  function viewFor(route) {
    if (route.name === "catalog") return viewCatalog();
    if (route.name === "stock") return viewStock();
    if (route.name === "orders") return viewOrders();
    if (route.name === "growers") return viewGrowers();
    if (route.name === "wire") return viewWire();
    if (route.name === "house") return viewHouse();
    return viewFloor();
  }

  function shell(body) {
    const [kicker] = titles(state.route.name);
    const links = NAV.map(
      ([name, text]) =>
        `<a href="#/${name}" class="${state.route.name === name ? "active" : ""}">${esc(text)}</a>`,
    ).join("");
    return `<div class="shell">
      <aside class="sider">
        <a class="brand" href="#/floor">${mark()} Grove</a>
        <nav aria-label="Floor">${links}</nav>
        <div class="aside-foot">
          <strong>${esc(state.user.full_name)}</strong>
          <span class="role-chip">${esc(state.user.role)}</span>
          <button type="button" class="text-btn signout" data-action="logout">Sign out</button>
        </div>
      </aside>
      <section class="main">${state.loading ? head(kicker, titles(state.route.name)[1]) + skeleton() : body}</section>
      ${modal()}
    </div>`;
  }

  function render() {
    const route = state.route;
    const root = $("#app");
    if (!state.user && route.name !== "login" && route.name !== "landing") {
      root.innerHTML = viewLogin();
    } else if (route.name === "login") {
      root.innerHTML = viewLogin();
    } else if (route.name === "landing" && !state.user) {
      root.innerHTML = viewLanding();
    } else {
      root.innerHTML = shell(viewFor(route));
    }
    const focus = document.querySelector("[data-autofocus]");
    if (focus) focus.focus();
    syncSocket();
  }

  function closeSocket() {
    if (state.socket) {
      state.socket.onclose = null;
      state.socket.close();
      state.socket = null;
    }
  }

  function syncSocket() {
    if (state.route.name !== "wire" || !state.user) {
      closeSocket();
      return;
    }
    if (state.socket && state.socket.readyState <= 1) return;
    const protocol = location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(
      `${protocol}://${location.host}/api/v1/live/ws?token=${encodeURIComponent(api.token())}`,
    );
    state.socket = socket;
    socket.onmessage = (message) => {
      const event = JSON.parse(message.data);
      if (event.type === "pong") return;
      state.data.events = [event, ...(state.data.events || [])].slice(0, 40);
      const list = document.getElementById("wire");
      if (!list) return;
      const empty = list.querySelector(".empty");
      if (empty) empty.remove();
      list.insertAdjacentHTML("afterbegin", wireItem(event));
    };
    socket.onclose = () => {
      if (state.socket === socket) state.socket = null;
    };
  }

  function catalogPath() {
    const params = new URLSearchParams();
    params.set("size", "100");
    params.set("sort", state.filters.sort || "name");
    if (state.filters.q) params.set("q", state.filters.q);
    if (state.filters.category) params.set("category", state.filters.category);
    if (state.filters.seasonal === "yes") params.set("seasonal", "true");
    if (state.filters.seasonal === "no") params.set("seasonal", "false");
    return `/fruits?${params.toString()}`;
  }

  async function hydrate(route) {
    if (route.name === "landing") {
      state.data.highlights = await api.get("/fruits?size=8&sort=name");
      return;
    }
    if (!state.user) return;
    if (route.name === "floor") {
      state.data.summary = await api.get("/reports/summary");
    } else if (route.name === "catalog") {
      state.data.catalog = await api.get(catalogPath());
      if (can("suppliers:read")) state.data.suppliers = await api.get("/suppliers?size=100");
    } else if (route.name === "stock") {
      state.data.lots = await api.get("/inventory/lots");
      state.data.catalog = await api.get("/fruits?size=100&sort=name");
    } else if (route.name === "orders") {
      state.data.orders = await api.get("/orders?size=40");
      state.data.catalog = await api.get("/fruits?size=100&sort=name");
    } else if (route.name === "growers") {
      state.data.suppliers = await api.get("/suppliers?size=100");
    } else if (route.name === "wire") {
      const recent = await api.get("/live/recent");
      state.data.events = (recent.items || []).slice().reverse();
    } else if (route.name === "house") {
      if (can("admin")) {
        state.data.users = await api.get("/users?size=100");
        state.data.keys = await api.get("/keys");
      }
      if (can("audit:read")) state.data.audit = await api.get("/audit?size=20");
    }
  }

  async function navigate() {
    closeSocket();
    const route = parseRoute();
    if (!PUBLIC.has(route.name) && !state.user) {
      if (location.hash !== "#/login") location.hash = "#/login";
      state.route = { name: "login", parts: ["login"] };
      render();
      return;
    }
    if (route.name === "landing" && state.user) {
      if (location.hash !== "#/floor") location.hash = "#/floor";
      return;
    }
    state.route = route;
    state.error = "";
    state.modal = null;
    state.loading = true;
    state.data = {};
    render();
    try {
      await hydrate(route);
    } catch (error) {
      state.error = error.message || "Request failed";
    } finally {
      state.loading = false;
      render();
    }
  }

  async function reload() {
    try {
      await hydrate(state.route);
      state.error = "";
    } catch (error) {
      state.error = error.message || "Request failed";
    }
    state.modal = null;
    render();
  }

  function formError(error) {
    const message = error.message || "Request failed";
    const node = document.getElementById("form-error");
    if (node) {
      node.hidden = false;
      node.textContent = message;
    }
    toast(message, "bad");
  }

  function openModal(next) {
    state.modal = next;
    render();
  }

  async function onClick(event) {
    const button = event.target.closest("[data-action], [data-demo]");
    if (!button) return;
    if (button.dataset.demo) {
      const form = document.getElementById("login-form");
      if (!form) return;
      form.email.value = button.dataset.demo;
      form.password.value = "Harvest2026";
      form.requestSubmit();
      return;
    }
    const action = button.dataset.action;
    if (action === "modal-back" && event.target === button) {
      state.modal = null;
      render();
      return;
    }
    if (button.hasAttribute("data-stop")) return;
    if (action === "show-register") {
      state.authMode = "register";
      render();
      return;
    }
    if (action === "show-login") {
      state.authMode = "login";
      render();
      return;
    }
    if (action === "logout") {
      await api.logout();
      state.user = null;
      location.hash = "#/";
      return;
    }
    if (action === "modal-close") {
      state.modal = null;
      render();
      return;
    }
    if (action === "add-line") {
      document.getElementById("lines").insertAdjacentHTML("beforeend", lineRow());
      return;
    }
    if (action === "remove-line") {
      const row = button.closest("[data-line]");
      if (row && document.querySelectorAll("[data-line]").length > 1) row.remove();
      return;
    }
    if (action === "new-fruit") return openModal({ type: "fruit", title: "New fruit", fruit: null });
    if (action === "edit-fruit") {
      const fruit = (state.data.catalog.items || []).find((item) => item.id === button.dataset.id);
      if (fruit) openModal({ type: "fruit", title: fruit.name, fruit });
      return;
    }
    if (action === "archive-fruit") {
      openModal({
        type: "confirm",
        title: "Archive this fruit?",
        body: `${button.dataset.name} leaves the book. Past orders keep the name.`,
        confirm: "Archive",
        run: async () => {
          await api.del(`/fruits/${button.dataset.id}`);
          toast("Archived");
          await reload();
        },
      });
      return;
    }
    if (action === "confirm-yes" && state.modal && state.modal.run) {
      try {
        await state.modal.run();
      } catch (error) {
        formError(error);
      }
      return;
    }
    if (action === "receive") return openModal({ type: "receive", title: "Receive stock" });
    if (action === "adjust") return openModal({ type: "adjust", title: "Adjust stock" });
    if (action === "new-order") return openModal({ type: "order", title: "New order" });
    if (action === "new-supplier") return openModal({ type: "supplier", title: "New grower" });
    if (action === "new-key") return openModal({ type: "key", title: "New key" });
    if (action === "export") {
      const response = await fetch("/api/v1/fruits/export", {
        headers: { Authorization: `Bearer ${api.token()}` },
      });
      if (!response.ok) {
        toast("Export failed", "bad");
        return;
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "grove-catalog.csv";
      link.click();
      URL.revokeObjectURL(url);
      return;
    }
    if (action === "cancel-order" || action === "fulfill") {
      try {
        if (action === "cancel-order") await api.post(`/orders/${button.dataset.id}/cancel`, {});
        else await api.post(`/orders/${button.dataset.id}/fulfill`, {});
        toast(action === "cancel-order" ? "Order cancelled" : "Order fulfilled");
        await reload();
      } catch (error) {
        toast(error.message, "bad");
      }
      return;
    }
    if (action === "revoke-key") {
      try {
        await api.del(`/keys/${button.dataset.id}`);
        toast("Key revoked");
        await reload();
      } catch (error) {
        toast(error.message, "bad");
      }
    }
  }

  async function onSubmit(event) {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || !form.dataset.form) return;
    event.preventDefault();
    const kind = form.dataset.form;
    try {
      if (kind === "login") {
        state.user = await api.login(form.email.value.trim(), form.password.value);
        location.hash = "#/floor";
        return;
      }
      if (kind === "register") {
        await api.post("/auth/register", {
          full_name: form.full_name.value,
          email: form.email.value,
          password: form.password.value,
        });
        state.user = await api.login(form.email.value.trim(), form.password.value);
        location.hash = "#/floor";
        return;
      }
      if (kind === "filter") {
        state.filters = {
          q: form.q.value.trim(),
          category: form.category.value,
          seasonal: form.seasonal.value,
          sort: form.sort.value,
        };
        await reload();
        return;
      }
      if (kind === "fruit") {
        const payload = {
          name: form.name.value,
          category: form.category.value,
          origin: form.origin.value,
          description: form.description.value,
          price_per_kg: form.price_per_kg.value,
          is_seasonal: form.is_seasonal.checked,
          season_label: form.season_label.value || null,
          supplier_id: form.supplier_id.value || null,
        };
        if (state.modal.fruit) {
          await api.patch(`/fruits/${state.modal.fruit.id}`, payload, { "If-Match": String(state.modal.fruit.version) });
          toast("Saved");
        } else {
          payload.sku = form.sku.value;
          await api.post("/fruits", payload);
          toast("Added to the book");
        }
        await reload();
        return;
      }
      if (kind === "receive") {
        await api.post("/inventory/receipts", {
          fruit_id: form.fruit_id.value,
          quantity_kg: form.quantity_kg.value,
          unit_cost: form.unit_cost.value,
          warehouse: form.warehouse.value,
          note: form.note.value || null,
        });
        toast("Lot received");
        await reload();
        return;
      }
      if (kind === "adjust") {
        await api.post("/inventory/adjustments", {
          fruit_id: form.fruit_id.value,
          quantity_kg: form.quantity_kg.value,
          reason: form.reason.value,
        });
        toast("Stock adjusted");
        await reload();
        return;
      }
      if (kind === "order") {
        const lines = [...form.querySelectorAll("[data-line]")]
          .map((row) => ({
            fruit_id: row.querySelector("[name=fruit_id]").value,
            quantity_kg: row.querySelector("[name=quantity_kg]").value,
          }))
          .filter((line) => line.fruit_id && line.quantity_kg);
        await api.post(
          "/orders",
          {
            customer_name: form.customer_name.value,
            customer_email: form.customer_email.value || null,
            notes: form.notes.value || null,
            lines,
          },
          { "Idempotency-Key": crypto.randomUUID() },
        );
        toast("Order committed");
        await reload();
        return;
      }
      if (kind === "supplier") {
        await api.post("/suppliers", {
          name: form.name.value,
          region: form.region.value,
          contact_email: form.contact_email.value || null,
          phone: form.phone.value || null,
          notes: form.notes.value || null,
        });
        toast("Grower saved");
        await reload();
        return;
      }
      if (kind === "key") {
        const created = await api.post("/keys", { name: form.name.value });
        state.modal = { type: "secret", title: "Key created", secret: created.secret };
        state.data.keys = await api.get("/keys");
        render();
        return;
      }
      if (kind === "password") {
        await api.post("/auth/password", {
          current_password: form.current_password.value,
          new_password: form.new_password.value,
        });
        form.reset();
        toast("Password changed. Other sessions were signed out.");
      }
    } catch (error) {
      formError(error);
    }
  }

  async function onChange(event) {
    const select = event.target.closest("[data-role]");
    if (!select) return;
    try {
      await api.patch(`/users/${select.dataset.role}`, { role: select.value });
      toast("Role updated");
    } catch (error) {
      toast(error.message, "bad");
      await reload();
    }
  }

  document.addEventListener("click", (event) => {
    void onClick(event);
  });
  document.addEventListener("submit", (event) => {
    void onSubmit(event);
  });
  document.addEventListener("change", (event) => {
    void onChange(event);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && state.modal) {
      state.modal = null;
      render();
    }
  });
  window.addEventListener("hashchange", () => {
    void navigate();
  });

  async function boot() {
    state.user = await api.restore();
    if (!location.hash) {
      location.hash = state.user ? "#/floor" : "#/";
      return;
    }
    await navigate();
  }

  void boot();
})();
