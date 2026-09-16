// WhatsSup frontend - vanilla JS, no build step.
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const TOKEN_KEY = "whatssup_token";
const USER_KEY  = "whatssup_user";

// ---- API helper ----
const api = {
  async req(method, path, body) {
    const headers = { "Content-Type": "application/json" };
    const token = localStorage.getItem(TOKEN_KEY);
    if (token) headers.Authorization = `Bearer ${token}`;
    const res = await fetch(`/api${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
    if (res.status === 401) { logout(); throw new Error("Unauthorized"); }
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try { detail = (await res.json()).detail || detail; } catch {}
      throw new Error(detail);
    }
    if (res.status === 204) return null;
    return res.json();
  },
  get(path)    { return this.req("GET",    path); },
  post(path, body) { return this.req("POST",   path, body); },
  put(path, body)  { return this.req("PUT",    path, body); },
  del(path)    { return this.req("DELETE", path); },
};

// ---- Auth ----
function logout() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  location.reload();
}

function applyAuth() {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) {
    $("#app").classList.remove("hidden");
    $("#loginScreen").classList.add("hidden");
    const u = JSON.parse(localStorage.getItem(USER_KEY) || "{}");
    $("#userBadge").textContent = `👤 ${u.username || ""}`;
  } else {
    $("#app").classList.add("hidden");
    $("#loginScreen").classList.remove("hidden");
  }
}

$("#loginForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("#loginError").classList.add("hidden");
  const username = $("#loginUser").value.trim();
  const password = $("#loginPass").value;
  try {
    const form = new URLSearchParams();
    form.append("username", username);
    form.append("password", password);
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: form,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      $("#loginError").textContent = err.detail || "Login fehlgeschlagen";
      $("#loginError").classList.remove("hidden");
      return;
    }
    const data = await res.json();
    localStorage.setItem(TOKEN_KEY, data.access_token);
    localStorage.setItem(USER_KEY, JSON.stringify({ username: data.username, is_admin: data.is_admin }));
    applyAuth();
    switchTab("today");
    loadAll();
  } catch (err) {
    $("#loginError").textContent = err.message;
    $("#loginError").classList.remove("hidden");
  }
});

$("#logoutBtn").addEventListener("click", logout);

// ---- Tabs ----
function switchTab(name) {
  $$(".tab").forEach(t => t.classList.toggle("active", t.dataset.tab === name));
  $$("main > section").forEach(s => s.classList.add("hidden"));
  $(`#tab-${name}`).classList.remove("hidden");
  if (name === "today")    loadToday();
  if (name === "supps")    loadMySupps();
  if (name === "catalog")  loadCatalog();
  if (name === "bp")       loadBP();
  if (name === "stats")    loadStats();
  if (name === "profile")  loadProfile();
}
$$(".tab").forEach(t => t.addEventListener("click", () => switchTab(t.dataset.tab)));

// ---- Toast ----
let toastTimer = null;
function toast(msg, kind = "ok") {
  const el = $("#toast");
  el.textContent = msg;
  el.className = `fixed bottom-4 left-1/2 -translate-x-1/2 px-4 py-2 rounded-lg shadow-xl show ${
    kind === "ok" ? "bg-emerald-600" : kind === "warn" ? "bg-amber-600" : "bg-rose-600"
  }`;
  el.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add("hidden"), 2500);
}

// ---- Today ----
async function loadToday() {
  const list = $("#todayList");
  list.innerHTML = `<div class="text-slate-500 text-sm">Lädt…</div>`;
  try {
    const [entries, interactions] = await Promise.all([
      api.get("/intake/today"),
      api.get("/my-supplements/interactions/check").catch(() => []),
    ]);

    if (interactions && interactions.length) {
      const warns = $("#interactionWarnings");
      warns.classList.remove("hidden");
      warns.innerHTML = `
        <div class="bg-amber-500/10 border border-amber-500/30 rounded-xl p-3 space-y-2">
          <div class="font-semibold text-amber-300">⚠️ Supplement-Interaktionen</div>
          ${interactions.map(i => `
            <div class="text-sm">
              <span class="pill severity-${i.severity}">${i.severity}</span>
              <span class="font-medium">${i.supplement_a} + ${i.supplement_b}</span>
              <div class="text-slate-400">${i.description}</div>
              <div class="text-emerald-300">→ ${i.recommendation}</div>
            </div>
          `).join("")}
        </div>
      `;
    } else {
      $("#interactionWarnings").classList.add("hidden");
    }

    if (!entries.length) {
      list.innerHTML = `<div class="text-slate-500 text-sm">Heute keine Einträge.</div>`;
      return;
    }

    list.innerHTML = entries.map(e => {
      const time = new Date(e.scheduled_for).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
      const dose = e.dose_taken ? `${e.dose_taken} ${e.unit || ""}`.trim() : "";
      const pill = `pill-${e.status}`;
      return `
        <div class="row-card rounded-xl p-4 flex items-center gap-3" data-intake="${e.id}">
          <div class="text-2xl font-bold tabular-nums w-14 text-center">${time}</div>
          <div class="flex-1">
            <div class="font-semibold">Supplement #${e.user_supplement_id}</div>
            ${dose ? `<div class="text-sm text-slate-400">${dose}</div>` : ""}
          </div>
          <span class="pill ${pill}">${e.status}</span>
          ${e.status === "pending" || e.status === "snoozed" ? `
            <div class="flex gap-1">
              <button class="px-2 py-1 text-xs rounded bg-emerald-600 hover:bg-emerald-500" data-act="confirm">✓</button>
              <button class="px-2 py-1 text-xs rounded bg-purple-600 hover:bg-purple-500" data-act="snooze">⏰</button>
              <button class="px-2 py-1 text-xs rounded bg-slate-600 hover:bg-slate-500" data-act="skip">✕</button>
            </div>
          ` : ""}
        </div>
      `;
    }).join("");

    list.querySelectorAll("button[data-act]").forEach(btn => {
      btn.addEventListener("click", async (ev) => {
        const card = ev.target.closest("[data-intake]");
        const intakeId = card.dataset.intake;
        const act = btn.dataset.act;
        try {
          if (act === "confirm") await api.post(`/intake/${intakeId}/confirm`, {});
          if (act === "skip")    await api.post(`/intake/${intakeId}/skip`, {});
          if (act === "snooze")  await api.post(`/intake/${intakeId}/snooze?minutes=30`, {});
          toast("OK");
          loadToday();
        } catch (e) { toast(e.message, "err"); }
      });
    });
  } catch (e) { toast(e.message, "err"); }
}
$("#refreshToday").addEventListener("click", loadToday);

// ---- My supplements ----
async function loadMySupps() {
  const list = $("#mySuppsList");
  list.innerHTML = `<div class="text-slate-500 text-sm">Lädt…</div>`;
  try {
    const data = await api.get("/my-supplements");
    if (!data.length) {
      list.innerHTML = `<div class="text-slate-500 text-sm">Noch nichts. Lege dein erstes Supplement an.</div>`;
      return;
    }
    list.innerHTML = data.map(s => `
      <div class="row-card rounded-xl p-4">
        <div class="flex items-start justify-between gap-3">
          <div>
            <div class="font-semibold">${s.supplement.name}</div>
            <div class="text-xs text-slate-400 uppercase">${s.supplement.category}</div>
          </div>
          <button class="text-slate-400 hover:text-rose-400" data-del="${s.id}">Entfernen</button>
        </div>
        <div class="mt-3 grid sm:grid-cols-3 gap-3 text-sm">
          <div>
            <div class="text-slate-400 text-xs">Empfohlene Dosis</div>
            <div>${s.recommended_dose ?? "—"} ${s.recommended_unit || ""}</div>
          </div>
          <div>
            <div class="text-slate-400 text-xs">Einnahmezeiten</div>
            <div>${s.schedule.length ? s.schedule.join(", ") : "—"}</div>
          </div>
          <div>
            <div class="text-slate-400 text-xs">Nächste Einnahme</div>
            <div>${s.next_due_at ? new Date(s.next_due_at).toLocaleString("de-DE", { dateStyle: "short", timeStyle: "short" }) : "—"}</div>
          </div>
        </div>
      </div>
    `).join("");

    list.querySelectorAll("[data-del]").forEach(btn => {
      btn.addEventListener("click", async () => {
        if (!confirm("Wirklich entfernen?")) return;
        try {
          await api.del(`/my-supplements/${btn.dataset.del}`);
          toast("Entfernt");
          loadMySupps();
        } catch (e) { toast(e.message, "err"); }
      });
    });
  } catch (e) { toast(e.message, "err"); }
}

$("#addSuppBtn").addEventListener("click", () => openAddSuppModal());

async function openAddSuppModal() {
  // Fetch catalog for picker
  let catalog;
  try {
    catalog = await api.get("/supplements");
  } catch (e) { toast(e.message, "err"); return; }

  $("#modalTitle").textContent = "Supplement hinzufügen";
  $("#modalBody").innerHTML = `
    <label class="block">
      <span class="text-sm text-slate-400">Supplement</span>
      <select id="mSupp" class="mt-1 w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-700">
        ${catalog.map(s => `<option value="${s.id}">${s.name} (${s.category})</option>`).join("")}
      </select>
    </label>
    <label class="block">
      <span class="text-sm text-slate-400">Eigene Dosis pro kg (optional, leer = Standard)</span>
      <input id="mDosePerKg" type="number" step="0.01"
             class="mt-1 w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-700" />
    </label>
    <label class="block">
      <span class="text-sm text-slate-400">Fixe Dosis (optional, überschreibt Pro-Kg)</span>
      <input id="mFixed" type="number" step="0.01"
             class="mt-1 w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-700" />
    </label>
    <label class="block">
      <span class="text-sm text-slate-400">Einnahmezeiten (HH:MM, mehrere mit Komma)</span>
      <input id="mSchedule" type="text" placeholder="08:00, 20:00"
             class="mt-1 w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-700" />
    </label>
    <label class="block">
      <span class="text-sm text-slate-400">Notizen</span>
      <textarea id="mNotes" rows="2"
                class="mt-1 w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-700"></textarea>
    </label>
    <button id="mSave" class="w-full py-2 rounded-lg bg-brand-500 hover:bg-brand-600 font-semibold">Speichern</button>
  `;
  $("#modal").classList.remove("hidden");
  $("#mSave").addEventListener("click", async () => {
    const scheduleRaw = $("#mSchedule").value;
    const schedule = scheduleRaw.split(",").map(s => s.trim()).filter(Boolean);
    try {
      await api.post("/my-supplements", {
        supplement_id: parseInt($("#mSupp").value, 10),
        custom_dose_per_kg: $("#mDosePerKg").value ? parseFloat($("#mDosePerKg").value) : null,
        custom_fixed_dose: $("#mFixed").value ? parseFloat($("#mFixed").value) : null,
        custom_unit: null,
        schedule,
        active: true,
        notes: $("#mNotes").value || null,
      });
      toast("Hinzugefügt");
      $("#modal").classList.add("hidden");
      loadMySupps();
    } catch (e) { toast(e.message, "err"); }
  });
}

$("#modalClose").addEventListener("click", () => $("#modal").classList.add("hidden"));
$("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") $("#modal").classList.add("hidden"); });

// ---- Catalog ----
let _catalogCache = [];
async function loadCatalog() {
  const list = $("#catalogList");
  const q = $("#catalogSearch").value || "";
  list.innerHTML = `<div class="text-slate-500 text-sm col-span-full">Lädt…</div>`;
  try {
    const data = await api.get(`/supplements${q ? `?q=${encodeURIComponent(q)}` : ""}`);
    _catalogCache = data;
    if (!data.length) { list.innerHTML = `<div class="text-slate-500 text-sm col-span-full">Keine Treffer.</div>`; return; }
    list.innerHTML = data.map(s => `
      <div class="row-card rounded-xl p-4">
        <div class="font-semibold">${s.name}</div>
        <div class="text-xs text-slate-400 uppercase">${s.category}</div>
        <div class="text-sm mt-2 text-slate-300">${s.notes || ""}</div>
        <div class="text-xs text-slate-500 mt-2">
          ${s.default_dose_per_kg ? `Default: ${s.default_dose_per_kg} ${s.default_unit}/kg` : `Default-Einheit: ${s.default_unit}`}
        </div>
      </div>
    `).join("");
  } catch (e) { toast(e.message, "err"); }
}
$("#catalogSearch").addEventListener("input", debounce(loadCatalog, 250));
function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }

// ---- Blood pressure ----
async function loadBP() {
  const list = $("#bpList");
  list.innerHTML = `<div class="text-slate-500 text-sm">Lädt…</div>`;
  try {
    const data = await api.get("/blood-pressure?days=90");
    if (!data.length) {
      list.innerHTML = `<div class="text-slate-500 text-sm">Noch keine Einträge.</div>`;
      return;
    }
    list.innerHTML = data.map(b => `
      <div class="row-card rounded-xl p-3 flex items-center gap-3">
        <div class="font-mono text-lg tabular-nums w-24 text-center">${b.systolic}/${b.diastolic}</div>
        ${b.pulse ? `<div class="text-sm text-slate-400">❤️ ${b.pulse}</div>` : ""}
        <div class="flex-1 text-sm text-slate-400">${new Date(b.recorded_at).toLocaleString("de-DE")}</div>
        <button data-bp-del="${b.id}" class="text-slate-400 hover:text-rose-400">✕</button>
      </div>
    `).join("");
    list.querySelectorAll("[data-bp-del]").forEach(btn => {
      btn.addEventListener("click", async () => {
        try {
          await api.del(`/blood-pressure/${btn.dataset.bpDel}`);
          loadBP();
        } catch (e) { toast(e.message, "err"); }
      });
    });
  } catch (e) { toast(e.message, "err"); }
}

$("#bpForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api.post("/blood-pressure", {
      systolic: parseInt($("#bpSys").value, 10),
      diastolic: parseInt($("#bpDia").value, 10),
      pulse: $("#bpPulse").value ? parseInt($("#bpPulse").value, 10) : null,
    });
    e.target.reset();
    toast("Eingetragen");
    loadBP();
  } catch (e) { toast(e.message, "err"); }
});

// ---- Stats ----
async function loadStats() {
  const box = $("#statsContainer");
  box.innerHTML = `<div class="text-slate-500 text-sm">Lädt…</div>`;
  try {
    const stats = await api.get("/stats/compliance?days=30");
    box.innerHTML = `
      <div class="row-card rounded-xl p-6">
        <div class="text-sm text-slate-400">Compliance (letzte ${stats.days} Tage)</div>
        <div class="text-5xl font-bold mt-1">${stats.compliance_pct}%</div>
        <div class="text-xs text-slate-500 mt-1">
          ${stats.total_taken} genommen / ${stats.total_scheduled} geplant
          · ${stats.total_skipped} übersprungen · ${stats.total_missed} verpasst
        </div>
        <div class="bar mt-3"><div style="width:${stats.compliance_pct}%; background:${stats.compliance_pct >= 80 ? "#22c55e" : stats.compliance_pct >= 50 ? "#eab308" : "#f43f5e"};"></div></div>
      </div>
      <div class="row-card rounded-xl p-6 space-y-2">
        <div class="font-semibold">Pro Supplement</div>
        ${Object.keys(stats.per_supplement).length === 0 ? '<div class="text-slate-500 text-sm">Noch keine Daten.</div>' :
          Object.entries(stats.per_supplement).map(([name, pct]) => `
            <div>
              <div class="flex justify-between text-sm"><span>${name}</span><span class="tabular-nums">${pct}%</span></div>
              <div class="bar"><div style="width:${pct}%; background:${pct >= 80 ? "#22c55e" : pct >= 50 ? "#eab308" : "#f43f5e"};"></div></div>
            </div>
          `).join("")
        }
      </div>
    `;
  } catch (e) { toast(e.message, "err"); }
}

// ---- Profile ----
async function loadProfile() {
  try {
    const p = await api.get("/profile");
    $("#profWeight").value   = p.body_weight_kg || "";
    $("#profDiscord").checked = !!p.notify_discord;
    $("#profTelegram").checked = !!p.notify_telegram;
    $("#profWhatsapp").checked = !!p.notify_whatsapp;
    $("#profWeb").checked     = !!p.notify_web;
  } catch (e) { toast(e.message, "err"); }
}

$("#profileForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api.put("/profile", {
      body_weight_kg: $("#profWeight").value ? parseFloat($("#profWeight").value) : null,
      timezone: "Europe/Berlin",
      notify_discord: $("#profDiscord").checked,
      notify_telegram: $("#profTelegram").checked,
      notify_whatsapp: $("#profWhatsapp").checked,
      notify_web: $("#profWeb").checked,
    });
    toast("Gespeichert");
  } catch (e) { toast(e.message, "err"); }
});

// ---- Boot ----
function loadAll() { loadToday(); }
applyAuth();
if (localStorage.getItem(TOKEN_KEY)) {
  loadAll();
}

// Service worker registration
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
