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
    // Admin tab only visible to admin users
    $("#tabAdminBtn").classList.toggle("hidden", !u.is_admin);
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
  if (name === "admin")    loadAdmin();
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
      const us = e.user_supplement || {};
      const name = us.supplement_name || `Supplement #${e.user_supplement_id}`;
      const cat = us.supplement_category || "";
      return `
        <div class="row-card rounded-xl p-4 flex items-center gap-3" data-intake="${e.id}">
          <div class="text-2xl font-bold tabular-nums w-14 text-center">${time}</div>
          <div class="flex-1">
            <div class="font-semibold">${name}</div>
            ${cat ? `<div class="text-xs text-slate-500 uppercase">${cat}</div>` : ""}
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
    <div class="block">
      <div class="flex items-center justify-between mb-1">
        <span class="text-sm text-slate-400">Einnahmezeiten</span>
        <button id="mAddTime" type="button"
                class="text-xs px-2 py-1 rounded bg-slate-700 hover:bg-slate-600 text-slate-200">
          + Uhrzeit
        </button>
      </div>
      <div id="mSchedule" class="space-y-2"></div>
    </div>
    <label class="block">
      <span class="text-sm text-slate-400">Notizen</span>
      <textarea id="mNotes" rows="2"
                class="mt-1 w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-700"></textarea>
    </label>
    <button id="mSave" class="w-full py-2 rounded-lg bg-brand-500 hover:bg-brand-600 font-semibold">Speichern</button>
  `;
  $("#modal").classList.remove("hidden");

  // Add one empty time slot to start
  const addTimeSlot = (value = "08:00") => {
    const row = document.createElement("div");
    row.className = "flex items-center gap-2";
    row.innerHTML = `
      <input type="time" value="${value}"
             class="m-time flex-1 px-3 py-2 rounded-lg bg-slate-800 border border-slate-700
                    focus:outline-none focus:ring-2 focus:ring-brand-500" />
      <button type="button" class="m-time-rm text-slate-400 hover:text-rose-400 px-2 py-1">✕</button>
    `;
    row.querySelector(".m-time-rm").addEventListener("click", () => {
      if ($("#mSchedule").children.length > 1) row.remove();
      else toast("Mindestens eine Uhrzeit nötig (oder leer = keine Reminder)", "warn");
    });
    $("#mSchedule").appendChild(row);
  };
  addTimeSlot();
  $("#mAddTime").addEventListener("click", () => addTimeSlot());

  $("#mSave").addEventListener("click", async () => {
    const schedule = $$("#mSchedule .m-time")
      .map(i => i.value)
      .filter(v => /^\d{2}:\d{2}$/.test(v));
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

$("#addCatalogBtn").addEventListener("click", () => openCreateCatalogModal());

function openCreateCatalogModal() {
  $("#modalTitle").textContent = "Neues Supplement im Katalog";
  $("#modalBody").innerHTML = `
    <p class="text-sm text-slate-400">
      Lege ein neues Supplement im globalen Katalog an. Steht danach allen Usern zur Verfügung.
    </p>
    <label class="block">
      <span class="text-sm text-slate-400">Name *</span>
      <input id="cName" type="text" required placeholder="z.B. Ashwagandha KSM-66"
             class="mt-1 w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-700" />
    </label>
    <label class="block">
      <span class="text-sm text-slate-400">Slug (URL-Identifier, nur Kleinbuchstaben + Bindestriche) *</span>
      <input id="cSlug" type="text" required placeholder="ashwagandha-ksm-66"
             pattern="[a-z0-9]+(-[a-z0-9]+)*"
             class="mt-1 w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-700" />
    </label>
    <div class="grid sm:grid-cols-2 gap-3">
      <label class="block">
        <span class="text-sm text-slate-400">Kategorie</span>
        <select id="cCategory" class="mt-1 w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-700">
          <option value="vitamin">Vitamin</option>
          <option value="mineral">Mineral</option>
          <option value="amino">Aminosäure</option>
          <option value="nootropic">Nootropikum</option>
          <option value="adaptogen">Adaptogen</option>
          <option value="omega">Omega-Fettsäure</option>
          <option value="herb">Kräuter</option>
          <option value="other" selected>Andere</option>
        </select>
      </label>
      <label class="block">
        <span class="text-sm text-slate-400">Standard-Einheit</span>
        <select id="cUnit" class="mt-1 w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-700">
          <option value="mg">mg</option>
          <option value="g">g</option>
          <option value="mcg">mcg</option>
          <option value="IU">IU</option>
          <option value="ml">ml</option>
          <option value="cup">Tasse</option>
        </select>
      </label>
    </div>
    <div class="grid sm:grid-cols-2 gap-3">
      <label class="block">
        <span class="text-sm text-slate-400">Dosis pro kg (optional)</span>
        <input id="cDosePerKg" type="number" step="0.001" min="0"
               class="mt-1 w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-700" />
      </label>
      <label class="block">
        <span class="text-sm text-slate-400">Halbwertszeit (h, optional)</span>
        <input id="cHalfLife" type="number" step="0.1" min="0"
               class="mt-1 w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-700" />
      </label>
    </div>
    <div class="grid sm:grid-cols-2 gap-3">
      <label class="flex items-center gap-2 text-sm">
        <input id="cWithFood" type="checkbox" class="accent-brand-500" />
        Mit Mahlzeit einnehmen
      </label>
      <label class="flex items-center gap-2 text-sm">
        <input id="cEmptyStomach" type="checkbox" class="accent-brand-500" />
        Auf nüchternen Magen
      </label>
    </div>
    <label class="block">
      <span class="text-sm text-slate-400">Notizen</span>
      <textarea id="cNotes" rows="2"
                class="mt-1 w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-700"></textarea>
    </label>
    <button id="cSave" class="w-full py-2 rounded-lg bg-brand-500 hover:bg-brand-600 font-semibold">Anlegen</button>
  `;
  $("#modal").classList.remove("hidden");

  // Auto-fill slug from name (until user edits slug manually)
  const nameEl = $("#cName"), slugEl = $("#cSlug");
  let slugTouched = false;
  slugEl.addEventListener("input", () => { slugTouched = true; });
  nameEl.addEventListener("input", () => {
    if (!slugTouched) {
      slugEl.value = nameEl.value
        .toLowerCase()
        .normalize("NFD").replace(/[\u0300-\u036f]/g, "")  // strip diacritics
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "");
    }
  });

  $("#cSave").addEventListener("click", async () => {
    const name = $("#cName").value.trim();
    const slug = $("#cSlug").value.trim();
    if (!name || !slug) {
      toast("Name und Slug sind Pflichtfelder", "err");
      return;
    }
    try {
      await api.post("/supplements", {
        name,
        slug,
        category: $("#cCategory").value,
        default_unit: $("#cUnit").value,
        default_dose_per_kg: $("#cDosePerKg").value ? parseFloat($("#cDosePerKg").value) : null,
        half_life_hours: $("#cHalfLife").value ? parseFloat($("#cHalfLife").value) : null,
        best_taken_with_food: $("#cWithFood").checked,
        best_taken_empty_stomach: $("#cEmptyStomach").checked,
        notes: $("#cNotes").value || null,
      });
      toast("Angelegt");
      $("#modal").classList.add("hidden");
      loadCatalog();
    } catch (e) { toast(e.message, "err"); }
  });
}

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

// ---- Admin: bot configuration ----
const BOT_DEFS = {
  discord: {
    label: "Discord",
    icon: "🎮",
    color: "indigo",
    desc: "Bot-Token, Channel-ID und optional erlaubte User-IDs für Inline-Buttons.",
    fields: [
      { id: "bot_token",   label: "Bot-Token",           type: "password", placeholder: "aus Discord Developer Portal" },
      { id: "channel_id",  label: "Channel-ID (optional)",type: "text",     placeholder: "leer = DM an User" },
      { id: "guild_id",    label: "Guild-ID (optional)",  type: "text",     placeholder: "nur für Diagnose" },
      { id: "allowed_users",label: "Erlaubte User-IDs",   type: "text",     placeholder: "Komma-getrennt; leer = alle im Channel" },
    ],
  },
  telegram: {
    label: "Telegram",
    icon: "✈️",
    color: "sky",
    desc: "Bot-Token (BotFather) und Chat-IDs, an die Reminder gehen.",
    fields: [
      { id: "bot_token",     label: "Bot-Token",           type: "password", placeholder: "von @BotFather" },
      { id: "allowed_chats", label: "Erlaubte Chat-IDs",   type: "text",     placeholder: "Komma-getrennt; leer = broadcast an alle konfigurierten" },
    ],
  },
  whatsapp: {
    label: "WhatsApp (CallMeBot)",
    icon: "📱",
    color: "emerald",
    desc: "Plain-Text-Erinnerungen via CallMeBot-Gateway. Keine Buttons.",
    fields: [
      { id: "phone",  label: "Telefonnummer (mit Ländervorwahl)", type: "text", placeholder: "z.B. 491701234567" },
      { id: "apikey", label: "CallMeBot API-Key",                 type: "password", placeholder: "per WhatsApp von CallMeBot zugeschickt" },
    ],
  },
};

function statusDot(status) {
  const colors = {
    running: "bg-emerald-400",
    stopped: "bg-slate-500",
    error:   "bg-rose-500",
    unknown: "bg-amber-400",
  };
  const label = {
    running: "läuft",
    stopped: "gestoppt",
    error:   "Fehler",
    unknown: "unbekannt",
  };
  return `<span class="inline-flex items-center gap-1.5 text-xs">
    <span class="inline-block w-2 h-2 rounded-full ${colors[status] || "bg-slate-500"}"></span>
    ${label[status] || status}
  </span>`;
}

async function loadAdmin() {
  const box = $("#adminBots");
  box.innerHTML = `<div class="text-slate-500 text-sm">Lädt…</div>`;
  const bots = await Promise.all(
    Object.keys(BOT_DEFS).map(name => api.get(`/admin/bots/${name}`).catch(e => ({ name, error: e.message })))
  );
  box.innerHTML = bots.map(b => renderBotCard(b)).join("");
  // Wire buttons
  Object.keys(BOT_DEFS).forEach(name => {
    const card = box.querySelector(`[data-bot="${name}"]`);
    if (!card) return;
    card.querySelector(".a-save")?.addEventListener("click", () => saveBot(name));
    card.querySelector(".a-restart")?.addEventListener("click", () => restartBot(name));
    card.querySelector(".a-reset")?.addEventListener("click", () => resetBot(name));
    card.querySelector(".a-enabled")?.addEventListener("change", e => {
      card.querySelector(".a-fields").classList.toggle("opacity-50", !e.target.checked);
    });
    // Initial opacity state
    const en = card.querySelector(".a-enabled");
    if (en && !en.checked) card.querySelector(".a-fields").classList.add("opacity-50");
  });
}

function renderBotCard(b) {
  const def = BOT_DEFS[b.name];
  if (!def) return "";
  if (b.error) {
    return `<div class="row-card rounded-xl p-4">
      <div class="font-semibold">${def.label}</div>
      <div class="text-rose-400 text-sm">${b.error}</div>
    </div>`;
  }
  const statusLine = b.runtime_message
    ? `<span class="text-xs text-rose-400 ml-2">${b.runtime_message}</span>`
    : "";
  const source = b.is_db_override
    ? `<span class="text-xs px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300">aus DB</span>`
    : `<span class="text-xs px-2 py-0.5 rounded bg-slate-700 text-slate-300">aus .env</span>`;
  const enabled = !!b.enabled;
  const fields = def.fields.map(f => `
    <label class="block">
      <span class="text-xs text-slate-400">${f.label}</span>
      <input data-field="${f.id}" type="${f.type}" value="${(b[f.id] || "").replace(/"/g, "&quot;")}"
             placeholder="${f.placeholder || ""}"
             class="mt-1 w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-700
                    focus:outline-none focus:ring-2 focus:ring-brand-500 font-mono text-sm" />
    </label>
  `).join("");

  return `
    <div class="row-card rounded-xl p-4 space-y-3" data-bot="${b.name}">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <span class="text-xl">${def.icon}</span>
          <span class="font-semibold">${def.label}</span>
          ${source}
          <span class="ml-2">${statusDot(b.runtime_status)}</span>${statusLine}
        </div>
        <label class="flex items-center gap-2 text-sm">
          <span class="text-slate-400">Aktiv</span>
          <input type="checkbox" class="a-enabled accent-brand-500" ${enabled ? "checked" : ""} />
        </label>
      </div>
      <p class="text-xs text-slate-400">${def.desc}</p>
      <div class="a-fields space-y-3">${fields}</div>
      <div class="flex flex-wrap gap-2 pt-2">
        <button class="a-save px-3 py-1.5 bg-brand-500 hover:bg-brand-600 rounded-lg text-sm font-semibold">Speichern & neu starten</button>
        <button class="a-restart px-3 py-1.5 bg-slate-700 hover:bg-slate-600 rounded-lg text-sm">Neu starten</button>
        ${b.is_db_override ? `<button class="a-reset px-3 py-1.5 text-rose-400 hover:bg-rose-500/20 rounded-lg text-sm">DB-Werte löschen (.env nutzen)</button>` : ""}
      </div>
      ${b.updated_at ? `<div class="text-xs text-slate-500">Zuletzt geändert: ${new Date(b.updated_at).toLocaleString("de-DE")}</div>` : ""}
    </div>
  `;
}

async function saveBot(name) {
  const card = $(`[data-bot="${name}"]`);
  if (!card) return;
  const body = {
    enabled: card.querySelector(".a-enabled").checked,
    bot_token:    card.querySelector('[data-field="bot_token"]')?.value || null,
    channel_id:   card.querySelector('[data-field="channel_id"]')?.value || null,
    guild_id:     card.querySelector('[data-field="guild_id"]')?.value || null,
    allowed_users:card.querySelector('[data-field="allowed_users"]')?.value || null,
    allowed_chats:card.querySelector('[data-field="allowed_chats"]')?.value || null,
    phone:        card.querySelector('[data-field="phone"]')?.value || null,
    apikey:       card.querySelector('[data-field="apikey"]')?.value || null,
  };
  // Strip nulls to defaults - route ignores null vs empty anyway
  try {
    const updated = await api.put(`/admin/bots/${name}`, body);
    toast(`Bot ${name} aktualisiert`, "ok");
    renderBotInPlace(updated);
  } catch (e) {
    toast(e.message, "err");
  }
}

async function restartBot(name) {
  try {
    const updated = await api.post(`/admin/bots/${name}/restart`);
    toast(`Bot ${name} neu gestartet`, "ok");
    renderBotInPlace(updated);
  } catch (e) {
    toast(e.message, "err");
  }
}

async function resetBot(name) {
  if (!confirm(`DB-Überschreibung für ${name} löschen? Der Bot nutzt dann wieder die .env-Werte.`)) return;
  try {
    const updated = await api.del(`/admin/bots/${name}`);
    toast(`Bot ${name} zurückgesetzt`, "ok");
    renderBotInPlace(updated);
  } catch (e) {
    toast(e.message, "err");
  }
}

function renderBotInPlace(b) {
  const card = $(`[data-bot="${b.name}"]`);
  if (!card) return;
  const tmp = document.createElement("div");
  tmp.innerHTML = renderBotCard(b);
  const fresh = tmp.firstElementChild;
  card.replaceWith(fresh);
  // Re-wire buttons
  fresh.querySelector(".a-save")?.addEventListener("click", () => saveBot(b.name));
  fresh.querySelector(".a-restart")?.addEventListener("click", () => restartBot(b.name));
  fresh.querySelector(".a-reset")?.addEventListener("click", () => resetBot(b.name));
  fresh.querySelector(".a-enabled")?.addEventListener("change", e => {
    fresh.querySelector(".a-fields").classList.toggle("opacity-50", !e.target.checked);
  });
  const en = fresh.querySelector(".a-enabled");
  if (en && !en.checked) fresh.querySelector(".a-fields").classList.add("opacity-50");
}


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
