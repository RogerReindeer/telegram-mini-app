(function () {
  const STORAGE_KEYS = {
    settings: "zefirki_reader_settings_v1",
    progress: "zefirki_reading_progress_v1",
  };

  const DEFAULT_SETTINGS = {
    siteTheme: "system",
    readerWidth: "comfort",
    readerFontSize: 16,
    readerLineHeight: 1.6,
    readerParagraphSpacing: 16,
    readerBg: "#fffaf3",
    readerText: "#111111",
    textAlign: "left",
    hideFoxes: false,
    spoilerWarningDisabled: false,
  };

  function safeJsonParse(value, fallback) {
    try {
      return JSON.parse(value) || fallback;
    } catch (error) {
      return fallback;
    }
  }

  function getSettings() {
    const saved = safeJsonParse(
      localStorage.getItem(STORAGE_KEYS.settings),
      {}
    );

    return Object.assign({}, DEFAULT_SETTINGS, saved);
  }

  function saveSettings(settings) {
    localStorage.setItem(STORAGE_KEYS.settings, JSON.stringify(settings));
  }

  function applySettings() {
    const settings = getSettings();
    const root = document.documentElement;
    const body = document.body;

    body.dataset.siteTheme = settings.siteTheme;
    body.dataset.readerWidth = settings.readerWidth;
    body.dataset.textAlign = settings.textAlign;

    if (settings.hideFoxes) {
      body.classList.add("hide-foxes");
    } else {
      body.classList.remove("hide-foxes");
    }

    root.style.setProperty("--reader-font-size", `${settings.readerFontSize}px`);
    root.style.setProperty("--reader-line-height", String(settings.readerLineHeight));
    root.style.setProperty("--reader-paragraph-spacing", `${settings.readerParagraphSpacing}px`);
    root.style.setProperty("--reader-bg", settings.readerBg);
    root.style.setProperty("--reader-text-color", settings.readerText);
  }

  function getProgressMap() {
    return safeJsonParse(
      localStorage.getItem(STORAGE_KEYS.progress),
      {}
    );
  }

  function saveProgressMap(progressMap) {
    localStorage.setItem(STORAGE_KEYS.progress, JSON.stringify(progressMap));
  }

  function clearProgress() {
    localStorage.removeItem(STORAGE_KEYS.progress);
  }

  function saveCurrentChapterProgress() {
    const chapterPage = document.querySelector("[data-chapter-page]");

    if (!chapterPage) {
      return;
    }

    const isLocked = chapterPage.dataset.isLocked === "true";

    if (isLocked) {
      return;
    }

    const novelId = chapterPage.dataset.novelId;
    const novelSlug = chapterPage.dataset.novelSlug;
    const novelTitle = chapterPage.dataset.novelTitle;
    const chapterId = chapterPage.dataset.chapterId;
    const chapterTitle = chapterPage.dataset.chapterTitle;

    if (!novelId || !chapterId) {
      return;
    }

    const progressMap = getProgressMap();

    progressMap[String(novelId)] = {
      novelId: String(novelId),
      novelSlug: novelSlug || "",
      novelTitle: novelTitle || "",
      chapterId: String(chapterId),
      chapterTitle: chapterTitle || "",
      chapterUrl: `/chapter/${chapterId}`,
      updatedAt: Date.now(),
    };

    saveProgressMap(progressMap);
  }

  function getLastProgressItem() {
    const progressMap = getProgressMap();

    return Object.values(progressMap)
      .filter(item => item && item.chapterId && item.novelId)
      .sort((a, b) => Number(b.updatedAt || 0) - Number(a.updatedAt || 0))[0] || null;
  }

  function findLibraryCardByNovelId(novelId) {
    return document.querySelector(`[data-library-novel-card][data-novel-id="${novelId}"]`);
  }

  function renderContinueReadingPanel() {
    const panel = document.getElementById("continueReadingPanel");

    if (!panel) {
      return;
    }

    const item = getLastProgressItem();

    if (!item) {
      panel.innerHTML = `
        <div class="continue-reading-empty">
          <div class="continue-reading-panel-header">
            <div>
              <div class="continue-reading-kicker">Продолжить читать</div>
              <div class="continue-reading-empty-text">Нет активных чтений</div>
            </div>
          </div>
        </div>
      `;
      return;
    }

    const card = findLibraryCardByNovelId(item.novelId);
    const coverUrl = card ? card.dataset.coverUrl : "";
    const novelTitle = item.novelTitle || (card ? card.dataset.novelTitle : "Новелла");
    const chapterTitle = item.chapterTitle || "Последняя открытая глава";
    const chapterUrl = item.chapterUrl || `/chapter/${item.chapterId}`;

    panel.innerHTML = `
      <div class="continue-reading-card">
        <div class="continue-reading-panel-header">
          <div>
            <div class="continue-reading-kicker">Продолжить читать</div>
            <div class="continue-reading-mini-title">Последняя открытая новелла</div>
          </div>

          <button class="continue-clear-button" type="button" id="clearReadingProgress">
            Очистить
          </button>
        </div>

        <div class="continue-reading-body">
          <a class="continue-cover-link" href="${chapterUrl}">
            ${
              coverUrl
                ? `<img class="continue-cover" src="${escapeHtmlAttribute(coverUrl)}" alt="">`
                : `<div class="continue-cover continue-cover-placeholder">📖</div>`
            }
          </a>

          <div class="continue-reading-info">
            <a class="continue-title" href="${chapterUrl}">
              ${escapeHtml(novelTitle)}
            </a>

            <div class="continue-chapter">
              ${escapeHtml(chapterTitle)}
            </div>

            <a class="continue-button" href="${chapterUrl}">
              Продолжить чтение
            </a>
          </div>
        </div>
      </div>
    `;

    const clearButton = document.getElementById("clearReadingProgress");

    if (clearButton) {
      clearButton.addEventListener("click", function () {
        clearProgress();
        renderContinueReadingPanel();
        updateNovelReadButton();
        markReadChapters();
      });
    }
  }

  function updateNovelReadButton() {
    const novelPage = document.querySelector("[data-novel-page]");
    const button = document.getElementById("novelReadButton");

    if (!novelPage || !button) {
      return;
    }

    const novelId = novelPage.dataset.novelId;
    const defaultHref = button.dataset.defaultHref;
    const defaultText = button.dataset.defaultText || "Начать читать";

    const progressMap = getProgressMap();
    const progress = progressMap[String(novelId)];

    if (progress && progress.chapterId) {
      button.href = progress.chapterUrl || `/chapter/${progress.chapterId}`;
      button.textContent = `Продолжить с ${progress.chapterTitle || "последней главы"}`;
      return;
    }

    button.href = defaultHref;
    button.textContent = defaultText;
  }

  function markReadChapters() {
    const progressMap = getProgressMap();
    const readChapterIds = new Set(
      Object.values(progressMap)
        .filter(item => item && item.chapterId)
        .map(item => String(item.chapterId))
    );

    document.querySelectorAll("[data-chapter-row]").forEach(row => {
      const chapterId = row.dataset.chapterId;

      if (readChapterIds.has(String(chapterId))) {
        row.classList.add("chapter-row-read");
      } else {
        row.classList.remove("chapter-row-read");
      }
    });
  }

  function initLibrarySort() {
    const select = document.getElementById("librarySort");
    const list = document.getElementById("libraryList");

    if (!select || !list) {
      return;
    }

    const savedSort = localStorage.getItem("zefirki_library_sort") || "sort-order";
    select.value = savedSort;

    function getNumber(card, name) {
      const value = Number(String(card.dataset[name] || "0").replace(",", "."));
      return isNaN(value) ? 0 : value;
    }

    function sortCards(mode) {
      const cards = Array.from(list.querySelectorAll("[data-library-novel-card]"));

      cards.sort((a, b) => {
        if (mode === "title") {
          return String(a.dataset.title || "").localeCompare(
            String(b.dataset.title || ""),
            "ru"
          );
        }

        if (mode === "status") {
          return String(a.dataset.status || "").localeCompare(
            String(b.dataset.status || ""),
            "ru"
          );
        }

        if (mode === "chapters") {
          return getNumber(b, "chapters") - getNumber(a, "chapters");
        }

        if (mode === "added") {
          return String(b.dataset.added || "").localeCompare(String(a.dataset.added || ""));
        }

        if (mode === "relation") {
          return String(a.dataset.relation || "").localeCompare(
            String(b.dataset.relation || ""),
            "ru"
          );
        }

        return getNumber(a, "sortOrder") - getNumber(b, "sortOrder");
      });

      cards.forEach(card => list.appendChild(card));
    }

    sortCards(savedSort);

    select.addEventListener("change", function () {
      localStorage.setItem("zefirki_library_sort", select.value);
      sortCards(select.value);
    });
  }

  function initDescriptionToggle() {
    document.querySelectorAll("[data-collapsible-description]").forEach(block => {
      const button = block.querySelector("[data-description-toggle]");

      if (!button) {
        return;
      }

      button.addEventListener("click", function () {
        block.classList.toggle("is-expanded");
        button.textContent = block.classList.contains("is-expanded") ? "Свернуть" : "Ещё";
      });
    });
  }

  function initSpoilers() {
    document.querySelectorAll(".tag-spoiler-reveal").forEach(button => {
      button.addEventListener("click", function () {
        const realText = button.dataset.spoiler || "";

        if (!realText) {
          return;
        }

        button.textContent = realText;
        button.classList.remove("tag-spoiler");
        button.classList.add("tag-spoiler-opened");
      });
    });
  }

  function initMiniAppExpandButton() {
    const tg = window.Telegram && window.Telegram.WebApp;

    if (!tg) {
      return;
    }

    try {
      tg.ready();
      tg.expand();
    } catch (error) {
      console.log("Telegram MiniApp expand warning:", error);
    }

    const button = document.createElement("button");
    button.type = "button";
    button.className = "miniapp-expand-button";
    button.textContent = "⛶";
    button.title = "Развернуть";

    button.addEventListener("click", function () {
      try {
        tg.expand();
      } catch (error) {
        console.log("Telegram MiniApp expand warning:", error);
      }
    });

    document.body.appendChild(button);
  }

  function createSettingsPanel() {
    if (document.getElementById("readerSettingsFab")) {
      return;
    }

    const settings = getSettings();

    const button = document.createElement("button");
    button.type = "button";
    button.className = "settings-fab";
    button.id = "readerSettingsFab";
    button.textContent = "⚙";
    button.title = "Настройки";

    const overlay = document.createElement("div");
    overlay.className = "settings-overlay";
    overlay.id = "readerSettingsOverlay";
    overlay.hidden = true;

    overlay.innerHTML = `
      <div class="settings-modal">
        <div class="settings-header">
          <div>
            <h2>Настройки чтения</h2>
            <p>Тема, ширина текста, размер шрифта и лисички.</p>
          </div>
          <button class="settings-close" type="button" id="readerSettingsClose">×</button>
        </div>

        <div class="settings-section active">
          <label class="settings-field">
            <span>Тема сайта</span>
            <select id="settingSiteTheme">
              <option value="system">Системная</option>
              <option value="light">Светлая</option>
              <option value="dark">Тёмная</option>
            </select>
          </label>

          <label class="settings-field">
            <span>Ширина чтения</span>
            <select id="settingReaderWidth">
              <option value="comfort">Удобная</option>
              <option value="full">Шире</option>
              <option value="wide">Почти весь экран</option>
            </select>
          </label>

          <label class="settings-field">
            <span>Размер текста</span>
            <select id="settingFontSize">
              <option value="15">15</option>
              <option value="16">16</option>
              <option value="17">17</option>
              <option value="18">18</option>
              <option value="20">20</option>
              <option value="22">22</option>
            </select>
          </label>

          <label class="settings-field">
            <span>Межстрочный интервал</span>
            <select id="settingLineHeight">
              <option value="1.5">1.5</option>
              <option value="1.6">1.6</option>
              <option value="1.7">1.7</option>
              <option value="1.8">1.8</option>
              <option value="2">2.0</option>
            </select>
          </label>

          <label class="settings-field">
            <span>Выравнивание</span>
            <select id="settingTextAlign">
              <option value="left">По левому краю</option>
              <option value="justify">По ширине</option>
            </select>
          </label>

          <label class="settings-check">
            <input type="checkbox" id="settingHideFoxes">
            <span>Скрыть лисичек</span>
          </label>
        </div>

        <div class="settings-footer">
          <button class="settings-reset" type="button" id="readerSettingsReset">
            Сбросить настройки
          </button>
        </div>
      </div>
    `;

    document.body.appendChild(button);
    document.body.appendChild(overlay);

    const elements = {
      overlay,
      close: overlay.querySelector("#readerSettingsClose"),
      reset: overlay.querySelector("#readerSettingsReset"),
      siteTheme: overlay.querySelector("#settingSiteTheme"),
      readerWidth: overlay.querySelector("#settingReaderWidth"),
      fontSize: overlay.querySelector("#settingFontSize"),
      lineHeight: overlay.querySelector("#settingLineHeight"),
      textAlign: overlay.querySelector("#settingTextAlign"),
      hideFoxes: overlay.querySelector("#settingHideFoxes"),
    };

    elements.siteTheme.value = settings.siteTheme;
    elements.readerWidth.value = settings.readerWidth;
    elements.fontSize.value = String(settings.readerFontSize);
    elements.lineHeight.value = String(settings.readerLineHeight);
    elements.textAlign.value = settings.textAlign;
    elements.hideFoxes.checked = Boolean(settings.hideFoxes);

    button.addEventListener("click", function () {
      overlay.hidden = false;
    });

    elements.close.addEventListener("click", function () {
      overlay.hidden = true;
    });

    overlay.addEventListener("click", function (event) {
      if (event.target === overlay) {
        overlay.hidden = true;
      }
    });

    function updateSetting(name, value) {
      const current = getSettings();
      current[name] = value;
      saveSettings(current);
      applySettings();
    }

    elements.siteTheme.addEventListener("change", () => updateSetting("siteTheme", elements.siteTheme.value));
    elements.readerWidth.addEventListener("change", () => updateSetting("readerWidth", elements.readerWidth.value));
    elements.fontSize.addEventListener("change", () => updateSetting("readerFontSize", Number(elements.fontSize.value)));
    elements.lineHeight.addEventListener("change", () => updateSetting("readerLineHeight", Number(elements.lineHeight.value)));
    elements.textAlign.addEventListener("change", () => updateSetting("textAlign", elements.textAlign.value));
    elements.hideFoxes.addEventListener("change", () => updateSetting("hideFoxes", elements.hideFoxes.checked));

    elements.reset.addEventListener("click", function () {
      saveSettings(DEFAULT_SETTINGS);
      applySettings();
      overlay.hidden = true;
      location.reload();
    });
  }

  function escapeHtml(value) {
    return String(value || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function escapeHtmlAttribute(value) {
    return escapeHtml(value);
  }

  document.addEventListener("DOMContentLoaded", function () {
    applySettings();
    saveCurrentChapterProgress();
    renderContinueReadingPanel();
    updateNovelReadButton();
    markReadChapters();
    initLibrarySort();
    initDescriptionToggle();
    initSpoilers();
    initMiniAppExpandButton();
    createSettingsPanel();
  });
})();
