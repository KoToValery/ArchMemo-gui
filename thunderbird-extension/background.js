// ArchiMemo — background.js
// Слуша onAfterSend, проверява .dwg прикачени + специалности, отваря popup.

const STORAGE_KEY = "specialty_emails";

// Default имейли — зареждат се при първо стартиране или ако storage е празен
const DEFAULT_SPECIALTY_EMAILS = [
  { email: "lachezar.tzvetkov@gmail.com", name: "Лъчо",          specialty: "ЕЛ" },
  { email: "chikalov.eood@abv.bg",        name: "Чикалов",       specialty: "ЕЛ" },
  { email: "astra.v@abv.bg",              name: "Веска",         specialty: "ВиК" },
  { email: "milena_mdg@mail.bg",          name: "Милена",        specialty: "ВиК" },
  { email: "mihailborkovtodorov@gmail.com",name: "Мишо Тодоров", specialty: "ВиК" },
  { email: "ingilizova_ov@abv.bg",        name: "Юлия",          specialty: "ОВК" },
  { email: "amitev@abv.bg",               name: "Сашо Митев",    specialty: "ОВК" },
  { email: "v_tunev@abv.bg",              name: "Тунев",         specialty: "КОНСТРУКЦИИ" },
  { email: "universproekt@abv.bg",        name: "Пламен",        specialty: "КОНСТРУКЦИИ" },
  { email: "gandjov@yahoo.com",           name: "Ганджов",       specialty: "КОНСТРУКЦИИ" },
  { email: "gandjov@gmail.com",           name: "Ганджов",       specialty: "КОНСТРУКЦИИ" },
  { email: "spas_zv@mail.bg",             name: "Звънчаров",     specialty: "КОНСТРУКЦИИ" },
  { email: "spaska.ruycheva@abv.bg",      name: "Руйчева",       specialty: "КОНСТРУКЦИИ" },
  { email: "vanya_orbelus@abv.bg",        name: "Ваня Орбелус",  specialty: "КОНСТРУКЦИИ" },
  { email: "kvmihov@gmail.com",           name: "Михов",         specialty: "ВЕРТИКАЛНА" },
  { email: "mapgeo@abv.bg",               name: "Пиргов",        specialty: "ВЕРТИКАЛНА" },
  { email: "milko7920@gmail.com",         name: "Милко",         specialty: "ВЕРТИКАЛНА" },
  { email: "gd2000@abv.bg",               name: "gd2000@abv.bg", specialty: "ВЕРТИКАЛНА" },
  { email: "popgavrilov@yahoo.com",       name: "Попгаврилов",   specialty: "ВЕРТИКАЛНА" },
  { email: "venang@abv.bg",               name: "В.Ангелов", specialty: "ВЕРТИКАЛНА" },
  { email: "mapgeo_ban@abv.bg",           name: "Г.Гърменов",    specialty: "ВЕРТИКАЛНА" },
  { email: "geocorrect_razlog@abv.bg",    name: "geocorrect_razlog@abv.bg", specialty: "ВЕРТИКАЛНА" },
  { email: "geokadpreciz@abv.bg",         name: "geokadpreciz@abv.bg",      specialty: "ВЕРТИКАЛНА" },
  { email: "geomap_geomap@mail.bg",       name: "geomap_geomap@mail.bg",    specialty: "ВЕРТИКАЛНА" },
  { email: "fire_trading@abv.bg",         name: "Марценков",     specialty: "ПБ" },
  { email: "nikola_kiuchukov@abv.bg",     name: "Кючуков",       specialty: "ПБ" },
  { email: "kaleti@abv.bg",               name: "Любина",        specialty: "КС" },
  { email: "stip46@abv.bg",               name: "И.Петров",      specialty: "КС" },
  { email: "ventsi.andonov@abv.bg",        name: "В.Андонов",     specialty: "Озеленяване" },
  { email: "pantev@nola7.com",            name: "Нола7",         specialty: "Nola7" },
  { email: "kazakov@nola7.com",           name: "Нола7",         specialty: "Nola7" },
  { email: "nola7blagoevgrad@nola7.com",  name: "Нола7",         specialty: "Nola7" },
  { email: "k.danov@intratechstudio.com", name: "Данов",         specialty: "ТЕХНОЛОГ" },
  { email: "dvn_proekt@mail.bg",          name: "Митко пътно",   specialty: "ПЪТНО" },
  { email: "petko.shopov@gmail.com",      name: "Шопов пътно",   specialty: "ПЪТНО" },
  { email: "ottiss@mail.bg",              name: "ottiss@mail.bg", specialty: "АСАНСьОР" },
  { email: "kostadintosev@gmail.com",     name: "Koto",          specialty: "Dev" },

];

// Зарежда имейлите от storage — ако няма нищо записано, записва defaults
async function loadSpecialtyEmails() {
  const result = await messenger.storage.sync.get(STORAGE_KEY);
  let emails = result[STORAGE_KEY];

  if (!emails || !Array.isArray(emails) || emails.length === 0) {
    // Първо стартиране — записваме defaults
    await messenger.storage.sync.set({ [STORAGE_KEY]: DEFAULT_SPECIALTY_EMAILS });
    console.log("ArchiMemo: Initialized storage with default emails");
    return DEFAULT_SPECIALTY_EMAILS;
  }

  return emails;
}

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

    // Зареждаме имейлите от storage
    const specialtyEmails = await loadSpecialtyEmails();
    console.log("ArchiMemo: Loaded emails from storage", specialtyEmails.length);

    const matched = specialtyEmails.filter(se =>
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
