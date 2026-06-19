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
    accentColor: "#ff6a00",
    appSize: "normal",
  };

  const DEFAULT_FILTER = { query: "", chips: [] };

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
        if (typeof telegram.ready === "function") telegram.ready();
        if (typeof telegram.expand === "function") telegram.expand();
      }
    } catch (error) {
      console.log("Telegram expand skipped:", error);
    }
  }

  function readJson(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (error) {
      return fallback;
    }
  }

  function writeJson(key, value) {
    localStorage.setItem(key, JSON.stringify(value));
  }

  function getSettings() {
    return { ...DEFAULT_SETTINGS, ...readJson(STORAGE_KEYS.settings, {}) };
  }

  function saveSettings(settings) {
    writeJson(STORAGE_KEYS.settings, settings);
  }

  function initSettings() {
    applySettings();
    if (!document.querySelector("[data-settings-fab]")) createSettingsUi();
    bindSettingsUi();
  }

  function applySettings() {
    const settings = getSettings();
    const body = document.body;
    body.dataset.siteTheme = settings.siteTheme || "light";
    body.dataset.readerTheme = settings.readerTheme || "cream";
    body.dataset.readerWidth = settings.readerWidth || "comfort";
    body.dataset.textAlign = settings.textAlign || "left";
    body.dataset.appSize = settings.appSize || "normal";
    body.classList.toggle("hide-foxes", Boolean(settings.hideFoxes));
    document.documentElement.style.setProperty("--accent", settings.accentColor || DEFAULT_SETTINGS.accentColor);
    document.documentElement.style.setProperty("--reader-font-size", `${settings.fontSize || 16}px`);
    document.documentElement.style.setProperty("--reader-line-height", settings.lineHeight || "1.6");
    document.documentElement.style.setProperty("--reader-paragraph-spacing", `${settings.paragraphSpacing || 16}px`);
    applyReaderTheme(settings.readerTheme || "cream");
    updateAppSizeButton();
  }

  function applyReaderTheme(theme) {
    const themes = {
      white: ["#f4f4f4", "#ffffff", "#111111", "#b45309"],
      sepia: ["#ead7bd", "#f4e3c8", "#2b211c", "#92400e"],
      dark: ["#0f0f0f", "#1b1b1b", "#eeeeee", "#fbbf24"],
      cream: ["#f7efe7", "#fffaf3", "#111111", "#b45309"],
    };
    const values = themes[theme] || themes.cream;
    document.documentElement.style.setProperty("--reader-page-bg", values[0]);
    document.documentElement.style.setProperty("--reader-bg", values[1]);
    document.documentElement.style.setProperty("--reader-text-color", values[2]);
    document.documentElement.style.setProperty("--reader-link-color", values[3]);
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
        settings.appSize = settings.appSize === "large" ? "normal" : "large";
        if (settings.appSize === "large") requestSoftExpand();
        saveSettings(settings);
        applySettings();
      });
      document.body.appendChild(button);
    }
    updateAppSizeButton();
  }

  function updateAppSizeButton() {
    const button = document.querySelector("[data-app-size-toggle]");
    if (!button) return;
    const isLarge = getSettings().appSize === "large";
    button.textContent = isLarge ? "↙" : "↗";
    button.title = isLarge ? "Вернуть обычный размер" : "Расширить окно";
    button.setAttribute("aria-label", button.title);
  }

  function initLibrary() {
    if (!document.getElementById("libraryRawCards")) return;
    initLibraryNovelMeta();
    initLibrarySearch();
    initLibraryFilters();
    initLibrarySortControl();
    initLibrarySectionToggles();
    renderLibraryCards();
  }

  function getLibraryFilter() {
    return { ...DEFAULT_FILTER, ...readJson(STORAGE_KEYS.libraryFilter, {}) };
  }

  function saveLibraryFilter(filter) {
    writeJson(STORAGE_KEYS.libraryFilter, filter);
  }

  function initLibrarySearch() {
    const toggle = document.getElementById("librarySearchToggle");
    const panel = document.getElementById("librarySearchPanel");
    const input = document.getElementById("librarySearchInput");
    const clear = document.getElementById("librarySearchClear");
    if (!toggle || !panel || !input) return;

    input.value = getLibraryFilter().query || "";
    toggle.addEventListener("click", function () {
      panel.hidden = !panel.hidden;
      if (!panel.hidden) input.focus();
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
      button.addEventListener("click", function () { toggleFilterChip(button.dataset.quickFilter); });
    });
  }

  function initLibraryFilters() {
    const open = document.getElementById("libraryFilterToggle");
    const sheet = document.getElementById("libraryFilterSheet");
    const reset = document.getElementById("libraryFilterReset");
    const apply = document.getElementById("libraryFilterApply");
    if (!open || !sheet) return;

    open.addEventListener("click", function () {
      syncFilterSheetButtons();
      updateFilterApplyButton();
      sheet.hidden = false;
    });
    sheet.querySelectorAll("[data-filter-close]").forEach(function (button) {
      button.addEventListener("click", function () { sheet.hidden = true; });
    });
    sheet.querySelectorAll("[data-filter-chip]").forEach(function (button) {
      button.addEventListener("click", function () {
        const chip = button.dataset.filterChip;
        if (chip === "all") {
          const current = getLibraryFilter();
          current.chips = [];
          saveLibraryFilter(current);
        } else {
          toggleFilterChip(chip, false);
        }
        syncFilterSheetButtons();
        renderLibraryCards();
        updateFilterApplyButton();
      });
    });
    if (reset) {
      reset.addEventListener("click", function () {
        saveLibraryFilter({ query: "", chips: [] });
        const input = document.getElementById("librarySearchInput");
        if (input) input.value = "";
        syncFilterSheetButtons();
        renderLibraryCards();
        updateFilterApplyButton();
      });
    }
    if (apply) apply.addEventListener("click", function () { sheet.hidden = true; renderLibraryCards(); });
  }

  function initLibrarySortControl() {
    const select = document.getElementById("librarySort");
    if (select) select.addEventListener("change", renderLibraryCards);
  }

  function toggleFilterChip(chip, shouldRender = true) {
    const current = getLibraryFilter();
    const normalized = String(chip || "").trim();
    if (!normalized) return;
    if (current.chips.includes(normalized)) {
      current.chips = current.chips.filter((item) => item !== normalized);
    } else {
      current.chips.push(normalized);
    }
    saveLibraryFilter(current);
    if (shouldRender) renderLibraryCards();
  }

  function syncFilterSheetButtons() {
    const current = getLibraryFilter();
    document.querySelectorAll("[data-filter-chip]").forEach(function (button) {
      const chip = button.dataset.filterChip;
      button.classList.toggle("active", chip === "all" ? current.chips.length === 0 : current.chips.includes(chip));
    });
  }

  function renderActiveFilters() {
    const filter = getLibraryFilter();
    const wrap = document.getElementById("libraryActiveFilters");
    if (!wrap) return;
    const items = [];
    filter.chips.forEach(function (chip) {
      items.push(`<button type="button" data-remove-filter="${escapeHtml(chip)}">${escapeHtml(chip)} <span>×</span></button>`);
    });
    if (filter.query) items.push(`<button type="button" data-clear-search>Поиск: ${escapeHtml(filter.query)} <span>×</span></button>`);
    wrap.hidden = items.length === 0;
    wrap.innerHTML = items.join("");
    wrap.querySelectorAll("[data-remove-filter]").forEach(function (button) {
      button.addEventListener("click", function () { toggleFilterChip(button.dataset.removeFilter); });
    });
    const clearSearch = wrap.querySelector("[data-clear-search]");
    if (clearSearch) {
      clearSearch.addEventListener("click", function () {
        const current = getLibraryFilter();
        current.query = "";
        saveLibraryFilter(current);
        const input = document.getElementById("librarySearchInput");
        if (input) input.value = "";
        renderLibraryCards();
      });
    }
  }

  function initLibrarySectionToggles() {
    document.querySelectorAll("[data-section-toggle]").forEach(function (button) {
      button.addEventListener("click", function () {
        const section = document.querySelector(`[data-library-section="${cssEscape(button.dataset.sectionToggle)}"]`);
        if (section) section.classList.toggle("collapsed");
      });
    });
  }

  function initLibraryNovelMeta() {
    const meta = readJson(STORAGE_KEYS.novelMeta, {});
    document.querySelectorAll("[data-library-novel-card]").forEach(function (card) {
      const novelId = card.dataset.novelId;
      if (!novelId) return;
      meta[novelId] = { novelId, novelSlug: card.dataset.novelSlug || "", novelTitle: card.dataset.novelTitle || "", coverUrl: card.dataset.novelCover || "" };
    });
    writeJson(STORAGE_KEYS.novelMeta, meta);
  }

  function renderLibraryCards() {
    const raw = document.getElementById("libraryRawCards");
    if (!raw) return;
    const lists = {
      reading: document.querySelector('[data-section-list="reading"]'),
      start: document.querySelector('[data-section-list="start"]'),
      waiting: document.querySelector('[data-section-list="waiting"]'),
      finished: document.querySelector('[data-section-list="finished"]'),
    };
    if (!lists.reading || !lists.start || !lists.waiting || !lists.finished) return;

    const filter = getLibraryFilter();
    const history = readJson(STORAGE_KEYS.readingHistory, []);
    const readIds = readJson(STORAGE_KEYS.readChapters, []);
    const historyByNovel = {};
    history.forEach((item) => { historyByNovel[String(item.novelId)] = item; });
    const buckets = { reading: [], start: [], waiting: [], finished: [] };

    Array.from(document.querySelectorAll("[data-library-novel-card]")).forEach(function (card) {
      const state = prepareLibraryCard(card, historyByNovel, readIds);
      card.dataset.cardState = state;
      if (!cardMatchesFilter(card, filter)) {
        raw.appendChild(card);
        return;
      }
      if (state === "new" || state === "reading" || state === "waiting_new") buckets.reading.push(card);
      else if (state === "start") buckets.start.push(card);
      else if (state === "locked" || state === "soon") buckets.waiting.push(card);
      else buckets.finished.push(card);
    });

    Object.values(buckets).forEach(sortCards);
    Object.keys(lists).forEach(function (key) {
      lists[key].innerHTML = "";
      buckets[key].forEach((card) => lists[key].appendChild(card));
      updateSection(key, buckets[key].length);
    });
    const visibleTotal = buckets.reading.length + buckets.start.length + buckets.waiting.length + buckets.finished.length;
    const empty = document.getElementById("libraryEmptyFilter");
    if (empty) empty.hidden = visibleTotal !== 0;
    renderActiveFilters();
    renderLibraryUpdateBanner(buckets.reading);
    updateFilterApplyButton(visibleTotal);
  }

  function prepareLibraryCard(card, historyByNovel) {
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
    const statePill = card.querySelector("[data-card-state-pill]");
    const progressFill = card.querySelector("[data-card-progress-fill]");
    const progressText = card.querySelector("[data-card-progress-text]");

    card.classList.remove("is-reading", "is-new", "is-finished", "is-start", "is-waiting", "is-locked", "is-soon");
    if (button) button.classList.remove("is-disabled-soft");

    const safeHistoryIndex = historyItem && historyItem.chapterIndex ? Math.min(Number(historyItem.chapterIndex || 0), available || Number(historyItem.chapterIndex || 0)) : 0;
    const newCount = historyItem ? getNewChapterCount(novelId, historyItem.availableChapters) : 0;
    let state = "start";
    let visualProgress = projectProgress;
    let progressLabel = chapters ? `${translated || 0} / ${chapters}` : "";

    if (!historyItem && !available) {
      state = projectStatus === "soon" ? "soon" : "locked";
      visualProgress = 0;
      progressLabel = "0 / 0";
    } else if (historyItem && newCount > 0) {
      state = "new";
      visualProgress = safeHistoryIndex && available ? clampNumber((safeHistoryIndex / available) * 100, 0, 100) : 0;
      progressLabel = `${safeHistoryIndex || 0} / ${available || 0}`;
    } else if (historyItem && available && safeHistoryIndex >= available) {
      state = projectStatus === "completed" ? "completed" : "waiting_new";
      visualProgress = 100;
      progressLabel = `${available} / ${available}`;
    } else if (historyItem) {
      state = "reading";
      visualProgress = safeHistoryIndex && available ? clampNumber((safeHistoryIndex / available) * 100, 0, 100) : 0;
      progressLabel = `${safeHistoryIndex || 0} / ${available || 0}`;
    } else {
      state = "start";
      visualProgress = 0;
      progressLabel = available ? `0 / ${available}` : `${translated || 0} / ${chapters || 0}`;
    }

    if (progressFill) progressFill.style.width = `${visualProgress}%`;
    if (progressText) progressText.textContent = progressLabel;

    const configs = {
      new: ["is-new is-reading", "Появилась новая доступная глава", "✨ Новая глава", "state-new", "Читать новую", `/novel/${card.dataset.novelSlug || ""}`],
      reading: ["is-reading", `Вы на главе ${escapeHtml(safeHistoryIndex || "")}`, "📖 Читаю", "state-reading", "Продолжить", `/chapter/${historyItem ? historyItem.chapterId : ""}`],
      waiting_new: ["is-reading is-waiting", "Всё доступное прочитано", "⏳ Жду новую главу", "state-waiting-new", "К оглавлению", `/novel/${card.dataset.novelSlug || ""}`],
      completed: ["is-finished", "Прочитано полностью", "✅ Прочитано", "state-completed", "Перечитать", `/chapter/${historyItem ? historyItem.chapterId : ""}`],
      locked: ["is-locked", "Открытых глав пока нет", "🔒 Жду доступа", "state-locked", "К оглавлению", `/novel/${card.dataset.novelSlug || ""}`],
      soon: ["is-soon", "Главы пока не открыты", "Скоро", "state-soon", "Скоро", `/novel/${card.dataset.novelSlug || ""}`],
      start: ["is-start", projectStatusLabel, "🌱 Можно начать", "state-start", "Начать читать", `/novel/${card.dataset.novelSlug || ""}`],
    };
    const config = configs[state] || configs.start;
    config[0].split(" ").forEach((cls) => cls && card.classList.add(cls));
    if (stateLine) stateLine.innerHTML = `<span>${config[1]}</span>`;
    if (statePill) { statePill.textContent = config[2]; statePill.className = `library-card-state-pill ${config[3]}`; }
    if (button) { button.textContent = config[4]; button.href = config[5]; if (state === "soon") button.classList.add("is-disabled-soft"); }
    return state;
  }

  function cardMatchesFilter(card, filter) {
    const query = String(filter.query || "").toLowerCase().trim();
    const chips = filter.chips || [];
    const state = card.dataset.cardState || "";
    const haystack = [card.dataset.novelTitle, card.dataset.title, card.dataset.description, card.dataset.tags, card.dataset.statusLabel, card.dataset.relation].join(" ").toLowerCase();
    if (query && !haystack.includes(query)) return false;
    for (const chip of chips) {
      if (!chip || chip === "all") continue;
      if (chip === "reading") { if (!(state === "reading" || state === "new" || state === "waiting_new")) return false; continue; }
      if (chip === "new") { if (state !== "new") return false; continue; }
      if (chip === "start") { if (state !== "start") return false; continue; }
      if (chip === "waiting") { if (!(state === "locked" || state === "soon")) return false; continue; }
      if (chip === "finished") { if (state !== "completed") return false; continue; }
      if (chip === "in_progress" || chip === "completed" || chip === "paused") { if (card.dataset.status !== chip) return false; continue; }
      if (!haystack.includes(String(chip).toLowerCase())) return false;
    }
    return true;
  }

  function sortCards(cards) {
    const mode = document.getElementById("librarySort")?.value || "smart";
    cards.sort(function (a, b) {
      if (mode === "title") return String(a.dataset.title || "").localeCompare(String(b.dataset.title || ""), "ru");
      if (mode === "status") return statusWeight(a.dataset.status) - statusWeight(b.dataset.status);
      if (mode === "chapters") return Number(b.dataset.chapters || 0) - Number(a.dataset.chapters || 0);
      if (mode === "translated") return Number(b.dataset.translatedChapters || 0) - Number(a.dataset.translatedChapters || 0);
      if (mode === "added") return String(b.dataset.added || "").localeCompare(String(a.dataset.added || ""));
      if (mode === "smart") {
        const stateWeightA = cardStateWeight(a.dataset.cardState);
        const stateWeightB = cardStateWeight(b.dataset.cardState);
        if (stateWeightA !== stateWeightB) return stateWeightA - stateWeightB;
      }
      return Number(a.dataset.sortOrder || 0) - Number(b.dataset.sortOrder || 0);
    });
  }

  function cardStateWeight(state) {
    return { new: 1, reading: 2, waiting_new: 3, start: 4, locked: 5, soon: 6, completed: 7 }[state] || 99;
  }

  function updateSection(name, count) {
    const section = document.querySelector(`[data-library-section="${cssEscape(name)}"]`);
    const countElement = document.querySelector(`[data-section-count="${cssEscape(name)}"]`);
    if (countElement) countElement.textContent = String(count);
    if (section) section.hidden = count === 0;
  }

  function updateFilterApplyButton(knownCount) {
    const button = document.getElementById("libraryFilterApply");
    if (!button) return;
    if (typeof knownCount === "number") { button.textContent = `Показать ${knownCount} книг`; return; }
    const visibleCards = document.querySelectorAll('[data-section-list="reading"] [data-library-novel-card], [data-section-list="start"] [data-library-novel-card], [data-section-list="waiting"] [data-library-novel-card], [data-section-list="finished"] [data-library-novel-card]');
    button.textContent = `Показать ${visibleCards.length} книг`;
  }

  function renderLibraryUpdateBanner(readingCards) {
    const banner = document.getElementById("libraryUpdateBanner");
    const text = document.getElementById("libraryUpdateText");
    const button = document.getElementById("libraryUpdateButton");
    const close = document.getElementById("libraryUpdateClose");
    if (!banner || !text || !button) return;
    const newCard = readingCards.find((card) => card.dataset.cardState === "new");
    if (!newCard) { banner.hidden = true; return; }
    text.textContent = `${newCard.dataset.novelTitle || "Новелла"} — доступна глава ${Number(newCard.dataset.availableChapters || 0)}`;
    button.href = `/novel/${newCard.dataset.novelSlug || ""}`;
    banner.hidden = false;
    if (close) close.onclick = function () { banner.hidden = true; };
  }

  function initNovelPageMeta() {
    const page = document.querySelector("[data-novel-page]");
    if (!page) return;
    const novelId = page.dataset.novelId;
    if (!novelId) return;
    const cover = document.querySelector(".title-cover");
    const meta = readJson(STORAGE_KEYS.novelMeta, {});
    meta[novelId] = { novelId, novelSlug: page.dataset.novelSlug || "", novelTitle: page.dataset.novelTitle || "", coverUrl: cover && cover.tagName === "IMG" ? cover.getAttribute("src") || "" : "" };
    writeJson(STORAGE_KEYS.novelMeta, meta);
  }

  function initChapterProgress() {
    const page = document.querySelector("[data-chapter-page]");
    if (!page || page.dataset.isLocked === "true") return;
    const novelId = page.dataset.novelId;
    const chapterId = page.dataset.chapterId;
    if (!novelId || !chapterId) return;
    const meta = readJson(STORAGE_KEYS.novelMeta, {});
    const novelMeta = meta[novelId] || {};
    saveReadingHistoryItem({
      novelId,
      novelSlug: page.dataset.novelSlug || novelMeta.novelSlug || "",
      novelTitle: page.dataset.novelTitle || novelMeta.novelTitle || "",
      coverUrl: novelMeta.coverUrl || "",
      chapterId,
      chapterTitle: page.dataset.chapterTitle || "",
      chapterIndex: Number(page.dataset.chapterIndex || 0),
      availableChapters: Number(page.dataset.availableChapters || 0),
      updatedAt: Date.now(),
    });
    saveReadChapter(chapterId);
  }

  function saveReadingHistoryItem(item) {
    const history = readJson(STORAGE_KEYS.readingHistory, []);
    writeJson(STORAGE_KEYS.readingHistory, history.filter((entry) => String(entry.novelId) !== String(item.novelId)).concat(item).slice(-50));
  }

  function saveReadChapter(chapterId) {
    const ids = readJson(STORAGE_KEYS.readChapters, []);
    if (!ids.includes(String(chapterId))) ids.push(String(chapterId));
    writeJson(STORAGE_KEYS.readChapters, ids.slice(-2000));
  }

  function getNewChapterCount(novelId, lastKnownAvailableChapters) {
    const card = document.querySelector(`[data-library-novel-card][data-novel-id="${cssEscape(String(novelId))}"]`);
    if (!card) return 0;
    const currentAvailable = Number(card.dataset.availableChapters || 0);
    const previousAvailable = Number(lastKnownAvailableChapters || 0);
    if (!currentAvailable || !previousAvailable) return 0;
    return Math.max(0, currentAvailable - previousAvailable);
  }

  function initNovelReadButton() {
    const page = document.querySelector("[data-novel-page]");
    const button = document.getElementById("novelReadButton");
    if (!page || !button) return;
    const item = readJson(STORAGE_KEYS.readingHistory, []).find((entry) => String(entry.novelId) === String(page.dataset.novelId));
    if (item && item.chapterId) {
      button.href = `/chapter/${item.chapterId}`;
      button.textContent = item.chapterTitle ? `Продолжить с ${item.chapterTitle}` : "Продолжить чтение";
    }
  }

  function initReadChapterMarks() {
    const readIds = readJson(STORAGE_KEYS.readChapters, []);
    if (!readIds.length) return;
    document.querySelectorAll("[data-chapter-row]").forEach((row) => { if (readIds.includes(String(row.dataset.chapterId))) row.classList.add("chapter-row-read"); });
  }

  function initCollapsibleDescription() {
    document.querySelectorAll("[data-collapsible-description]").forEach(function (block) {
      const content = block.querySelector(".collapsible-description-content");
      const button = block.querySelector("[data-description-toggle]");
      if (!content || !button) return;
      if (content.scrollHeight <= 120) { button.hidden = true; block.classList.add("is-expanded"); return; }
      button.addEventListener("click", function () { const expanded = block.classList.toggle("is-expanded"); button.textContent = expanded ? "Свернуть" : "Ещё"; });
    });
  }

  function initPaidChapterReveal() {
    const button = document.querySelector("[data-paid-toggle]");
    if (!button) return;
    button.addEventListener("click", function () {
      document.querySelectorAll("[data-paid-extra]").forEach(function (row) { row.hidden = false; requestAnimationFrame(function () { row.classList.add("paid-chapter-extra-open"); }); });
      document.querySelector("[data-paid-fade]")?.remove();
    });
  }

  function initSpoilerReveal() {
    document.querySelectorAll("[data-spoiler]").forEach(function (button) {
      button.addEventListener("click", function () {
        if (localStorage.getItem(STORAGE_KEYS.spoilerConfirmed) === "true") { revealSpoiler(button); return; }
        showSpoilerWarning(function (remember) { if (remember) localStorage.setItem(STORAGE_KEYS.spoilerConfirmed, "true"); revealSpoiler(button); });
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
      overlay.innerHTML = `<div class="spoiler-warning-modal"><h2>Осторожно, спойлер</h2><p>Этот тег может раскрыть важную деталь сюжета.</p><label class="spoiler-warning-check"><input type="checkbox" data-spoiler-remember><span>Больше не предупреждать</span></label><div class="spoiler-warning-actions"><button type="button" class="spoiler-warning-cancel" data-spoiler-cancel>Не открывать</button><button type="button" class="spoiler-warning-confirm" data-spoiler-confirm>Показать</button></div></div>`;
      document.body.appendChild(overlay);
    }
    overlay.hidden = false;
    overlay.querySelector("[data-spoiler-cancel]").onclick = function () { overlay.hidden = true; };
    overlay.querySelector("[data-spoiler-confirm]").onclick = function () { const remember = overlay.querySelector("[data-spoiler-remember]"); overlay.hidden = true; onConfirm(remember && remember.checked); };
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
    overlay.innerHTML = `<div class="settings-modal" role="dialog" aria-modal="true"><div class="settings-header"><div><h2>Настройки</h2><p>Оформление сайта и читалки.</p></div><button class="settings-close" type="button" data-settings-close>×</button></div><div class="settings-tabs"><button class="settings-tab active" type="button" data-settings-tab="reader">Читалка</button><button class="settings-tab" type="button" data-settings-tab="site">Сайт</button><button class="settings-tab" type="button" data-settings-tab="about">О проекте</button></div><section class="settings-section active" data-settings-section="reader"><label class="settings-field"><span>Тема текста</span><select data-setting="readerTheme"><option value="cream">Кремовая</option><option value="white">Белая</option><option value="sepia">Сепия</option><option value="dark">Тёмная</option></select></label><label class="settings-field"><span>Ширина текста</span><select data-setting="readerWidth"><option value="comfort">Комфортная</option><option value="full">Широкая</option><option value="wide">Почти вся страница</option></select></label><label class="settings-field"><span>Размер шрифта</span><select data-setting="fontSize"><option value="15">15</option><option value="16">16</option><option value="17">17</option><option value="18">18</option><option value="19">19</option><option value="20">20</option></select></label><label class="settings-field"><span>Межстрочный интервал</span><select data-setting="lineHeight"><option value="1.45">1.45</option><option value="1.6">1.6</option><option value="1.75">1.75</option><option value="1.9">1.9</option></select></label><label class="settings-field"><span>Отступ абзацев</span><select data-setting="paragraphSpacing"><option value="12">12</option><option value="16">16</option><option value="20">20</option><option value="24">24</option></select></label><label class="settings-field"><span>Выравнивание</span><select data-setting="textAlign"><option value="left">По левому краю</option><option value="justify">По ширине</option></select></label></section><section class="settings-section" data-settings-section="site"><label class="settings-field"><span>Тема сайта</span><select data-setting="siteTheme"><option value="light">Светлая</option><option value="system">Как в системе</option><option value="dark">Тёмная</option></select></label><label class="settings-field"><span>Акцентный цвет</span><span class="settings-color-row"><select data-setting="accentColor"><option value="#ff6a00">Апельсин</option><option value="#ec4899">Малина</option><option value="#8b5cf6">Фиолетовый</option><option value="#0ea5e9">Голубой</option><option value="#10b981">Зелёный</option></select><input type="color" data-setting-color value="#ff6a00"></span></label><label class="settings-check"><input type="checkbox" data-setting-checkbox="hideFoxes"><span>Спрятать лисичек</span></label></section><section class="settings-section" data-settings-section="about"><div class="about-box"><div data-about-fox-wrap></div><h3>Зефиркины баоцзы</h3><p>Мини-читалка для новелл, раннего доступа и удобного возвращения к последней главе.</p><div class="about-links"><a href="/library">Библиотека</a></div></div></section><div class="settings-footer"><button class="settings-reset" type="button" data-settings-reset>Сбросить настройки</button></div></div>`;
    document.body.appendChild(fab);
    document.body.appendChild(overlay);
  }

  function bindSettingsUi() {
    const settings = getSettings();
    const fab = document.querySelector("[data-settings-fab]");
    const overlay = document.querySelector("[data-settings-overlay]");
    if (!fab || !overlay) return;
    fillSettingsInputs(settings);
    fab.addEventListener("click", function () { overlay.hidden = false; });
    overlay.addEventListener("click", function (event) { if (event.target === overlay) overlay.hidden = true; });
    overlay.querySelector("[data-settings-close]")?.addEventListener("click", function () { overlay.hidden = true; });
    overlay.querySelectorAll("[data-settings-tab]").forEach(function (tab) { tab.addEventListener("click", function () { const name = tab.dataset.settingsTab; overlay.querySelectorAll("[data-settings-tab]").forEach((item) => item.classList.toggle("active", item === tab)); overlay.querySelectorAll("[data-settings-section]").forEach((section) => section.classList.toggle("active", section.dataset.settingsSection === name)); }); });
    overlay.querySelectorAll("[data-setting]").forEach(function (input) { input.addEventListener("change", function () { const current = getSettings(); current[input.dataset.setting] = input.value; saveSettings(current); applySettings(); }); });
    overlay.querySelectorAll("[data-setting-checkbox]").forEach(function (input) { input.addEventListener("change", function () { const current = getSettings(); current[input.dataset.settingCheckbox] = input.checked; saveSettings(current); applySettings(); }); });
    const colorInput = overlay.querySelector("[data-setting-color]");
    if (colorInput) colorInput.addEventListener("input", function () { const current = getSettings(); current.accentColor = colorInput.value; saveSettings(current); applySettings(); });
    overlay.querySelector("[data-settings-reset]")?.addEventListener("click", function () { saveSettings({ ...DEFAULT_SETTINGS }); fillSettingsInputs(getSettings()); applySettings(); });
    const aboutFoxWrap = overlay.querySelector("[data-about-fox-wrap]");
    if (aboutFoxWrap) { const foxUrl = getFoxUrl("fox_sitting_front") || getFoxUrl("fox_pic") || getFoxUrl("fox_peek"); aboutFoxWrap.innerHTML = foxUrl ? `<img class="about-fox" src="${escapeHtml(foxUrl)}" alt="Лисичка" data-fox>` : `<div class="about-fox-emoji" data-fox>🦊</div>`; }
  }

  function fillSettingsInputs(settings) {
    document.querySelectorAll("[data-setting]").forEach(function (input) { if (Object.prototype.hasOwnProperty.call(settings, input.dataset.setting)) input.value = settings[input.dataset.setting]; });
    document.querySelectorAll("[data-setting-checkbox]").forEach(function (input) { if (Object.prototype.hasOwnProperty.call(settings, input.dataset.settingCheckbox)) input.checked = Boolean(settings[input.dataset.settingCheckbox]); });
    const colorInput = document.querySelector("[data-setting-color]");
    if (colorInput) colorInput.value = settings.accentColor || DEFAULT_SETTINGS.accentColor;
  }

  function getFoxUrl(name) { return (window.ZEFIRKI_FOX && window.ZEFIRKI_FOX[name]) || ""; }
  function statusWeight(status) { return { completed: 1, in_progress: 2, paused: 3 }[status] || 4; }
  function clampNumber(value, min, max) { return Number.isNaN(value) ? min : Math.min(max, Math.max(min, value)); }
  function cssEscape(value) { return window.CSS && typeof window.CSS.escape === "function" ? window.CSS.escape(value) : String(value).replace(/"/g, '\\"'); }
  function escapeHtml(value) { return String(value || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"); }
})();

:root {
  --accent: #ff6a00;
  --accent-soft: rgba(255, 106, 0, 0.12);
  --page-bg: #fff4e8;
  --card-bg: rgba(255, 255, 255, 0.82);
  --card-bg-solid: #fffaf5;
  --text: #241713;
  --muted: #7c6a60;
  --border: rgba(102, 66, 42, 0.12);
  --shadow: 0 16px 40px rgba(80, 50, 20, 0.12);
  --reader-page-bg: #f7efe7;
  --reader-bg: #fffaf3;
  --reader-text-color: #111;
  --reader-link-color: #b45309;
  --reader-font-size: 16px;
  --reader-line-height: 1.6;
  --reader-paragraph-spacing: 16px;
}
* { box-sizing: border-box; }
html { min-height: 100%; }
body { min-height: 100%; margin: 0; font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--page-bg); color: var(--text); }
body[data-site-theme="dark"] { --page-bg:#131313; --card-bg:rgba(30,30,30,.9); --card-bg-solid:#1c1c1c; --text:#f4f4f4; --muted:#c4b8ae; --border:rgba(255,255,255,.12); --shadow:0 16px 40px rgba(0,0,0,.35); }
a { color: inherit; text-decoration: none; }
button, select, input { font: inherit; }
button { cursor: pointer; }
[hidden] { display: none !important; }
.page { width: 100%; min-height: 100vh; padding: 24px; }
.primary-read-button { display: inline-flex; justify-content: center; min-width: 190px; border-radius: 999px; padding: 12px 18px; background: var(--accent); color: #fff; font-weight: 900; }
.empty { padding: 28px 18px; border: 1px solid var(--border); border-radius: 22px; background: var(--card-bg); color: var(--muted); text-align: center; box-shadow: var(--shadow); }
.library-empty-fox { margin-bottom: 8px; font-size: 42px; }

.library-redesign { background: radial-gradient(circle at 82% 6%, rgba(255,176,92,.20), transparent 30%), radial-gradient(circle at 12% 18%, rgba(255,224,186,.75), transparent 34%), linear-gradient(180deg, #fff8f0 0%, #fff0e2 100%); }
.library-app-shell { width: 100%; min-height: 100vh; padding: 18px 12px 30px; }
.library-screen { width: min(100%, 560px); margin: 0 auto; }
body[data-app-size="large"] .library-screen { width: min(100%, 760px); }
.library-hero { position: relative; display: flex; justify-content: space-between; gap: 16px; min-height: 150px; padding: 20px 14px 10px; overflow: visible; }
.library-brand { display: inline-flex; gap: 4px; align-items: center; margin-bottom: 6px; color: #ff640a; font-size: 14px; font-weight: 950; line-height: 1; text-transform: uppercase; letter-spacing: .02em; }
.library-hero h1 { margin: 0 0 6px; color: #211713; font-size: clamp(40px, 11vw, 54px); line-height: .98; letter-spacing: -.055em; font-weight: 950; }
.library-hero p { margin: 0; color: #76665c; font-size: 17px; line-height: 1.35; }
.library-hero-fox, .library-hero-fox-placeholder { width: 96px; height: 96px; flex: 0 0 auto; filter: drop-shadow(0 14px 22px rgba(92,56,25,.18)); }
.library-hero-fox { display: block; object-fit: contain; transform: scaleX(-1) rotate(4deg); }
.library-hero-fox-placeholder { display: grid; place-items: center; font-size: 64px; }
.library-actions { display: grid; grid-template-columns: 1fr 1fr minmax(150px, 1.35fr); gap: 10px; margin-bottom: 12px; }
.library-action-button, .library-sort-pill { min-height: 46px; border: 1px solid rgba(87,54,31,.12); border-radius: 999px; background: rgba(255,255,255,.76); color: #241713; box-shadow: 0 8px 24px rgba(92,56,25,.06); backdrop-filter: blur(10px); }
.library-action-button { display: inline-flex; align-items: center; justify-content: center; gap: 7px; padding: 0 14px; font-weight: 850; }
.library-action-icon { font-size: 20px; }
.library-sort-pill { display: flex; align-items: center; gap: 4px; padding: 0 12px; font-size: 13px; font-weight: 850; }
.library-sort-pill select { min-width: 0; width: 100%; border: 0; background: transparent; color: #241713; font-size: 13px; font-weight: 850; outline: none; }
.library-search-panel, .library-update-banner, .library-empty-filter { margin-bottom: 12px; padding: 12px; border: 1px solid rgba(87,54,31,.12); border-radius: 22px; background: rgba(255,255,255,.78); box-shadow: 0 16px 36px rgba(92,56,25,.08); }
.library-search-input-wrap { display: grid; grid-template-columns: auto 1fr auto; gap: 8px; align-items: center; min-height: 48px; padding: 0 12px; border: 1px solid rgba(87,54,31,.10); border-radius: 16px; background: #fffaf5; color: #7a6a62; }
.library-search-input-wrap input { width: 100%; border: 0; background: transparent; color: #241713; outline: none; font-size: 15px; }
.library-search-input-wrap button { width: 28px; height: 28px; border: 0; border-radius: 999px; background: transparent; color: #7a6a62; font-size: 24px; line-height: 1; }
.library-quick-tags, .library-active-filters { display: flex; flex-wrap: wrap; gap: 8px; }
.library-quick-tags { margin-top: 10px; }
.library-quick-tags button, .library-active-filters button { border: 1px solid rgba(255,106,0,.22); border-radius: 999px; padding: 8px 12px; background: rgba(255,244,232,.9); color: #ff640a; font-size: 13px; font-weight: 850; }
.library-active-filters { margin: 4px 0 12px; }
.library-update-banner { display: grid; grid-template-columns: auto 1fr auto auto; gap: 12px; align-items: center; margin-bottom: 18px; }
.library-update-icon { width: 44px; height: 44px; display: grid; place-items: center; border-radius: 16px; background: rgba(255,100,10,.12); font-size: 24px; }
.library-update-title { color: #241713; font-size: 15px; font-weight: 950; }
.library-update-subtitle { margin-top: 2px; color: #6f625d; font-size: 14px; line-height: 1.3; }
.library-update-button { display: inline-flex; min-height: 38px; align-items: center; justify-content: center; border-radius: 999px; padding: 0 18px; background: linear-gradient(135deg,#ff7b00,#ff5b00); color: #fff; font-weight: 950; box-shadow: 0 12px 26px rgba(255,100,10,.25); }
.library-update-close { width: 32px; height: 32px; border: 0; border-radius: 999px; background: transparent; color: #7a6a62; font-size: 24px; line-height: 1; }
.library-section { margin-bottom: 18px; }
.library-section-header { width: 100%; display: flex; justify-content: space-between; align-items: center; border: 0; margin: 0 0 8px; padding: 0 4px; background: transparent; color: #171312; font-size: 20px; font-weight: 950; letter-spacing: -.03em; }
.library-section-count { display: inline-flex; min-width: 23px; height: 23px; align-items: center; justify-content: center; margin-left: 6px; border-radius: 999px; background: #3d97ff; color: #fff; font-size: 13px; font-weight: 950; vertical-align: middle; }
.library-section[data-library-section="start"] .library-section-count { background: rgba(34,197,94,.18); color: #138b3f; }
.library-section[data-library-section="waiting"] .library-section-count { background: rgba(245,158,11,.18); color: #a15f00; }
.library-section[data-library-section="finished"] .library-section-count { background: rgba(87,54,31,.12); color: #2b211c; }
.library-section-arrow { color: #6f625d; font-size: 20px; }
.library-section-helper { display: none; margin: -2px 4px 10px; color: #9a897e; font-size: 13px; line-height: 1.35; }
.library-section[data-library-section="waiting"] .library-section-helper { display: block; }
.library-section.collapsed .library-section-list, .library-section.collapsed .library-section-helper { display: none; }
.library-section.collapsed .library-section-arrow { transform: rotate(180deg); }
.library-section-list { display: flex; flex-direction: column; gap: 10px; }
.library-book-card { display: grid; grid-template-columns: 118px minmax(0,1fr); gap: 13px; padding: 12px; border: 1px solid rgba(87,54,31,.09); border-radius: 20px; background: rgba(255,255,255,.82); box-shadow: 0 12px 30px rgba(92,56,25,.08); transition: transform .16s ease,border-color .16s ease,box-shadow .16s ease,opacity .16s ease; backdrop-filter: blur(12px); }
.library-book-card:hover { transform: translateY(-1px); box-shadow: 0 18px 42px rgba(92,56,25,.12); }
.library-book-card.is-new { border-color: rgba(255,100,10,.5); box-shadow: 0 18px 44px rgba(255,100,10,.13), 0 0 0 1px rgba(255,100,10,.12) inset; }
.library-book-card.is-locked, .library-book-card.is-soon, .library-book-card.is-finished { opacity: .86; }
.library-book-card.is-finished .library-book-cover, .library-book-card.is-locked .library-book-cover, .library-book-card.is-soon .library-book-cover { filter: grayscale(.7); }
.library-book-cover-link, .library-cover-frame, .library-book-cover { width: 118px; }
.library-cover-frame { position: relative; display: block; }
.library-book-cover { height: 164px; display: flex; align-items: center; justify-content: center; border-radius: 16px; object-fit: cover; background: linear-gradient(135deg,#0f2140,#142f62); color: #fff; font-size: 14px; box-shadow: 0 12px 24px rgba(21,34,55,.18); }
.library-age-badge { position: absolute; right: 7px; bottom: 7px; z-index: 3; display: inline-flex; min-width: 34px; height: 26px; align-items: center; justify-content: center; padding: 0 8px; border-radius: 999px; background: rgba(17,17,17,.78); color: #fff; font-size: 12px; font-weight: 950; line-height: 1; box-shadow: 0 8px 18px rgba(0,0,0,.24); backdrop-filter: blur(8px); }
.library-book-body { min-width: 0; display: flex; flex-direction: column; }
.library-book-topline { display: grid; grid-template-columns: 1fr auto; gap: 8px; align-items: start; margin-bottom: 5px; }
.library-book-title { color: #171312; font-size: 16px; line-height: 1.24; font-weight: 950; letter-spacing: -.02em; overflow-wrap: anywhere; }
.library-book-menu { width: 28px; height: 28px; border: 0; border-radius: 999px; background: transparent; color: #5b4b43; font-size: 22px; line-height: 1; }
.library-book-description { display: -webkit-box; overflow: hidden; min-height: 34px; margin: 0 0 7px; color: #76665c; font-size: 13px; line-height: 1.35; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.library-book-state-line { display: flex; flex-wrap: wrap; gap: 6px 8px; align-items: center; min-height: 20px; margin-bottom: 7px; color: #6f625d; font-size: 13px; line-height: 1.25; }
.library-card-stats { display: flex; flex-wrap: wrap; gap: 12px; margin: 0 0 7px; color: #5c4e46; font-size: 13px; line-height: 1.2; }
.library-card-stats span { display: inline-flex; align-items: center; gap: 4px; white-space: nowrap; }
.library-progress-row { display: grid; grid-template-columns: 1fr auto; gap: 8px; align-items: center; margin: 0 0 8px; }
.library-progress-track { height: 7px; overflow: hidden; border-radius: 999px; background: rgba(93,64,44,.12); }
.library-progress-fill { display: block; height: 100%; width: 0%; border-radius: inherit; background: linear-gradient(90deg,#ff7b00,#ff5b00); }
.library-progress-text { color: #51443e; font-size: 12px; font-weight: 850; }
.library-card-tags { display: flex; flex-wrap: wrap; gap: 5px; min-width: 0; margin-bottom: 9px; }
.library-mini-tag, .tag { display: inline-flex; min-height: 22px; align-items: center; border: 0; border-radius: 999px; padding: 4px 8px; background: rgba(87,54,31,.07); color: #2b211c; font-size: 11px; font-weight: 850; white-space: nowrap; }
.tag { min-height: 24px; font-size: 12px; }
.library-mini-tag.tag-slash, .tag-slash { background: rgba(82,146,255,.16); color: #1d5fd4; }
.library-mini-tag.tag-get, .tag-get { background: rgba(255,82,82,.13); color: #d64242; }
.library-mini-tag.tag-gen, .tag-gen { background: rgba(34,197,94,.13); color: #138b3f; }
.tag-country { background: rgba(14,165,233,.16); }
.tag-rating { background: rgba(239,68,68,.16); }
.tag-spoiler { background: rgba(0,0,0,.12); color: var(--muted); }
.tag-spoiler-reveal { cursor: pointer; }
.tag-spoiler-opened { background: rgba(139,92,246,.18); }
.library-card-footer { display: grid; grid-template-columns: minmax(0,1fr) auto; gap: 10px; align-items: center; margin-top: auto; }
.library-card-state-pill { display: inline-flex; width: fit-content; max-width: 100%; min-height: 30px; align-items: center; justify-content: center; border-radius: 999px; padding: 0 12px; font-size: 12px; font-weight: 950; white-space: nowrap; }
.state-reading { background: rgba(124,92,255,.16); color: #6b3fe8; }
.state-new { background: rgba(255,106,0,.15); color: #ff640a; }
.state-start { background: rgba(34,197,94,.14); color: #138b3f; }
.state-waiting-new, .state-locked, .state-soon { background: rgba(245,158,11,.16); color: #a15f00; }
.state-completed { background: rgba(34,197,94,.15); color: #138b3f; }
.library-card-button { display: inline-flex; min-height: 38px; min-width: 118px; align-items: center; justify-content: center; border-radius: 999px; padding: 0 16px; background: linear-gradient(135deg,#ff7b00,#ff5b00); color: #fff; font-size: 13px; font-weight: 950; box-shadow: 0 12px 26px rgba(255,100,10,.22); }
.library-card-button.is-disabled-soft, .library-book-card.is-finished .library-card-button, .library-book-card.is-locked .library-card-button, .library-book-card.is-soon .library-card-button { background: #f2ebe3; color: #6f625d; box-shadow: none; }
.library-filter-sheet { position: fixed; inset: 0; z-index: 1300; }
.library-filter-backdrop { position: absolute; inset: 0; background: rgba(30,20,12,.34); }
.library-filter-panel { position: absolute; left: 50%; bottom: 0; width: min(100%,560px); max-height: min(86vh,760px); overflow: auto; transform: translateX(-50%); border-radius: 30px 30px 0 0; background: #fffaf5; box-shadow: 0 -22px 60px rgba(92,56,25,.20); }
.library-filter-handle { width: 48px; height: 5px; margin: 10px auto 8px; border-radius: 999px; background: rgba(87,54,31,.18); }
.library-filter-header { display: flex; justify-content: space-between; gap: 14px; align-items: center; padding: 6px 24px 14px; }
.library-filter-header h2 { margin: 0; color: #171312; font-size: 26px; line-height: 1; font-weight: 950; }
.library-filter-header button { width: 36px; height: 36px; border: 0; border-radius: 999px; background: transparent; color: #6f625d; font-size: 30px; line-height: 1; }
.library-filter-group { padding: 0 24px 18px; }
.library-filter-group h3, .library-filter-legend h3 { margin: 0 0 10px; color: #6f625d; font-size: 14px; font-weight: 900; }
.library-filter-chips { display: flex; flex-wrap: wrap; gap: 10px; }
.library-filter-chips button { min-height: 38px; border: 1px solid rgba(87,54,31,.12); border-radius: 999px; padding: 0 14px; background: rgba(255,255,255,.72); color: #2b211c; font-size: 13px; font-weight: 850; }
.library-filter-chips button.active { border-color: rgba(255,100,10,.55); background: linear-gradient(135deg,#ff7b00,#ff5b00); color: #fff; }
.library-filter-legend { margin: 0 16px 16px; padding: 16px; border: 1px solid rgba(87,54,31,.10); border-radius: 22px; background: rgba(255,255,255,.64); }
.library-filter-legend-grid { display: grid; gap: 10px; }
.library-filter-legend-grid div { display: grid; grid-template-columns: auto 1fr; gap: 2px 10px; align-items: start; }
.library-filter-legend-grid span { grid-row: span 2; font-size: 20px; }
.library-filter-legend-grid strong { color: #241713; font-size: 13px; }
.library-filter-legend-grid small { color: #7a6a62; font-size: 12px; line-height: 1.25; }
.library-filter-footer { position: sticky; bottom: 0; display: grid; grid-template-columns: 1fr 1.35fr; gap: 12px; padding: 16px 24px 24px; border-top: 1px solid rgba(87,54,31,.10); background: #fffaf5; }
.library-filter-reset, .library-filter-apply { min-height: 58px; border-radius: 16px; font-size: 16px; font-weight: 950; }
.library-filter-reset { border: 1px solid rgba(255,100,10,.7); background: transparent; color: #2b211c; }
.library-filter-apply { border: 0; background: linear-gradient(135deg,#ff7b00,#ff5b00); color: #fff; box-shadow: 0 16px 34px rgba(255,100,10,.22); }

.title-hero, .character-card, .chapters-section, .locked-chapter-notice, .chapter-content { border: 1px solid var(--border); border-radius: 26px; background: var(--card-bg); box-shadow: var(--shadow); }
.title-hero { position: relative; overflow: hidden; margin-bottom: 18px; padding: 22px; }
.title-hero-bg { position: absolute; inset: 0; opacity: .08; background-position: center; background-size: cover; filter: blur(16px); transform: scale(1.08); }
.title-hero-content { position: relative; display: grid; grid-template-columns: 170px minmax(0,1fr); gap: 24px; align-items: start; }
.title-cover-wrap { overflow: hidden; border-radius: 18px; background: #f3e4d4; }
.title-cover, .title-cover.placeholder { width: 100%; aspect-ratio: 3/4; display: flex; align-items: center; justify-content: center; object-fit: cover; font-size: 42px; }
.novel-page-title-line { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.title-info h1 { margin: 0 0 6px; font-size: clamp(28px,4.6vw,42px); line-height: 1.18; }
.novel-title-en { margin: 0 0 10px; color: var(--muted); font-style: italic; }
.inline-fox { width: 58px; max-width: 14vw; flex: 0 0 auto; }
.title-status-line, .novel-meta-line, .novel-tags { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.novel-tags { margin-top: 12px; }
.status-label, .meta-pill { display: inline-flex; align-items: center; border-radius: 999px; padding: 6px 10px; font-size: 13px; font-weight: 900; }
.status-label { color: #fff; line-height: 1; }
.meta-pill { min-height: 28px; gap: 6px; background: rgba(242,140,56,.14); color: var(--text); }
.progress-mini { width: 58px; height: 6px; overflow: hidden; border-radius: 999px; background: rgba(80,50,20,.14); }
.progress-mini span { display: block; height: 100%; border-radius: inherit; background: var(--accent); }
.novel-description { color: var(--muted); line-height: 1.55; }
.collapsible-description { position: relative; max-width: 860px; margin-top: 14px; padding-bottom: 36px; }
.collapsible-description-content { overflow: hidden; max-height: 112px; position: relative; }
.collapsible-description:not(.is-expanded) .collapsible-description-content::after { content: ""; position: absolute; left: 0; right: 0; bottom: 0; height: 36px; background: linear-gradient(to bottom, rgba(255,250,243,0), var(--card-bg-solid)); }
.collapsible-description.is-expanded .collapsible-description-content { max-height: none; }
.description-toggle, .paid-chapters-toggle, .settings-reset { border: 0; border-radius: 999px; padding: 8px 12px; background: var(--accent-soft); color: var(--text); font-weight: 800; }
.collapsible-description:not(.is-expanded) .description-toggle { position: absolute; left: 0; bottom: 0; z-index: 4; }
.collapsible-description.is-expanded .description-toggle { position: static; display: inline-flex; margin-top: 4px; }
.character-info { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 14px; margin-bottom: 18px; }
.character-card { padding: 16px; }
.character-card h2 { margin: 0 0 8px; font-size: 18px; }
.character-card p { margin: 0; color: var(--muted); line-height: 1.55; }
.novel-read-action { margin-bottom: 18px; }
.chapters-section { padding: 18px; }
.section-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 12px; }
.section-title { margin: 0; font-size: 24px; }
.section-fox { width: 58px; }
.chapter-list { display: flex; flex-direction: column; gap: 8px; }
.volume-header { margin: 12px 0 4px; color: var(--muted); font-size: 14px; font-weight: 900; }
.chapter-row { display: flex; gap: 12px; align-items: center; justify-content: space-between; border: 1px solid var(--border); border-radius: 16px; padding: 12px 14px; background: var(--card-bg-solid); }
.chapter-row-read .chapter-title { opacity: .58; }
.chapter-access { flex: 0 0 auto; border-radius: 999px; padding: 5px 9px; font-size: 12px; font-weight: 900; }
.chapter-access-public { background: rgba(68,187,68,.15); }
.chapter-access-locked { background: rgba(245,158,11,.16); }
.paid-chapter-extra { opacity: 0; transform: translateY(-4px); transition: opacity .22s ease, transform .22s ease; }
.paid-chapter-extra-open { opacity: 1; transform: translateY(0); }
.paid-chapters-fade { position: relative; padding: 18px 14px 16px; text-align: center; background: linear-gradient(to bottom,rgba(255,250,243,0),rgba(255,250,243,.92) 28%,rgba(255,250,243,1)); }
.paid-chapters-toggle { background: var(--accent); color: #fff; box-shadow: 0 10px 24px rgba(80,50,20,.16); }

.page-chapter { background: var(--reader-page-bg); }
.chapter-layout { max-width: min(820px, calc(100vw - 24px)); }
body[data-app-size="large"] .chapter-layout { max-width: min(1040px, calc(100vw - 16px)); }
body[data-reader-width="full"] .chapter-layout { max-width: min(1040px, calc(100vw - 24px)); }
body[data-reader-width="wide"] .chapter-layout { max-width: min(1180px, calc(100vw - 24px)); }
.back-link { display: inline-flex; margin-bottom: 14px; color: var(--muted); font-weight: 900; }
.chapter-header { margin-bottom: 14px; }
.chapter-header h1 { margin: 0 0 6px; font-size: clamp(26px,4.6vw,42px); line-height: 1.18; }
.chapter-subtitle { margin-top: 8px; display: flex; flex-wrap: wrap; gap: 8px; }
.locked-chapter-notice { margin-bottom: 18px; padding: 18px; }
.locked-title { margin-bottom: 10px; font-size: 20px; font-weight: 900; }
.locked-chapter-notice p { color: var(--muted); line-height: 1.55; }
.chapter-content-shell { position: relative; width: min(100%,720px); margin: 22px auto 0; }
body[data-reader-width="full"] .chapter-content-shell { width: min(100%,860px); }
body[data-reader-width="wide"] .chapter-content-shell { width: min(100%,980px); }
.chapter-side-fox { position: absolute; left: -58px; top: 20px; z-index: 3; width: 72px; pointer-events: none; }
.chapter-content { width: 100%; padding: 28px; background: var(--reader-bg); color: var(--reader-text-color); font-size: var(--reader-font-size); line-height: var(--reader-line-height); user-select: none; -webkit-user-select: none; }
.chapter-content p { margin: 0 0 var(--reader-paragraph-spacing); }
.chapter-content img { max-width: 100%; height: auto; }
body[data-text-align="justify"] .chapter-content { text-align: justify; }
.chapter-content-locked { max-height: 460px; overflow: hidden; position: relative; }
.chapter-content-locked::after { content: ""; position: absolute; inset: auto 0 0; height: 140px; background: linear-gradient(to bottom,rgba(255,250,243,0),var(--reader-bg)); }
.chapter-navigation { display: grid; grid-template-columns: 1fr auto 1fr; gap: 10px; width: min(100%,720px); margin: 18px auto 0; }
.chapter-nav-button, .chapter-nav-placeholder { min-height: 42px; }
.chapter-nav-button { display: inline-flex; align-items: center; justify-content: center; border-radius: 999px; padding: 10px 14px; background: var(--reader-bg); color: var(--reader-text-color); font-weight: 900; box-shadow: var(--shadow); }
.chapter-nav-main { background: var(--accent); color: #fff; }
.chapter-footer-fox-wrap { display: flex; justify-content: center; margin-top: 18px; }
.chapter-footer-fox { width: 76px; }
.settings-fab, .app-size-fab { position: fixed; z-index: 1000; width: 44px; height: 44px; border: 0; border-radius: 999px; color: #fff; font-size: 21px; font-weight: 900; line-height: 1; box-shadow: 0 12px 30px rgba(80,50,20,.22); }
.settings-fab { right: 12px; bottom: 12px; background: #2b211c; }
.app-size-fab { top: 12px; right: 12px; display: inline-flex; align-items: center; justify-content: center; background: var(--accent); }
.settings-overlay, .spoiler-warning-overlay { position: fixed; inset: 0; z-index: 1200; display: flex; align-items: center; justify-content: center; padding: 16px; background: rgba(0,0,0,.45); }
.settings-modal, .spoiler-warning-modal { width: min(560px,100%); max-height: min(760px, calc(100vh - 32px)); overflow: auto; border-radius: 24px; background: var(--card-bg-solid); color: var(--text); box-shadow: 0 24px 80px rgba(0,0,0,.35); padding: 18px; }
.settings-header { display: flex; justify-content: space-between; gap: 14px; align-items: flex-start; margin-bottom: 14px; }
.settings-header h2 { margin: 0 0 4px; }
.settings-header p { margin: 0; color: var(--muted); }
.settings-close { width: 36px; height: 36px; border: 0; border-radius: 999px; background: rgba(80,50,20,.08); color: var(--text); font-size: 24px; line-height: 1; }
.settings-tabs { display: flex; gap: 8px; margin-bottom: 14px; overflow-x: auto; }
.settings-tab { border: 0; border-radius: 999px; padding: 8px 12px; background: rgba(80,50,20,.08); color: var(--text); font-weight: 900; }
.settings-tab.active { background: var(--accent); color: #fff; }
.settings-section { display: none; }
.settings-section.active { display: block; }
.settings-field { display: grid; gap: 7px; margin-bottom: 12px; color: var(--muted); font-size: 14px; font-weight: 800; }
.settings-field select, .settings-field input[type="color"] { width: 100%; border: 1px solid var(--border); border-radius: 14px; padding: 10px 12px; background: var(--card-bg); color: var(--text); }
.settings-color-row { display: grid; grid-template-columns: 1fr 56px; gap: 8px; }
.settings-check { display: flex; align-items: center; gap: 10px; margin: 12px 0; color: var(--text); font-weight: 800; }
.about-box { text-align: center; color: var(--muted); }
.about-fox { width: 88px; }
.about-fox-emoji { font-size: 70px; }
.spoiler-warning-modal h2 { margin: 0 0 8px; }
.spoiler-warning-modal p { color: var(--muted); line-height: 1.5; }
.spoiler-warning-check { display: flex; gap: 10px; align-items: center; margin: 14px 0; }
.spoiler-warning-actions { display: flex; justify-content: flex-end; gap: 10px; }
.spoiler-warning-cancel, .spoiler-warning-confirm { border: 0; border-radius: 999px; padding: 9px 14px; font-weight: 900; }
.spoiler-warning-cancel { background: rgba(80,50,20,.08); color: var(--text); }
.spoiler-warning-confirm { background: var(--accent); color: #fff; }
.hide-foxes [data-fox] { display: none !important; }

body[data-site-theme="dark"] .library-redesign, body[data-site-theme="dark"].library-redesign { background: radial-gradient(circle at 80% 0%, rgba(255,177,96,.12), transparent 34%), linear-gradient(180deg,#171311 0%,#101010 100%); }
body[data-site-theme="dark"] .library-hero h1, body[data-site-theme="dark"] .library-book-title, body[data-site-theme="dark"] .library-section-header, body[data-site-theme="dark"] .library-action-button, body[data-site-theme="dark"] .library-sort-pill, body[data-site-theme="dark"] .library-sort-pill select { color: #f6eee7; }
body[data-site-theme="dark"] .library-hero p, body[data-site-theme="dark"] .library-book-description, body[data-site-theme="dark"] .library-book-state-line, body[data-site-theme="dark"] .library-progress-text, body[data-site-theme="dark"] .library-card-stats { color: #c7b9ae; }
body[data-site-theme="dark"] .library-book-card, body[data-site-theme="dark"] .library-action-button, body[data-site-theme="dark"] .library-sort-pill, body[data-site-theme="dark"] .library-search-panel, body[data-site-theme="dark"] .library-update-banner, body[data-site-theme="dark"] .library-empty-filter { background: rgba(32,28,26,.86); border-color: rgba(255,255,255,.09); }
body[data-site-theme="dark"] .library-search-input-wrap, body[data-site-theme="dark"] .library-filter-panel, body[data-site-theme="dark"] .library-filter-footer { background: #201c1a; }
body[data-site-theme="dark"] .library-search-input-wrap input, body[data-site-theme="dark"] .library-filter-header h2, body[data-site-theme="dark"] .library-filter-chips button { color: #f6eee7; }
body[data-site-theme="dark"] .library-filter-chips button { background: rgba(255,255,255,.06); border-color: rgba(255,255,255,.09); }

@media (max-width: 820px) {
  .page { padding: 16px; }
  .title-hero-content { grid-template-columns: 130px minmax(0,1fr); gap: 16px; }
  .character-info { grid-template-columns: 1fr; }
  .chapter-content-shell, .chapter-navigation { width: 100% !important; }
  .chapter-side-fox { left: 8px; top: -34px; width: 56px; }
  .chapter-content { padding-top: 34px; }
}
@media (max-width: 640px) {
  .library-app-shell { padding: 14px 10px 24px; }
  .library-hero { padding: 18px 8px 8px; }
  .library-hero-fox, .library-hero-fox-placeholder { width: 82px; height: 82px; }
  .library-hero-fox-placeholder { font-size: 56px; }
  .library-actions { grid-template-columns: 1fr 1fr; }
  .library-sort-pill { grid-column: 1 / -1; }
  .library-book-card { grid-template-columns: 112px minmax(0,1fr); gap: 12px; padding: 12px; }
  .library-book-cover-link, .library-cover-frame, .library-book-cover { width: 112px; }
  .library-book-cover { height: 154px; }
  .library-book-title { font-size: 15px; }
  .library-book-description { font-size: 12px; }
  .library-card-stats { gap: 9px; font-size: 12px; }
  .library-card-tags .library-mini-tag:nth-child(n+4) { display: none; }
  .library-card-footer { grid-template-columns: 1fr; gap: 8px; }
  .library-card-button { width: 100%; }
  .library-update-banner { grid-template-columns: auto 1fr auto; }
  .library-update-button { grid-column: 2 / 4; width: 100%; }
  .library-filter-panel { width: 100%; }
  .title-hero-content { grid-template-columns: 1fr; }
  .title-cover-wrap { max-width: 180px; }
  .chapter-content { padding: 22px 18px; }
  .chapter-navigation { grid-template-columns: 1fr; }
  .chapter-nav-placeholder { display: none; }
}
@media (max-width: 420px) {
  .library-book-card { grid-template-columns: 94px minmax(0,1fr); }
  .library-book-cover-link, .library-cover-frame, .library-book-cover { width: 94px; }
  .library-book-cover { height: 132px; border-radius: 14px; }
  .library-age-badge { right: 6px; bottom: 6px; min-width: 30px; height: 23px; font-size: 11px; }
  .library-mini-tag:nth-child(n+4) { display: none; }
}
