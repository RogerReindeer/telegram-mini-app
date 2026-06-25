(function () {
  const STORAGE_KEYS = {
    settings: "zefirki_reader_settings",
    readingHistory: "zefirki_reading_history",
    novelMeta: "zefirki_novel_meta",
    readChapters: "zefirki_read_chapters",
    spoilerConfirmed: "zefirki_spoiler_confirmed",
    libraryFilter: "zefirki_library_filter",
    hiddenNovels: "zefirki_hidden_novels",
    favoriteNovels: "zefirki_favorite_novels",
    completedNovels: "zefirki_completed_novels",
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

  document.addEventListener("DOMContentLoaded", async function () {
    initTelegram();
    const reloading = await initTelegramAuth();
    if (reloading) return;

    initSettings();
    initAppFullscreenButton();
    initLibrary();
    initNovelPageMeta();
    initChapterProgress();
    initNovelReadButton();
    initNovelReadingProgress();
    initReadChapterMarks();
    initCollapsibleDescription();
    initPaidChapterReveal();
    initChapterSortToggle();
    initChapterJumpButtons();
    initSpoilerReveal();
    initAccessActions();
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

  function getTelegramWebApp() {
    return window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  }

  function getTelegramInitData() {
    const telegram = getTelegramWebApp();

    if (telegram && telegram.initData) {
      try {
        sessionStorage.setItem("zefirki_telegram_init_data", telegram.initData);
      } catch (error) {
        console.debug("Telegram initData cache unavailable", error);
      }
      return telegram.initData;
    }

    const candidates = [];
    try {
      candidates.push(new URLSearchParams(window.location.search).get("tgWebAppData"));
    } catch (error) {
      console.debug("Telegram query params unavailable", error);
    }

    try {
      const hash = window.location.hash.replace(/^#/, "");
      candidates.push(new URLSearchParams(hash).get("tgWebAppData"));
    } catch (error) {
      console.debug("Telegram hash params unavailable", error);
    }

    try {
      candidates.push(
        window.Telegram &&
        window.Telegram.WebView &&
        window.Telegram.WebView.initParams
          ? window.Telegram.WebView.initParams.tgWebAppData
          : ""
      );
    } catch (error) {
      console.debug("Telegram WebView params unavailable", error);
    }

    try {
      candidates.push(sessionStorage.getItem("zefirki_telegram_init_data"));
    } catch (error) {
      console.debug("Telegram initData cache unavailable", error);
    }

    const initData = candidates.find(function (value) {
      return typeof value === "string" && value.trim().length > 0;
    }) || "";

    if (initData) {
      try {
        sessionStorage.setItem("zefirki_telegram_init_data", initData);
      } catch (error) {
        console.debug("Telegram initData cache unavailable", error);
      }
    }

    return initData;
  }

  function simpleHash(value) {
    let hash = 0;
    const text = String(value || "");
    for (let index = 0; index < text.length; index += 1) {
      hash = ((hash << 5) - hash + text.charCodeAt(index)) | 0;
    }
    return Math.abs(hash).toString(36);
  }

  function showAuthOverlay() {
    let overlay = document.querySelector("[data-auth-overlay]");
    if (!overlay) {
      overlay = document.createElement("div");
      overlay.className = "auth-overlay";
      overlay.dataset.authOverlay = "true";
      overlay.innerHTML = `<div class="auth-overlay-card"><span class="auth-spinner"></span><span>Проверяем доступ в Telegram…</span></div>`;
      document.body.appendChild(overlay);
    }
    overlay.hidden = false;
  }

  function hideAuthOverlay() {
    const overlay = document.querySelector("[data-auth-overlay]");
    if (overlay) overlay.hidden = true;
  }

  async function postTelegramAuth(initData) {
    const response = await fetch("/api/auth/telegram", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ init_data: initData }),
    });
    const data = await response.json().catch(function () { return {}; });
    if (!response.ok) {
      throw new Error(data.detail || "Не удалось проверить доступ Telegram");
    }
    return data;
  }

  async function initTelegramAuth() {
    const initData = getTelegramInitData();
    const viewer = window.ZEFIRKI_VIEWER || {};

    if (!initData || viewer.authenticated) return false;

    const attemptKey = `zefirki_auth_attempt_${simpleHash(initData)}`;
    if (sessionStorage.getItem(attemptKey) === "done") return false;

    sessionStorage.setItem(attemptKey, "done");
    showAuthOverlay();
    try {
      await postTelegramAuth(initData);
      window.location.reload();
      return true;
    } catch (error) {
      console.error(error);
      hideAuthOverlay();
      return false;
    }
  }

  function initAccessActions() {
    document.querySelectorAll("[data-telegram-link]").forEach(function (link) {
      link.addEventListener("click", function (event) {
        const telegram = getTelegramWebApp();
        const href = link.getAttribute("href") || "";
        if (telegram && href.startsWith("https://t.me/") && typeof telegram.openTelegramLink === "function") {
          event.preventDefault();
          telegram.openTelegramLink(href);
        }
      });
    });

    document.querySelectorAll("[data-refresh-access]").forEach(function (button) {
      button.addEventListener("click", async function () {
        const initData = getTelegramInitData();
        if (!initData) {
          alert(
            "Telegram не передал данные Mini App. Закройте это окно и откройте читалку через кнопку Mini App в боте, а не через обычную ссылку."
          );
          return;
        }
        button.disabled = true;
        button.textContent = "Проверяем…";
        showAuthOverlay();
        try {
          await postTelegramAuth(initData);
          window.location.reload();
        } catch (error) {
          console.error(error);
          hideAuthOverlay();
          button.disabled = false;
          button.textContent = "Проверить доступ ещё раз";
          alert(error.message || "Не удалось проверить доступ");
        }
      });
    });
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

    // В этой версии лисички — обязательный фирменный элемент.
    // Если в старом localStorage была включена настройка hideFoxes, она могла скрыть все изображения.
    if (settings.hideFoxes) {
      settings.hideFoxes = false;
      saveSettings(settings);
    }
    body.classList.remove("hide-foxes");

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

  function isMobileTelegramClient() {
    const telegram = getTelegramWebApp();
    const platform = String(telegram && telegram.platform || "").toLowerCase();
    if (["android", "android_x", "ios"].includes(platform)) return true;
    return /android|iphone|ipad|ipod|mobile/i.test(navigator.userAgent || "");
  }

  function initAppFullscreenButton() {
    let button = document.querySelector("[data-app-size-toggle]");
    if (!button) {
      button = document.createElement("button");
      button.className = "app-size-fab app-fullscreen-fab";
      button.type = "button";
      button.dataset.appSizeToggle = "true";
      document.body.appendChild(button);
    }

    if (isMobileTelegramClient()) {
      button.hidden = true;
      return;
    }

    const telegram = getTelegramWebApp();
    if (!telegram) {
      button.hidden = true;
      return;
    }

    const update = function () {
      const isFullscreen = Boolean(telegram.isFullscreen);
      button.textContent = isFullscreen ? "↙" : "↗";
      button.title = isFullscreen ? "Вернуть обычный размер" : "Открыть на весь экран";
      button.setAttribute("aria-label", button.title);
      button.setAttribute("aria-pressed", isFullscreen ? "true" : "false");
    };

    button.hidden = false;
    button.addEventListener("click", function () {
      try {
        if (telegram.isFullscreen && typeof telegram.exitFullscreen === "function") {
          telegram.exitFullscreen();
        } else if (typeof telegram.requestFullscreen === "function") {
          telegram.requestFullscreen();
        } else if (typeof telegram.expand === "function") {
          telegram.expand();
        }
      } catch (error) {
        console.error("Не удалось изменить полноэкранный режим", error);
      }
      window.setTimeout(update, 120);
    });

    if (typeof telegram.onEvent === "function") {
      telegram.onEvent("fullscreenChanged", update);
      telegram.onEvent("fullscreenFailed", update);
    }
    update();
  }

  function initLibrary() {
    if (!document.getElementById("libraryRawCards")) return;
    initLibraryNovelMeta();
    initLibrarySearch();
    initLibraryFilters();
    initLibrarySortControl();
    initLibrarySectionToggles();
    initLibraryCardMenus();
    initLibraryCardNavigation();
    renderLibraryCards();
  }

  function getLibraryFilter() {
    return { ...DEFAULT_FILTER, ...readJson(STORAGE_KEYS.libraryFilter, {}) };
  }

  function saveLibraryFilter(filter) {
    writeJson(STORAGE_KEYS.libraryFilter, filter);
  }

  function animateLibraryControl(element, className = "is-animating", duration = 260) {
    if (!element) return;
    element.classList.remove(className);
    void element.offsetWidth;
    element.classList.add(className);
    window.setTimeout(function () {
      element.classList.remove(className);
    }, duration);
  }

  function initLibrarySearch() {
    const toggle = document.getElementById("librarySearchToggle");
    const panel = document.getElementById("librarySearchPanel");
    const input = document.getElementById("librarySearchInput");
    const clear = document.getElementById("librarySearchClear");
    if (!toggle || !panel || !input) return;

    input.value = getLibraryFilter().query || "";
    toggle.setAttribute("aria-expanded", panel.hidden ? "false" : "true");
    toggle.addEventListener("click", function () {
      const willOpen = panel.hidden;
      panel.hidden = !willOpen;
      toggle.classList.toggle("is-active", willOpen);
      toggle.setAttribute("aria-expanded", willOpen ? "true" : "false");
      animateLibraryControl(toggle);
      if (willOpen) input.focus();
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

    open.setAttribute("aria-expanded", "false");
    open.addEventListener("click", function () {
      syncFilterSheetButtons();
      updateFilterApplyButton();
      sheet.hidden = false;
      open.classList.add("is-active");
      open.setAttribute("aria-expanded", "true");
      animateLibraryControl(open);
    });
    sheet.querySelectorAll("[data-filter-close]").forEach(function (button) {
      button.addEventListener("click", function () {
        sheet.hidden = true;
        open.classList.remove("is-active");
        open.setAttribute("aria-expanded", "false");
      });
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
    if (apply) apply.addEventListener("click", function () {
      sheet.hidden = true;
      open.classList.remove("is-active");
      open.setAttribute("aria-expanded", "false");
      renderLibraryCards();
    });
  }

  function initLibrarySortControl() {
    const select = document.getElementById("librarySort");
    const pill = select ? select.closest(".library-sort-pill") : null;
    if (!select) return;
    select.addEventListener("change", function () {
      animateLibraryControl(pill, "is-changing", 340);
      renderLibraryCards();
    });
    select.addEventListener("focus", function () { pill?.classList.add("is-active"); });
    select.addEventListener("blur", function () { pill?.classList.remove("is-active"); });
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
        if (!section) return;
        const collapsed = section.classList.toggle("collapsed");
        button.setAttribute("aria-expanded", collapsed ? "false" : "true");
      });
    });
  }

  function initLibraryNovelMeta() {
    const meta = readJson(STORAGE_KEYS.novelMeta, {});

    document.querySelectorAll("[data-library-novel-card]").forEach(function (card) {
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

  function initLibraryCardNavigation() {
    document.addEventListener("click", function (event) {
      const card = event.target.closest("[data-library-novel-card]");

      if (!card) {
        return;
      }

      if (event.target.closest("a, button, input, select, textarea, [data-card-menu]")) {
        return;
      }

      const href = card.dataset.cardHref;

      if (href) {
        window.location.href = href;
      }
    });

    document.addEventListener("keydown", function (event) {
      const card = event.target.closest("[data-library-novel-card]");

      if (!card || event.target !== card || (event.key !== "Enter" && event.key !== " ")) {
        return;
      }

      event.preventDefault();

      const href = card.dataset.cardHref;

      if (href) {
        window.location.href = href;
      }
    });
  }

  function initLibraryCardMenus() {
    // Capture-фаза нужна, чтобы клик по ⋮ не перехватывался кликабельной карточкой.
    document.addEventListener("click", function (event) {
      const menuButton = event.target.closest("[data-card-menu-button]");

      if (menuButton) {
        event.preventDefault();
        event.stopPropagation();

        const card = menuButton.closest("[data-library-novel-card]");
        if (card) toggleCardMenu(card, menuButton);
        return;
      }

      const menuAction = event.target.closest("[data-card-menu-action]");
      if (menuAction) {
        event.preventDefault();
        event.stopPropagation();
        handleCardMenuAction(menuAction);
        return;
      }

      // Любое нажатие за пределами открытого меню и его кнопки закрывает меню.
      if (!event.target.closest("[data-card-menu]") && !event.target.closest("[data-card-menu-button]")) {
        closeAllCardMenus();
      }
    }, true);

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") closeAllCardMenus();
    });

    window.addEventListener("resize", closeAllCardMenus);
    window.addEventListener("orientationchange", closeAllCardMenus);
    window.addEventListener("scroll", closeAllCardMenus, { passive: true, capture: true });
  }

  function toggleCardMenu(card, button) {
    const novelId = String(card.dataset.novelId || "");
    const existing = document.querySelector(`[data-card-menu][data-novel-id="${cssEscape(novelId)}"]`);
    const wasOpen = Boolean(existing);

    closeAllCardMenus();
    if (wasOpen) return;

    const menu = buildCardMenu(card);
    document.body.appendChild(menu);
    positionCardMenu(menu, button);
    button.setAttribute("aria-expanded", "true");

    const firstAction = menu.querySelector("[data-card-menu-action]");
    if (firstAction) firstAction.focus({ preventScroll: true });
  }

  function positionCardMenu(menu, button) {
    const viewportGap = 12;
    const buttonRect = button.getBoundingClientRect();
    const width = Math.min(300, Math.max(236, window.innerWidth - viewportGap * 2));

    menu.style.setProperty("width", `${width}px`);
    menu.style.setProperty("left", "0px", "important");
    menu.style.setProperty("top", "0px", "important");
    menu.style.setProperty("right", "auto", "important");
    menu.style.setProperty("bottom", "auto", "important");
    menu.style.visibility = "hidden";

    const menuHeight = Math.min(menu.scrollHeight, window.innerHeight - viewportGap * 2);
    let left = buttonRect.right - width;
    left = Math.max(viewportGap, Math.min(left, window.innerWidth - width - viewportGap));

    let top = buttonRect.bottom + 8;
    if (top + menuHeight > window.innerHeight - viewportGap) {
      top = Math.max(viewportGap, buttonRect.top - menuHeight - 8);
    }

    menu.style.setProperty("left", `${Math.round(left)}px`, "important");
    menu.style.setProperty("top", `${Math.round(top)}px`, "important");
    menu.style.setProperty("max-height", `${Math.max(160, window.innerHeight - viewportGap * 2)}px`);
    menu.style.visibility = "visible";
  }

  function closeAllCardMenus() {
    document.querySelectorAll("[data-card-menu]").forEach(function (menu) {
      menu.remove();
    });

    document.querySelectorAll("[data-card-menu-button][aria-expanded=\"true\"]").forEach(function (button) {
      button.setAttribute("aria-expanded", "false");
    });
  }

  function buildCardMenu(card) {
    const novelId = card.dataset.novelId || "";
    const isFavorite = getIdList(STORAGE_KEYS.favoriteNovels).includes(novelId);
    const state = card.dataset.cardState || "";
    const hasHistory = readJson(STORAGE_KEYS.readingHistory, []).some(function (item) {
      return String(item.novelId) === String(novelId);
    });
    const isReading = state === "reading" || state === "new" || state === "waiting_new";
    const isCompleted = state === "completed" || getIdList(STORAGE_KEYS.completedNovels).includes(novelId);

    const items = [
      ["contents", "☷", "К оглавлению"],
      ["favorite", isFavorite ? "♥" : "♡", isFavorite ? "Убрать из избранного" : "Добавить в избранное"],
      [isCompleted ? "unmark-read" : "mark-read", "✓", isCompleted ? "Убрать из прочитанного" : "Отметить как прочитанное"],
    ];

    if (isReading || hasHistory) {
      items.push(["remove-reading", "◌", "Убрать из читаю"]);
      items.push(["reset-progress", "↻", "Сбросить прогресс"]);
    }

    items.push(["reread", "↺", "Перечитать сначала"]);
    items.push(["hide", "⊘", "Скрыть карточку"]);

    const menu = document.createElement("div");
    menu.className = "library-card-menu-popover";
    menu.dataset.cardMenu = "true";
    menu.dataset.novelId = novelId;
    menu.setAttribute("role", "menu");
    menu.setAttribute("aria-label", "Действия с новеллой");

    menu.innerHTML = items.map(function (item) {
      return `
        <button type="button" role="menuitem" data-card-menu-action="${item[0]}" data-novel-id="${escapeHtml(novelId)}">
          <span class="library-card-menu-icon">${item[1]}</span>
          <span>${escapeHtml(item[2])}</span>
        </button>
      `;
    }).join("");

    return menu;
  }

  function handleCardMenuAction(actionButton) {
    const action = actionButton.dataset.cardMenuAction;
    const novelId = actionButton.dataset.novelId || "";
    const card = document.querySelector(`[data-library-novel-card][data-novel-id="${cssEscape(novelId)}"]`);

    if (!card) {
      closeAllCardMenus();
      return;
    }

    const novelSlug = card.dataset.novelSlug || "";

    if (action === "contents") {
      window.location.href = `/novel/${novelSlug}`;
      return;
    }

    if (action === "favorite") {
      toggleIdInList(STORAGE_KEYS.favoriteNovels, novelId);
      closeAllCardMenus();
      renderLibraryCards();
      return;
    }

    if (action === "mark-read") {
      addIdToList(STORAGE_KEYS.completedNovels, novelId);
      closeAllCardMenus();
      renderLibraryCards();
      return;
    }

    if (action === "unmark-read") {
      removeIdFromList(STORAGE_KEYS.completedNovels, novelId);
      closeAllCardMenus();
      renderLibraryCards();
      return;
    }

    if (action === "remove-reading" || action === "reset-progress") {
      removeReadingHistoryForNovel(novelId);
      removeIdFromList(STORAGE_KEYS.completedNovels, novelId);
      closeAllCardMenus();
      renderLibraryCards();
      return;
    }

    if (action === "reread") {
      removeReadingHistoryForNovel(novelId);
      removeIdFromList(STORAGE_KEYS.completedNovels, novelId);
      closeAllCardMenus();
      window.location.href = `/novel/${novelSlug}`;
      return;
    }

    if (action === "hide") {
      addIdToList(STORAGE_KEYS.hiddenNovels, novelId);
      closeAllCardMenus();
      renderLibraryCards();
    }
  }

  function getIdList(key) {
    const list = readJson(key, []);

    if (!Array.isArray(list)) {
      return [];
    }

    return list.map(String);
  }

  function writeIdList(key, list) {
    writeJson(key, Array.from(new Set(list.map(String))));
  }

  function addIdToList(key, id) {
    if (!id) {
      return;
    }

    const list = getIdList(key);

    if (!list.includes(String(id))) {
      list.push(String(id));
    }

    writeIdList(key, list);
  }

  function removeIdFromList(key, id) {
    writeIdList(key, getIdList(key).filter(function (item) {
      return item !== String(id);
    }));
  }

  function toggleIdInList(key, id) {
    const list = getIdList(key);

    if (list.includes(String(id))) {
      removeIdFromList(key, id);
    } else {
      addIdToList(key, id);
    }
  }

  function removeReadingHistoryForNovel(novelId) {
    const history = readJson(STORAGE_KEYS.readingHistory, []);

    if (!Array.isArray(history)) {
      return;
    }

    writeJson(STORAGE_KEYS.readingHistory, history.filter(function (entry) {
      return String(entry.novelId) !== String(novelId);
    }));
  }

  function renderLibraryCards() {
    closeAllCardMenus();

    const raw = document.getElementById("libraryRawCards");

    if (!raw) {
      return;
    }

    const lists = {
      favorite: document.querySelector('[data-section-list="favorite"]'),
      reading: document.querySelector('[data-section-list="reading"]'),
      start: document.querySelector('[data-section-list="start"]'),
      waiting: document.querySelector('[data-section-list="waiting"]'),
      finished: document.querySelector('[data-section-list="finished"]'),
    };

    if (!lists.favorite || !lists.reading || !lists.start || !lists.waiting || !lists.finished) {
      return;
    }

    const filter = getLibraryFilter();
    const history = readJson(STORAGE_KEYS.readingHistory, []);
    const readIds = readJson(STORAGE_KEYS.readChapters, []);
    const hiddenNovels = getIdList(STORAGE_KEYS.hiddenNovels);
    const favoriteNovels = getIdList(STORAGE_KEYS.favoriteNovels);
    const completedNovels = getIdList(STORAGE_KEYS.completedNovels);
    const historyByNovel = {};

    history.forEach(function (item) {
      historyByNovel[String(item.novelId)] = item;
    });

    const buckets = {
      favorite: [],
      reading: [],
      start: [],
      waiting: [],
      finished: [],
    };

    Array.from(document.querySelectorAll("[data-library-novel-card]")).forEach(function (card) {
      const novelId = String(card.dataset.novelId || "");

      if (hiddenNovels.includes(novelId)) {
        raw.appendChild(card);
        return;
      }

      const state = prepareLibraryCard(card, historyByNovel, readIds, completedNovels);
      card.dataset.cardState = state;
      card.dataset.isFavorite = favoriteNovels.includes(novelId) ? "true" : "false";

      if (!cardMatchesFilter(card, filter)) {
        raw.appendChild(card);
        return;
      }

      if (favoriteNovels.includes(novelId)) {
        buckets.favorite.push(card);
        return;
      }

      if (state === "new" || state === "reading" || state === "waiting_new") {
        buckets.reading.push(card);
      } else if (state === "start") {
        buckets.start.push(card);
      } else if (state === "locked" || state === "soon") {
        buckets.waiting.push(card);
      } else {
        buckets.finished.push(card);
      }
    });

    Object.values(buckets).forEach(sortCards);

    Object.keys(lists).forEach(function (key) {
      lists[key].innerHTML = "";
      buckets[key].forEach(function (card) {
        lists[key].appendChild(card);
      });
      updateSection(key, buckets[key].length);
    });

    const visibleTotal = Object.values(buckets).reduce(function (sum, list) {
      return sum + list.length;
    }, 0);

    const empty = document.getElementById("libraryEmptyFilter");

    if (empty) {
      empty.hidden = visibleTotal !== 0;
    }

    renderActiveFilters();
    renderLibraryUpdateBanner(buckets.reading.concat(buckets.favorite));
    updateFilterApplyButton(visibleTotal);
  }

  function prepareLibraryCard(card, historyByNovel, readIds, completedNovels) {
    const novelId = String(card.dataset.novelId || "");
    const historyItem = historyByNovel[novelId];
    const isCompletedByUser = Array.isArray(completedNovels) && completedNovels.includes(novelId);

    const chapters = Number(card.dataset.chapters || 0);
    const translated = Number(card.dataset.translatedChapters || 0);
    const available = Number(card.dataset.availableChapters || 0);
    const projectStatus = String(card.dataset.status || "");

    const button = card.querySelector("[data-card-main-button]");
    const statePill = card.querySelector("[data-card-state-pill]");
    const projectStatusPill = card.querySelector("[data-project-status-pill]");
    const progressRow = card.querySelector("[data-card-progress-row]");
    const progressFill = card.querySelector("[data-card-progress-fill]");
    const progressText = card.querySelector("[data-card-progress-text]");

    card.classList.remove(
      "is-reading",
      "is-new",
      "is-finished",
      "is-start",
      "is-waiting",
      "is-locked",
      "is-soon",
      "is-favorite"
    );

    if (button) {
      button.classList.remove("is-disabled-soft");
    }

    const isFavorite = getIdList(STORAGE_KEYS.favoriteNovels).includes(novelId);

    if (isFavorite) {
      card.classList.add("is-favorite");
    }

    const safeHistoryIndex = historyItem && historyItem.chapterIndex
      ? Math.min(Number(historyItem.chapterIndex || 0), available || Number(historyItem.chapterIndex || 0))
      : 0;

    const newCount = historyItem ? getNewChapterCount(novelId, historyItem.availableChapters) : 0;

    let state = "start";
    let visualProgress = 0;
    let progressLabel = available ? `0 / ${available}` : "0 / 0";

    if (isCompletedByUser) {
      state = "completed";
      visualProgress = 100;
      progressLabel = available ? `${available} / ${available}` : `${chapters || translated || 0} / ${chapters || translated || 0}`;
    } else if (!historyItem && !available) {
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
      progressLabel = available ? `0 / ${available}` : "0 / 0";
    }

    const isReadingSectionState = state === "new" || state === "reading" || state === "waiting_new";
    const showReadingProgress = isFavorite || isReadingSectionState;

    if (progressRow) {
      progressRow.hidden = !showReadingProgress;
      progressRow.setAttribute("aria-hidden", showReadingProgress ? "false" : "true");
    }

    if (progressFill) {
      progressFill.style.width = `${visualProgress}%`;
    }

    if (progressText) {
      progressText.textContent = progressLabel;
    }

    const currentChapterLabel = safeHistoryIndex > 0
      ? `На главе ${safeHistoryIndex}`
      : "";

    const configs = {
      new: ["is-new is-reading", "", "✨ Новая глава", "state-new", "Читать новую", `/novel/${card.dataset.novelSlug || ""}`],
      reading: ["is-reading", "", currentChapterLabel, "state-reading", "Продолжить", `/chapter/${historyItem ? historyItem.chapterId : ""}`],
      waiting_new: ["is-reading is-waiting", "", currentChapterLabel || "Всё прочитано", "state-waiting-new", "К оглавлению", `/novel/${card.dataset.novelSlug || ""}`],
      completed: ["is-finished", "", "Прочитано", "state-completed", "Перечитать", historyItem ? `/chapter/${historyItem.chapterId}` : `/novel/${card.dataset.novelSlug || ""}`],
      locked: ["is-locked", "", "", "state-locked", "К оглавлению", `/novel/${card.dataset.novelSlug || ""}`],
      soon: ["is-soon", "", "", "state-soon", "Скоро", `/novel/${card.dataset.novelSlug || ""}`],
      start: [
        "is-start",
        "",
        "",
        "state-start",
        "Начать читать",
        `/novel/${card.dataset.novelSlug || ""}`,
      ],
    };

    const config = configs[state] || configs.start;

    config[0].split(" ").forEach(function (cls) {
      if (cls) {
        card.classList.add(cls);
      }
    });

    const isSoonState = state === "soon" || state === "locked";

    if (projectStatusPill) {
      const originalStatus = projectStatusPill.dataset.projectStatus || projectStatus || "in_progress";
      const originalLabel = projectStatusPill.dataset.projectStatusLabel || "Переводится";
      projectStatusPill.textContent = isSoonState ? "Скоро" : originalLabel;
      projectStatusPill.className = `library-stat-status status-${isSoonState ? "soon" : originalStatus}`;
    }

    if (statePill) {
      const stateLabel = String(config[2] || "").trim();
      const shouldShowState = !isSoonState && Boolean(stateLabel);
      statePill.hidden = !shouldShowState;
      statePill.textContent = stateLabel;
      statePill.className = `library-card-state-pill ${config[3]}`;
      statePill.setAttribute("aria-hidden", shouldShowState ? "false" : "true");
    }

    if (button) {
      button.textContent = config[4];
      button.href = config[5];

      if (state === "soon") {
        button.classList.add("is-disabled-soft");
      }
    }

    return state;
  }

  function cardMatchesFilter(card, filter) {
    const query = String(filter.query || "").toLowerCase().trim();
    const chips = filter.chips || [];
    const state = card.dataset.cardState || "";
    const isFavorite = card.dataset.isFavorite === "true" || card.classList.contains("is-favorite");
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

      if (chip === "favorite") {
        if (!isFavorite) {
          return false;
        }
        continue;
      }

      if (chip === "reading") {
        if (!(state === "reading" || state === "new" || state === "waiting_new")) {
          return false;
        }
        continue;
      }

      if (chip === "new") {
        if (state !== "new") {
          return false;
        }
        continue;
      }

      if (chip === "start") {
        if (state !== "start") {
          return false;
        }
        continue;
      }

      if (chip === "waiting") {
        if (!(state === "locked" || state === "soon")) {
          return false;
        }
        continue;
      }

      if (chip === "finished") {
        if (state !== "completed") {
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
    const mode = document.getElementById("librarySort")?.value || "smart";

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
        const stateWeightA = cardStateWeight(a.dataset.cardState);
        const stateWeightB = cardStateWeight(b.dataset.cardState);

        if (stateWeightA !== stateWeightB) {
          return stateWeightA - stateWeightB;
        }
      }

      return Number(a.dataset.sortOrder || 0) - Number(b.dataset.sortOrder || 0);
    });
  }

  function cardStateWeight(state) {
    return {
      new: 1,
      reading: 2,
      waiting_new: 3,
      start: 4,
      locked: 5,
      soon: 6,
      completed: 7,
    }[state] || 99;
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
      button.textContent = `Показать ${knownCount} новелл`;
      return;
    }

    const visibleCards = document.querySelectorAll(
      '[data-section-list="favorite"] [data-library-novel-card], ' +
      '[data-section-list="reading"] [data-library-novel-card], ' +
      '[data-section-list="start"] [data-library-novel-card], ' +
      '[data-section-list="waiting"] [data-library-novel-card], ' +
      '[data-section-list="finished"] [data-library-novel-card]'
    );

    button.textContent = `Показать ${visibleCards.length} новелл`;
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
      return card.dataset.cardState === "new";
    });

    if (!newCard) {
      banner.hidden = true;
      return;
    }

    text.textContent = `${newCard.dataset.novelTitle || "Новелла"} — доступна глава ${Number(newCard.dataset.availableChapters || 0)}`;
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
      button.textContent = "Продолжить чтение";
    }
  }

  function initNovelReadingProgress() {
    const page = document.querySelector("[data-novel-page]");
    const block = document.querySelector("[data-novel-reading-progress]");
    if (!page || !block) return;

    const item = readJson(STORAGE_KEYS.readingHistory, []).find((entry) =>
      String(entry.novelId) === String(page.dataset.novelId)
    );

    if (!item) {
      block.hidden = true;
      return;
    }

    const available = Math.max(0, Number(page.dataset.availableChapters || item.availableChapters || 0));
    const current = Math.max(0, Math.min(available || Number.MAX_SAFE_INTEGER, Number(item.chapterIndex || 0) + 1));
    const percent = available > 0 ? Math.min(100, Math.round((current / available) * 100)) : 0;
    const bar = block.querySelector("[data-novel-reading-progress-bar]");
    const text = block.querySelector("[data-novel-reading-progress-text]");

    if (bar) bar.style.width = `${percent}%`;
    if (text) text.textContent = available > 0 ? `${current} / ${available}` : `${current}`;
    block.hidden = false;
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

      const updateButtonState = function () {
        const collapsedHeight = content.clientHeight;
        const fullHeight = content.scrollHeight;
        const hasOverflow = fullHeight > collapsedHeight + 2;

        if (!hasOverflow && !block.classList.contains("is-expanded")) {
          button.hidden = true;
          block.classList.add("is-expanded");
          button.setAttribute("aria-expanded", "true");
          return;
        }

        button.hidden = false;
        const expanded = block.classList.contains("is-expanded");
        button.textContent = expanded ? "Свернуть" : "Ещё";
        button.setAttribute("aria-expanded", expanded ? "true" : "false");
      };

      button.setAttribute("aria-controls", content.id || "novelDescriptionContent");
      if (!content.id) content.id = "novelDescriptionContent";

      button.addEventListener("click", function (event) {
        event.preventDefault();
        event.stopPropagation();
        block.classList.toggle("is-expanded");
        updateButtonState();
      });

      requestAnimationFrame(updateButtonState);
      window.addEventListener("load", updateButtonState, { once: true });
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


  function initChapterJumpButtons() {
    document.querySelectorAll("[data-chapter-jump]").forEach(function (button) {
      button.addEventListener("click", function () {
        const targetId = button.dataset.chapterJump === "end" ? "chapterListEnd" : "chapterListStart";
        const target = document.getElementById(targetId);
        if (!target) return;
        target.scrollIntoView({ behavior: "smooth", block: button.dataset.chapterJump === "end" ? "end" : "start" });
      });
    });
  }

  function initChapterSortToggle() {
    const button = document.querySelector("[data-chapter-sort-toggle]");
    const list = document.querySelector("[data-chapter-list]");

    if (!button || !list) {
      return;
    }

    const label = button.querySelector("[data-chapter-sort-label]");

    button.addEventListener("click", function () {
      const currentOrder = button.dataset.sortOrder === "desc" ? "desc" : "asc";
      const nextOrder = currentOrder === "asc" ? "desc" : "asc";

      button.dataset.sortOrder = nextOrder;

      if (label) {
        label.textContent = nextOrder === "asc"
          ? "Сортировка: по порядку"
          : "Сортировка: новые сверху";
      }

      sortChapterList(list, nextOrder);
    });
  }

  function sortChapterList(list, order) {
    const fade = list.querySelector("[data-paid-fade]");
    const rows = Array.from(list.querySelectorAll("[data-chapter-row]"));
    const volumeHeaders = Array.from(list.querySelectorAll("[data-volume-header]"));

    rows.sort(function (a, b) {
      const aValue = Number(a.dataset.sortValue || 0);
      const bValue = Number(b.dataset.sortValue || 0);

      return order === "asc" ? aValue - bValue : bValue - aValue;
    });

    volumeHeaders.forEach(function (header) {
      header.remove();
    });

    rows.forEach(function (row) {
      list.appendChild(row);
    });

    if (fade) {
      list.appendChild(fade);
    }
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
    overlay.innerHTML = `<div class="settings-modal" role="dialog" aria-modal="true"><div class="settings-header"><div><h2>Настройки</h2><p>Оформление сайта и читалки</p></div><button class="settings-close" type="button" data-settings-close>×</button></div><div class="settings-tabs"><button class="settings-tab active" type="button" data-settings-tab="reader">Читалка</button><button class="settings-tab" type="button" data-settings-tab="site">Сайт</button><button class="settings-tab" type="button" data-settings-tab="access">Доступ</button><button class="settings-tab" type="button" data-settings-tab="about">О проекте</button></div><section class="settings-section active" data-settings-section="reader"><label class="settings-field"><span>Тема текста</span><select data-setting="readerTheme"><option value="cream">Кремовая</option><option value="white">Белая</option><option value="sepia">Сепия</option><option value="dark">Тёмная</option></select></label><label class="settings-field"><span>Ширина текста</span><select data-setting="readerWidth"><option value="comfort">Комфортная</option><option value="full">Широкая</option><option value="wide">Почти вся страница</option></select></label><label class="settings-field"><span>Размер шрифта</span><select data-setting="fontSize"><option value="15">15</option><option value="16">16</option><option value="17">17</option><option value="18">18</option><option value="19">19</option><option value="20">20</option></select></label><label class="settings-field"><span>Межстрочный интервал</span><select data-setting="lineHeight"><option value="1.45">1.45</option><option value="1.6">1.6</option><option value="1.75">1.75</option><option value="1.9">1.9</option></select></label><label class="settings-field"><span>Отступ абзацев</span><select data-setting="paragraphSpacing"><option value="12">12</option><option value="16">16</option><option value="20">20</option><option value="24">24</option></select></label><label class="settings-field"><span>Выравнивание</span><select data-setting="textAlign"><option value="left">По левому краю</option><option value="justify">По ширине</option></select></label></section><section class="settings-section" data-settings-section="site"><label class="settings-field"><span>Тема сайта</span><select data-setting="siteTheme"><option value="light">Светлая</option><option value="system">Как в системе</option><option value="dark">Тёмная</option></select></label><label class="settings-field"><span>Акцентный цвет</span><span class="settings-color-row"><select data-setting="accentColor"><option value="#ff6a00">Апельсин</option><option value="#ec4899">Малина</option><option value="#8b5cf6">Фиолетовый</option><option value="#0ea5e9">Голубой</option><option value="#10b981">Зелёный</option></select><input type="color" data-setting-color value="#ff6a00"></span></label></section><section class="settings-section" data-settings-section="access"><div class="access-debug-box"><div class="access-debug-toolbar"><div><h3>Проверка доступа</h3><p>Telegram, группы, подписки Tribute и купленные новеллы</p></div><button class="settings-access-refresh" type="button" data-access-debug-refresh>Обновить</button></div><div class="access-debug-content" data-access-debug-content><p>Откройте вкладку, чтобы проверить права</p></div></div></section><section class="settings-section" data-settings-section="about"><div class="about-box"><div data-about-fox-wrap></div><h3>Зефиркины баоцзы</h3><p>Мини-читалка для новелл, раннего доступа и удобного возвращения к последней главе</p><div class="about-links"><a href="/library">Библиотека</a></div></div></section><div class="settings-footer"><button class="settings-reset" type="button" data-settings-reset>Сбросить настройки</button></div></div>`;
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
    overlay.querySelectorAll("[data-settings-tab]").forEach(function (tab) { tab.addEventListener("click", function () { const name = tab.dataset.settingsTab; overlay.querySelectorAll("[data-settings-tab]").forEach((item) => item.classList.toggle("active", item === tab)); overlay.querySelectorAll("[data-settings-section]").forEach((section) => section.classList.toggle("active", section.dataset.settingsSection === name)); if (name === "access") loadAccessDebug(false); }); });
    overlay.querySelectorAll("[data-setting]").forEach(function (input) { input.addEventListener("change", function () { const current = getSettings(); current[input.dataset.setting] = input.value; saveSettings(current); applySettings(); }); });
    overlay.querySelectorAll("[data-setting-checkbox]").forEach(function (input) { input.addEventListener("change", function () { const current = getSettings(); current[input.dataset.settingCheckbox] = input.checked; saveSettings(current); applySettings(); }); });
    const colorInput = overlay.querySelector("[data-setting-color]");
    if (colorInput) colorInput.addEventListener("input", function () { const current = getSettings(); current.accentColor = colorInput.value; saveSettings(current); applySettings(); });
    overlay.querySelector("[data-settings-reset]")?.addEventListener("click", function () { saveSettings({ ...DEFAULT_SETTINGS }); fillSettingsInputs(getSettings()); applySettings(); });
    overlay.querySelector("[data-access-debug-refresh]")?.addEventListener("click", function () { loadAccessDebug(true); });
    const aboutFoxWrap = overlay.querySelector("[data-about-fox-wrap]");
    if (aboutFoxWrap) {
      const foxUrl = getFoxUrl("fox_sitting_front") || getFoxUrl("fox_pic") || getFoxUrl("fox_peek") || getFoxUrl("fox_side");
      aboutFoxWrap.innerHTML = foxUrl ? `<img class="about-fox" src="${escapeHtml(foxUrl)}" alt="Лисичка" data-fox>` : "";
    }
  }

  async function loadAccessDebug(refresh) {
    const container = document.querySelector("[data-access-debug-content]");
    if (!container) return;
    container.innerHTML = '<div class="access-debug-loading">Проверяем права…</div>';
    try {
      const response = await fetch(`/api/auth/debug?refresh=${refresh ? "true" : "false"}`, { credentials: "same-origin" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Не удалось проверить доступ");
      renderAccessDebug(container, data);
    } catch (error) {
      container.innerHTML = `<div class="access-debug-error">${escapeHtml(error.message || error)}</div>`;
    }
  }

  function renderAccessDebug(container, data) {
    const telegram = data.telegram || {};
    const rights = data.rights || {};
    const groups = data.groups || {};
    const subscriptions = Array.isArray(data.tribute_subscriptions) ? data.tribute_subscriptions : [];
    const entitlements = Array.isArray(data.book_entitlements) ? data.book_entitlements : [];
    const config = data.configuration || {};
    const roleLabels = { guest: "Гость", traveler: "Странствующий читатель", keeper: "Хранитель свитков" };
    const groupRow = function (label, group) {
      group = group || {};
      const state = group.active ? "Да" : "Нет";
      const cls = group.active ? "is-ok" : (group.ok ? "is-no" : "is-error");
      return `<div class="access-debug-row"><span>${escapeHtml(label)}</span><strong class="${cls}">${escapeHtml(state)}</strong><small>ID: ${escapeHtml(group.chat_id || "не настроен")} · status: ${escapeHtml(group.status || "—")}${group.description ? ` · ${escapeHtml(group.description)}` : ""}</small></div>`;
    };
    const subscriptionsHtml = subscriptions.length
      ? subscriptions.map((item) => `<li>${escapeHtml(item.access_role || "—")} · план ${escapeHtml(item.external_plan_id || "—")} · до ${escapeHtml(item.expires_at || "—")} · ${escapeHtml(item.status || "—")}</li>`).join("")
      : "<li>Активных подписок Tribute нет.</li>";
    const entitlementsHtml = entitlements.length
      ? entitlements.map((item) => `<li>NovelID ${escapeHtml(item.novel_id || "—")} · ${escapeHtml(item.access_type || "—")} · источник ${escapeHtml(item.source_type || "—")}</li>`).join("")
      : "<li>Купленных или выданных книг нет.</li>";
    container.innerHTML = `
      <div class="access-debug-summary">
        <div><span>Telegram ID</span><strong>${escapeHtml(telegram.user_id || "не получен")}</strong></div>
        <div><span>Пользователь</span><strong>${escapeHtml(telegram.first_name || "—")}${telegram.username ? ` · @${escapeHtml(telegram.username)}` : ""}</strong></div>
        <div><span>Итоговые права</span><strong>${escapeHtml(roleLabels[rights.role] || rights.role || "Гость")}</strong></div>
      </div>
      <h4>Что разрешено</h4>
      <div class="access-debug-row"><span>Обычные книги</span><strong class="is-ok">Видит</strong><small>Чтение только после FreeReleaseDate.</small></div>
      <div class="access-debug-row"><span>Книги с 🎁</span><strong class="${rights.can_view_gift_books ? "is-ok" : "is-no"}">${rights.can_view_gift_books ? "Видит" : "Не видит"}</strong><small>Странствующий получает только видимость книги, не премиальные главы.</small></div>
      <div class="access-debug-row"><span>Премиальные релизы</span><strong class="${rights.can_read_premium_releases ? "is-ok" : "is-no"}">${rights.can_read_premium_releases ? "Читает" : "Не читает"}</strong><small>Открываются только Хранителю по PremiumReleaseDate.</small></div>
      <div class="access-debug-row"><span>Полный доступ к книгам</span><strong class="${rights.book_entitlements_count ? "is-ok" : "is-no"}">${escapeHtml(String(rights.book_entitlements_count || 0))}</strong><small>NovelID: ${escapeHtml((rights.full_book_novel_ids || []).join(", ") || "—")}</small></div>
      <h4>Telegram-группы</h4>
      ${groupRow("🌱 Странствующий", groups.traveler)}
      ${groupRow("📜 Хранитель", groups.keeper)}
      <h4>Подписки Tribute</h4><ul>${subscriptionsHtml}</ul>
      <h4>Книжные доступы</h4><ul>${entitlementsHtml}</ul>
      <details class="access-debug-config"><summary>Техническая конфигурация</summary><pre>${escapeHtml(JSON.stringify(config, null, 2))}</pre></details>
      <p class="access-debug-time">Проверено: ${escapeHtml(data.checked_at || "—")}</p>`;
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
