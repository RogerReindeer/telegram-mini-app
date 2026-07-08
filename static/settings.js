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
    syncQueue: "zefirki_sync_queue",
    syncStatus: "zefirki_sync_status",
    chapterCache: "zefirki_chapter_cache",
    readerControlsHidden: "zefirki_reader_controls_hidden",
    globalSettingsOpenTab: "zefirki_global_settings_tab",
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
    accentColor: "#ff6a00",
    appSize: "normal",
    readerPanelTab: "reader",
  };

  const DEFAULT_FILTER = { query: "", chips: [] };

  document.addEventListener("DOMContentLoaded", async function () {
    initTelegram();
    const reloading = await initTelegramAuth();
    if (reloading) return;
    await loadServerUserState();

    // Каждый модуль запускается независимо: ошибка в библиотеке не должна
    // скрывать оглавление, главы или настройки на других экранах.
    const initializers = [
      initSettings,
      initAppFullscreenButton,
      initLibrary,
      initNovelPageMeta,
      initChapterContentCache,
      initChapterProgress,
      initChapterScrollProgress,
      initReaderFloatingControls,
      initReaderQuickSettings,
      initReaderControlsVisibilityToggle,
      initFloatingControlsAutoHide,
      initChapterRetry,
      initNovelReadButton,
      initNovelReadingProgress,
      initReadChapterMarks,
      initCollapsibleDescription,
      initPaidChapterReveal,
      initChapterSortToggle,
      initChapterJumpButtons,
      initSpoilerReveal,
      initAccessActions,
      initSyncQueue,
    ];

    initializers.forEach(function (initializer) {
      try {
        initializer();
      } catch (error) {
        console.error(`Не удалось запустить ${initializer.name}`, error);
      }
    });
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
            "Telegram не передал данные Mini App — закройте это окно и откройте читалку через кнопку Mini App в боте, а не через обычную ссылку"
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

  function normalizeServerHistoryRow(row) {
    const chapterIndex = Number(row.chapter_index || 0);
    const availableChapters = Number(row.available_chapters || 0);
    const scrollPosition = Number(row.scroll_position || 0);
    return {
      novelId: String(row.novel_id || row.novelId || ""),
      novelSlug: row.novel_slug || row.novelSlug || "",
      novelTitle: row.novel_title || row.novelTitle || "",
      coverUrl: row.cover_url || row.coverUrl || "",
      chapterId: row.chapter_id || row.chapterId || "",
      chapterTitle: row.chapter_title || row.chapterTitle || "",
      chapterIndex,
      chapterNumber: Number(row.chapter_number || row.chapterNumber || chapterIndex + 1),
      availableChapters,
      continueUrl: row.continue_url || row.continueUrl || (row.chapter_id ? `/chapter/${row.chapter_id}` : ""),
      scrollPosition: Math.max(0, Math.min(1, scrollPosition)),
      scrollPositionPx: Math.max(0, Math.round(Number(row.scroll_position_px || row.scrollPositionPx || 0))),
      chapterProgressPercent: Number(row.chapter_progress_percent || row.chapterProgressPercent || Math.round(Math.max(0, Math.min(1, scrollPosition)) * 100)),
      bookProgressPercent: Number(row.book_progress_percent || row.bookProgressPercent || (availableChapters > 0 ? Math.round(((chapterIndex + 1) / availableChapters) * 100) : 0)),
      progressLabel: row.progress_label || row.progressLabel || (availableChapters > 0 ? `Глава ${chapterIndex + 1} из ${availableChapters}` : `Глава ${chapterIndex + 1}`),
      isCompleted: Boolean(row.is_completed || row.isCompleted),
      updatedAt: Date.parse(row.updated_at || row.updatedAt || "") || Date.now(),
    };
  }

  function formatRelativeTime(timestamp) {
    const value = Number(timestamp || 0);
    if (!value) return "";
    const diffMs = Date.now() - value;
    if (diffMs < 0) return "только что";
    const minutes = Math.floor(diffMs / 60000);
    if (minutes < 1) return "только что";
    if (minutes < 60) return `${minutes} мин назад`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours} ч назад`;
    const days = Math.floor(hours / 24);
    if (days < 7) return `${days} дн назад`;
    return new Date(value).toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" });
  }


  function isAuthenticatedViewer() {
    return Boolean(window.ZEFIRKI_VIEWER && window.ZEFIRKI_VIEWER.authenticated && window.ZEFIRKI_VIEWER.user_id);
  }

  function makeRequestError(message, status, retryable) {
    const error = new Error(message || "Ошибка запроса");
    error.status = status || 0;
    error.retryable = retryable !== false;
    return error;
  }

  function isRetryableStatus(status) {
    return !status || status === 408 || status === 425 || status === 429 || status >= 500;
  }

  async function apiRequest(url, options = {}) {
    const timeoutMs = Number(options.timeoutMs || 12000);
    const controller = typeof AbortController !== "undefined" ? new AbortController() : null;
    const timeoutId = controller ? window.setTimeout(function () { controller.abort(); }, timeoutMs) : null;

    try {
      const response = await fetch(url, {
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", ...((options && options.headers) || {}) },
        ...(options || {}),
        signal: controller ? controller.signal : options.signal,
      });
      const data = await response.json().catch(function () { return {}; });
      if (!response.ok) {
        const message = data.detail || data.error || "Ошибка сохранения данных";
        throw makeRequestError(message, response.status, isRetryableStatus(response.status));
      }
      return data;
    } catch (error) {
      if (error && error.name === "AbortError") {
        throw makeRequestError("Сервер не ответил вовремя", 0, true);
      }
      if (error && typeof error.retryable === "boolean") {
        throw error;
      }
      throw makeRequestError(error && error.message ? error.message : "Сеть временно недоступна", 0, true);
    } finally {
      if (timeoutId) window.clearTimeout(timeoutId);
    }
  }

  function readSyncQueue() {
    const queue = readJson(STORAGE_KEYS.syncQueue, []);
    return Array.isArray(queue) ? queue.filter(Boolean) : [];
  }

  function writeSyncQueue(queue) {
    writeJson(STORAGE_KEYS.syncQueue, Array.isArray(queue) ? queue.slice(-100) : []);
    updateSyncStatusIndicator();
  }

  function compactSyncQueue(queue) {
    const latestByKey = new Map();
    const ordered = [];

    queue.forEach(function (task) {
      if (!task || !task.type || !task.key) return;
      if (task.type === "reset-progress") {
        const novelKey = `progress:${task.novel_id}`;
        for (const key of Array.from(latestByKey.keys())) {
          if (key === novelKey || key.startsWith(`${novelKey}:`)) latestByKey.delete(key);
        }
      }
      latestByKey.set(task.key, task);
    });

    latestByKey.forEach(function (task) { ordered.push(task); });
    ordered.sort(function (a, b) { return Number(a.createdAt || 0) - Number(b.createdAt || 0); });
    return ordered.slice(-100);
  }

  function enqueueSyncTask(task) {
    if (!isAuthenticatedViewer() || !task || !task.type) return;
    const now = Date.now();
    const prepared = {
      ...task,
      attempts: Number(task.attempts || 0),
      createdAt: Number(task.createdAt || now),
      updatedAt: now,
    };
    const queue = compactSyncQueue(readSyncQueue().filter(function (item) { return item.key !== prepared.key; }).concat(prepared));
    writeSyncQueue(queue);
  }

  function markSyncStatus(status, detail) {
    writeJson(STORAGE_KEYS.syncStatus, { status, detail: detail || "", updatedAt: Date.now() });
    updateSyncStatusIndicator();
  }

  function syncStatusLabel(status, pending) {
    if (!navigator.onLine) return "Нет сети";
    if (pending > 0) return "";
    if (status === "syncing") return "Синхронизация…";
    if (status === "error") return "Синхронизация позже";
    if (status === "ok") return "Сохранено";
    return "";
  }

  function ensureSyncStatusIndicator() {
    let indicator = document.querySelector("[data-sync-status]");
    if (indicator) return indicator;
    indicator = document.createElement("button");
    indicator.type = "button";
    indicator.className = "sync-status-pill";
    indicator.dataset.syncStatus = "idle";
    indicator.hidden = true;
    indicator.addEventListener("click", function () { flushSyncQueue(); });
    document.body.appendChild(indicator);
    return indicator;
  }

  function updateSyncStatusIndicator() {
    const indicator = ensureSyncStatusIndicator();
    const pending = readSyncQueue().length;
    const status = readJson(STORAGE_KEYS.syncStatus, { status: "idle" });
    const label = syncStatusLabel(status.status, pending);
    indicator.textContent = label;
    indicator.dataset.syncStatus = status.status || "idle";
    indicator.dataset.pending = String(pending);
    indicator.hidden = !label || pending > 0 || (pending === 0 && status.status !== "syncing" && status.status !== "error" && navigator.onLine);
  }

  let syncQueueRunning = false;

  async function runSyncTask(task) {
    if (task.type === "progress") {
      return apiRequest("/api/user/progress", { method: "PUT", body: JSON.stringify(task.payload) });
    }
    if (task.type === "library") {
      return apiRequest("/api/user/library", { method: "PUT", body: JSON.stringify(task.payload) });
    }
    if (task.type === "reset-progress") {
      return apiRequest("/api/user/progress/reset", { method: "POST", body: JSON.stringify(task.payload) });
    }
    return Promise.resolve();
  }

  async function flushSyncQueue() {
    if (syncQueueRunning || !isAuthenticatedViewer() || !navigator.onLine) {
      updateSyncStatusIndicator();
      return;
    }

    syncQueueRunning = true;
    markSyncStatus("syncing");

    try {
      let queue = compactSyncQueue(readSyncQueue());
      while (queue.length > 0) {
        const task = queue[0];
        try {
          await runSyncTask(task);
          queue = compactSyncQueue(readSyncQueue()).filter(function (item) { return item.key !== task.key; });
          writeSyncQueue(queue);
        } catch (error) {
          if (error && error.retryable === false) {
            queue = compactSyncQueue(readSyncQueue()).filter(function (item) { return item.key !== task.key; });
            writeSyncQueue(queue);
            continue;
          }
          task.attempts = Number(task.attempts || 0) + 1;
          task.updatedAt = Date.now();
          writeSyncQueue(compactSyncQueue([task].concat(queue.slice(1))));
          throw error;
        }
      }
      markSyncStatus("ok");
      window.setTimeout(updateSyncStatusIndicator, 1800);
    } catch (error) {
      console.warn("Серверная синхронизация будет повторена позже", error);
      markSyncStatus("error", error && error.message ? error.message : "sync_failed");
    } finally {
      syncQueueRunning = false;
      updateSyncStatusIndicator();
    }
  }

  function initSyncQueue() {
    updateSyncStatusIndicator();
    window.addEventListener("online", flushSyncQueue);
    window.addEventListener("offline", updateSyncStatusIndicator);
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) flushSyncQueue();
    });
    window.setTimeout(flushSyncQueue, 800);
  }

  async function loadServerUserState() {
    if (!isAuthenticatedViewer()) return;
    try {
      const data = await apiRequest("/api/user/state");
      const progress = Array.isArray(data.progress) ? data.progress : [];
      const library = Array.isArray(data.library) ? data.library : [];

      const serverHistoryRows = Array.isArray(data.history) && data.history.length ? data.history : progress;
      if (serverHistoryRows.length === 0) {
        await migrateLocalProgressToServer();
      } else {
        const history = serverHistoryRows
          .map(normalizeServerHistoryRow)
          .filter(function (item) { return item.novelId && item.chapterId; })
          .sort(function (a, b) { return Number(b.updatedAt || 0) - Number(a.updatedAt || 0); });
        writeJson(STORAGE_KEYS.readingHistory, history.slice(0, 50));
        const readIds = serverHistoryRows.flatMap(function (row) {
          return Array.isArray(row.read_chapter_ids) ? row.read_chapter_ids.map(String) : [];
        });
        writeJson(STORAGE_KEYS.readChapters, Array.from(new Set(readIds)).slice(-3000));
      }

      if (library.length === 0) {
        await migrateLocalLibraryToServer();
      } else {
        writeJson(STORAGE_KEYS.favoriteNovels, library.filter((row) => row.is_favorite).map((row) => String(row.novel_id)));
        writeJson(STORAGE_KEYS.completedNovels, library.filter((row) => row.is_completed).map((row) => String(row.novel_id)));
        writeJson(STORAGE_KEYS.hiddenNovels, library.filter((row) => row.is_hidden).map((row) => String(row.novel_id)));
      }
      flushSyncQueue();
    } catch (error) {
      console.warn("Серверный прогресс временно недоступен; используется локальный кеш", error);
    }
  }

  async function migrateLocalProgressToServer() {
    const history = readJson(STORAGE_KEYS.readingHistory, []);
    if (!Array.isArray(history) || history.length === 0) return;
    const readIds = readJson(STORAGE_KEYS.readChapters, []);
    await Promise.all(history.slice(-50).map(function (item) {
      return saveProgressToServer(item, readIds).catch(function () {});
    }));
  }

  async function migrateLocalLibraryToServer() {
    const ids = new Set([].concat(
      getIdList(STORAGE_KEYS.favoriteNovels),
      getIdList(STORAGE_KEYS.completedNovels),
      getIdList(STORAGE_KEYS.hiddenNovels)
    ));
    await Promise.all(Array.from(ids).map(function (novelId) {
      return syncLibraryState(novelId).catch(function () {});
    }));
  }

  function buildProgressPayload(item, readIds) {
    return {
      novel_id: Number(item.novelId),
      novel_slug: item.novelSlug || "",
      novel_title: item.novelTitle || "",
      cover_url: item.coverUrl || "",
      chapter_id: item.chapterId,
      chapter_title: item.chapterTitle || "",
      chapter_index: Number(item.chapterIndex || 0),
      available_chapters: Number(item.availableChapters || 0),
      scroll_position: Number(item.scrollPosition || 0),
      scroll_position_px: Math.max(0, Math.round(Number(item.scrollPositionPx || 0))),
      completed: true,
      read_chapter_ids: Array.isArray(readIds) ? readIds.slice(-3000) : [],
    };
  }

  function saveProgressToServer(item, readIds) {
    if (!isAuthenticatedViewer() || !item || !item.novelId || !item.chapterId) return Promise.resolve();
    const payload = buildProgressPayload(item, readIds);
    return apiRequest("/api/user/progress", { method: "PUT", body: JSON.stringify(payload) }).catch(function (error) {
      if (!error || error.retryable !== false) {
        enqueueSyncTask({
          type: "progress",
          key: `progress:${payload.novel_id}`,
          novel_id: payload.novel_id,
          chapter_id: payload.chapter_id,
          payload,
        });
      }
      throw error;
    });
  }

  function buildLibraryPayload(novelId) {
    return {
      novel_id: Number(novelId),
      is_favorite: getIdList(STORAGE_KEYS.favoriteNovels).includes(String(novelId)),
      is_completed: getIdList(STORAGE_KEYS.completedNovels).includes(String(novelId)),
      is_hidden: getIdList(STORAGE_KEYS.hiddenNovels).includes(String(novelId)),
    };
  }

  function syncLibraryState(novelId) {
    if (!isAuthenticatedViewer() || !novelId) return Promise.resolve();
    const payload = buildLibraryPayload(novelId);
    return apiRequest("/api/user/library", { method: "PUT", body: JSON.stringify(payload) }).catch(function (error) {
      if (!error || error.retryable !== false) {
        enqueueSyncTask({
          type: "library",
          key: `library:${payload.novel_id}`,
          novel_id: payload.novel_id,
          payload,
        });
      }
      throw error;
    });
  }

  function resetProgressOnServer(novelId) {
    if (!isAuthenticatedViewer() || !novelId) return Promise.resolve();
    const payload = { novel_id: Number(novelId) };
    enqueueSyncTask({
      type: "reset-progress",
      key: `reset-progress:${payload.novel_id}`,
      novel_id: payload.novel_id,
      payload,
    });
    return flushSyncQueue();
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
    const requestedSiteTheme = settings.siteTheme || "system";
    const systemDark = requestedSiteTheme === "system" && window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    const resolvedSiteTheme = requestedSiteTheme === "system" ? (systemDark ? "dark" : "light") : requestedSiteTheme;
    body.dataset.siteTheme = resolvedSiteTheme;
    body.dataset.siteThemeChoice = requestedSiteTheme;
    body.dataset.resolvedTheme = resolvedSiteTheme;
    body.classList.toggle("site-theme-system", requestedSiteTheme === "system");
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

      const href = card.dataset.cardActionHref || card.dataset.cardHref;

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

      const href = card.dataset.cardActionHref || card.dataset.cardHref;

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
    const isHidden = getIdList(STORAGE_KEYS.hiddenNovels).includes(novelId);

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
    items.push([isHidden ? "unhide" : "hide", isHidden ? "◉" : "⊘", isHidden ? "Вернуть в библиотеку" : "Скрыть карточку"]);

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
      syncLibraryState(novelId).catch(console.warn);
      closeAllCardMenus();
      renderLibraryCards();
      return;
    }

    if (action === "mark-read") {
      addIdToList(STORAGE_KEYS.completedNovels, novelId);
      syncLibraryState(novelId).catch(console.warn);
      closeAllCardMenus();
      renderLibraryCards();
      return;
    }

    if (action === "unmark-read") {
      removeIdFromList(STORAGE_KEYS.completedNovels, novelId);
      syncLibraryState(novelId).catch(console.warn);
      closeAllCardMenus();
      renderLibraryCards();
      return;
    }

    if (action === "remove-reading" || action === "reset-progress") {
      removeReadingHistoryForNovel(novelId);
      removeIdFromList(STORAGE_KEYS.completedNovels, novelId);
      resetProgressOnServer(novelId).catch(console.warn);
      syncLibraryState(novelId).catch(console.warn);
      closeAllCardMenus();
      renderLibraryCards();
      return;
    }

    if (action === "reread") {
      removeReadingHistoryForNovel(novelId);
      removeIdFromList(STORAGE_KEYS.completedNovels, novelId);
      resetProgressOnServer(novelId).catch(console.warn);
      syncLibraryState(novelId).catch(console.warn);
      closeAllCardMenus();
      window.location.href = `/novel/${novelSlug}`;
      return;
    }

    if (action === "hide") {
      addIdToList(STORAGE_KEYS.hiddenNovels, novelId);
      syncLibraryState(novelId).catch(console.warn);
      closeAllCardMenus();
      renderLibraryCards();
      return;
    }

    if (action === "unhide") {
      removeIdFromList(STORAGE_KEYS.hiddenNovels, novelId);
      syncLibraryState(novelId).catch(console.warn);
      closeAllCardMenus();
      renderLibraryCards();
      return;
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
      hidden: document.querySelector('[data-section-list="hidden"]'),
    };

    if (!lists.favorite || !lists.reading || !lists.start || !lists.waiting || !lists.finished || !lists.hidden) {
      return;
    }

    const filter = getLibraryFilter();
    const storedHistory = readJson(STORAGE_KEYS.readingHistory, []);
    const storedReadIds = readJson(STORAGE_KEYS.readChapters, []);
    const history = Array.isArray(storedHistory) ? storedHistory : [];
    const readIds = Array.isArray(storedReadIds) ? storedReadIds : [];
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
      hidden: [],
    };

    const cards = Array.from(document.querySelectorAll("[data-library-novel-card]"));

    cards.forEach(function (card) {
      const novelId = String(card.dataset.novelId || "");

      const state = prepareLibraryCard(card, historyByNovel, readIds, completedNovels);
      card.dataset.cardState = state;
      card.dataset.isFavorite = favoriteNovels.includes(novelId) ? "true" : "false";
      card.dataset.isHidden = hiddenNovels.includes(novelId) ? "true" : "false";

      if (hiddenNovels.includes(novelId)) {
        if (cardMatchesFilter(card, filter)) {
          buckets.hidden.push(card);
        } else {
          raw.appendChild(card);
        }
        return;
      }

      if (!cardMatchesFilter(card, filter)) {
        raw.appendChild(card);
        return;
      }

      if (favoriteNovels.includes(novelId)) {
        buckets.favorite.push(card);
      } else if (state === "new" || state === "reading" || state === "waiting_new") {
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
    renderLibraryContinuePanel(history, cards);
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
    const hasFutureChapters = available > 0 && projectStatus !== "completed" && (Number(translated || 0) > available || Number(chapters || 0) > available || projectStatus === "in_progress" || projectStatus === "paused");

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
    card.dataset.newChaptersCount = String(newCount);

    let state = "start";
    let visualProgress = 0;
    let progressLabel = available ? `0 / ${available}` : "0 / 0";

    if (isCompletedByUser && !hasFutureChapters) {
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
      new: ["is-new is-reading", "", `✨ ${newCount === 1 ? "Новая глава" : `${newCount} новые главы`}`, "state-new", "Читать новое", `/novel/${card.dataset.novelSlug || ""}`],
      reading: ["is-reading", "", currentChapterLabel, "state-reading", "Продолжить", `/chapter/${historyItem ? historyItem.chapterId : ""}`],
      waiting_new: ["is-reading is-waiting", "", "Жду главу", "state-waiting-new", "К оглавлению", `/novel/${card.dataset.novelSlug || ""}`],
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

    card.dataset.cardActionHref = config[5] || card.dataset.cardHref || "";
    card.setAttribute("aria-label", `${config[4]}: ${card.dataset.novelTitle || card.dataset.title || "новелла"}`);

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

      if (chip === "hidden") {
        if (card.dataset.isHidden !== "true") {
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
      if (mode === "hidden-first" || mode === "hidden-last") {
        const hiddenA = a.dataset.isHidden === "true" ? 1 : 0;
        const hiddenB = b.dataset.isHidden === "true" ? 1 : 0;
        if (hiddenA !== hiddenB) {
          return mode === "hidden-first" ? hiddenB - hiddenA : hiddenA - hiddenB;
        }
      }

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
      const keepVisible = name === "reading";
      section.hidden = keepVisible ? false : count === 0;
      section.classList.toggle("is-empty", count === 0);
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
      '[data-section-list="finished"] [data-library-novel-card], ' +
      '[data-section-list="hidden"] [data-library-novel-card]'
    );

    button.textContent = `Показать ${visibleCards.length} новелл`;
  }

  function renderLibraryContinuePanel(history, cards) {
    const panel = document.getElementById("libraryContinuePanel");
    const list = document.getElementById("libraryContinueList");
    const clear = document.getElementById("libraryContinueClear");

    if (!panel || !list) {
      return;
    }

    const cardsByNovel = {};
    cards.forEach(function (card) {
      cardsByNovel[String(card.dataset.novelId || "")] = card;
    });

    const items = Array.isArray(history)
      ? history.slice().sort(function (a, b) { return Number(b.updatedAt || 0) - Number(a.updatedAt || 0); })
      : [];

    const visibleItems = items.filter(function (item) {
      return item && item.novelId && item.chapterId && cardsByNovel[String(item.novelId)];
    }).slice(0, 3);

    let continuePanelHidden = false;
    try { continuePanelHidden = window.localStorage.getItem("zefirki_continue_panel_hidden") === "1"; } catch (error) {}
    panel.hidden = visibleItems.length === 0 || continuePanelHidden;
    if (clear) clear.hidden = visibleItems.length === 0;

    if (!visibleItems.length) {
      list.innerHTML = "";
      return;
    }

    list.innerHTML = visibleItems.map(function (item, index) {
      const card = cardsByNovel[String(item.novelId)];
      const cover = item.coverUrl || card.dataset.novelCover || "";
      const title = item.novelTitle || card.dataset.novelTitle || "Новелла";
      const chapterTitle = item.chapterTitle || "Последняя открытая глава";
      const available = Number(item.availableChapters || card.dataset.availableChapters || 0);
      const chapterNumber = Number(item.chapterNumber || Number(item.chapterIndex || 0) + 1);
      const bookPercent = Math.max(0, Math.min(100, Number(item.bookProgressPercent || (available > 0 ? Math.round((chapterNumber / available) * 100) : 0))));
      const chapterPercent = Math.max(0, Math.min(100, Number(item.chapterProgressPercent || Math.round(Number(item.scrollPosition || 0) * 100))));
      const progressText = item.progressLabel || (available > 0 ? `Глава ${Math.min(chapterNumber, available)} из ${available}` : `Глава ${chapterNumber}`);
      const lastRead = formatRelativeTime(item.updatedAt);
      const href = item.continueUrl || `/chapter/${item.chapterId}`;
      return `
        <a class="library-continue-card ${index === 0 ? "library-continue-card-primary" : ""}" href="${escapeHtml(href)}">
          <span class="library-continue-cover-wrap">
            ${cover ? `<img src="${escapeHtml(cover)}" alt="" aria-hidden="true">` : `<span class="library-continue-cover-placeholder" aria-hidden="true">📖</span>`}
          </span>
          <span class="library-continue-copy">
            <span class="library-continue-title-line">
              <strong class="library-continue-title">${escapeHtml(title)}</strong>
              <span class="library-continue-chapter">${escapeHtml(chapterTitle)}</span>
            </span>
            <small class="library-continue-meta">${escapeHtml(progressText)}${chapterPercent > 0 ? ` · ${chapterPercent}% главы` : ""}${lastRead ? ` · ${lastRead}` : ""}</small>
            <span class="library-continue-progress-row" aria-hidden="true">
              <span class="library-continue-progress"><span style="width:${bookPercent}%"></span></span>
            </span>
          </span>
        </a>
      `;
    }).join("");

    if (clear) {
      clear.onclick = function () {
        try { window.localStorage.setItem("zefirki_continue_panel_hidden", "1"); } catch (error) {}
        panel.hidden = true;
      };
    }
  }

  function renderLibraryUpdateBanner(readingCards) {
    const banner = document.getElementById("libraryUpdateBanner");
    const text = document.getElementById("libraryUpdateText");
    const title = banner ? banner.querySelector(".library-update-title") : null;
    const button = document.getElementById("libraryUpdateButton");
    const close = document.getElementById("libraryUpdateClose");

    if (!banner || !text || !button) {
      return;
    }

    const newCards = readingCards
      .filter(function (card) { return card.dataset.cardState === "new"; })
      .sort(function (a, b) { return Number(b.dataset.newChaptersCount || 0) - Number(a.dataset.newChaptersCount || 0); });

    if (!newCards.length) {
      banner.hidden = true;
      return;
    }

    const totalNewChapters = newCards.reduce(function (sum, card) {
      return sum + Math.max(1, Number(card.dataset.newChaptersCount || 1));
    }, 0);
    const firstCard = newCards[0];
    const novelCountText = newCards.length === 1 ? "1 новелле" : `${newCards.length} новеллах`;

    if (title) {
      title.textContent = totalNewChapters === 1 ? "Новая глава" : `${totalNewChapters} новые главы`;
    }
    text.textContent = newCards.length === 1
      ? `${firstCard.dataset.novelTitle || "Новелла"} — можно продолжить чтение`
      : `Новые главы доступны в ${novelCountText}`;
    button.href = firstCard.dataset.cardActionHref || `/novel/${firstCard.dataset.novelSlug || ""}`;
    button.textContent = newCards.length === 1 ? "Читать" : "К новинкам";
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


  function trimChapterCache(cache) {
    const entries = Object.entries(cache || {})
      .filter(function ([, value]) { return value && value.chapterId && value.html; })
      .sort(function (a, b) { return Number(b[1].savedAt || 0) - Number(a[1].savedAt || 0); })
      .slice(0, 12);
    return Object.fromEntries(entries);
  }

  function safeCachedChapterHtml(html) {
    const template = document.createElement("template");
    template.innerHTML = String(html || "");
    template.content.querySelectorAll("script, iframe, object, embed, form, input, button").forEach(function (node) {
      node.remove();
    });
    template.content.querySelectorAll("*").forEach(function (node) {
      Array.from(node.attributes).forEach(function (attribute) {
        const name = attribute.name.toLowerCase();
        const value = String(attribute.value || "").trim().toLowerCase();
        if (name.startsWith("on") || value.startsWith("javascript:")) {
          node.removeAttribute(attribute.name);
        }
      });
    });
    return template.innerHTML;
  }

  function initChapterContentCache() {
    const page = document.querySelector("[data-chapter-page]");
    if (!page || page.dataset.isLocked === "true") return;

    const chapterId = page.dataset.chapterId || "";
    const article = document.querySelector("[data-cache-chapter-content]");
    const offlineShell = document.querySelector("[data-chapter-offline-copy]");
    const offlineContent = document.querySelector("[data-chapter-offline-copy-content]");
    const offlineTime = document.querySelector("[data-chapter-offline-copy-time]");
    const cachedNote = document.querySelector("[data-chapter-cached-note]");
    if (!chapterId) return;

    const cache = readJson(STORAGE_KEYS.chapterCache, {});
    const cached = cache[chapterId];
    const hasServerContent = Boolean(article && article.textContent && article.textContent.trim().length > 20 && !article.querySelector(".chapter-empty-text"));

    if (hasServerContent && article) {
      const html = safeCachedChapterHtml(article.innerHTML).trim();
      if (html.length > 20 && html.length < 650000) {
        cache[chapterId] = {
          chapterId,
          novelId: page.dataset.novelId || "",
          novelSlug: page.dataset.novelSlug || "",
          novelTitle: page.dataset.novelTitle || "",
          chapterTitle: page.dataset.chapterTitle || "",
          html,
          savedAt: Date.now(),
        };
        writeJson(STORAGE_KEYS.chapterCache, trimChapterCache(cache));
      }
      return;
    }

    if (cached && cached.html && offlineShell && offlineContent) {
      offlineContent.innerHTML = safeCachedChapterHtml(cached.html);
      if (offlineTime) offlineTime.textContent = cached.savedAt ? formatRelativeTime(cached.savedAt) : "";
      offlineShell.hidden = false;
      if (cachedNote) cachedNote.hidden = false;
      if (article) article.hidden = true;
    }
  }

  function initChapterProgress() {
    const page = document.querySelector("[data-chapter-page]");
    if (!page || page.dataset.isLocked === "true") return;
    const novelId = page.dataset.novelId;
    const chapterId = page.dataset.chapterId;
    if (!novelId || !chapterId) return;
    const meta = readJson(STORAGE_KEYS.novelMeta, {});
    const novelMeta = meta[novelId] || {};
    const existing = readJson(STORAGE_KEYS.readingHistory, []).find(function (entry) {
      return String(entry.novelId) === String(novelId) && String(entry.chapterId) === String(chapterId);
    });

    const makeItem = function () {
      const doc = document.documentElement;
      const maxScroll = Math.max(1, doc.scrollHeight - window.innerHeight);
      return {
        novelId,
        novelSlug: page.dataset.novelSlug || novelMeta.novelSlug || "",
        novelTitle: page.dataset.novelTitle || novelMeta.novelTitle || "",
        coverUrl: novelMeta.coverUrl || "",
        chapterId,
        chapterTitle: page.dataset.chapterTitle || "",
        chapterIndex: Number(page.dataset.chapterIndex || 0),
        availableChapters: Number(page.dataset.availableChapters || 0),
        scrollPosition: Math.max(0, Math.min(1, window.scrollY / maxScroll)),
        scrollPositionPx: Math.max(0, Math.round(window.scrollY)),
        updatedAt: Date.now(),
      };
    };

    saveReadChapter(chapterId);
    saveReadingHistoryItem(makeItem(), { sync: true });

    if (existing && Number(existing.scrollPosition) > 0) {
      requestAnimationFrame(function () {
        const maxScroll = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
        window.scrollTo({ top: maxScroll * Number(existing.scrollPosition), behavior: "auto" });
      });
    }
    // Дальнейшее отслеживание прогресса при скролле (включая бесконечную
    // подгрузку глав) делает initInfiniteProgressFix ниже — он привязывает
    // прогресс к реально видимой главе. Второй independent scroll-listener
    // здесь раньше писал в тот же ключ zefirki_reading_history с чужим,
    // захваченным при открытии страницы chapterId — при бесконечной
    // подгрузке это устаревшее значение периодически перезаписывало
    // правильную запись и ломало восстановление позиции чтения.
  }

  function initChapterScrollProgress() {
    const page = document.querySelector("[data-chapter-page]");
    const bar = document.querySelector("[data-chapter-scroll-progress-bar]");
    if (!page || !bar || page.dataset.isLocked === "true") return;

    let ticking = false;
    const update = function () {
      const doc = document.documentElement;
      const maxScroll = Math.max(1, doc.scrollHeight - window.innerHeight);
      const percent = clampNumber((window.scrollY / maxScroll) * 100, 0, 100);
      bar.style.width = `${percent}%`;
      ticking = false;
    };
    const requestUpdate = function () {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(update);
    };
    update();
    window.addEventListener("scroll", requestUpdate, { passive: true });
    window.addEventListener("resize", requestUpdate, { passive: true });
  }

  function initReaderFloatingControls() {
    const page = document.querySelector("[data-chapter-page]");
    const controls = document.querySelector("[data-reader-floating-controls]");
    if (!page || !controls || page.dataset.isLocked === "true") return;

    const upButton = controls.querySelector("[data-scroll-up]");
    const downButton = controls.querySelector("[data-scroll-down]");

    const scrollByPage = function (direction) {
      const distance = Math.max(260, Math.round(window.innerHeight * 0.82));
      window.scrollBy({ top: direction * distance, behavior: "smooth" });
    };

    if (upButton) {
      upButton.addEventListener("click", function () {
        if (window.scrollY <= Math.max(80, window.innerHeight * 0.18)) {
          window.scrollTo({ top: 0, behavior: "smooth" });
          return;
        }
        scrollByPage(-1);
      });
    }

    if (downButton) {
      downButton.addEventListener("click", function () {
        scrollByPage(1);
      });
    }

    let ticking = false;
    const update = function () {
      ticking = false;
      const doc = document.documentElement;
      const maxScroll = Math.max(1, doc.scrollHeight - window.innerHeight);
      const progress = clampNumber(window.scrollY / maxScroll, 0, 1);
      controls.classList.toggle("reader-floating-controls-at-top", progress < 0.02);
      controls.classList.toggle("reader-floating-controls-at-bottom", progress > 0.98);
    };
    const requestUpdate = function () {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(update);
    };

    update();
    window.addEventListener("scroll", requestUpdate, { passive: true });
    window.addEventListener("resize", requestUpdate, { passive: true });
  }


  function setReaderSetting(name, value) {
    const current = getSettings();
    current[name] = String(value);
    saveSettings(current);
    applySettings();
    fillSettingsInputs(getSettings());
    updateReaderQuickSettingsState();
  }

  function readerSettingLabel(name, value) {
    const labels = {
      readerTheme: { cream: "Кремовая", white: "Белая", sepia: "Сепия", dark: "Тёмная" },
      readerWidth: { comfort: "Комфорт", full: "Шире", wide: "Макс." },
      textAlign: { left: "Слева", justify: "По ширине" },
      lineHeight: { "1.1": "Мини", "1.2": "Очень плотно", "1.3": "Плотно", "1.45": "Норма", "1.6": "Свободно", "1.75": "Воздух", "1.9": "Макс." },
      paragraphSpacing: { "0": "0", "2": "2", "4": "4", "8": "8", "12": "12", "16": "16", "20": "20", "24": "24" },
    };
    return (labels[name] && labels[name][String(value)]) || String(value);
  }

  function createReaderSegment(name, values) {
    return values.map(function (value) {
      return `<button class="reader-quick-option" type="button" data-reader-setting="${escapeHtml(name)}" data-reader-value="${escapeHtml(value)}">${escapeHtml(readerSettingLabel(name, value))}</button>`;
    }).join("");
  }

  function ensureReaderQuickSettingsPanel() {
    let panel = document.querySelector("[data-reader-quick-settings]");
    if (panel) return panel;

    panel = document.createElement("aside");
    panel.className = "reader-quick-settings reader-quick-settings-v2";
    panel.dataset.readerQuickSettings = "true";
    panel.hidden = true;
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-modal", "false");
    panel.setAttribute("aria-label", "Настройки чтения");
    panel.innerHTML = `
      <div class="reader-quick-settings-card reader-settings-card-v2">
        <div class="reader-settings-drag" aria-hidden="true"></div>
        <div class="reader-quick-settings-head reader-settings-head-v2">
          <div>
            <div class="reader-quick-title">Настройки</div>
            <div class="reader-quick-subtitle">Чтение и интерфейс</div>
          </div>
          <button class="reader-quick-close reader-settings-close-v2" type="button" data-reader-quick-close aria-label="Закрыть настройки">×</button>
        </div>

        <div class="reader-settings-tabs-v2" role="tablist" aria-label="Разделы настроек">
          <button class="reader-settings-tab-v2 is-active" type="button" data-reader-settings-tab="reader" role="tab" aria-selected="true">Читалка</button>
          <button class="reader-settings-tab-v2" type="button" data-reader-settings-tab="global" role="tab" aria-selected="false">Приложение</button>
        </div>

        <div class="reader-settings-pane-v2 is-active" data-reader-settings-pane="reader">
          <section class="reader-settings-section-v2">
            <div class="reader-settings-section-head-v2">
              <span>Размер текста</span>
              <strong data-reader-font-value>16</strong>
            </div>
            <div class="reader-font-control-v2">
              <button type="button" data-reader-font-step="-1" aria-label="Уменьшить шрифт">A−</button>
              <div class="reader-font-track-v2" aria-hidden="true"><span data-reader-font-track></span></div>
              <button type="button" data-reader-font-step="1" aria-label="Увеличить шрифт">A+</button>
            </div>
          </section>

          <section class="reader-settings-section-v2">
            <div class="reader-settings-section-head-v2"><span hidden>Фон главы</span></div>
            <div class="reader-choice-grid-v2 reader-choice-grid-4-v2">
              ${createReaderSegment("readerTheme", ["cream", "white", "sepia", "dark"])}
            </div>
          </section>

          <section class="reader-settings-section-v2">
            <div class="reader-settings-section-head-v2"><span>Ширина текста</span></div>
            <div class="reader-choice-grid-v2 reader-choice-grid-3-v2">
              ${createReaderSegment("readerWidth", ["comfort", "full", "wide"])}
            </div>
          </section>

          <section class="reader-settings-section-v2">
            <div class="reader-settings-section-head-v2"><span>Воздух между строками</span></div>
            <div class="reader-choice-grid-v2 reader-choice-grid-4-v2">
              ${createReaderSegment("lineHeight", ["1.1", "1.2", "1.3", "1.45", "1.6", "1.75", "1.9"])}
            </div>
          </section>

          <section class="reader-settings-section-v2">
            <div class="reader-settings-section-head-v2"><span>Абзацы</span></div>
            <div class="reader-choice-grid-v2 reader-choice-grid-4-v2">
              ${createReaderSegment("paragraphSpacing", ["0", "2", "4", "8", "12", "16", "20", "24"])}
            </div>
          </section>

          <section class="reader-settings-section-v2">
            <div class="reader-settings-section-head-v2"><span>Выравнивание</span></div>
            <div class="reader-choice-grid-v2 reader-choice-grid-2-v2">
              ${createReaderSegment("textAlign", ["left", "justify"])}
            </div>
          </section>
        </div>

        <div class="reader-settings-pane-v2" data-reader-settings-pane="global">
          <section class="reader-settings-section-v2">
            <div class="reader-settings-section-head-v2"><span>Тема приложения</span></div>
            <div class="reader-choice-grid-v2 reader-choice-grid-3-v2">
              <button class="reader-quick-option" type="button" data-global-setting="siteTheme" data-global-value="light">Светлая</button>
              <button class="reader-quick-option" type="button" data-global-setting="siteTheme" data-global-value="system">Системная</button>
              <button class="reader-quick-option" type="button" data-global-setting="siteTheme" data-global-value="dark">Тёмная</button>
            </div>
          </section>

          <section class="reader-settings-section-v2">
            <div class="reader-settings-section-head-v2"><span>Плотность интерфейса</span></div>
            <div class="reader-choice-grid-v2 reader-choice-grid-3-v2">
              <button class="reader-quick-option" type="button" data-global-setting="appSize" data-global-value="compact">Плотно</button>
              <button class="reader-quick-option" type="button" data-global-setting="appSize" data-global-value="normal">Норма</button>
              <button class="reader-quick-option" type="button" data-global-setting="appSize" data-global-value="large">Крупно</button>
            </div>
          </section>

          <section class="reader-settings-section-v2">
            <div class="reader-settings-section-head-v2"><span>Акцент</span></div>
            <div class="reader-choice-grid-v2 reader-choice-grid-5-v2 reader-accent-grid-v2">
              <button class="reader-quick-option reader-accent-option" type="button" data-global-setting="accentColor" data-global-value="#ff6a00"><span style="--swatch:#ff6a00"></span>Оранж</button>
              <button class="reader-quick-option reader-accent-option" type="button" data-global-setting="accentColor" data-global-value="#ec4899"><span style="--swatch:#ec4899"></span>Розовый</button>
              <button class="reader-quick-option reader-accent-option" type="button" data-global-setting="accentColor" data-global-value="#8b5cf6"><span style="--swatch:#8b5cf6"></span>Фиолет</button>
              <button class="reader-quick-option reader-accent-option" type="button" data-global-setting="accentColor" data-global-value="#0ea5e9"><span style="--swatch:#0ea5e9"></span>Синий</button>
              <button class="reader-quick-option reader-accent-option" type="button" data-global-setting="accentColor" data-global-value="#10b981"><span style="--swatch:#10b981"></span>Зелёный</button>
            </div>
          </section>

          <section class="reader-settings-section-v2">
            <div class="reader-settings-section-head-v2"><span>Панель чтения</span></div>
            <div class="reader-choice-grid-v2 reader-choice-grid-2-v2">
              <button class="reader-quick-option" type="button" data-reader-controls-choice="show">Показывать</button>
              <button class="reader-quick-option" type="button" data-reader-controls-choice="hide">Скрывать</button>
            </div>
          </section>
        </div>

        <div class="reader-quick-footer reader-settings-footer-v2">
          <button type="button" class="reader-quick-reset" data-reader-quick-reset>Сбросить</button>
        </div>
      </div>`;
    document.body.appendChild(panel);
    return panel;
  }

    function updateReaderQuickSettingsState() {
    const panel = document.querySelector("[data-reader-quick-settings]");
    if (!panel) return;
    const settings = getSettings();
    const font = clampNumber(Number(settings.fontSize || DEFAULT_SETTINGS.fontSize), 4, 22);
    const fontValue = panel.querySelector("[data-reader-font-value]");
    if (fontValue) fontValue.textContent = String(font);
    const track = panel.querySelector("[data-reader-font-track]");
    if (track) track.style.width = `${((font - 4) / 18) * 100}%`;

    panel.querySelectorAll("[data-reader-setting]").forEach(function (button) {
      const name = button.dataset.readerSetting;
      const currentValue = String(settings[name] || DEFAULT_SETTINGS[name] || "");
      const active = currentValue === String(button.dataset.readerValue || "");
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });

    panel.querySelectorAll("[data-global-setting]").forEach(function (button) {
      const name = button.dataset.globalSetting;
      const currentValue = String(settings[name] || DEFAULT_SETTINGS[name] || "").toLowerCase();
      const targetValue = String(button.dataset.globalValue || "").toLowerCase();
      const active = currentValue === targetValue;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });

    let hidden = false;
    try { hidden = window.localStorage.getItem(STORAGE_KEYS.readerControlsHidden) === "1"; } catch (error) {}
    panel.querySelectorAll("[data-reader-controls-choice]").forEach(function (button) {
      const active = (button.dataset.readerControlsChoice === "hide") === hidden;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }

    function openReaderQuickSettings(panel, toggle) {
    panel.hidden = false;
    document.body.classList.add("reader-quick-settings-open");
    if (toggle) toggle.setAttribute("aria-expanded", "true");
    updateReaderQuickSettingsState();
    const first = panel.querySelector("button");
    if (first) window.setTimeout(function () { first.focus({ preventScroll: true }); }, 30);
  }

  function closeReaderQuickSettings(panel, toggle) {
    panel.hidden = true;
    document.body.classList.remove("reader-quick-settings-open");
    if (toggle) toggle.setAttribute("aria-expanded", "false");
  }

  function initReaderQuickSettings() {
    const page = document.querySelector("[data-chapter-page]");
    const controls = document.querySelector("[data-reader-floating-controls]");
    if (!page || !controls || page.dataset.isLocked === "true") return;

    let toggle = controls.querySelector("[data-reader-settings-toggle]");
    if (!toggle) {
      toggle = document.createElement("button");
      toggle.className = "reader-floating-button reader-settings-toggle";
      toggle.type = "button";
      toggle.dataset.readerSettingsToggle = "true";
      toggle.setAttribute("aria-label", "Настройки чтения");
      toggle.setAttribute("aria-expanded", "false");
      toggle.title = "Настройки чтения";
      toggle.textContent = "Aa";
      controls.appendChild(toggle);
    }

    const panel = ensureReaderQuickSettingsPanel();
    updateReaderQuickSettingsState();

    function selectReaderSettingsTab(name) {
      panel.querySelectorAll("[data-reader-settings-tab]").forEach(function (tab) {
        const active = tab.dataset.readerSettingsTab === name;
        tab.classList.toggle("is-active", active);
        tab.setAttribute("aria-selected", active ? "true" : "false");
      });
      panel.querySelectorAll("[data-reader-settings-pane]").forEach(function (pane) {
        pane.classList.toggle("is-active", pane.dataset.readerSettingsPane === name);
      });
      try { window.localStorage.setItem(STORAGE_KEYS.globalSettingsOpenTab, name); } catch (error) {}
    }

    try {
      selectReaderSettingsTab(window.localStorage.getItem(STORAGE_KEYS.globalSettingsOpenTab) || "reader");
    } catch (error) {
      selectReaderSettingsTab("reader");
    }

    toggle.addEventListener("click", function () {
      if (panel.hidden) {
        openReaderQuickSettings(panel, toggle);
      } else {
        closeReaderQuickSettings(panel, toggle);
      }
    });

    panel.querySelector("[data-reader-quick-close]")?.addEventListener("click", function () {
      closeReaderQuickSettings(panel, toggle);
      toggle.focus({ preventScroll: true });
    });

    panel.querySelectorAll("[data-reader-settings-tab]").forEach(function (tab) {
      tab.addEventListener("click", function () { selectReaderSettingsTab(tab.dataset.readerSettingsTab || "reader"); });
    });

    panel.querySelectorAll("[data-reader-setting]").forEach(function (button) {
      button.addEventListener("click", function () {
        setReaderSetting(button.dataset.readerSetting, button.dataset.readerValue);
      });
    });

    panel.querySelectorAll("[data-global-setting]").forEach(function (button) {
      button.addEventListener("click", function () {
        const current = getSettings();
        current[button.dataset.globalSetting] = button.dataset.globalValue;
        saveSettings(current);
        applySettings();
        fillSettingsInputs(getSettings());
        updateReaderQuickSettingsState();
      });
    });

    panel.querySelectorAll("[data-reader-controls-choice]").forEach(function (button) {
      button.addEventListener("click", function () {
        const hidden = button.dataset.readerControlsChoice === "hide";
        document.body.classList.toggle("reader-controls-hidden", hidden);
        const floating = document.querySelector("[data-reader-floating-controls]");
        if (floating) floating.setAttribute("aria-hidden", hidden ? "true" : "false");
        const visibilityToggle = document.querySelector("[data-reader-controls-visibility-toggle]");
        if (visibilityToggle) {
          visibilityToggle.setAttribute("aria-pressed", hidden ? "true" : "false");
          visibilityToggle.setAttribute("aria-label", hidden ? "Показать панель чтения" : "Скрыть панель чтения");
          visibilityToggle.textContent = hidden ? "☰" : "×";
        }
        try { window.localStorage.setItem(STORAGE_KEYS.readerControlsHidden, hidden ? "1" : "0"); } catch (error) {}
        updateReaderQuickSettingsState();
      });
    });

    panel.querySelectorAll("[data-reader-font-step]").forEach(function (button) {
      button.addEventListener("click", function () {
        const settings = getSettings();
        const next = clampNumber(Number(settings.fontSize || DEFAULT_SETTINGS.fontSize) + Number(button.dataset.readerFontStep || 0), 4, 22);
        setReaderSetting("fontSize", next);
      });
    });

    panel.querySelector("[data-reader-quick-reset]")?.addEventListener("click", function () {
      const current = getSettings();
      ["readerTheme", "readerWidth", "fontSize", "lineHeight", "paragraphSpacing", "textAlign", "siteTheme", "appSize", "accentColor"].forEach(function (key) {
        current[key] = DEFAULT_SETTINGS[key];
      });
      saveSettings(current);
      applySettings();
      fillSettingsInputs(getSettings());
      updateReaderQuickSettingsState();
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && !panel.hidden) {
        closeReaderQuickSettings(panel, toggle);
        toggle.focus({ preventScroll: true });
      }
    });

    document.addEventListener("click", function (event) {
      if (panel.hidden) return;
      if (panel.contains(event.target) || toggle.contains(event.target)) return;
      closeReaderQuickSettings(panel, toggle);
    }, true);
  }

  function applyReaderControlsHidden(hidden) {
    document.body.classList.toggle("reader-controls-hidden", hidden);
    const controls = document.querySelector("[data-reader-floating-controls]");
    if (controls) controls.setAttribute("aria-hidden", hidden ? "true" : "false");
    const toggle = document.querySelector("[data-reader-controls-visibility-toggle]");
    if (toggle) {
      toggle.setAttribute("aria-pressed", hidden ? "true" : "false");
      toggle.setAttribute("aria-label", hidden ? "Показать панель чтения" : "Скрыть панель чтения");
      toggle.textContent = hidden ? "☰" : "×";
    }
  }

    function initReaderControlsVisibilityToggle() {
    const page = document.querySelector("[data-chapter-page]");
    const controls = document.querySelector("[data-reader-floating-controls]");

    if (!page || !controls || page.dataset.isLocked === "true") return;

    let toggle = document.querySelector("[data-reader-controls-visibility-toggle]");

    if (!toggle) {
      toggle = document.createElement("button");
      toggle.className = "reader-controls-visibility-toggle";
      toggle.type = "button";
      toggle.dataset.readerControlsVisibilityToggle = "true";
      toggle.setAttribute("aria-controls", "readerFloatingControls");
      toggle.setAttribute("aria-label", "Скрыть панель чтения");
      document.body.appendChild(toggle);
    }

    controls.id = controls.id || "readerFloatingControls";

    // Панель всегда стартует видимой — состояние скрытия управляется тапами
    // в течение сессии, а не запоминается между перезагрузками.
    applyReaderControlsHidden(false);

    toggle.addEventListener("click", function () {
      applyReaderControlsHidden(!document.body.classList.contains("reader-controls-hidden"));
    });
  }

  function initFloatingControlsAutoHide() {
    const novelAction = document.querySelector(".novel-read-action");
    const chapterNav = document.querySelector(".chapter-navigation");
    if (!novelAction && !chapterNav) return;
    const chapterPage = document.querySelector("[data-chapter-page]");
    if (chapterPage && chapterPage.dataset.isLocked === "true") return;

    // Кнопка "Начать/Продолжить читать" становится плавающей только после
    // того, как её обычное место в потоке страницы уходит за верх экрана —
    // иначе fixed-версия перекрывала бы "О новелле" сразу при загрузке.
    // Важно: наблюдаем не за самой кнопкой, а за неподвижным маркером рядом
    // с ней. Если наблюдать за кнопкой, то после переключения в position:fixed
    // она сама оказывается в зоне видимости (внизу экрана), наблюдатель тут же
    // снимает is-floating, кнопка возвращается в поток, снова уходит из вида —
    // и так по кругу (моргание/дублирование).
    if (novelAction && typeof IntersectionObserver === "function") {
      const sentinel = document.createElement("span");
      sentinel.setAttribute("aria-hidden", "true");
      sentinel.style.cssText = "display:block;width:1px;height:1px;";
      novelAction.parentNode.insertBefore(sentinel, novelAction);

      const observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          const scrolledPast = !entry.isIntersecting && entry.boundingClientRect.top < 0;
          novelAction.classList.toggle("is-floating", scrolledPast);
          if (!scrolledPast) applyReaderControlsHidden(false);
        });
      }, { threshold: 0 });
      observer.observe(sentinel);
    }

    // Тап по пустому месту (не по ссылке/кнопке/лисичке) переключает
    // видимость плавающих кнопок — один тап прячет, следующий возвращает.
    // Скролл сам по себе больше ничего не прячет и не показывает.
    document.addEventListener("click", function (event) {
      const interactive = event.target.closest(
        "a, button, input, select, textarea, [role='button'], [data-card-menu], [data-fox]"
      );
      if (interactive) return;
      applyReaderControlsHidden(!document.body.classList.contains("reader-controls-hidden"));
    });
  }

  function initChapterRetry() {
    document.querySelectorAll("[data-chapter-retry]").forEach(function (button) {
      button.addEventListener("click", function () {
        window.location.reload();
      });
    });
  }

  function saveReadingHistoryItem(item, options = {}) {
    const history = readJson(STORAGE_KEYS.readingHistory, []);
    const nextHistory = history.filter((entry) => String(entry.novelId) !== String(item.novelId)).concat(item).slice(-50);
    writeJson(STORAGE_KEYS.readingHistory, nextHistory);
    try { window.localStorage.removeItem("zefirki_continue_panel_hidden"); } catch (error) {}
    if (options.sync !== false) {
      saveProgressToServer(item, readJson(STORAGE_KEYS.readChapters, [])).catch(console.warn);
    }
  }

  function saveReadChapter(chapterId) {
    const ids = readJson(STORAGE_KEYS.readChapters, []);
    if (!ids.includes(String(chapterId))) ids.push(String(chapterId));
    writeJson(STORAGE_KEYS.readChapters, ids.slice(-3000));
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
    const hint = document.getElementById("novelReadHint");
    if (!page || !button) return;

    const item = readJson(STORAGE_KEYS.readingHistory, []).find((entry) =>
      String(entry.novelId) === String(page.dataset.novelId)
    );

    if (item && item.chapterId) {
      button.href = `/chapter/${item.chapterId}`;
      button.textContent = "Продолжить чтение";

      if (hint) {
        const available = Number(item.availableChapters || page.dataset.availableChapters || 0);
        const current = Math.max(1, Number(item.chapterIndex || 0) + 1);
        hint.textContent = available > 0 ? `Глава ${current} из ${available}` : `Глава ${current}`;
        hint.hidden = false;
      }
      return;
    }

    const firstAvailable = document.querySelector("[data-chapter-row]:not(.chapter-row-locked)");
    if (firstAvailable && firstAvailable.dataset.chapterId) {
      button.href = `/chapter/${firstAvailable.dataset.chapterId}`;
    }
    button.textContent = "Начать читать";

    if (hint) {
      hint.textContent = "";
      hint.hidden = true;
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
    const page = document.querySelector("[data-novel-page]");
    const historyItem = page ? readJson(STORAGE_KEYS.readingHistory, []).find((entry) => String(entry.novelId) === String(page.dataset.novelId)) : null;
    document.querySelectorAll("[data-chapter-row]").forEach(function (row) {
      if (readIds.includes(String(row.dataset.chapterId))) row.classList.add("chapter-row-read");
      if (historyItem && String(historyItem.chapterId) === String(row.dataset.chapterId)) {
        row.classList.add("chapter-row-current");
        row.setAttribute("aria-current", "page");
      }
    });
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
    const listEnd = list.querySelector(".chapter-list-end");
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

    if (listEnd) {
      listEnd.remove();
    }

    rows.forEach(function (row) {
      list.appendChild(row);
    });

    if (fade) {
      list.appendChild(fade);
    }

    if (listEnd) {
      list.appendChild(listEnd);
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
      overlay.innerHTML = `<div class="spoiler-warning-modal"><h2>Осторожно, спойлер</h2><p>Этот тег может раскрыть важную деталь сюжета</p><label class="spoiler-warning-check"><input type="checkbox" data-spoiler-remember><span>Больше не предупреждать</span></label><div class="spoiler-warning-actions"><button type="button" class="spoiler-warning-cancel" data-spoiler-cancel>Не открывать</button><button type="button" class="spoiler-warning-confirm" data-spoiler-confirm>Показать</button></div></div>`;
      document.body.appendChild(overlay);
    }
    overlay.hidden = false;
    overlay.querySelector("[data-spoiler-cancel]").onclick = function () { overlay.hidden = true; };
    overlay.querySelector("[data-spoiler-confirm]").onclick = function () { const remember = overlay.querySelector("[data-spoiler-remember]"); overlay.hidden = true; onConfirm(remember && remember.checked); };
  }

  function createSettingsUi() {
    const fab = document.createElement("button");
    fab.className = "settings-fab settings-fab-v2";
    fab.type = "button";
    fab.dataset.settingsFab = "true";
    fab.setAttribute("aria-label", "Глобальные настройки");
    fab.textContent = "⚙";

    const overlay = document.createElement("div");
    overlay.className = "settings-overlay settings-overlay-v2";
    overlay.hidden = true;
    overlay.dataset.settingsOverlay = "true";
    overlay.innerHTML = `
      <div class="settings-modal settings-modal-v2" role="dialog" aria-modal="true" aria-label="Глобальные настройки">
        <div class="settings-header settings-header-v2">
          <div>
            <h2>Настройки</h2>
            <p>Единые настройки приложения и читалки</p>
          </div>
          <button class="settings-close settings-close-v2" type="button" data-settings-close aria-label="Закрыть">×</button>
        </div>

        <div class="settings-tabs settings-tabs-v2">
          <button class="settings-tab active" type="button" data-settings-tab="reader">Читалка</button>
          <button class="settings-tab" type="button" data-settings-tab="site">Приложение</button>
          <button class="settings-tab" type="button" data-settings-tab="access">Доступ</button>
          <button class="settings-tab" type="button" data-settings-tab="about">О проекте</button>
        </div>

        <section class="settings-section settings-section-v2 active" data-settings-section="reader">
          <div class="global-settings-grid-v2">
            <label class="settings-field settings-field-v2"><span>Фон главы</span><select data-setting="readerTheme"><option value="cream">Кремовая</option><option value="white">Белая</option><option value="sepia">Сепия</option><option value="dark">Тёмная</option></select></label>
            <label class="settings-field settings-field-v2"><span>Ширина</span><select data-setting="readerWidth"><option value="comfort">Комфорт</option><option value="full">Шире</option><option value="wide">Максимум</option></select></label>
            <label class="settings-field settings-field-v2"><span>Размер</span><select data-setting="fontSize"><option value="4">4</option><option value="5">5</option><option value="6">6</option><option value="7">7</option><option value="8">8</option><option value="9">9</option><option value="10">10</option><option value="11">11</option><option value="12">12</option><option value="13">13</option><option value="14">14</option><option value="15">15</option><option value="16">16</option><option value="17">17</option><option value="18">18</option><option value="19">19</option><option value="20">20</option><option value="21">21</option><option value="22">22</option></select></label>
            <label class="settings-field settings-field-v2"><span>Интервал</span><select data-setting="lineHeight"><option value="1.1">Мини</option><option value="1.2">Очень плотно</option><option value="1.3">Плотно</option><option value="1.45">Норма</option><option value="1.6">Свободно</option><option value="1.75">Воздух</option><option value="1.9">Макс.</option></select></label>
            <label class="settings-field settings-field-v2"><span>Абзацы</span><select data-setting="paragraphSpacing"><option value="0">0</option><option value="2">2</option><option value="4">4</option><option value="8">8</option><option value="12">12</option><option value="16">16</option><option value="20">20</option><option value="24">24</option></select></label>
            <label class="settings-field settings-field-v2"><span>Край</span><select data-setting="textAlign"><option value="left">Слева</option><option value="justify">По ширине</option></select></label>
          </div>
        </section>

        <section class="settings-section settings-section-v2" data-settings-section="site">
          <div class="global-settings-grid-v2">
            <label class="settings-field settings-field-v2"><span>Тема приложения</span><select data-setting="siteTheme"><option value="light">Светлая</option><option value="system">Как в Telegram/системе</option><option value="dark">Тёмная</option></select></label>
            <label class="settings-field settings-field-v2"><span>Плотность</span><select data-setting="appSize"><option value="compact">Плотно</option><option value="normal">Норма</option><option value="large">Крупно</option></select></label>
            <label class="settings-field settings-field-v2"><span>Акцент</span><span class="settings-color-row settings-color-row-v2"><select data-setting="accentColor"><option value="#ff6a00">Апельсин</option><option value="#ec4899">Розовый</option><option value="#8b5cf6">Фиолетовый</option><option value="#0ea5e9">Голубой</option><option value="#10b981">Зелёный</option></select><input type="color" data-setting-color value="#ff6a00"></span></label>
          </div>
          <p class="settings-hint-v2">Эти настройки применяются ко всей библиотеке, оглавлению и читалке</p>
        </section>

        <section class="settings-section settings-section-v2" data-settings-section="access"><div class="access-debug-box"><div class="access-debug-toolbar"><div><h3>Проверка доступа</h3><p>Telegram, группы, подписки Tribute и купленные новеллы</p></div><button class="settings-access-refresh" type="button" data-access-debug-refresh>Обновить</button></div><div class="access-debug-content" data-access-debug-content><p>Откройте вкладку, чтобы проверить права</p></div></div></section>

        <section class="settings-section settings-section-v2" data-settings-section="about"><div class="about-box"><div data-about-fox-wrap></div><h3>Зефиркины баоцзы</h3><p>Мини-читалка для новелл, раннего доступа и удобного возвращения к последней главе</p><div class="about-links"><a href="/library">Библиотека</a></div></div></section>

        <div class="settings-footer settings-footer-v2"><button class="settings-reset" type="button" data-settings-reset>Сбросить всё</button></div>
      </div>`;
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
    overlay.querySelectorAll("[data-setting]").forEach(function (input) { input.addEventListener("change", function () { const current = getSettings(); current[input.dataset.setting] = input.value; saveSettings(current); applySettings(); updateReaderQuickSettingsState(); }); });
    overlay.querySelectorAll("[data-setting-checkbox]").forEach(function (input) { input.addEventListener("change", function () { const current = getSettings(); current[input.dataset.settingCheckbox] = input.checked; saveSettings(current); applySettings(); }); });
    const colorInput = overlay.querySelector("[data-setting-color]");
    if (colorInput) colorInput.addEventListener("input", function () { const current = getSettings(); current.accentColor = colorInput.value; saveSettings(current); applySettings(); updateReaderQuickSettingsState(); });
    overlay.querySelector("[data-settings-reset]")?.addEventListener("click", function () { saveSettings({ ...DEFAULT_SETTINGS }); fillSettingsInputs(getSettings()); applySettings(); updateReaderQuickSettingsState(); });
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



/* ===== v129 clean settings controller ===== */
(function () {
  "use strict";
  const SETTINGS_KEY = "zefirki_reader_settings";
  const CONTROLS_KEY = "zefirki_reader_controls_hidden";
  const DEFAULTS = {
    siteTheme: "system",
    readerTheme: "cream",
    readerWidth: "comfort",
    fontSize: "16",
    lineHeight: "1.6",
    paragraphSpacing: "16",
    textAlign: "left",
    accentColor: "#ff6a00",
    appSize: "normal"
  };
  const LABELS = {
    readerTheme: { cream: "Кремовая", white: "Белая", sepia: "Сепия", dark: "Тёмная" },
    readerWidth: { comfort: "Комфорт", full: "Шире", wide: "Макс" },
    lineHeight: { "1.1": "Мини", "1.2": "Очень плотно", "1.3": "Плотно", "1.45": "Норма", "1.6": "Свободно", "1.75": "Воздух", "1.9": "Макс." },
    paragraphSpacing: { "0": "0", "2": "2", "4": "4", "8": "8", "12": "12", "16": "16", "20": "20", "24": "24" },
    textAlign: { left: "Слева", justify: "По ширине" },
    siteTheme: { light: "Светлая", system: "Системная", dark: "Тёмная" },
    appSize: { compact: "Плотно", normal: "Норма", large: "Крупно" },
    accentColor: { "#ff6a00": "Оранж", "#ec4899": "Розовый", "#8b5cf6": "Фиолет", "#0ea5e9": "Синий", "#10b981": "Зелёный" },
    readerControls: { show: "Показывать", hide: "Скрывать" }
  };

  function readJson(key, fallback) {
    try {
      const raw = window.localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (error) {
      return fallback;
    }
  }
  function writeJson(key, value) {
    try { window.localStorage.setItem(key, JSON.stringify(value)); } catch (error) {}
  }
  function readSettings() { return Object.assign({}, DEFAULTS, readJson(SETTINGS_KEY, {})); }
  function writeSettings(next) { writeJson(SETTINGS_KEY, Object.assign({}, DEFAULTS, next)); }
  function clamp(value, min, max) {
    value = Number(value);
    if (Number.isNaN(value)) value = min;
    return Math.min(max, Math.max(min, value));
  }
  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
  function applyCleanSettings() {
    const settings = readSettings();
    const body = document.body;
    if (!body) return;
    const requestedSiteTheme = settings.siteTheme || "system";
    const systemDark = requestedSiteTheme === "system" && window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    const resolvedSiteTheme = requestedSiteTheme === "system" ? (systemDark ? "dark" : "light") : requestedSiteTheme;
    body.dataset.siteTheme = resolvedSiteTheme;
    body.dataset.siteThemeChoice = requestedSiteTheme;
    body.dataset.resolvedTheme = resolvedSiteTheme;
    body.classList.toggle("site-theme-system", requestedSiteTheme === "system");
    body.dataset.readerTheme = settings.readerTheme || "cream";
    body.dataset.readerWidth = settings.readerWidth || "comfort";
    body.dataset.textAlign = settings.textAlign || "left";
    body.dataset.appSize = settings.appSize || "normal";
    document.documentElement.style.setProperty("--accent", settings.accentColor || DEFAULTS.accentColor);
    document.documentElement.style.setProperty("--zb-accent", settings.accentColor || DEFAULTS.accentColor);
    document.documentElement.style.setProperty("--reader-font-size", `${clamp(settings.fontSize, 4, 24)}px`);
    document.documentElement.style.setProperty("--reader-line-height", settings.lineHeight || "1.6");
    document.documentElement.style.setProperty("--reader-paragraph-spacing", `${clamp(settings.paragraphSpacing, 0, 32)}px`);
  }
  function setSetting(name, value) {
    const settings = readSettings();
    settings[name] = String(value);
    writeSettings(settings);
    applyCleanSettings();
    updateSheetState();
  }
  function setFont(delta) {
    const settings = readSettings();
    settings.fontSize = String(clamp(Number(settings.fontSize || 16) + delta, 4, 24));
    writeSettings(settings);
    applyCleanSettings();
    updateSheetState();
  }
  function getControlsChoice() {
    try { return window.localStorage.getItem(CONTROLS_KEY) === "true" ? "hide" : "show"; } catch (error) { return "show"; }
  }
  function setControlsChoice(value) {
    try { window.localStorage.setItem(CONTROLS_KEY, value === "hide" ? "true" : "false"); } catch (error) {}
    document.body.classList.toggle("reader-controls-hidden", value === "hide");
    updateSheetState();
  }
  function choice(name, value, extra) {
    const label = (LABELS[name] && LABELS[name][value]) || value;
    return `<button class="zb-choice ${extra || ""}" type="button" data-zb-setting="${escapeHtml(name)}" data-zb-value="${escapeHtml(value)}">${escapeHtml(label)}</button>`;
  }
  function choiceRow(name, values) {
    return `<div class="zb-choice-row">${values.map((value) => choice(name, value)).join("")}</div>`;
  }
  function accentRow() {
    const colors = ["#ff6a00", "#ec4899", "#8b5cf6", "#0ea5e9", "#10b981"];
    return `<div class="zb-choice-row">${colors.map((value) => {
      const label = LABELS.accentColor[value];
      return `<button class="zb-choice" type="button" data-zb-setting="accentColor" data-zb-value="${value}"><span class="zb-accent-dot" style="--dot:${value}"></span>${label}</button>`;
    }).join("")}</div>`;
  }
  function settingCard(label, valueSlot, body) {
    return `<section class="zb-setting-card"><div class="zb-setting-label"><span>${label}</span>${valueSlot || ""}</div>${body}</section>`;
  }
  function ensureSheet() {
    let overlay = document.querySelector("[data-zb-settings-overlay]");
    if (overlay) return overlay;
    overlay = document.createElement("aside");
    overlay.className = "zb-settings-overlay";
    overlay.dataset.zbSettingsOverlay = "true";
    overlay.hidden = true;
    overlay.innerHTML = `
      <div class="zb-settings-sheet" role="dialog" aria-modal="true" aria-label="Настройки">
        <div class="zb-settings-drag" aria-hidden="true"></div>
        <header class="zb-settings-head">
          <div>
            <h2 class="zb-settings-title" data-zb-settings-title>Настройки</h2>
            <p class="zb-settings-subtitle" data-zb-settings-subtitle>Единые настройки приложения и чтения</p>
          </div>
          <button class="zb-settings-close" type="button" data-zb-settings-close aria-label="Закрыть">×</button>
        </header>
        <nav class="zb-settings-tabs" aria-label="Разделы настроек">
          <button class="zb-settings-tab is-active" type="button" data-zb-tab="reader">Читалка</button>
          <button class="zb-settings-tab" type="button" data-zb-tab="app">Приложение</button>
          <button class="zb-settings-tab" type="button" data-zb-tab="access">Доступ</button>
          <button class="zb-settings-tab" type="button" data-zb-tab="about">О проекте</button>
        </nav>
        <div class="zb-settings-body">
          <section class="zb-settings-pane is-active" data-zb-pane="reader">
            <div class="zb-settings-grid">
              ${settingCard("Размер", `<strong class="zb-setting-value" data-zb-font-value>16</strong>`, `<div class="zb-stepper"><button type="button" data-zb-font-step="-1">A−</button><div class="zb-range-track" aria-hidden="true"><span data-zb-font-track></span></div><button type="button" data-zb-font-step="1">A+</button></div>`)}
              ${settingCard("Ширина", "", choiceRow("readerWidth", ["comfort", "full", "wide"]))}
              ${settingCard("Интервал", "", choiceRow("lineHeight", ["1.1", "1.2", "1.3", "1.45", "1.6", "1.75", "1.9"]))}
              ${settingCard("Абзацы", "", choiceRow("paragraphSpacing", ["0", "2", "4", "8", "12", "16", "20", "24"]))}
              ${settingCard("Край", "", choiceRow("textAlign", ["left", "justify"]))}
            </div>
            <section class="zb-reader-preview" data-zb-reader-preview aria-label="Предпросмотр текста">
              <div class="zb-reader-preview-label">Предпросмотр</div>
              <p>Первый абзац показывает размер, интервал и ширину строки. Так сразу видно, как будет выглядеть глава во время чтения.</p>
              <p>Второй абзац показывает отступы между абзацами и выравнивание текста.</p>
            </section>
          </section>
          <section class="zb-settings-pane" data-zb-pane="app">
            <div class="zb-settings-grid">
              ${settingCard("Тема", "", choiceRow("siteTheme", ["light", "system", "dark"]))}
              ${settingCard("Плотность", "", choiceRow("appSize", ["compact", "normal", "large"]))}
              ${settingCard("Акцент", "", accentRow())}
              ${settingCard("Панель в читалке", "", `<div class="zb-choice-row"><button class="zb-choice" type="button" data-zb-controls="show">Показывать</button><button class="zb-choice" type="button" data-zb-controls="hide">Скрывать</button></div>`)}
            </div>
            <p class="zb-settings-note">Эти настройки применяются к библиотеке, оглавлению и чтению</p>
          </section>
          <section class="zb-settings-pane" data-zb-pane="access">
            <div class="zb-access-box"><h3>Доступ</h3><p>Доступ проверяется через Telegram и сохранённые права. Подробная диагностика остаётся в админке, чтобы не перегружать интерфейс читателя</p></div>
          </section>
          <section class="zb-settings-pane" data-zb-pane="about">
            <div class="zb-about-box"><h3>Зефиркины баоцзы</h3><p>Мини-читалка для библиотеки, оглавления, раннего доступа и удобного возвращения к последней главе</p></div>
          </section>
        </div>
        <footer class="zb-settings-footer"><button class="zb-reset-button" type="button" data-zb-reset>Сбросить</button></footer>
      </div>`;
    document.body.appendChild(overlay);
    bindSheet(overlay);
    return overlay;
  }
  function ensureButtons() {
    if (document.body.classList.contains("page-library") && !document.querySelector("[data-zb-global-settings]")) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "zb-global-settings-button";
      button.dataset.zbGlobalSettings = "true";
      button.setAttribute("aria-label", "Открыть настройки");
      button.textContent = "⚙";
      button.addEventListener("click", function () { openSheet("app"); });
      document.body.appendChild(button);
    }
    if (document.body.classList.contains("page-chapter") && !document.querySelector("[data-zb-reader-settings]")) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "zb-reader-settings-button";
      button.dataset.zbReaderSettings = "true";
      button.setAttribute("aria-label", "Открыть настройки чтения");
      button.textContent = "Aa";
      button.addEventListener("click", function () { openSheet("reader"); });
      document.body.appendChild(button);
    }
  }
  function openSheet(tab) {
    const overlay = ensureSheet();
    overlay.hidden = false;
    setTab(tab || "reader");
    updateSheetState();
    document.body.classList.add("zb-settings-open");
  }
  function closeSheet() {
    const overlay = document.querySelector("[data-zb-settings-overlay]");
    if (overlay) overlay.hidden = true;
    document.body.classList.remove("zb-settings-open");
  }
  function setTab(tab) {
    const overlay = ensureSheet();
    overlay.querySelectorAll("[data-zb-tab]").forEach(function (button) {
      const active = button.dataset.zbTab === tab;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-selected", active ? "true" : "false");
    });
    overlay.querySelectorAll("[data-zb-pane]").forEach(function (pane) {
      pane.classList.toggle("is-active", pane.dataset.zbPane === tab);
    });
    const title = overlay.querySelector("[data-zb-settings-title]");
    const subtitle = overlay.querySelector("[data-zb-settings-subtitle]");
    if (title) title.textContent = tab === "reader" ? "Настройки чтения" : tab === "app" ? "Настройки приложения" : tab === "access" ? "Доступ" : "О проекте";
    if (subtitle) subtitle.textContent = tab === "reader" ? "Текст, ширина, интервалы и предпросмотр" : tab === "app" ? "Тема, плотность, акцент и панель" : tab === "access" ? "Как приложение понимает права читателя" : "Информация о читалке";
  }
  function bindSheet(overlay) {
    overlay.addEventListener("click", function (event) {
      if (event.target === overlay) closeSheet();
    });
    overlay.querySelector("[data-zb-settings-close]").addEventListener("click", closeSheet);
    overlay.querySelectorAll("[data-zb-tab]").forEach(function (button) {
      button.addEventListener("click", function () { setTab(button.dataset.zbTab); updateSheetState(); });
    });
    overlay.addEventListener("click", function (event) {
      const setting = event.target.closest("[data-zb-setting]");
      if (setting) {
        setSetting(setting.dataset.zbSetting, setting.dataset.zbValue);
        return;
      }
      const step = event.target.closest("[data-zb-font-step]");
      if (step) {
        setFont(Number(step.dataset.zbFontStep || 0));
        return;
      }
      const controls = event.target.closest("[data-zb-controls]");
      if (controls) {
        setControlsChoice(controls.dataset.zbControls);
        return;
      }
      const reset = event.target.closest("[data-zb-reset]");
      if (reset) {
        writeSettings(DEFAULTS);
        setControlsChoice("show");
        applyCleanSettings();
        updateSheetState();
      }
    });
  }
  function updateSheetState() {
    const overlay = document.querySelector("[data-zb-settings-overlay]");
    if (!overlay) return;
    const settings = readSettings();
    const font = clamp(settings.fontSize, 4, 24);
    const fontValue = overlay.querySelector("[data-zb-font-value]");
    if (fontValue) fontValue.textContent = String(font);
    const track = overlay.querySelector("[data-zb-font-track]");
    if (track) track.style.width = `${((font - 4) / 20) * 100}%`;
    overlay.querySelectorAll("[data-zb-setting]").forEach(function (button) {
      const active = String(settings[button.dataset.zbSetting] || "").toLowerCase() === String(button.dataset.zbValue || "").toLowerCase();
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
    const controlsChoice = getControlsChoice();
    overlay.querySelectorAll("[data-zb-controls]").forEach(function (button) {
      const active = button.dataset.zbControls === controlsChoice;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }
  function interceptOldReaderSettings() {
    document.addEventListener("click", function (event) {
      const oldToggle = event.target.closest("[data-reader-settings-toggle]");
      if (!oldToggle) return;
      event.preventDefault();
      event.stopPropagation();
      if (typeof event.stopImmediatePropagation === "function") event.stopImmediatePropagation();
      openSheet("reader");
    }, true);
  }
  function cleanupOldUi() {
    document.querySelectorAll(".settings-fab, .settings-fab-v2, .settings-overlay, .settings-overlay-v2, .reader-quick-settings, .reader-quick-settings-v2").forEach(function (node) {
      if (!node.classList.contains("zb-settings-overlay")) {
        node.setAttribute("aria-hidden", "true");
      }
    });
  }
  function initCleanSettings() {
    applyCleanSettings();
    ensureSheet();
    ensureButtons();
    cleanupOldUi();
    interceptOldReaderSettings();
    setControlsChoice(getControlsChoice());
    [0, 150, 500, 1200].forEach(function (delay) {
      window.setTimeout(function () { applyCleanSettings(); ensureButtons(); cleanupOldUi(); updateSheetState(); }, delay);
    });
    try {
      const observer = new MutationObserver(function () { cleanupOldUi(); ensureButtons(); });
      observer.observe(document.body, { childList: true, subtree: true });
    } catch (error) {}
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initCleanSettings);
  } else {
    initCleanSettings();
  }
})();


/* === v134 reader preview, system theme and infinite chapter scroll === */
(function () {
  const SETTINGS_KEY = "zefirki_reader_settings";
  const DEFAULTS = {
    siteTheme: "system",
    readerWidth: "comfort",
    fontSize: "16",
    lineHeight: "1.6",
    paragraphSpacing: "16",
    textAlign: "left",
    accentColor: "#ff6a00",
    appSize: "normal"
  };
  function readSettings() {
    try { return Object.assign({}, DEFAULTS, JSON.parse(window.localStorage.getItem(SETTINGS_KEY) || "{}")); }
    catch (error) { return Object.assign({}, DEFAULTS); }
  }
  function resolveTheme(settings) {
    const choice = settings.siteTheme || "system";
    const dark = choice === "system" && window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    return choice === "system" ? (dark ? "dark" : "light") : choice;
  }
  function applySystemThemeAndAccent() {
    const settings = readSettings();
    const resolved = resolveTheme(settings);
    document.body.dataset.siteTheme = resolved;
    document.body.dataset.resolvedTheme = resolved;
    document.body.dataset.siteThemeChoice = settings.siteTheme || "system";
    document.body.classList.toggle("site-theme-system", (settings.siteTheme || "system") === "system");
    document.documentElement.style.setProperty("--accent", settings.accentColor || DEFAULTS.accentColor);
    document.documentElement.style.setProperty("--zb-accent", settings.accentColor || DEFAULTS.accentColor);
  }
  function ensurePreview() {
    const pane = document.querySelector('[data-zb-pane="reader"]');
    if (!pane) return null;
    let preview = pane.querySelector('[data-zb-reader-preview]');
    if (!preview) {
      preview = document.createElement("section");
      preview.className = "zb-reader-preview";
      preview.dataset.zbReaderPreview = "true";
      preview.setAttribute("aria-label", "Предпросмотр текста");
      preview.innerHTML = '<div class="zb-reader-preview-label">Предпросмотр</div><p>Первый абзац показывает размер, интервал и ширину строки. Так сразу видно, как будет выглядеть глава во время чтения.</p><p>Второй абзац показывает отступы между абзацами и выравнивание текста.</p>';
      pane.appendChild(preview);
    }
    return preview;
  }
  function updatePreview() {
    applySystemThemeAndAccent();
    const settings = readSettings();
    const preview = ensurePreview();
    if (!preview) return;
    preview.style.setProperty("--preview-font-size", `${Math.max(4, Math.min(24, Number(settings.fontSize || 16)))}px`);
    preview.style.setProperty("--preview-line-height", settings.lineHeight || "1.6");
    preview.style.setProperty("--preview-paragraph", `${Math.max(0, Math.min(32, Number(settings.paragraphSpacing || 16)))}px`);
    preview.dataset.previewWidth = settings.readerWidth || "comfort";
    preview.dataset.previewAlign = settings.textAlign || "left";
    preview.querySelectorAll("p").forEach(function (p) {
      p.style.fontSize = "var(--preview-font-size)";
      p.style.lineHeight = "var(--preview-line-height)";
      p.style.marginBottom = "var(--preview-paragraph)";
      p.style.textAlign = settings.textAlign === "justify" ? "justify" : "left";
    });
  }
  function hideReaderBackgroundControls() {
    document.querySelectorAll('[data-zb-setting="readerTheme"], [data-reader-setting="readerTheme"]').forEach(function (button) {
      const card = button.closest('.zb-setting-card, .reader-settings-section-v2');
      if (card) card.hidden = true;
      else button.hidden = true;
    });
  }
  function initSettingsPreview() {
    updatePreview();
    hideReaderBackgroundControls();
    document.addEventListener("click", function (event) {
      if (event.target.closest('[data-zb-setting], [data-zb-font-step], [data-zb-tab], [data-reader-setting], [data-reader-font-step], [data-global-setting]')) {
        window.setTimeout(function () { updatePreview(); hideReaderBackgroundControls(); }, 0);
        window.setTimeout(function () { updatePreview(); hideReaderBackgroundControls(); }, 80);
      }
    }, true);
    [0, 150, 600, 1400].forEach(function (delay) {
      window.setTimeout(function () { updatePreview(); hideReaderBackgroundControls(); }, delay);
    });
  }
  function initSystemThemeWatcher() {
    applySystemThemeAndAccent();
    try {
      const media = window.matchMedia("(prefers-color-scheme: dark)");
      const handler = function () { applySystemThemeAndAccent(); updatePreview(); };
      if (media.addEventListener) media.addEventListener("change", handler);
      else if (media.addListener) media.addListener(handler);
    } catch (error) {}
    window.addEventListener("storage", function (event) { if (event.key === SETTINGS_KEY) { applySystemThemeAndAccent(); updatePreview(); } });
    [0, 200, 700, 1500].forEach(function (delay) { window.setTimeout(applySystemThemeAndAccent, delay); });
  }
  function initChapterInfiniteScroll() {
    const page = document.querySelector('[data-chapter-page]');
    const source = document.querySelector('[data-cache-chapter-content]');
    if (!page || !source || page.dataset.isLocked === "true") return;
    let nav = document.querySelector('.chapter-navigation');
    let next = nav ? Array.from(nav.querySelectorAll('a[href*="/chapter/"]')).find(function (a) { return /Следующая/i.test(a.textContent || ""); }) : null;
    let nextUrl = next ? next.href : "";
    if (!nextUrl) return;
    let loading = false;
    let stopped = false;
    const status = document.createElement("div");
    status.className = "chapter-infinite-status";
    status.textContent = "";
    if (nav && nav.parentNode) nav.parentNode.insertBefore(status, nav);
    function extractNext(doc) {
      const nextLink = Array.from(doc.querySelectorAll('.chapter-navigation a[href*="/chapter/"]')).find(function (a) { return /Следующая/i.test(a.textContent || ""); });
      return nextLink ? new URL(nextLink.getAttribute('href'), window.location.origin).href : "";
    }
    function appendChapter(doc, url) {
      const nextPage = doc.querySelector('[data-chapter-page]');
      if (!nextPage || nextPage.dataset.isLocked === "true") {
        stopped = true;
        status.innerHTML = '<span class="chapter-loading-stop" aria-hidden="true">🔒</span><span>Дальше начинается закрытая или платная глава</span>';
        return;
      }
      const content = doc.querySelector('[data-cache-chapter-content]');
      const title = doc.querySelector('.chapter-header h1');
      if (!content) { stopped = true; return; }
      const wrap = document.createElement("section");
      wrap.className = "chapter-infinite-item";
      wrap.dataset.chapterInfiniteItem = "true";
      wrap.dataset.novelId = nextPage.dataset.novelId || page.dataset.novelId || "";
      wrap.dataset.novelSlug = nextPage.dataset.novelSlug || page.dataset.novelSlug || "";
      wrap.dataset.novelTitle = nextPage.dataset.novelTitle || page.dataset.novelTitle || "";
      wrap.dataset.chapterId = nextPage.dataset.chapterId || "";
      wrap.dataset.chapterTitle = nextPage.dataset.chapterTitle || (title ? title.textContent : "");
      wrap.dataset.chapterIndex = nextPage.dataset.chapterIndex || "0";
      wrap.dataset.availableChapters = nextPage.dataset.availableChapters || page.dataset.availableChapters || "0";
      wrap.dataset.chapterUrl = url;
      wrap.innerHTML = `<header class="chapter-infinite-head"><span>Следующая глава</span><h2>${title ? title.textContent : "Глава"}</h2></header><article class="chapter-content chapter-content-infinite">${content.innerHTML}</article>`;
      if (nav && nav.parentNode) nav.parentNode.insertBefore(wrap, nav);
      try {
        document.dispatchEvent(new CustomEvent("zefirki:chapter-appended", { detail: {
          novelId: wrap.dataset.novelId,
          chapterId: wrap.dataset.chapterId,
          chapterTitle: wrap.dataset.chapterTitle,
          chapterIndex: wrap.dataset.chapterIndex,
          availableChapters: wrap.dataset.availableChapters,
          element: wrap
        }}));
      } catch (error) {}
      nextUrl = extractNext(doc);
      if (!nextUrl || nextUrl === url) {
        stopped = true;
        status.innerHTML = '<span class="chapter-loading-done" aria-hidden="true">✓</span><span>Доступные главы закончились</span>';
      } else {
        status.textContent = "";
      }
    }
    function loadNext() {
      if (loading || stopped || !nextUrl) return;
      loading = true;
      status.innerHTML = '<span class="chapter-loading-spinner" aria-hidden="true"></span><span>Загружаю следующую главу…</span>';
      const currentUrl = nextUrl;
      fetch(currentUrl, { credentials: "same-origin" })
        .then(function (response) { if (!response.ok) throw new Error(String(response.status)); return response.text(); })
        .then(function (html) { appendChapter(new DOMParser().parseFromString(html, "text/html"), currentUrl); })
        .catch(function () { stopped = true; status.innerHTML = '<span class="chapter-loading-stop" aria-hidden="true">!</span><span>Не удалось автоматически загрузить следующую главу</span>'; })
        .finally(function () { loading = false; });
    }
    function maybeLoad() {
      if (stopped || loading) return;
      const remaining = document.documentElement.scrollHeight - (window.scrollY + window.innerHeight);
      if (remaining < 1000) loadNext();
    }
    window.addEventListener("scroll", maybeLoad, { passive: true });
    window.addEventListener("resize", maybeLoad, { passive: true });
    window.setTimeout(maybeLoad, 800);
  }
  function initV134() {
    initSystemThemeWatcher();
    initSettingsPreview();
    initChapterInfiniteScroll();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initV134);
  else initV134();
})();


/* === v135 loading indicators and infinite-scroll progress fix === */
(function () {
  const SETTINGS_KEY = "zefirki_reader_settings";
  const HISTORY_KEY = "zefirki_reading_history";
  const META_KEY = "zefirki_novel_meta";
  const READ_KEY = "zefirki_read_chapters";
  const DEFAULT_ACCENT = "#ff6a00";

  function readJson(key, fallback) {
    try {
      const raw = window.localStorage.getItem(key);
      if (!raw) return fallback;
      const parsed = JSON.parse(raw);
      return parsed == null ? fallback : parsed;
    } catch (error) {
      return fallback;
    }
  }

  function writeJson(key, value) {
    try { window.localStorage.setItem(key, JSON.stringify(value)); }
    catch (error) {}
  }

  function clamp(value, min, max) {
    const number = Number(value);
    if (!Number.isFinite(number)) return min;
    return Math.max(min, Math.min(max, number));
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function ensureNavigationLoader() {
    let overlay = document.querySelector("[data-app-route-loading]");
    if (overlay) return overlay;
    overlay = document.createElement("div");
    overlay.className = "app-route-loading";
    overlay.dataset.appRouteLoading = "true";
    overlay.setAttribute("role", "status");
    overlay.setAttribute("aria-live", "polite");
    overlay.hidden = true;
    overlay.innerHTML = '<div class="app-route-loading-card"><span class="app-route-spinner" aria-hidden="true"></span><span data-app-route-loading-text>Загружается…</span></div>';
    document.body.appendChild(overlay);
    return overlay;
  }

  function showNavigationLoader(text) {
    const overlay = ensureNavigationLoader();
    const label = overlay.querySelector("[data-app-route-loading-text]");
    if (label) label.textContent = text || "Загружается…";
    overlay.hidden = false;
    document.body.classList.add("app-is-loading-route");
  }

  function initRouteLoadingIndicators() {
    ensureNavigationLoader();
    document.addEventListener("click", function (event) {
      const link = event.target.closest('a[href]');
      if (!link) return;
      if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      if (link.target && link.target !== "_self") return;
      if (link.hasAttribute("download")) return;
      const href = link.getAttribute("href") || "";
      if (!href || href.startsWith("#") || href.startsWith("javascript:")) return;
      let url;
      try { url = new URL(href, window.location.href); }
      catch (error) { return; }
      if (url.origin !== window.location.origin) return;
      if (url.pathname === window.location.pathname && url.hash) return;
      const text = /\/chapter\//.test(url.pathname) ? "Открываю главу…" : /\/novel\//.test(url.pathname) ? "Открываю оглавление…" : "Загружается…";
      showNavigationLoader(text);
    }, true);
    window.addEventListener("pageshow", function () {
      const overlay = document.querySelector("[data-app-route-loading]");
      if (overlay) overlay.hidden = true;
      document.body.classList.remove("app-is-loading-route");
    });
  }

  function getNovelMeta(novelId) {
    const meta = readJson(META_KEY, {});
    return meta[String(novelId)] || {};
  }

  function saveReadChapterId(chapterId) {
    if (!chapterId) return [];
    const ids = Array.isArray(readJson(READ_KEY, [])) ? readJson(READ_KEY, []) : [];
    const normalized = ids.map(String);
    if (!normalized.includes(String(chapterId))) normalized.push(String(chapterId));
    const trimmed = normalized.slice(-3000);
    writeJson(READ_KEY, trimmed);
    return trimmed;
  }

  function sectionProgress(element) {
    if (!element) return 0;
    const rect = element.getBoundingClientRect();
    const top = window.scrollY + rect.top;
    const height = Math.max(1, element.offsetHeight - window.innerHeight);
    return clamp((window.scrollY - top) / height, 0, 1);
  }

  function buildHistoryItemFromElement(element) {
    const page = document.querySelector("[data-chapter-page]");
    if (!page || !element) return null;
    const novelId = element.dataset.novelId || page.dataset.novelId || "";
    const meta = getNovelMeta(novelId);
    const chapterId = element.dataset.chapterId || page.dataset.chapterId || "";
    if (!novelId || !chapterId) return null;
    const chapterIndex = Number(element.dataset.chapterIndex || page.dataset.chapterIndex || 0);
    const available = Number(element.dataset.availableChapters || page.dataset.availableChapters || 0);
    const title = element.dataset.chapterTitle || page.dataset.chapterTitle || "";
    const progress = sectionProgress(element);
    return {
      novelId: String(novelId),
      novelSlug: element.dataset.novelSlug || page.dataset.novelSlug || meta.novelSlug || "",
      novelTitle: element.dataset.novelTitle || page.dataset.novelTitle || meta.novelTitle || "",
      coverUrl: meta.coverUrl || "",
      chapterId: String(chapterId),
      chapterTitle: title,
      chapterIndex: chapterIndex,
      chapterNumber: chapterIndex + 1,
      availableChapters: available,
      progressLabel: available > 0 ? `Глава ${Math.min(chapterIndex + 1, available)} из ${available}` : `Глава ${chapterIndex + 1}`,
      scrollPosition: progress,
      scrollPositionPx: Math.max(0, Math.round(window.scrollY)),
      updatedAt: Date.now(),
      continueUrl: `/chapter/${encodeURIComponent(String(chapterId))}`,
    };
  }

  let lastSavedChapterKey = "";
  let serverTimer = null;

  function putProgressToServer(item, readIds) {
    if (!item || !item.novelId || !item.chapterId) return;
    const viewer = window.ZEFIRKI_VIEWER || {};
    if (!viewer || (!viewer.user_id && !viewer.userId && !viewer.telegram_id && !viewer.telegramId)) return;
    const payload = {
      novel_id: Number(item.novelId),
      novel_slug: item.novelSlug || "",
      novel_title: item.novelTitle || "",
      cover_url: item.coverUrl || "",
      chapter_id: item.chapterId,
      chapter_title: item.chapterTitle || "",
      chapter_index: Number(item.chapterIndex || 0),
      available_chapters: Number(item.availableChapters || 0),
      scroll_position: Number(item.scrollPosition || 0),
      scroll_position_px: Math.max(0, Math.round(Number(item.scrollPositionPx || 0))),
      completed: true,
      read_chapter_ids: Array.isArray(readIds) ? readIds.slice(-3000) : [],
    };
    window.fetch("/api/user/progress", {
      method: "PUT",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).catch(function () {});
  }

  function saveVisibleProgress(element, options) {
    const item = buildHistoryItemFromElement(element);
    if (!item) return;
    const readIds = saveReadChapterId(item.chapterId);
    const history = Array.isArray(readJson(HISTORY_KEY, [])) ? readJson(HISTORY_KEY, []) : [];
    const next = history.filter(function (entry) { return String(entry.novelId) !== String(item.novelId); }).concat(item).slice(-50);
    writeJson(HISTORY_KEY, next);
    const key = `${item.novelId}:${item.chapterId}`;
    if (key !== lastSavedChapterKey) {
      lastSavedChapterKey = key;
      document.dispatchEvent(new CustomEvent("zefirki:reading-progress-visible", { detail: item }));
    }
    if (options && options.sync) {
      putProgressToServer(item, readIds);
    } else if (!serverTimer) {
      serverTimer = window.setTimeout(function () {
        serverTimer = null;
        const current = getCurrentVisibleChapterElement();
        const currentItem = buildHistoryItemFromElement(current);
        if (currentItem) putProgressToServer(currentItem, saveReadChapterId(currentItem.chapterId));
      }, 5000);
    }
  }

  function registerOriginalChapterElement() {
    const page = document.querySelector("[data-chapter-page]");
    if (!page || page.dataset.isLocked === "true") return null;
    let original = document.querySelector("[data-current-chapter-progress-root]");
    if (original) return original;
    original = document.querySelector(".chapter-content-shell") || document.querySelector("[data-cache-chapter-content]") || page;
    original.dataset.currentChapterProgressRoot = "true";
    original.dataset.chapterProgressItem = "true";
    original.dataset.novelId = page.dataset.novelId || "";
    original.dataset.novelSlug = page.dataset.novelSlug || "";
    original.dataset.novelTitle = page.dataset.novelTitle || "";
    original.dataset.chapterId = page.dataset.chapterId || "";
    original.dataset.chapterTitle = page.dataset.chapterTitle || "";
    original.dataset.chapterIndex = page.dataset.chapterIndex || "0";
    original.dataset.availableChapters = page.dataset.availableChapters || "0";
    return original;
  }

  function allChapterProgressElements() {
    const original = registerOriginalChapterElement();
    const items = Array.from(document.querySelectorAll("[data-chapter-infinite-item]"));
    if (original && !items.includes(original)) items.unshift(original);
    items.forEach(function (element) { element.dataset.chapterProgressItem = "true"; });
    return items;
  }

  function getCurrentVisibleChapterElement() {
    const items = allChapterProgressElements();
    if (!items.length) return null;
    const activationLine = window.innerHeight * 0.28;
    let best = null;
    let bestTop = -Infinity;
    items.forEach(function (item) {
      const rect = item.getBoundingClientRect();
      if (rect.bottom <= 96 || rect.top >= window.innerHeight) return;
      if (rect.top <= activationLine && rect.top > bestTop) {
        bestTop = rect.top;
        best = item;
      }
    });
    if (best) return best;
    return items.find(function (item) {
      const rect = item.getBoundingClientRect();
      return rect.bottom > 96 && rect.top < window.innerHeight * 0.72;
    }) || items[0];
  }

  function initInfiniteProgressFix() {
    const page = document.querySelector("[data-chapter-page]");
    if (!page || page.dataset.isLocked === "true") return;
    registerOriginalChapterElement();
    let scrollTimer = null;
    const onScroll = function () {
      window.clearTimeout(scrollTimer);
      scrollTimer = window.setTimeout(function () {
        const current = getCurrentVisibleChapterElement();
        if (current) saveVisibleProgress(current, { sync: false });
      }, 140);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });
    window.addEventListener("pagehide", function () {
      const current = getCurrentVisibleChapterElement();
      if (current) saveVisibleProgress(current, { sync: true });
    });
    document.addEventListener("zefirki:chapter-appended", function (event) {
      const element = event.detail && event.detail.element;
      if (element) {
        element.dataset.chapterProgressItem = "true";
        window.setTimeout(onScroll, 220);
      }
    });
    if ("IntersectionObserver" in window) {
      const observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          const rect = entry.target.getBoundingClientRect();
          if (entry.isIntersecting && rect.top <= window.innerHeight * 0.28 && rect.bottom > 96) {
            saveVisibleProgress(entry.target, { sync: false });
          }
        });
      }, { threshold: [0.22, 0.45, 0.7] });
      const observeAll = function () { allChapterProgressElements().forEach(function (item) { observer.observe(item); }); };
      observeAll();
      document.addEventListener("zefirki:chapter-appended", observeAll);
    }
    window.setTimeout(onScroll, 600);
  }

  function initV135() {
    initRouteLoadingIndicators();
    initInfiniteProgressFix();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initV135);
  else initV135();
})();


/* v141 — compact paywall unlock modal and smaller reader spacing options */
(function () {
  function initPaywallUnlock() {
    document.querySelectorAll('[data-paywall-unlock-open]').forEach(function (button) {
      if (button.dataset.v141Bound === 'true') return;
      button.dataset.v141Bound = 'true';
      button.addEventListener('click', function () {
        const root = button.closest('.chapter-paywall-actions') || document;
        const panel = root.querySelector('[data-paywall-unlock-panel]');
        if (!panel) return;
        panel.hidden = false;
        panel.classList.add('is-open');
        const first = panel.querySelector('a, button:not([data-paywall-unlock-close])');
        if (first) first.focus({ preventScroll: true });
      });
    });
    document.querySelectorAll('[data-paywall-unlock-close]').forEach(function (button) {
      if (button.dataset.v141Bound === 'true') return;
      button.dataset.v141Bound = 'true';
      button.addEventListener('click', function () {
        const panel = button.closest('[data-paywall-unlock-panel]');
        if (!panel) return;
        panel.classList.remove('is-open');
        panel.hidden = true;
      });
    });
    document.addEventListener('click', function (event) {
      const panel = event.target && event.target.closest && event.target.closest('[data-paywall-unlock-panel].is-open');
      if (panel && event.target === panel) {
        panel.classList.remove('is-open');
        panel.hidden = true;
      }
    });
  }

  function enhanceReaderSpacingControls() {
    const addOptions = function (select, values) {
      if (!select) return;
      values.forEach(function (item) {
        if (!select.querySelector('option[value="' + item.value + '"]')) {
          const option = document.createElement('option');
          option.value = item.value;
          option.textContent = item.label;
          select.insertBefore(option, select.firstChild);
        }
      });
    };
    addOptions(document.querySelector('select[data-setting="lineHeight"]'), [
      { value: '1.3', label: 'Плотно' },
      { value: '1.2', label: 'Очень плотно' },
      { value: '1.1', label: 'Мини' }
    ]);
    addOptions(document.querySelector('select[data-setting="paragraphSpacing"]'), [
      { value: '8', label: '8' },
      { value: '4', label: '4' },
      { value: '2', label: '2' },
      { value: '0', label: '0' }
    ]);
  }

  function initV141() {
    initPaywallUnlock();
    enhanceReaderSpacingControls();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initV141);
  else initV141();
})();
