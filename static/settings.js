const READER_SETTINGS_KEY = "zefirki_reader_settings_v5";

const DEFAULT_SETTINGS = {
  readerMode: "standard",
  textAlign: "left",
  textColor: "#111111",
  readerBg: "#fffaf3",
  linkColor: "#2563eb",
  fontSize: "16",
  lineHeight: "1.6",
  paragraphSpacing: "16",

  tagMode: "list",
  tagColorScheme: "pastel",
  tagGrouping: "flat",

  siteTheme: "light",
  cardRadius: "16",
  cardShadow: "light",
  animations: "off",
  interfaceFont: "system",
  showFoxes: true,
};

function loadSettings() {
  const raw = localStorage.getItem(READER_SETTINGS_KEY);

  if (!raw) {
    return { ...DEFAULT_SETTINGS };
  }

  try {
    return { ...DEFAULT_SETTINGS, ...JSON.parse(raw) };
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}

function saveSettings(settings) {
  localStorage.setItem(READER_SETTINGS_KEY, JSON.stringify(settings));
}

let readerSettings = loadSettings();

function applySettings() {
  const root = document.documentElement;

  root.style.setProperty("--reader-text-color", readerSettings.textColor);
  root.style.setProperty("--reader-bg", readerSettings.readerBg);
  root.style.setProperty("--reader-link-color", readerSettings.linkColor);
  root.style.setProperty("--reader-font-size", `${readerSettings.fontSize}px`);
  root.style.setProperty("--reader-line-height", readerSettings.lineHeight);
  root.style.setProperty("--reader-paragraph-spacing", `${readerSettings.paragraphSpacing}px`);
  root.style.setProperty("--card-radius", `${readerSettings.cardRadius}px`);

  document.body.dataset.readerMode = readerSettings.readerMode;
  document.body.dataset.textAlign = readerSettings.textAlign;
  document.body.dataset.siteTheme = readerSettings.siteTheme;
  document.body.dataset.cardShadow = readerSettings.cardShadow;
  document.body.dataset.animations = readerSettings.animations;
  document.body.dataset.interfaceFont = readerSettings.interfaceFont;
  document.body.dataset.tagMode = readerSettings.tagMode;
  document.body.dataset.tagColorScheme = readerSettings.tagColorScheme;
  document.body.dataset.tagGrouping = readerSettings.tagGrouping;

  document.body.classList.toggle("hide-foxes", !readerSettings.showFoxes);
}

function updateSetting(key, value) {
  readerSettings[key] = value;
  saveSettings(readerSettings);
  applySettings();
}

function createSettingsPanel() {
  const panel = document.createElement("div");

  panel.innerHTML = `
    <button class="settings-fab" id="settingsFab" type="button" aria-label="Настройки">
      ⚙️
    </button>

    <div class="settings-overlay" id="settingsOverlay" hidden>
      <div class="settings-modal">
        <div class="settings-header">
          <div>
            <h2>Настройки</h2>
            <p>Все изменения сохраняются автоматически.</p>
          </div>
          <button class="settings-close" id="settingsClose" type="button" aria-label="Закрыть">×</button>
        </div>

        <div class="settings-tabs">
          <button class="settings-tab active" data-tab="reader">Читалка</button>
          <button class="settings-tab" data-tab="appearance">Внешний вид</button>
          <button class="settings-tab" data-tab="tags">Теги</button>
          <button class="settings-tab" data-tab="about">О проекте</button>
        </div>

        <div class="settings-content">
          <section class="settings-section active" data-section="reader">
            ${selectField("readerMode", "Режим чтения", [
              ["standard", "Стандартный"],
              ["center", "По центру"],
              ["wide", "На всю ширину"],
            ])}

            ${selectField("textAlign", "Выравнивание текста", [
              ["left", "По левому краю"],
              ["justify", "По ширине"],
            ])}

            ${presetAndColorField("textColor", "Цвет текста", [
              ["#111111", "Чёрный"],
              ["#333333", "Тёмно-серый"],
              ["#666666", "Серый"],
            ])}

            ${presetAndColorField("readerBg", "Цвет фона читалки", [
              ["#ffffff", "Белый"],
              ["#fffaf3", "Кремовый"],
              ["#f4ecd8", "Сепия"],
              ["#222222", "Тёмно-серый"],
              ["#000000", "Чёрный"],
            ])}

            ${presetAndColorField("linkColor", "Цвет ссылок", [
              ["#2563eb", "Синий"],
              ["#15803d", "Зелёный"],
              ["#f28c38", "Оранжевый"],
            ])}

            ${selectField("fontSize", "Размер шрифта", [
              ["14", "14px"],
              ["16", "16px"],
              ["18", "18px"],
              ["20", "20px"],
              ["22", "22px"],
              ["24", "24px"],
            ])}

            ${selectField("lineHeight", "Межстрочный интервал", [
              ["1.4", "1.4"],
              ["1.6", "1.6"],
              ["1.8", "1.8"],
              ["2.0", "2.0"],
            ])}

            ${selectField("paragraphSpacing", "Отступы между абзацами", [
              ["0", "0px"],
              ["8", "8px"],
              ["16", "16px"],
              ["24", "24px"],
            ])}
          </section>

          <section class="settings-section" data-section="appearance">
            ${selectField("siteTheme", "Тема сайта", [
              ["light", "Светлая"],
              ["dark", "Тёмная"],
              ["system", "Системная"],
              ["contrast", "Контрастная"],
            ])}

            ${selectField("cardRadius", "Скругление карточек", [
              ["0", "0px"],
              ["8", "8px"],
              ["16", "16px"],
              ["24", "24px"],
            ])}

            ${selectField("cardShadow", "Тени карточек", [
              ["none", "Без тени"],
              ["light", "Лёгкая"],
              ["medium", "Средняя"],
              ["deep", "Глубокая"],
            ])}

            ${selectField("animations", "Анимации", [
              ["off", "Отключены"],
            ])}

            ${selectField("interfaceFont", "Шрифт интерфейса", [
              ["system", "Системный"],
              ["sans", "Sans-serif"],
              ["serif", "Serif"],
              ["mono", "Monospace"],
            ])}

            ${checkboxField("showFoxes", "Показывать лисичек")}
          </section>

          <section class="settings-section" data-section="tags">
            ${selectField("tagMode", "Отображение тегов", [
              ["list", "Обычный список"],
              ["cloud", "Облако тегов"],
            ])}

            ${selectField("tagColorScheme", "Цветовая схема тегов", [
              ["pastel", "Пастельная"],
              ["mono", "Монохромная"],
              ["contrast", "Контрастная"],
            ])}

            ${selectField("tagGrouping", "Группировка тегов", [
              ["flat", "Плоский список"],
              ["grouped", "По категориям"],
            ])}
          </section>

          <section class="settings-section" data-section="about">
            <div class="about-box">
              <img class="about-fox" src="/static/fox_hearts.png" alt="Лисичка" data-fox>
              <h3>Зефиркины баоцзы</h3>
              <p>
                Мини-читалка переводов с настройками чтения и уютными лисичками.
              </p>

              <div class="about-links">
                <a href="https://t.me/" target="_blank" rel="noopener noreferrer">Telegram</a>
                <a href="https://boosty.to/" target="_blank" rel="noopener noreferrer">Boosty</a>
                <a href="https://www.bllate.pro/" target="_blank" rel="noopener noreferrer">BLlate</a>
              </div>
            </div>
          </section>
        </div>

        <div class="settings-footer">
          <button class="settings-reset" id="settingsReset" type="button">
            Сбросить настройки
          </button>
        </div>
      </div>
    </div>
  `;

  document.body.appendChild(panel);

  bindSettingsPanel();
  fillSettingsControls();
}

function selectField(key, label, options) {
  return `
    <label class="settings-field">
      <span>${label}</span>
      <select data-setting="${key}">
        ${options.map(([value, text]) => `<option value="${value}">${text}</option>`).join("")}
      </select>
    </label>
  `;
}

function presetAndColorField(key, label, options) {
  return `
    <label class="settings-field">
      <span>${label}</span>
      <select data-setting="${key}" data-color-select="${key}">
        ${options.map(([value, text]) => `<option value="${value}">${text}</option>`).join("")}
        <option value="custom">Пользовательский</option>
      </select>
      <input type="color" data-setting="${key}" data-color-picker="${key}" />
    </label>
  `;
}

function checkboxField(key, label) {
  return `
    <label class="settings-check">
      <input type="checkbox" data-setting="${key}" />
      <span>${label}</span>
    </label>
  `;
}

function fillSettingsControls() {
  document.querySelectorAll("[data-setting]").forEach(control => {
    const key = control.dataset.setting;

    if (control.type === "checkbox") {
      control.checked = Boolean(readerSettings[key]);
      return;
    }

    if (control.dataset.colorPicker) {
      control.value = readerSettings[key];
      return;
    }

    if (control.dataset.colorSelect) {
      const hasOption = Array.from(control.options).some(
        option => option.value === readerSettings[key]
      );

      control.value = hasOption ? readerSettings[key] : "custom";
      return;
    }

    control.value = readerSettings[key];
  });
}

function bindSettingsPanel() {
  const overlay = document.getElementById("settingsOverlay");
  const fab = document.getElementById("settingsFab");
  const close = document.getElementById("settingsClose");
  const reset = document.getElementById("settingsReset");

  fab.addEventListener("click", () => {
    overlay.hidden = false;
  });

  close.addEventListener("click", () => {
    overlay.hidden = true;
  });

  overlay.addEventListener("click", event => {
    if (event.target === overlay) {
      overlay.hidden = true;
    }
  });

  document.addEventListener("keydown", event => {
    if (event.key === "Escape") {
      overlay.hidden = true;
    }
  });

  document.querySelectorAll(".settings-tab").forEach(tab => {
    tab.addEventListener("click", () => {
      const tabName = tab.dataset.tab;

      document.querySelectorAll(".settings-tab").forEach(item => {
        item.classList.toggle("active", item === tab);
      });

      document.querySelectorAll(".settings-section").forEach(section => {
        section.classList.toggle("active", section.dataset.section === tabName);
      });
    });
  });

  document.querySelectorAll("[data-setting]").forEach(control => {
    control.addEventListener("input", () => handleSettingControl(control));
    control.addEventListener("change", () => handleSettingControl(control));
  });

  reset.addEventListener("click", () => {
    const confirmed = confirm("Сбросить все настройки к стандартным?");

    if (!confirmed) return;

    readerSettings = { ...DEFAULT_SETTINGS };
    saveSettings(readerSettings);
    fillSettingsControls();
    applySettings();
  });
}

function handleSettingControl(control) {
  const key = control.dataset.setting;

  if (control.type === "checkbox") {
    updateSetting(key, control.checked);
    return;
  }

  if (control.dataset.colorSelect) {
    if (control.value === "custom") {
      const picker = document.querySelector(`[data-color-picker="${key}"]`);
      updateSetting(key, picker.value);
    } else {
      updateSetting(key, control.value);

      const picker = document.querySelector(`[data-color-picker="${key}"]`);
      if (picker) picker.value = control.value;
    }

    return;
  }

  if (control.dataset.colorPicker) {
    updateSetting(key, control.value);
    fillSettingsControls();
    return;
  }

  updateSetting(key, control.value);
}

document.addEventListener("DOMContentLoaded", () => {
  createSettingsPanel();
  applySettings();
});
