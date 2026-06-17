(function () {
  const STORAGE_KEYS = {
    settings: "zefirki_reader_settings",
    readingHistory: "zefirki_reading_history",
    novelMeta: "zefirki_novel_meta",
    readChapters: "zefirki_read_chapters",
    spoilerConfirmed: "zefirki_spoiler_confirmed",
    libraryView: "zefirki_library_view",
  };

  const DEFAULT_SETTINGS = {
    siteTheme: "system",
    readerTheme: "cream",
    readerWidth: "comfort",
    fontSize: "16",
    lineHeight: "1.6",
    paragraphSpacing: "16",
    textAlign: "left",
    hideFoxes: false,
    accentColor: "#f28c38",
  };

  document.addEventListener("DOMContentLoaded", function () {
    initTelegram();
    initSettings();
    initLibraryView();
    initLibrarySort();
    initLibrarySearch();
    initLibraryNovelMeta();
    initNovelPageMeta();
    initChapterProgress();
    initReadingHistory();
    initNovelReadButton();
    initReadChapterMarks();
    initCollapsibleDescription();
    initSpoilerReveal();
  });

  function initTelegram() {
    try {
      if (window.Telegram && window.Telegram.WebApp) {
        window.Telegram.WebApp.ready();
        window.Telegram.WebApp.expand();
      }
    } catch (error) {
      console.log("Telegram WebApp init skipped:", error);
    }
  }

  function readJson(key, fallback) {
    try {
      const raw = localStorage.getItem(key);

      if (!raw) {
        return fallback;
      }

      return JSON.parse(raw);
    } catch (error) {
      return fallback;
    }
  }

  function writeJson(key, value) {
    localStorage.setItem(key, JSON.stringify(value));
  }

  function getSettings() {
    return {
      ...DEFAULT_SETTINGS,
      ...readJson(STORAGE_KEYS.settings, {}),
    };
  }

  function saveSettings(settings) {
    writeJson(STORAGE_KEYS.settings, settings);
  }

  function initSettings() {
    applySettings();

    if (!document.querySelector("[data-settings-fab]")) {
      createSettingsUi();
    }

    bindSettingsUi();
  }

  function applySettings() {
    const settings = getSettings();
    const body = document.body;

    body.dataset.siteTheme = settings.siteTheme;
    body.dataset.readerTheme = settings.readerTheme;
    body.dataset.readerWidth = settings.readerWidth;
    body.dataset.textAlign = settings.textAlign;

    body.classList.toggle("hide-foxes", Boolean(settings.hideFoxes));

    document.documentElement.style.setProperty("--accent", settings.accentColor || DEFAULT_SETTINGS.accentColor);
    document.documentElement.style.setProperty("--reader-font-size", `${settings.fontSize || DEFAULT_SETTINGS.fontSize}px`);
    document.documentElement.style.setProperty("--reader-line-height", settings.lineHeight || DEFAULT_SETTINGS.lineHeight);
    document.documentElement.style.setProperty("--reader-paragraph-spacing", `${settings.paragraphSpacing || DEFAULT_SETTINGS.paragraphSpacing}px`);

    applyReaderTheme(settings.readerTheme);
  }

  function applyReaderTheme(theme) {
    if (theme === "white") {
      document.documentElement.style.setProperty("--reader-page-bg", "#f4f4f4");
      document.documentElement.style.setProperty("--reader-bg", "#ffffff");
      document.documentElement.style.setProperty("--reader-text-color", "#111111");
      document.documentElement.style.setProperty("--reader-link-color", "#b45309");
      return;
    }

    if (theme === "sepia") {
      document.documentElement.style.setProperty("--reader-page-bg", "#ead7bd");
      document.documentElement.style.setProperty("--reader-bg", "#f4e3c8");
      document.documentElement.style.setProperty("--reader-text-color", "#2b211c");
      document.documentElement.style.setProperty("--reader-link-color", "#92400e");
      return;
    }

    if (theme === "dark") {
      document.documentElement.style.setProperty("--reader-page-bg", "#0f0f0f");
      document.documentElement.style.setProperty("--reader-bg", "#1b1b1b");
      document.documentElement.style.setProperty("--reader-text-color", "#eeeeee");
      document.documentElement.style.setProperty("--reader-link-color", "#fbbf24");
      return;
    }

    document.documentElement.style.setProperty("--reader-page-bg", "#f7efe7");
    document.documentElement.style.setProperty("--reader-bg", "#fffaf3");
    document.documentElement.style.setProperty("--reader-text-color", "#111111");
    document.documentElement.style.setProperty("--reader-link-color", "#b45309");
  }

  function createSettingsUi() {
    const fab = document.createElement("button");
    fab.className = "settings-fab";
    fab.type = "button";
    fab.dataset.settingsFab = "true";
    fab.textContent = "⚙️";

    const overlay = document.createElement("div");
    overlay.className = "settings-overlay";
    overlay.hidden = true;
    overlay.dataset.settingsOverlay = "true";

    overlay.innerHTML = `
      <div class="settings-modal" role="dialog" aria-modal="true">
        <div class="settings-header">
          <div>
            <h2>Настройки</h2>
            <p>Оформление сайта и читалки.</p>
          </div>
          <button class="settings-close" type="button" data-settings-close>×</button>
        </div>

        <div class="settings-tabs">
          <button class="settings-tab active" type="button" data-settings-tab="reader">Читалка</button>
          <button class="settings-tab" type="button" data-settings-tab="site">Сайт</button>
          <button class="settings-tab" type="button" data-settings-tab="about">О проекте</button>
        </div>

        <section class="settings-section active" data-settings-section="reader">
          <label class="settings-field">
            <span>Тема текста</span>
            <select data-setting="readerTheme">
              <option value="cream">Кремовая</option>
              <option value="white">Белая</option>
              <option value="sepia">Сепия</option>
              <option value="dark">Тёмная</option>
            </select>
          </label>

          <label class="settings-field">
            <span>Ширина текста</span>
            <select data-setting="readerWidth">
              <option value="comfort">Комфортная</option>
              <option value="full">Широкая</option>
              <option value="wide">Почти вся страница</option>
            </select>
          </label>

          <label class="settings-field">
            <span>Размер шрифта</span>
            <select data-setting="fontSize">
              <option value="15">15</option>
              <option value="16">16</option>
              <option value="17">17</option>
              <option value="18">18</option>
              <option value="19">19</option>
              <option value="20">20</option>
            </select>
          </label>

          <label class="settings-field">
            <span>Межстрочный интервал</span>
            <select data-setting="lineHeight">
              <option value="1.45">1.45</option>
              <option value="1.6">1.6</option>
              <option value="1.75">1.75</option>
              <option value="1.9">1.9</option>
            </select>
          </label>

          <label class="settings-field">
            <span>Отступ абзацев</span>
            <select data-setting="paragraphSpacing">
              <option value="12">12</option>
              <option value="16">16</option>
              <option value="20">20</option>
              <option value="24">24</option>
            </select>
          </label>

          <label class="settings-field">
            <span>Выравнивание</span>
            <select data-setting="textAlign">
              <option value="left">По левому краю</option>
              <option value="justify">По ширине</option>
            </select>
          </label>
        </section>

        <section class="settings-section" data-settings-section="site">
          <label class="settings-field">
            <span>Тема сайта</span>
            <select data-setting="siteTheme">
              <option value="system">Как в системе</option>
              <option value="light">Светлая</option>
              <option value="dark">Тёмная</option>
            </select>
          </label>

          <label class="settings-field">
            <span>Акцентный цвет</span>
            <span class="settings-color-row">
              <select data-setting="accentColor">
                <option value="#f28c38">Апельсин</option>
                <option value="#ec4899">Малина</option>
                <option value="#8b5cf6">Фиолетовый</option>
                <option value="#0ea5e9">Голубой</option>
                <option value="#10b981">Зелёный</option>
              </select>
              <input type="color" data-setting-color value="#f28c38">
            </span>
          </label>

          <label class="settings-check">
            <input type="checkbox" data-setting-checkbox="hideFoxes">
            <span>Спрятать лисичек</span>
          </label>
        </section>

        <section class="settings-section" data-settings-section="about">
          <div class="about-box">
            <div data-about-fox-wrap></div>
            <h3>Зефиркины баоцзы</h3>
            <p>
              Мини-читалка для новелл, раннего доступа и удобного возвращения к последней главе.
            </p>
            <div class="about-links">
              <a href="/library">Библиотека</a>
            </div>
          </div>
        </section>

        <div class="settings-footer">
          <button class="settings-reset" type="button" data-settings-reset>Сбросить настройки</button>
        </div>
      </div>
    `;

    document.body.appendChild(fab);
    document.body.appendChild(overlay);
  }

  function bindSettingsUi() {
    const settings = getSettings();
    const fab = document.querySelector("[data-settings-fab]");
    const overlay = document.querySelector("[data-settings-overlay]");

    if (!fab || !overlay) {
      return;
    }

    fillSettingsInputs(settings);

    fab.addEventListener("click", function () {
      overlay.hidden = false;
    });

    overlay.addEventListener("click", function (event) {
      if (event.target === overlay) {
        overlay.hidden = true;
      }
    });

    const close = overlay.querySelector("[data-settings-close]");
    if (close) {
      close.addEventListener("click", function () {
        overlay.hidden = true;
      });
    }

    overlay.querySelectorAll("[data-settings-tab]").forEach(function (tab) {
      tab.addEventListener("click", function () {
        const name = tab.dataset.settingsTab;

        overlay.querySelectorAll("[data-settings-tab]").forEach(function (item) {
          item.classList.toggle("active", item === tab);
        });

        overlay.querySelectorAll("[data-settings-section]").forEach(function (section) {
          section.classList.toggle("active", section.dataset.settingsSection === name);
        });
      });
    });

    overlay.querySelectorAll("[data-setting]").forEach(function (input) {
      input.addEventListener("change", function () {
        const current = getSettings();
        current[input.dataset.setting] = input.value;
        saveSettings(current);
        applySettings();

        if (input.dataset.setting === "accentColor") {
          const colorInput = overlay.querySelector("[data-setting-color]");
          if (colorInput) {
            colorInput.value = input.value;
          }
        }
      });
    });

    overlay.querySelectorAll("[data-setting-checkbox]").forEach(function (input) {
      input.addEventListener("change", function () {
        const current = getSettings();
        current[input.dataset.settingCheckbox] = input.checked;
        saveSettings(current);
        applySettings();
      });
    });

    const colorInput = overlay.querySelector("[data-setting-color]");
    if (colorInput) {
      colorInput.addEventListener("input", function () {
        const current = getSettings();
        current.accentColor = colorInput.value;
        saveSettings(current);
        applySettings();

        const select = overlay.querySelector('[data-setting="accentColor"]');
        if (select) {
          select.value = colorInput.value;
        }
      });
    }

    const reset = overlay.querySelector("[data-settings-reset]");
    if (reset) {
      reset.addEventListener("click", function () {
        saveSettings({ ...DEFAULT_SETTINGS });
        fillSettingsInputs(getSettings());
        applySettings();
      });
    }

    const aboutFoxWrap = overlay.querySelector("[data-about-fox-wrap]");
    if (aboutFoxWrap) {
      const foxUrl = getFoxUrl("fox_sitting_front") || getFoxUrl("fox_pic") || getFoxUrl("fox_peek");

      if (foxUrl) {
        aboutFoxWrap.innerHTML = `<img class="about-fox" src="${escapeHtml(foxUrl)}" alt="Лисичка" data-fox>`;
      }
    }
  }

  function fillSettingsInputs(settings) {
    document.querySelectorAll("[data-setting]").forEach(function (input) {
      const key = input.dataset.setting;

      if (Object.prototype.hasOwnProperty.call(settings, key)) {
        input.value = settings[key];
      }
    });

    document.querySelectorAll("[data-setting-checkbox]").forEach(function (input) {
      const key = input.dataset.settingCheckbox;

      if (Object.prototype.hasOwnProperty.call(settings, key)) {
        input.checked = Boolean(settings[key]);
      }
    });

    const colorInput = document.querySelector("[data-setting-color]");
    if (colorInput) {
      colorInput.value = settings.accentColor || DEFAULT_SETTINGS.accentColor;
    }
  }

  function getFoxUrl(name) {
    return (window.ZEFIRKI_FOX && window.ZEFIRKI_FOX[name]) || "";
  }

  function initLibraryView() {
    const list = document.getElementById("libraryList");
    const buttons = document.querySelectorAll("[data-library-view-button]");

    if (!list || !buttons.length) {
      return;
    }

    const savedView = localStorage.getItem(STORAGE_KEYS.libraryView) || "list";
    applyLibraryView(savedView);

    buttons.forEach(function (button) {
      button.addEventListener("click", function () {
        const view = button.dataset.libraryViewButton || "list";
        localStorage.setItem(STORAGE_KEYS.libraryView, view);
        applyLibraryView(view);
      });
    });

    function applyLibraryView(view) {
      const normalizedView = view === "grid" ? "grid" : "list";

      list.dataset.libraryView = normalizedView;
      list.classList.toggle("novel-list-grid", normalizedView === "grid");
      list.classList.toggle("novel-list-list", normalizedView === "list");

      buttons.forEach(function (button) {
        button.classList.toggle("active", button.dataset.libraryViewButton === normalizedView);
      });
    }
  }

  function initLibrarySearch() {
    const input = document.getElementById("librarySearch");
    const list = document.getElementById("libraryList");
    const empty = document.getElementById("libraryEmptySearch");

    if (!input || !list) {
      return;
    }

    input.addEventListener("input", applyLibrarySearch);

    function applyLibrarySearch() {
      const query = normalizeSearchText(input.value);
      const cards = Array.from(list.querySelectorAll("[data-library-novel-card]"));
      let visibleCount = 0;

      cards.forEach(function (card) {
        const title = normalizeSearchText(card.dataset.title || card.dataset.novelTitle || "");
        const isVisible = !query || title.includes(query);

        card.hidden = !isVisible;

        if (isVisible) {
          visibleCount += 1;
        }
      });

      if (empty) {
        empty.hidden = visibleCount !== 0;
      }
    }
  }

  function normalizeSearchText(value) {
    return String(value || "")
      .toLowerCase()
      .replace(/ё/g, "е")
      .replace(/\s+/g, " ")
      .trim();
  }

  function initLibrarySort() {
    const select = document.getElementById("librarySort");
    const list = document.getElementById("libraryList");

    if (!select || !list) {
      return;
    }

    select.addEventListener("change", function () {
      const cards = Array.from(list.querySelectorAll("[data-library-novel-card]"));
      const mode = select.value;

      cards.sort(function (a, b) {
        if (mode === "title") {
          return String(a.dataset.title || "").localeCompare(String(b.dataset.title || ""), "ru");
        }

        if (mode === "status") {
          return statusWeight(a.dataset.status) - statusWeight(b.dataset.status);
        }

        if (mode === "chapters") {
          return Number(b.dataset.chapters || 0) - Number(a.dataset.chapters || 0);
        }

        if (mode === "translated") {
          return Number(b.dataset.translatedChapters || 0) - Number(a.dataset.translatedChapters || 0);
        }

        if (mode === "added") {
          return String(b.dataset.added || "").localeCompare(String(a.dataset.added || ""));
        }

        if (mode === "relation") {
          return String(a.dataset.relation || "").localeCompare(String(b.dataset.relation || ""), "ru");
        }

        return Number(a.dataset.sortOrder || 0) - Number(b.dataset.sortOrder || 0);
      });

      cards.forEach(function (card) {
        list.appendChild(card);
      });
    });
  }

  function statusWeight(status) {
    if (status === "completed") {
      return 1;
    }

    if (status === "in_progress") {
      return 2;
    }

    if (status === "paused") {
      return 3;
    }

    return 4;
  }

  function initLibraryNovelMeta() {
    const cards = document.querySelectorAll("[data-library-novel-card]");

    if (!cards.length) {
      return;
    }

    const meta = readJson(STORAGE_KEYS.novelMeta, {});

    cards.forEach(function (card) {
      const novelId = card.dataset.novelId;

      if (!novelId) {
        return;
      }

      meta[novelId] = {
        novelId,
        novelSlug: card.dataset.novelSlug || "",
        novelTitle: card.dataset.novelTitle || "",
        coverUrl: card.dataset.novelCover || "",
      };
    });

    writeJson(STORAGE_KEYS.novelMeta, meta);
  }

  function initNovelPageMeta() {
    const page = document.querySelector("[data-novel-page]");

    if (!page) {
      return;
    }

    const novelId = page.dataset.novelId;

    if (!novelId) {
      return;
    }

    const cover = document.querySelector(".title-cover");
    const meta = readJson(STORAGE_KEYS.novelMeta, {});

    meta[novelId] = {
      novelId,
      novelSlug: page.dataset.novelSlug || "",
      novelTitle: page.dataset.novelTitle || "",
      coverUrl: cover && cover.tagName === "IMG" ? cover.getAttribute("src") || "" : "",
    };

    writeJson(STORAGE_KEYS.novelMeta, meta);
  }

  function initChapterProgress() {
    const page = document.querySelector("[data-chapter-page]");

    if (!page) {
      return;
    }

    const isLocked = page.dataset.isLocked === "true";

    if (isLocked) {
      return;
    }

    const novelId = page.dataset.novelId;
    const novelSlug = page.dataset.novelSlug;
    const novelTitle = page.dataset.novelTitle;
    const chapterId = page.dataset.chapterId;
    const chapterTitle = page.dataset.chapterTitle;

    if (!novelId || !chapterId) {
      return;
    }

    const meta = readJson(STORAGE_KEYS.novelMeta, {});
    const novelMeta = meta[novelId] || {};

    const item = {
      novelId,
      novelSlug: novelSlug || novelMeta.novelSlug || "",
      novelTitle: novelTitle || novelMeta.novelTitle || "",
      coverUrl: novelMeta.coverUrl || "",
      chapterId,
      chapterTitle: chapterTitle || "",
      updatedAt: Date.now(),
    };

    saveReadingHistoryItem(item);
    saveReadChapter(chapterId);
  }

  function saveReadingHistoryItem(item) {
    const history = readJson(STORAGE_KEYS.readingHistory, []);
    const filtered = history.filter(function (entry) {
      return String(entry.novelId) !== String(item.novelId);
    });

    filtered.push(item);

    writeJson(STORAGE_KEYS.readingHistory, filtered.slice(-50));
  }

  function saveReadChapter(chapterId) {
    const ids = readJson(STORAGE_KEYS.readChapters, []);

    if (!ids.includes(String(chapterId))) {
      ids.push(String(chapterId));
    }

    writeJson(STORAGE_KEYS.readChapters, ids.slice(-2000));
  }

  function initReadingHistory() {
    const container = document.getElementById("readingHistory");

    if (!container) {
      return;
    }

    renderReadingHistory();

    const clearButton = document.getElementById("clearReadingHistory");

    if (clearButton) {
      clearButton.addEventListener("click", function () {
        localStorage.removeItem(STORAGE_KEYS.readingHistory);
        renderReadingHistory();
      });
    }
  }

  function renderReadingHistory() {
    const container = document.getElementById("readingHistory");
    const clearButton = document.getElementById("clearReadingHistory");

    if (!container) {
      return;
    }

    const history = readJson(STORAGE_KEYS.readingHistory, []);

    if (clearButton) {
      clearButton.hidden = history.length === 0;
    }

    if (!history.length) {
      container.innerHTML = `
        <div class="reading-history-empty">
          Здесь появится история чтения, когда вы откроете первую главу.
        </div>
      `;
      return;
    }

    const cards = history.map(function (item) {
      const coverHtml = item.coverUrl
        ? `<img class="continue-card-cover" src="${escapeHtml(item.coverUrl)}" alt="${escapeHtml(item.novelTitle || "")}">`
        : `<div class="continue-card-cover continue-card-cover-placeholder">📖</div>`;

      return `
        <article class="continue-card">
          <a class="continue-card-cover-link" href="/novel/${escapeHtml(item.novelSlug || "")}">
            ${coverHtml}
          </a>

          <div class="continue-card-body">
            <a class="continue-card-title" href="/novel/${escapeHtml(item.novelSlug || "")}">
              ${escapeHtml(item.novelTitle || "Без названия")}
            </a>

            <div class="continue-card-chapter">
              ${escapeHtml(item.chapterTitle || "Глава")}
            </div>

            <a class="continue-card-button" href="/chapter/${escapeHtml(item.chapterId)}">
              Продолжить
            </a>
          </div>
        </article>
      `;
    });

    container.innerHTML = cards.join("");
    container.scrollLeft = container.scrollWidth;
  }

  function initNovelReadButton() {
    const page = document.querySelector("[data-novel-page]");
    const button = document.getElementById("novelReadButton");

    if (!page || !button) {
      return;
    }

    const novelId = page.dataset.novelId;
    const history = readJson(STORAGE_KEYS.readingHistory, []);
    const item = history.find(function (entry) {
      return String(entry.novelId) === String(novelId);
    });

    if (item && item.chapterId) {
      button.href = `/chapter/${item.chapterId}`;
      button.textContent = item.chapterTitle
        ? `Продолжить с ${item.chapterTitle}`
        : "Продолжить чтение";
    }
  }

  function initReadChapterMarks() {
    const readIds = readJson(STORAGE_KEYS.readChapters, []);

    if (!readIds.length) {
      return;
    }

    document.querySelectorAll("[data-chapter-row]").forEach(function (row) {
      if (readIds.includes(String(row.dataset.chapterId))) {
        row.classList.add("chapter-row-read");
      }
    });
  }

  function initCollapsibleDescription() {
    document.querySelectorAll("[data-collapsible-description]").forEach(function (block) {
      const content = block.querySelector(".collapsible-description-content");
      const button = block.querySelector("[data-description-toggle]");

      if (!content || !button) {
        return;
      }

      if (content.scrollHeight <= 120) {
        button.hidden = true;
        block.classList.add("is-expanded");
        return;
      }

      button.addEventListener("click", function () {
        const expanded = block.classList.toggle("is-expanded");
        button.textContent = expanded ? "Свернуть" : "Ещё";
      });
    });
  }

  function initSpoilerReveal() {
    document.querySelectorAll("[data-spoiler]").forEach(function (button) {
      button.addEventListener("click", function () {
        const confirmed = localStorage.getItem(STORAGE_KEYS.spoilerConfirmed) === "true";

        if (confirmed) {
          revealSpoiler(button);
          return;
        }

        showSpoilerWarning(function (remember) {
          if (remember) {
            localStorage.setItem(STORAGE_KEYS.spoilerConfirmed, "true");
          }

          revealSpoiler(button);
        });
      });
    });
  }

  function revealSpoiler(button) {
    button.textContent = button.dataset.spoiler || "";
    button.classList.remove("tag-spoiler");
    button.classList.add("tag-spoiler-opened");
  }

  function showSpoilerWarning(onConfirm) {
    let overlay = document.querySelector("[data-spoiler-warning-overlay]");

    if (!overlay) {
      overlay = document.createElement("div");
      overlay.className = "spoiler-warning-overlay";
      overlay.dataset.spoilerWarningOverlay = "true";

      overlay.innerHTML = `
        <div class="spoiler-warning-modal">
          <h2>Осторожно, спойлер</h2>
          <p>Этот тег может раскрыть важную деталь сюжета.</p>

          <label class="spoiler-warning-check">
            <input type="checkbox" data-spoiler-remember>
            <span>Больше не предупреждать</span>
          </label>

          <div class="spoiler-warning-actions">
            <button type="button" class="spoiler-warning-cancel" data-spoiler-cancel>Не открывать</button>
            <button type="button" class="spoiler-warning-confirm" data-spoiler-confirm>Показать</button>
          </div>
        </div>
      `;

      document.body.appendChild(overlay);
    }

    overlay.hidden = false;

    const cancel = overlay.querySelector("[data-spoiler-cancel]");
    const confirm = overlay.querySelector("[data-spoiler-confirm]");
    const remember = overlay.querySelector("[data-spoiler-remember]");

    const close = function () {
      overlay.hidden = true;
    };

    cancel.onclick = close;

    confirm.onclick = function () {
      const shouldRemember = remember && remember.checked;
      close();
      onConfirm(shouldRemember);
    };
  }

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
})();
