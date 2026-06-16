const READER_SETTINGS_KEY = "zefirki_reader_settings_v6";
const SPOILER_WARNING_DISABLED_KEY = "zefirki_spoiler_warning_disabled_v1";

const DEFAULT_SETTINGS = {
  readerWidth: "full",
  textAlign: "left",
  textColor: "#111111",
  readerBg: "#fffaf3",
  fontSize: "16",
  lineHeight: "1.6",
  paragraphSpacing: "16",

  siteTheme: "light",
  cardRadius: "16",
  showFoxes: true,
  spoilerWarning: true,
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
  root.style.setProperty("--reader-font-size", `${readerSettings.fontSize}px`);
  root.style.setProperty("--reader-line-height", readerSettings.lineHeight);
  root.style.setProperty("--reader-paragraph-spacing", `${readerSettings.paragraphSpacing}px`);
  root.style.setProperty("--card-radius", `${readerSettings.cardRadius}px`);

  document.body.dataset.readerWidth = readerSettings.readerWidth;
  document.body.dataset.textAlign = readerSettings.textAlign;
  document.body.dataset.siteTheme = readerSettings.siteTheme;

  document.body.classList.toggle("hide-foxes", !readerSettings.showFoxes);

  if (!readerSettings.spoilerWarning) {
    localStorage.setItem(SPOILER_WARNING_DISABLED_KEY, "true");
  }
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
            <p>Сохраняются автоматически.</p>
          </div>
          <button class="settings-close" id="settingsClose" type="button" aria-label="Закрыть">×</button>
        </div>

        <div class="settings-tabs">
          <button class="settings-tab active" data-tab="reader">Чтение</button>
          <button class="settings-tab" data-tab="view">Вид</button>
          <button class="settings-tab" data-tab="about">О проекте</button>
        </div>

        <div class="settings-content">
          <section class="settings-section active" data-section="reader">
            ${selectField("fontSize", "Размер текста", [
              ["14", "14px"],
              ["16", "16px"],
              ["18", "18px"],
              ["20", "20px"],
              ["22", "22px"],
              ["24", "24px"],
            ])}

            ${selectField("lineHeight", "Интервал", [
              ["1.4", "1.4"],
              ["1.6", "1.6"],
              ["1.8", "1.8"],
              ["2.0", "2.0"],
            ])}

            ${selectField("paragraphSpacing", "Абзацы", [
              ["0", "0px"],
              ["8", "8px"],
              ["16", "16px"],
              ["24", "24px"],
            ])}

            ${selectField("readerWidth", "Ширина текста", [
              ["full", "На всю ширину"],
              ["comfort", "Комфортная колонка"],
              ["wide", "Очень широкая"],
            ])}

            ${selectField("textAlign", "Выравнивание", [
              ["left", "По левому краю"],
              ["justify", "По ширине"],
            ])}

            ${presetAndColorField("textColor", "Цвет текста", [
              ["#111111", "Чёрный"],
              ["#333333", "Тёмно-серый"],
              ["#f4f4f4", "Светлый"],
            ])}

            ${presetAndColorField("readerBg", "Фон читалки", [
              ["#ffffff", "Белый"],
              ["#fffaf3", "Кремовый"],
              ["#f4ecd8", "Сепия"],
              ["#222222", "Тёмный"],
              ["#000000", "Чёрный"],
            ])}
          </section>

          <section class="settings-section" data-section="view">
            ${selectField("siteTheme", "Тема сайта", [
              ["light", "Светлая"],
              ["dark", "Тёмная"],
              ["system", "Системная"],
            ])}

            ${selectField("cardRadius", "Скругление", [
              ["0", "0px"],
              ["8", "8px"],
              ["16", "16px"],
              ["24", "24px"],
            ])}

            ${checkboxField("showFoxes", "Показывать лисичек")}
            ${checkboxField("spoilerWarning", "Предупреждать о спойлерах")}
          </section>

          <section class="settings-section" data-section="about">
            <div class="about-box">
              <img class="about-fox" src="/static/fox_hearts.png" alt="Лисичка" data-fox>
              <h3>Зефиркины баоцзы</h3>
              <p>
                Мини-читалка переводов с удобной настройкой текста,
                каталогом новелл и уютными лисичками.
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
            Сбросить
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
      <div class="settings-color-row">
        <select data-setting="${key}" data-color-select="${key}">
          ${options.map(([value, text]) => `<option value="${value}">${text}</option>`).join("")}
          <option value="custom">Свой</option>
        </select>
        <input type="color" data-setting="${key}" data-color-picker="${key}" />
      </div>
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
    const confirmed = confirm("Сбросить настройки к стандартным?");

    if (!confirmed) return;

    readerSettings = { ...DEFAULT_SETTINGS };
    saveSettings(readerSettings);
    localStorage.removeItem(SPOILER_WARNING_DISABLED_KEY);
    fillSettingsControls();
    applySettings();
  });
}

function handleSettingControl(control) {
  const key = control.dataset.setting;

  if (control.type === "checkbox") {
    updateSetting(key, control.checked);

    if (key === "spoilerWarning" && control.checked) {
      localStorage.removeItem(SPOILER_WARNING_DISABLED_KEY);
    }

    if (key === "spoilerWarning" && !control.checked) {
      localStorage.setItem(SPOILER_WARNING_DISABLED_KEY, "true");
    }

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

function createSpoilerWarningModal() {
  const modal = document.createElement("div");

  modal.innerHTML = `
    <div class="spoiler-warning-overlay" id="spoilerWarningOverlay" hidden>
      <div class="spoiler-warning-modal">
        <h2>Возможен спойлер</h2>
        <p>
          Этот тег может раскрывать важные детали сюжета.
          Показать его?
        </p>

        <label class="spoiler-warning-check">
          <input type="checkbox" id="spoilerDontShowAgain">
          <span>Больше не предупреждать</span>
        </label>

        <div class="spoiler-warning-actions">
          <button type="button" class="spoiler-warning-cancel" id="spoilerCancel">
            Отказаться
          </button>
          <button type="button" class="spoiler-warning-confirm" id="spoilerConfirm">
            Продолжить
          </button>
        </div>
      </div>
    </div>
  `;

  document.body.appendChild(modal);
}

let pendingSpoilerButton = null;

function bindSpoilerTags() {
  document.querySelectorAll(".tag-spoiler-reveal").forEach(button => {
    button.addEventListener("click", () => {
      const warningDisabled =
        localStorage.getItem(SPOILER_WARNING_DISABLED_KEY) === "true" ||
        readerSettings.spoilerWarning === false;

      if (warningDisabled) {
        openSpoilerTag(button);
        return;
      }

      pendingSpoilerButton = button;

      const overlay = document.getElementById("spoilerWarningOverlay");
      const checkbox = document.getElementById("spoilerDontShowAgain");

      checkbox.checked = false;
      overlay.hidden = false;
    });
  });

  const overlay = document.getElementById("spoilerWarningOverlay");
  const cancel = document.getElementById("spoilerCancel");
  const confirm = document.getElementById("spoilerConfirm");

  if (!overlay || !cancel || !confirm) return;

  cancel.addEventListener("click", () => {
    pendingSpoilerButton = null;
    overlay.hidden = true;
  });

  confirm.addEventListener("click", () => {
    const checkbox = document.getElementById("spoilerDontShowAgain");

    if (checkbox.checked) {
      localStorage.setItem(SPOILER_WARNING_DISABLED_KEY, "true");
      readerSettings.spoilerWarning = false;
      saveSettings(readerSettings);
      fillSettingsControls();
    }

    if (pendingSpoilerButton) {
      openSpoilerTag(pendingSpoilerButton);
    }

    pendingSpoilerButton = null;
    overlay.hidden = true;
  });

  overlay.addEventListener("click", event => {
    if (event.target === overlay) {
      pendingSpoilerButton = null;
      overlay.hidden = true;
    }
  });
}

function openSpoilerTag(button) {
  button.textContent = button.dataset.spoiler;
  button.classList.remove("tag-spoiler");
  button.classList.add("tag-spoiler-opened");
}

document.addEventListener("DOMContentLoaded", () => {
  createSettingsPanel();
  createSpoilerWarningModal();
  applySettings();
  bindSpoilerTags();
});
