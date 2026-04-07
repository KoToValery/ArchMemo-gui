// ArchiMemo — popup.js

const SPECIALTY_COLORS = {
  "ЕЛ":          "badge-el",
  "ВиК":         "badge-vik",
  "ОВК":         "badge-ovk",
  "КОНСТРУКЦИИ": "badge-kon",
  "КС":          "badge-ks",
  "ПБ":          "badge-pb",
  "ВЕРТИКАЛНА":  "badge-vert",
};

function badgeClass(specialty) {
  return SPECIALTY_COLORS[specialty] || "badge-def";
}

let pending = null;

async function init() {
  const data = await messenger.storage.local.get("pending");
  pending = data.pending;
  if (!pending) { window.close(); return; }

  // Специалности
  const specEl = document.getElementById("specialties");
  pending.specialties.forEach(s => {
    const span = document.createElement("span");
    span.className = `badge ${badgeClass(s.specialty)}`;
    span.textContent = `${s.specialty} (${s.name})`;
    specEl.appendChild(span);
  });

  // Файлове
  const listEl = document.getElementById("fileList");
  pending.dwgFiles.forEach(f => {
    const li = document.createElement("li");
    li.textContent = "📄 " + f;
    listEl.appendChild(li);
  });
}

// Запиши
document.getElementById("btnSave").addEventListener("click", async () => {
  const date = pending.date;
  const log = {};

  for (const s of pending.specialties) {
    const key = `${s.specialty}__${s.name}`;
    log[key] = {
      specialty: s.specialty,
      engineer:  s.name,
      email:     s.email || "",
      sends:     [{ date, files: [...pending.dwgFiles] }],
    };
  }

  // Download
  const blob = new Blob([JSON.stringify(log, null, 2)], { type: "application/json" });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");
  a.href     = url;
  a.download = `podlozhki_${date}.json`;
  a.click();
  URL.revokeObjectURL(url);

  await messenger.storage.local.remove("pending");
  setTimeout(() => window.close(), 1000);
});

// Пропусни
document.getElementById("btnSkip").addEventListener("click", async () => {
  await messenger.storage.local.remove("pending");
  window.close();
});

init();
