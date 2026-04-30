// ArchiMemo — options.js
// Управление на имейл адресите за разпознаване на специалности

const SPECIALTY_COLORS = {
  "ЕЛ":          "badge-el",
  "ВиК":         "badge-vik",
  "ОВК":         "badge-ovk",
  "КОНСТРУКЦИИ": "badge-kon",
  "КС":          "badge-ks",
  "ПБ":          "badge-pb",
  "ВЕРТИКАЛНА":  "badge-vert",
  "Озеленяване": "badge-def",
  "ТЕХНОЛОГ":    "badge-def",
  "ПЪТНО":       "badge-def",
  "АСАНСЬОР":    "badge-def",
  "Nola7":       "badge-def",
  "Dev":         "badge-def",
};

const STORAGE_KEY = "specialty_emails";

// Зарежда имейлите от storage
async function loadEmails() {
  const result = await messenger.storage.sync.get(STORAGE_KEY);
  return result[STORAGE_KEY] || [];
}

// Запазва имейлите в storage
async function saveEmails(emails) {
  await messenger.storage.sync.set({ [STORAGE_KEY]: emails });
}

// Връща CSS клас за бейдж според специалността
function badgeClass(specialty) {
  return SPECIALTY_COLORS[specialty] || "badge-def";
}

// Рендерира списъка с имейли
async function renderEmails() {
  const listEl = document.getElementById("emailList");
  const emails = await loadEmails();

  if (emails.length === 0) {
    listEl.innerHTML = '<div class="empty-state">Няма добавени имейли. Добавете първия от формата горе.</div>';
    return;
  }

  listEl.innerHTML = "";
  emails.forEach((item, index) => {
    const div = document.createElement("div");
    div.className = "email-item";
    div.innerHTML = `
      <div class="email-info">
        <div class="email-address">
          ${escapeHtml(item.email)}
          <span class="badge ${badgeClass(item.specialty)}">${escapeHtml(item.specialty)}</span>
        </div>
        <div class="email-meta">${escapeHtml(item.name || "—")}</div>
      </div>
      <button class="btn btn-danger" data-index="${index}">Изтрий</button>
    `;
    listEl.appendChild(div);
  });

  // Закачаме event listeners за бутоните за изтриване
  listEl.querySelectorAll(".btn-danger").forEach(btn => {
    btn.addEventListener("click", async (e) => {
      const index = parseInt(e.target.dataset.index, 10);
      await deleteEmail(index);
    });
  });
}

// Добавя нов имейл
async function addEmail() {
  const emailInput = document.getElementById("newEmail");
  const nameInput = document.getElementById("newName");
  const specialtyInput = document.getElementById("newSpecialty");
  const statusEl = document.getElementById("statusMsg");

  const email = emailInput.value.trim().toLowerCase();
  const name = nameInput.value.trim();
  const specialty = specialtyInput.value;

  // Валидация
  if (!email || !email.includes("@")) {
    showStatus("Моля, въведете валиден имейл адрес.", "error");
    return;
  }
  if (!name) {
    showStatus("Моля, въведете име.", "error");
    return;
  }

  const emails = await loadEmails();

  // Проверка за дублиране
  if (emails.some(e => e.email === email)) {
    showStatus("Този имейл вече съществува в списъка.", "error");
    return;
  }

  // Добавяне
  emails.push({ email, name, specialty });
  await saveEmails(emails);

  // Изчистване на формата
  emailInput.value = "";
  nameInput.value = "";
  specialtyInput.value = "ЕЛ";

  showStatus(`Имейлът ${email} беше добавен успешно.`, "success");
  await renderEmails();
}

// Изтрива имейл по индекс
async function deleteEmail(index) {
  const emails = await loadEmails();
  if (index < 0 || index >= emails.length) return;

  const removed = emails.splice(index, 1)[0];
  await saveEmails(emails);

  showStatus(`Имейлът ${removed.email} беше премахнат.`, "success");
  await renderEmails();
}

// Показва статус съобщение
function showStatus(message, type) {
  const statusEl = document.getElementById("statusMsg");
  statusEl.textContent = message;
  statusEl.className = `status-msg ${type}`;
  setTimeout(() => {
    statusEl.className = "status-msg";
  }, 3000);
}

// Escape HTML за сигурност
function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

// Инициализация
document.addEventListener("DOMContentLoaded", () => {
  renderEmails();

  document.getElementById("btnAdd").addEventListener("click", addEmail);

  // Enter key в полетата
  document.getElementById("newEmail").addEventListener("keypress", (e) => {
    if (e.key === "Enter") addEmail();
  });
  document.getElementById("newName").addEventListener("keypress", (e) => {
    if (e.key === "Enter") addEmail();
  });
});
