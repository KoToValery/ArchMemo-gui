// ArchiMemo — background.js
// Слуша onAfterSend, проверява .dwg прикачени + специалности, отваря popup.

const SPECIALTY_EMAILS = [
  { email: "lachezar.tzvetkov@gmail.com", name: "Лъчо",         specialty: "ЕЛ" },
  { email: "astra.v@abv.bg",              name: "Веска",         specialty: "ВиК" },
  { email: "milena_mdg@mail.bg",          name: "Милена",        specialty: "ВиК" },
  { email: "mihailborkovtodorov@gmail.com",name: "Мишо Тодоров", specialty: "ВиК" },
  { email: "ingilizova_ov@abv.bg",        name: "Юлия",          specialty: "ОВК" },
  { email: "v_tunev@abv.bg",              name: "Тунев",         specialty: "КОНСТРУКЦИИ" },
  { email: "universproekt@abv.bg",        name: "Пламен",        specialty: "КОНСТРУКЦИИ" },
  { email: "kvmihov@gmail.com",           name: "Михов",         specialty: "ВЕРТИКАЛНА" },
  { email: "gandjov@yahoo.com",           name: "Ганджов",       specialty: "КОНСТРУКЦИИ" },
  { email: "gandjov@gmail.com",           name: "Ганджов",       specialty: "КОНСТРУКЦИИ" },
  { email: "spas_zv@mail.bg",             name: "Звънчаров",     specialty: "КОНСТРУКЦИИ" },
  { email: "spaska.ruycheva@abv.bg",      name: "Руйчева",       specialty: "КОНСТРУКЦИИ" },
  { email: "kaleti@abv.bg",               name: "Любина",        specialty: "КС" },
  { email: "pantev@nola7.com",            name: "Нола7",         specialty: "Nola7" },
  { email: "kostadintosev@gmail.com",     name: "Koto",          specialty: "Dev" },
  { email: "fire_trading@abv.bg",         name: "Марценков",     specialty: "ПБ" },
];

// Нормализира имейл адрес — маха display name, < >, интервали, lowercase
function normalizeEmail(raw) {
  const m = raw.match(/<([^>]+)>/);
  return (m ? m[1] : raw).trim().toLowerCase();
}

// Събира всички получатели от To, CC, BCC
function collectRecipients(msg) {
  const fields = [
    ...(msg.recipients || []),
    ...(msg.ccList    || []),
    ...(msg.bccList   || []),
  ];
  return fields.map(normalizeEmail);
}

// Проверява прикачени файлове за .dwg
async function getDwgAttachments(messageId) {
  const parts = await messenger.messages.listAttachments(messageId);
  return parts
    .filter(p => p.name && p.name.toLowerCase().endsWith(".dwg"))
    .map(p => p.name);
}

// Основен handler
messenger.messages.onNewMailReceived;  // не е нужен — ползваме compose

// Thunderbird MV3 — onAfterSend е в compose API
messenger.compose.onAfterSend.addListener(async (tab, sendInfo) => {
  console.log("ArchiMemo: onAfterSend triggered", sendInfo);
  try {
    const msgId = sendInfo.messages?.[0]?.id;
    if (!msgId) {
      console.log("ArchiMemo: No message ID");
      return;
    }

    const msg  = await messenger.messages.get(msgId);
    console.log("ArchiMemo: Message", msg);
    
    const dwgs = await getDwgAttachments(msgId);
    console.log("ArchiMemo: DWG attachments", dwgs);
    if (dwgs.length === 0) {
      console.log("ArchiMemo: No DWG files, skipping");
      return;
    }

    const recipients = collectRecipients(msg);
    console.log("ArchiMemo: Recipients", recipients);
    
    const matched = SPECIALTY_EMAILS.filter(se =>
      recipients.includes(se.email.toLowerCase())
    );
    console.log("ArchiMemo: Matched specialties", matched);
    if (matched.length === 0) {
      console.log("ArchiMemo: No specialty matches, skipping");
      return;
    }

    // Дедупликация — ако един инженер е в To и CC
    const seen = new Set();
    const unique = matched.filter(m => {
      const key = `${m.specialty}__${m.name}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });

    console.log("ArchiMemo: Unique specialties", unique);

    // Запази данните и отвори popup
    await messenger.storage.local.set({
      pending: {
        dwgFiles:    dwgs,
        specialties: unique,
        date:        new Date().toISOString().slice(0, 10),
      }
    });

    console.log("ArchiMemo: Opening popup");
    await messenger.windows.create({
      url:    "popup/popup.html",
      type:   "popup",
      width:  520,
      height: 560,
    });

  } catch (err) {
    console.error("ArchiMemo background error:", err);
  }
});
