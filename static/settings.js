(function () {
  const STORAGE_KEYS = {
    settings: "zefirki_reader_settings",
    readingHistory: "zefirki_reading_history",
    novelMeta: "zefirki_novel_meta",
    readChapters: "zefirki_read_chapters",
    spoilerConfirmed: "zefirki_spoiler_confirmed",
    libraryFilter: "zefirki_library_filter",
  };

  const DEFAULT_SETTINGS = {
    siteTheme: "light",
    readerTheme: "cream",
    readerWidth: "comfort",
    fontSize: "16",
    lineHeight: "1.6",
    paragraphSpacing: "16",
    textAlign: "left",
    hideFoxes: false,
    accentColor: "#f28c38",
    appSize: "normal",
  };

  const DEFAULT_FILTER = {
    query: "",
    chips: [],
  };

  document.addEventListener("DOMContentLoaded", function () {
    initTelegram();
    initSettings();
    initAppSizeButton();
    initLibrary();
    initNovelPageMeta();
    initChapterProgress();
    initNovelReadButton();
    initReadChapterMarks();
    initCollapsibleDescription();
    initPaidChapterReveal();
    initSpoilerReveal();
  });

  function initTelegram() {
    try {
      if (window.Telegram && window.Telegram.WebApp) {
        window.Telegram.WebApp.ready();
      }
    } catch (error) {
      console.log("Telegram WebApp init skipped:", error);
    }
  }

  function requestSoftExpand() {
    try {
      if (window.Telegram && window.Telegram.WebApp) {
        const telegram = window.Telegram.WebApp;

        if (typeof telegram.ready === "function") {
          telegram.ready();
        }

        if (typeof telegram.expand === "function") {
          telegram.expand();
        }
      }
    } catch (error) {
      console.log("Telegram expand skipped:", error);
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

    body.dataset.siteTheme = settings.siteTheme || "light";
    body.dataset.readerTheme = settings.readerTheme || DEFAULT_SETTINGS.readerTheme;
    body.dataset.readerWidth = settings.readerWidth || DEFAULT_SETTINGS.readerWidth;
    body.dataset.textAlign = settings.textAlign || DEFAULT_SETTINGS.textAlign;
    body.dataset.appSize = settings.appSize || DEFAULT_SETTINGS.appSize;

    body.classList.toggle("hide-foxes", Boolean(settings.hideFoxes));

    document.documentElement.style.setProperty("--accent", settings.accentColor || DEFAULT_SETTINGS.accentColor);
    document.documentElement.style.setProperty("--reader-font-size", `${settings.fontSize || DEFAULT_SETTINGS.fontSize}px`);
    document.documentElement.style.setProperty("--reader-line-height", settings.lineHeight || DEFAULT_SETTINGS.lineHeight);
    document.documentElement.style.setProperty("--reader-paragraph-spacing", `${settings.paragraphSpacing || DEFAULT_SETTINGS.paragraphSpacing}px`);

    applyReaderTheme(settings.readerTheme || DEFAULT_SETTINGS.readerTheme);
    updateAppSizeButton();
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

  function initAppSizeButton() {
    let button = document.querySelector("[data-app-size-toggle]");

    if (!button) {
      button = document.createElement("button");
      button.className = "app-size-fab";
      button.type = "button";
      button.dataset.appSizeToggle = "true";

      button.addEventListener("click", function () {
        const settings = getSettings();

        if (settings.appSize === "large") {
          settings.appSize = "normal";
        } else {
          settings.appSize = "large";
          requestSoftExpand();
        }

        saveSettings(settings);
        applySettings();
      });

      document.body.appendChild(button);
    }

    updateAppSizeButton();
  }

  function updateAppSizeButton() {
    const button = document.querySelector("[data-app-size-toggle]");

    if (!button) {
      return;
    }

    const settings = getSettings();
    const isLarge = settings.appSize === "large";

    button.textContent = isLarge ? "↙" : "↗";
    button.title = isLarge ? "Вернуть обычный размер" : "Расширить окно";
    button.setAttribute(
      "aria-label",
      isLarge ? "Вернуть обычный размер" : "Расширить окно"
    );
  }

  function initLibrary() {
    const raw = document.getElementById("libraryRawCards");

    if (!raw) {
      return;
    }

    initLibraryNovelMeta();
    initLibrarySearch();
    initLibraryFilters();
    initLibrarySortControl();
    initLibrarySectionToggles();
    renderLibraryCards();
  }

  function getLibraryFilter() {
    return {
      ...DEFAULT_FILTER,
      ...readJson(STORAGE_KEYS.libraryFilter, {}),
    };
  }

  function saveLibraryFilter(filter) {
    writeJson(STORAGE_KEYS.libraryFilter, filter);
  }

  function initLibrarySearch() {
    const toggle = document.getElementById("librarySearchToggle");
    const panel = document.getElementById("librarySearchPanel");
    const input = document.getElementById("librarySearchInput");
    const clear = document.getElementById("librarySearchClear");

    if (!toggle || !panel || !input) {
      return;
    }

    const filter = getLibraryFilter();

    input.value = filter.query || "";

    toggle.addEventListener("click", function () {
      panel.hidden = !panel.hidden;

      if (!panel.hidden) {
        input.focus();
      }
    });

    input.addEventListener("input", function () {
      const current = getLibraryFilter();

      current.query = input.value.trim();

      saveLibraryFilter(current);
      renderLibraryCards();
    });

    if (clear) {
      clear.addEventListener("click", function () {
        const current = getLibraryFilter();

        current.query = "";
        input.value = "";

        saveLibraryFilter(current);
        renderLibraryCards();
        input.focus();
      });
    }

    document.querySelectorAll("[data-quick-filter]").forEach(function (button) {
      button.addEventListener("click", function () {
        toggleFilterChip(button.dataset.quickFilter);
      });
    });
  }

  function initLibraryFilters() {
    const open = document.getElementById("libraryFilterToggle");
    const sheet = document.getElementById("libraryFilterSheet");
    const reset = document.getElementById("libraryFilterReset");
    const apply = document.getElementById("libraryFilterApply");

    if (!open || !sheet) {
      return;
    }

    open.addEventListener("click", function () {
      syncFilterSheetButtons();
      updateFilterApplyButton();
      sheet.hidden = false;
    });

    sheet.querySelectorAll("[data-filter-close]").forEach(function (button) {
      button.addEventListener("click", function () {
        sheet.hidden = true;
      });
    });

    sheet.querySelectorAll("[data-filter-chip]").forEach(function (button) {
      button.addEventListener("click", function () {
        const chip = button.dataset.filterChip;

        if (chip === "all") {
          const current = getLibraryFilter();

          current.chips = [];

          saveLibraryFilter(current);
          syncFilterSheetButtons();
          renderLibraryCards();
          updateFilterApplyButton();
          return;
        }

        toggleFilterChip(chip);
        syncFilterSheetButtons();
        updateFilterApplyButton();
      });
    });

    if (reset) {
      reset.addEventListener("click", function () {
        const current = getLibraryFilter();

        current.chips = [];
        current.query = "";

        saveLibraryFilter(current);

        const input = document.getElementById("librarySearchInput");

        if (input) {
          input.value = "";
        }

        syncFilterSheetButtons();
        renderLibraryCards();
        updateFilterApplyButton();
      });
    }

    if (apply) {
      apply.addEventListener("click", function () {
        sheet.hidden = true;
        renderLibraryCards();
      });
    }
  }

  function initLibrarySortControl() {
    const select = document.getElementById("librarySort");

    if (!select) {
      return;
    }

    select.addEventListener("change", function () {
      renderLibraryCards();
    });
  }

  function toggleFilterChip(chip) {
    const current = getLibraryFilter();
    const normalized = String(chip || "").trim();

    if (!normalized) {
      return;
    }

    if (current.chips.includes(normalized)) {
      current.chips = current.chips.filter(function (item) {
        return item !== normalized;
      });
    } else {
      current.chips.push(normalized);
    }

    saveLibraryFilter(current);
    renderLibraryCards();
  }

  function syncFilterSheetButtons() {
    const current = getLibraryFilter();

    document.querySelectorAll("[data-filter-chip]").forEach(function (button) {
      const chip = button.dataset.filterChip;

      if (chip === "all") {
        button.classList.toggle("active", current.chips.length === 0);
      } else {
        button.classList.toggle("active", current.chips.includes(chip));
      }
    });
  }

  function renderActiveFilters() {
    const filter = getLibraryFilter();
    const wrap = document.getElementById("libraryActiveFilters");

    if (!wrap) {
      return;
    }

    const items = [];

    filter.chips.forEach(function (chip) {
      items.push(`
        <button type="button" data-remove-filter="${escapeHtml(chip)}">
          ${escapeHtml(chip)} <span>×</span>
        </button>
      `);
    });

    if (filter.query) {
      items.push(`
        <button type="button" data-clear-search>
          Поиск: ${escapeHtml(filter.query)} <span>×</span>
        </button>
      `);
    }

    wrap.hidden = items.length === 0;
    wrap.innerHTML = items.join("");

    wrap.querySelectorAll("[data-remove-filter]").forEach(function (button) {
      button.addEventListener("click", function () {
        toggleFilterChip(button.dataset.removeFilter);
      });
    });

    const clearSearch = wrap.querySelector("[data-clear-search]");

    if (clearSearch) {
      clearSearch.addEventListener("click", function () {
        const current = getLibraryFilter();

        current.query = "";

        saveLibraryFilter(current);

        const input = document.getElementById("librarySearchInput");

        if (input) {
          input.value = "";
        }

        renderLibraryCards();
      });
    }
  }

  function initLibrarySectionToggles() {
    document.querySelectorAll("[data-section-toggle]").forEach(function (button) {
      button.addEventListener("click", function () {
        const sectionName = button.dataset.sectionToggle;
        const section = document.querySelector(`[data-library-section="${cssEscape(sectionName)}"]`);

        if (!section) {
          return;
        }

        section.classList.toggle("collapsed");
      });
    });
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

  function renderLibraryCards() {
    const raw = document.getElementById("libraryRawCards");

    if (!raw) {
      return;
    }

    const readingList = document.querySelector('[data-section-list="reading"]');
    const startList = document.querySelector('[data-section-list="start"]');
    const finishedList = document.querySelector('[data-section-list="finished"]');
    const empty = document.getElementById("libraryEmptyFilter");

    if (!readingList || !startList || !finishedList) {
      return;
    }

    const allCards = Array.from(document.querySelectorAll("[data-library-novel-card]"));
    const filter = getLibraryFilter();
    const history = readJson(STORAGE_KEYS.readingHistory, []);
    const readIds = readJson(STORAGE_KEYS.readChapters, []);

    const historyByNovel = {};

    history.forEach(function (item) {
      historyByNovel[String(item.novelId)] = item;
    });

    const buckets = {
      reading: [],
      start: [],
      finished: [],
    };

    allCards.forEach(function (card) {
      prepareLibraryCard(card, historyByNovel, readIds);

      if (!cardMatchesFilter(card, filter, historyByNovel)) {
        raw.appendChild(card);
        return;
      }

      const state = getCardState(card, historyByNovel);

      buckets[state].push(card);
    });

    sortCards(buckets.reading);
    sortCards(buckets.start);
    sortCards(buckets.finished);

    readingList.innerHTML = "";
    startList.innerHTML = "";
    finishedList.innerHTML = "";

    buckets.reading.forEach(function (card) {
      readingList.appendChild(card);
    });

    buckets.start.forEach(function (card) {
      startList.appendChild(card);
    });

    buckets.finished.forEach(function (card) {
      finishedList.appendChild(card);
    });

    updateSection("reading", buckets.reading.length);
    updateSection("start", buckets.start.length);
    updateSection("finished", buckets.finished.length);

    const visibleTotal = buckets.reading.length + buckets.start.length + buckets.finished.length;

    if (empty) {
      empty.hidden = visibleTotal !== 0;
    }

    renderActiveFilters();
    renderLibraryUpdateBanner(buckets.reading);
    updateFilterApplyButton(visibleTotal);
  }

 function prepareLibraryCard(card, historyByNovel, readIds) {
  const novelId = String(card.dataset.novelId || "");
  const historyItem = historyByNovel[novelId];

  const chapters = Number(card.dataset.chapters || 0);
  const translated = Number(card.dataset.translatedChapters || 0);
  const available = Number(card.dataset.availableChapters || 0);
  const projectProgress = clampNumber(Number(card.dataset.progress || 0), 0, 100);
  const projectStatus = String(card.dataset.status || "");
  const projectStatusLabel = card.dataset.statusLabel || "Переводится";

  const button = card.querySelector("[data-card-main-button]");
  const stateLine = card.querySelector("[data-card-state-line]");
  const progressFill = card.querySelector("[data-card-progress-fill]");
  const progressText = card.querySelector("[data-card-progress-text]");

  card.classList.remove("is-reading", "is-new", "is-finished", "is-start");

  const safeHistoryIndex = historyItem && historyItem.chapterIndex
    ? Math.min(Number(historyItem.chapterIndex || 0), available || Number(historyItem.chapterIndex || 0))
    : 0;

  if (progressFill) {
    const visualProgress = historyItem && safeHistoryIndex && available
      ? clampNumber(safeHistoryIndex / available * 100, 0, 100)
      : projectProgress;

    progressFill.style.width = `${visualProgress}%`;
  }

  if (progressText) {
    if (historyItem && safeHistoryIndex && available) {
      progressText.textContent = `${safeHistoryIndex} / ${available}`;
    } else if (chapters) {
      progressText.textContent = `${translated || 0} / ${chapters}`;
    } else {
      progressText.textContent = "";
    }
  }

  const newCount = historyItem ? getNewChapterCount(novelId, historyItem.availableChapters) : 0;

  if (historyItem && newCount > 0) {
    card.classList.add("is-new");

    if (stateLine) {
      stateLine.innerHTML = `
        <span class="library-status-chip library-status-new">Новая глава</span>
        <span>Вы остановились: ${escapeHtml(historyItem.chapterTitle || "последняя прочитанная глава")}</span>
      `;
    }

    if (button) {
      button.textContent = "Читать новую";
      button.href = `/novel/${card.dataset.novelSlug || ""}`;
    }

    return;
  }

  if (historyItem && available && safeHistoryIndex >= available) {
    card.classList.add("is-finished");

    if (projectStatus === "completed") {
      if (stateLine) {
        stateLine.innerHTML = `
          <span class="library-status-chip library-status-finished">Прочитано</span>
          <span>Книга завершена, вы прочитали всё доступное</span>
        `;
      }

      if (button) {
        button.textContent = "Перечитать";
        button.href = `/chapter/${historyItem.chapterId}`;
      }

      return;
    }

    if (stateLine) {
      stateLine.innerHTML = `
        <span class="library-status-chip library-status-finished">Жду новую</span>
        <span>Вы дошли до последней доступной главы</span>
      `;
    }

    if (button) {
      button.textContent = "К оглавлению";
      button.href = `/novel/${card.dataset.novelSlug || ""}`;
    }

    return;
  }

  if (historyItem) {
    card.classList.add("is-reading");

    if (stateLine) {
      stateLine.innerHTML = `
        <span class="library-status-chip">Читаю</span>
        <span>Вы остановились: ${escapeHtml(historyItem.chapterTitle || "глава " + safeHistoryIndex)}</span>
      `;
    }

    if (button) {
      button.textContent = "Продолжить";
      button.href = `/chapter/${historyItem.chapterId}`;
    }

    return;
  }

  card.classList.add("is-start");

  if (!available) {
    if (stateLine) {
      stateLine.innerHTML = `
        <span class="library-status-chip">Скоро</span>
        <span>Открытых глав пока нет</span>
      `;
    }

    if (button) {
      button.textContent = "Скоро";
      button.href = `/novel/${card.dataset.novelSlug || ""}`;
      button.classList.add("is-disabled-soft");
    }

    return;
  }

  if (stateLine) {
    stateLine.innerHTML = `
      <span class="library-status-chip">${escapeHtml(projectStatusLabel)}</span>
      <span>Открыто ${available} из ${chapters || available}</span>
    `;
  }

  if (button) {
    button.textContent = "Начать читать";
    button.href = `/novel/${card.dataset.novelSlug || ""}`;
    button.classList.remove("is-disabled-soft");
  }
}

  function getCardState(card, historyByNovel) {
    const novelId = String(card.dataset.novelId || "");
    const historyItem = historyByNovel[novelId];

    if (!historyItem) {
      return "start";
    }

    const available = Number(card.dataset.availableChapters || 0);
    const newCount = getNewChapterCount(novelId, historyItem.availableChapters);

    if (newCount > 0) {
      return "reading";
    }

    if (available && Number(historyItem.chapterIndex || 0) >= available) {
      return "finished";
    }

    return "reading";
  }

  function cardMatchesFilter(card, filter, historyByNovel) {
    const query = String(filter.query || "").toLowerCase().trim();
    const chips = filter.chips || [];

    const haystack = [
      card.dataset.novelTitle,
      card.dataset.title,
      card.dataset.description,
      card.dataset.tags,
      card.dataset.statusLabel,
      card.dataset.relation,
    ].join(" ").toLowerCase();

    if (query && !haystack.includes(query)) {
      return false;
    }

    for (const chip of chips) {
      if (!chip || chip === "all") {
        continue;
      }

      if (chip === "reading") {
        if (!historyByNovel[String(card.dataset.novelId || "")]) {
          return false;
        }

        continue;
      }

      if (chip === "new") {
        const item = historyByNovel[String(card.dataset.novelId || "")];

        if (!item || getNewChapterCount(card.dataset.novelId, item.availableChapters) <= 0) {
          return false;
        }

        continue;
      }

      if (chip === "finished") {
        const item = historyByNovel[String(card.dataset.novelId || "")];
        const available = Number(card.dataset.availableChapters || 0);

        if (!item || !available || Number(item.chapterIndex || 0) < available) {
          return false;
        }

        continue;
      }

      if (chip === "in_progress" || chip === "completed" || chip === "paused") {
        if (card.dataset.status !== chip) {
          return false;
        }

        continue;
      }

      if (!haystack.includes(String(chip).toLowerCase())) {
        return false;
      }
    }

    return true;
  }

  function sortCards(cards) {
    const select = document.getElementById("librarySort");
    const mode = select ? select.value : "smart";

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

      if (mode === "smart") {
        const aNew = a.classList.contains("is-new") ? 0 : 1;
        const bNew = b.classList.contains("is-new") ? 0 : 1;

        if (aNew !== bNew) {
          return aNew - bNew;
        }
      }

      return Number(a.dataset.sortOrder || 0) - Number(b.dataset.sortOrder || 0);
    });
  }

  function updateSection(name, count) {
    const section = document.querySelector(`[data-library-section="${cssEscape(name)}"]`);
    const countElement = document.querySelector(`[data-section-count="${cssEscape(name)}"]`);

    if (countElement) {
      countElement.textContent = String(count);
    }

    if (section) {
      section.hidden = count === 0;
    }
  }

  function updateFilterApplyButton(knownCount) {
    const button = document.getElementById("libraryFilterApply");

    if (!button) {
      return;
    }

    if (typeof knownCount === "number") {
      button.textContent = `Показать ${knownCount} книг`;
      return;
    }

    const visibleCards = document.querySelectorAll(
      '[data-section-list="reading"] [data-library-novel-card], ' +
      '[data-section-list="start"] [data-library-novel-card], ' +
      '[data-section-list="finished"] [data-library-novel-card]'
    );

    button.textContent = `Показать ${visibleCards.length} книг`;
  }

  function renderLibraryUpdateBanner(readingCards) {
    const banner = document.getElementById("libraryUpdateBanner");
    const text = document.getElementById("libraryUpdateText");
    const button = document.getElementById("libraryUpdateButton");
    const close = document.getElementById("libraryUpdateClose");

    if (!banner || !text || !button) {
      return;
    }

    const newCard = readingCards.find(function (card) {
      return card.classList.contains("is-new");
    });

    if (!newCard) {
      banner.hidden = true;
      return;
    }

    const title = newCard.dataset.novelTitle || "Новелла";
    const available = Number(newCard.dataset.availableChapters || 0);

    text.textContent = `${title} — доступна глава ${available}`;
    button.href = `/novel/${newCard.dataset.novelSlug || ""}`;
    banner.hidden = false;

    if (close) {
      close.onclick = function () {
        banner.hidden = true;
      };
    }
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
    const chapterIndex = Number(page.dataset.chapterIndex || 0);
    const availableChapters = Number(page.dataset.availableChapters || 0);

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
      chapterIndex,
      availableChapters,
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

  function getNewChapterCount(novelId, lastKnownAvailableChapters) {
    const card = document.querySelector(
      `[data-library-novel-card][data-novel-id="${cssEscape(String(novelId))}"]`
    );

    if (!card) {
      return 0;
    }

    const currentAvailable = Number(card.dataset.availableChapters || 0);
    const previousAvailable = Number(lastKnownAvailableChapters || 0);

    if (!currentAvailable || !previousAvailable) {
      return 0;
    }

    return Math.max(0, currentAvailable - previousAvailable);
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

  function initPaidChapterReveal() {
    const button = document.querySelector("[data-paid-toggle]");

    if (!button) {
      return;
    }

    button.addEventListener("click", function () {
      document.querySelectorAll("[data-paid-extra]").forEach(function (row) {
        row.hidden = false;

        requestAnimationFrame(function () {
          row.classList.add("paid-chapter-extra-open");
        });
      });

      const fade = document.querySelector("[data-paid-fade]");

      if (fade) {
        fade.remove();
      }
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
              <option value="light">Светлая</option>
              <option value="system">Как в системе</option>
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

  function statusWeight(status) {
    if (status === "completed") return 1;
    if (status === "in_progress") return 2;
    if (status === "paused") return 3;

    return 4;
  }

  function clampNumber(value, min, max) {
    if (Number.isNaN(value)) {
      return min;
    }

    return Math.min(max, Math.max(min, value));
  }

  function cssEscape(value) {
    if (window.CSS && typeof window.CSS.escape === "function") {
      return window.CSS.escape(value);
    }

    return value.replace(/"/g, '\\"');
  }

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
})();
