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
    accentColor: { "#ff6a00": "Оранжевый", "#ec4899": "Розовый", "#8b5cf6": "Фиолетовый", "#0ea5e9": "Синий", "#10b981": "Зелёный" },
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
    const activeAccent = settings.accentColor || DEFAULTS.accentColor;
    document.documentElement.style.setProperty("--accent", activeAccent);
    document.documentElement.style.setProperty("--zb-accent", activeAccent);
    document.documentElement.style.setProperty("--site-accent", activeAccent);
    document.documentElement.style.setProperty("--app-accent", activeAccent);
    document.documentElement.style.setProperty("--accent-color", activeAccent);
    document.documentElement.style.setProperty("--accent-soft", `color-mix(in srgb, ${activeAccent} 12%, transparent)`);
    document.documentElement.style.setProperty("--reader-font-size", `${clamp(settings.fontSize, 4, 24)}px`);
    document.documentElement.style.setProperty("--reader-line-height", settings.lineHeight || "1.6");
    document.documentElement.style.setProperty("--reader-paragraph-spacing", `${clamp(settings.paragraphSpacing, 0, 32)}px`);
    const readerThemes = {
      cream: ["#f7efe7", "#fffaf3", "#111111", "#b45309"],
      white: ["#f4f4f4", "#ffffff", "#111111", "#b45309"],
      sepia: ["#ead7bd", "#f4e3c8", "#2b211c", "#92400e"],
      dark: ["#0f0f0f", "#1b1b1b", "#eeeeee", "#fbbf24"]
    };
    const readerPalette = readerThemes[settings.readerTheme] || readerThemes.cream;
    document.documentElement.style.setProperty("--reader-page-bg", readerPalette[0]);
    document.documentElement.style.setProperty("--reader-bg", readerPalette[1]);
    document.documentElement.style.setProperty("--reader-text-color", readerPalette[2]);
    document.documentElement.style.setProperty("--reader-link-color", readerPalette[3]);
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
  function settingSelect(name, values) {
    return `<span class="zb-setting-select-wrap"><select class="zb-setting-select" data-zb-select-setting="${escapeHtml(name)}" aria-label="${escapeHtml(name)}">${values.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml((LABELS[name] && LABELS[name][value]) || value)}</option>`).join("")}</select><span class="zb-setting-select-chevron" aria-hidden="true"></span></span>`;
  }
  function accentSelect() {
    const colors = ["#ff6a00", "#ec4899", "#8b5cf6", "#0ea5e9", "#10b981"];
    return `<span class="zb-setting-select-wrap zb-setting-select-wrap-accent"><span class="zb-setting-select-accent-dot" data-zb-accent-preview aria-hidden="true"></span><select class="zb-setting-select" data-zb-select-setting="accentColor" aria-label="Акцент">${colors.map((value) => `<option value="${value}">${escapeHtml(LABELS.accentColor[value] || value)}</option>`).join("")}</select><span class="zb-setting-select-chevron" aria-hidden="true"></span></span>`;
  }
  function compactSettingRow(label, hint, body) {
    return `<section class="zb-compact-setting-row"><div class="zb-compact-setting-copy"><strong>${escapeHtml(label)}</strong>${hint ? `<span>${escapeHtml(hint)}</span>` : ""}</div><div class="zb-compact-setting-control">${body}</div></section>`;
  }
  function settingCard(label, valueSlot, body) {
    return `<section class="zb-setting-card"><div class="zb-setting-label"><span>${label}</span>${valueSlot || ""}</div>${body}</section>`;
  }
  function formatSubscriptionDate(value) {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleDateString("ru-RU", { day: "2-digit", month: "long", year: "numeric" });
  }
  let subscriptionSummaryLoaded = false;
  let subscriptionSummaryLoading = false;
/* v229 compatibility wording (not rendered): Дата не передаётся Telegram · Пока вы состоите в группе */
  function supportPickerHtml(data) {
    const support = (data && data.support) || {};
    const travelerUrl = String(support.traveler_url || "").trim();
    const keeperUrl = String(support.keeper_url || "").trim();
    if (!travelerUrl && !keeperUrl) return "";
    const links = [];
    if (travelerUrl) links.push(`<a href="${escapeHtml(travelerUrl)}" target="_blank" rel="noopener noreferrer" data-telegram-link><strong>🌱 «Странствующий читатель»</strong><span>Поддержать проект и открыть новеллы 🎁</span></a>`);
    if (keeperUrl) links.push(`<a href="${escapeHtml(keeperUrl)}" target="_blank" rel="noopener noreferrer" data-telegram-link><strong>📜 «Хранитель свитков»</strong><span>Всё из 🌱 и ранние главы</span></a>`);
    return `<details class="zb-support-picker"><summary>Выбрать уровень поддержки</summary><div class="zb-support-picker-menu">${links.join("")}</div></details>`;
  }
  function subscriptionStatusHtml(data) {
    if (data && data.admin_preview) {
      return `<div class="zb-subscription-status zb-subscription-status-active"><div><span>Режим администратора</span><strong>Полный доступ для проверки читалки</strong></div><div class="zb-subscription-status-meta"><span>Прогресс и аналитика в браузерном режиме не сохраняются.</span></div></div>`;
    }
    if (!data || !data.active) {
      return `<p class="zb-subscription-status zb-subscription-status-empty">Сейчас активных подписок нет.</p>`;
    }
    const item = data || {};
    const membershipBased = Boolean(item.membership_based);
    const label = item.label || (item.role === "keeper" ? "📜 Хранитель свитков" : "🌱 Странствующий читатель");
    const source = item.provider_label || (item.provider === "reader_coins" ? "Монетки" : item.provider === "boosty" ? "Boosty" : "");
    const details = [];
    if (item.started_at) details.push(`<span><b>Куплена:</b> ${escapeHtml(formatSubscriptionDate(item.started_at))}</span>`);
    if (item.expires_at) details.push(`<span><b>Действует до:</b> ${escapeHtml(formatSubscriptionDate(item.expires_at))}</span>`);
    if (membershipBased && !item.started_at && !item.expires_at) details.push(`<span>Доступ подтверждён по участию в закрытой группе${source ? ` · ${escapeHtml(source)}` : ""}.</span>`);
    return `<div class="zb-subscription-status zb-subscription-status-active"><div><span>Активная подписка</span><strong>${escapeHtml(label)}</strong></div>${details.length ? `<div class="zb-subscription-status-meta">${details.join("")}</div>` : ""}</div>`;
  }
  async function loadSubscriptionSummary(force) {
    const box = document.querySelector("[data-zb-subscription-summary]");
    if (!box || (subscriptionSummaryLoaded && !force) || subscriptionSummaryLoading) return;
    subscriptionSummaryLoading = true;
    box.innerHTML = `<div class="zb-access-loading">Проверяем подписку…</div>`;
    try {
      const response = await fetch("/api/auth/subscription?refresh=true", { credentials: "same-origin" });
      const data = await response.json().catch(function () { return {}; });
      if (!response.ok) throw new Error(data.detail || "Не удалось получить данные подписки");
      subscriptionSummaryLoaded = true;
      if (data && data.admin_preview) {
        box.innerHTML = subscriptionStatusHtml(data);
      } else {
        box.innerHTML = `
          ${subscriptionStatusHtml(data)}
          <p class="zb-subscription-support-copy">Подписка — это поддержка переводов: благодаря ей мы можем покупать главы, брать новые истории и чаще выпускать обновления. Бонусный доступ в читалке — наше спасибо за поддержку.</p>
          <div class="zb-subscription-levels">
            <article class="zb-subscription-level">
              <h4>🌱 «Странствующий читатель»</h4>
              <p>Открывает новеллы с отметкой 🎁 — они доступны здесь и на Boosty.</p>
              <strong class="zb-subscription-bonus">🎁 +3 новеллы</strong>
            </article>
            <article class="zb-subscription-level">
              <h4>📜 «Хранитель свитков»</h4>
              <p>Открывает всё из 🌱 и ранние главы к некоторым переводам.</p>
              <strong class="zb-subscription-bonus">🎁 +3 новеллы · 📜 +34 главы</strong>
            </article>
          </div>
          <p class="zb-subscription-free-note">Бесплатные главы можно читать без подписки.</p>
          ${supportPickerHtml(data)}`;
      }
    } catch (error) {
      box.innerHTML = `<div class="zb-subscription-empty"><strong>Не удалось проверить подписку</strong><span>${escapeHtml(error && error.message ? error.message : "Попробуйте ещё раз.")}</span><button type="button" class="zb-access-retry" data-zb-access-retry>Повторить</button></div>`;
    } finally {
      subscriptionSummaryLoading = false;
    }
  }
  let walletBalanceLoaded = false;
  let walletBalanceLoading = false;
  let walletCatalog = {};
  const pendingWalletActions = new Map();
  function formatCoins(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number.toLocaleString("ru-RU") : "—";
  }
  function walletActionId(key) {
    if (pendingWalletActions.has(key)) return pendingWalletActions.get(key);
    let existing = "";
    try { existing = window.sessionStorage.getItem(key) || ""; } catch (error) {}
    const validUuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    const created = validUuid.test(existing) ? existing : window.crypto?.randomUUID?.()
      || "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (char) {
        const value = Math.floor(Math.random() * 16);
        return (char === "x" ? value : (value & 3) | 8).toString(16);
      });
    pendingWalletActions.set(key, created);
    try { window.sessionStorage.setItem(key, created); } catch (error) {}
    return created;
  }
  function clearWalletAction(key) {
    pendingWalletActions.delete(key);
    try { window.sessionStorage.removeItem(key); } catch (error) {}
  }
  function setWalletBalance(value) {
    document.querySelectorAll("[data-zb-wallet-balance]").forEach(function (node) {
      node.textContent = formatCoins(value);
    });
  }
  function setWalletStatus(text, tone) {
    const status = document.querySelector("[data-zb-wallet-status]");
    if (!status) return;
    status.textContent = text || "";
    status.dataset.tone = tone || "info";
    status.hidden = !text;
  }
  function safeWalletLink(value) {
    if (!String(value || "").trim()) return "";
    try {
      const url = new URL(String(value || ""), window.location.origin);
      return url.protocol === "https:" && url.hostname === "t.me" ? url.href : "";
    } catch (error) {
      return "";
    }
  }
  function walletErrorMessage(detail) {
    const messages = {
      test_coin_topup_disabled: "Тестовое пополнение завершено. Обновите баланс.",
      test_coin_action_conflict: "Не удалось подтвердить пополнение. Обновите баланс и повторите попытку.",
      store_temporarily_unavailable: "Пополнение временно недоступно. Попробуйте ещё раз.",
    };
    return messages[detail] || "Не удалось пополнить баланс. Проверьте соединение и повторите попытку.";
  }
  function renderWalletTopup(catalog, readOnly) {
    walletCatalog = catalog || {};
    if (readOnly) walletCatalog = { ...walletCatalog, test_topup_enabled: false };
    const testEnabled = Boolean(walletCatalog.test_topup_enabled) && !readOnly;
    const minimum = Math.max(10, Number(walletCatalog.test_topup_min || 10));
    const maximum = Math.max(minimum, Number(walletCatalog.test_topup_max || 1000));
    const testSection = document.querySelector("[data-zb-wallet-test-topup]");
    const custom = document.querySelector("[data-zb-wallet-custom]");
    const customSubmit = document.querySelector("[data-zb-wallet-custom-submit]");
    if (testSection) testSection.hidden = !testEnabled;
    if (custom) {
      custom.min = String(minimum);
      custom.max = String(maximum);
      custom.disabled = !testEnabled;
    }
    if (customSubmit) customSubmit.disabled = !testEnabled;
    document.querySelectorAll("[data-zb-wallet-test-amount]").forEach(function (button) {
      const amount = Number(button.dataset.zbWalletTestAmount || 0);
      button.disabled = !testEnabled || amount < minimum || amount > maximum;
    });
    const tribute = document.querySelector("[data-zb-wallet-tribute]");
    const tributeUrl = safeWalletLink(walletCatalog.topup_url);
    if (tribute) {
      tribute.href = tributeUrl || "https://t.me/qinghe_rpg_bot";
      tribute.hidden = readOnly;
    }
    document.querySelectorAll("[data-zb-wallet-stars-amount], [data-zb-wallet-stars-custom], [data-zb-wallet-stars-submit]").forEach(function (control) {
      control.disabled = true;
    });
  }
  async function loadWalletBalance(force) {
    const box = document.querySelector("[data-zb-wallet-box]");
    if (!box || (walletBalanceLoaded && !force) || walletBalanceLoading) return;
    walletBalanceLoading = true;
    box.classList.add("is-loading");
    setWalletStatus("Загружаем баланс…", "info");
    try {
      const responses = await Promise.allSettled([
        fetch("/api/store/wallet", { credentials: "same-origin" }),
        fetch("/api/store/products", { credentials: "same-origin" })
      ]);
      if (responses[0].status !== "fulfilled") throw new Error("Не удалось загрузить баланс. Попробуйте ещё раз.");
      const walletResponse = responses[0].value;
      const wallet = await walletResponse.json().catch(function () { return {}; });
      if (!walletResponse.ok) throw new Error("Баланс временно недоступен. Попробуйте ещё раз.");
      setWalletBalance(wallet.balance || 0);
      const catalogResponse = responses[1].status === "fulfilled" ? responses[1].value : null;
      if (!catalogResponse || !catalogResponse.ok) {
        renderWalletTopup({}, Boolean(wallet.read_only));
        setWalletStatus("Баланс загружен. Способы пополнения временно недоступны — нажмите на баланс ещё раз.", "error");
        walletBalanceLoaded = false;
        return;
      }
      const catalog = await catalogResponse.json();
      walletBalanceLoaded = true;
      renderWalletTopup(catalog, Boolean(wallet.read_only));
      setWalletStatus("", "info");
      const hint = box.querySelector("[data-zb-wallet-hint]");
      if (hint) hint.textContent = wallet.read_only ? "В режиме просмотра баланс недоступен" : "Нажмите, чтобы пополнить";
    } catch (error) {
      setWalletBalance("—");
      setWalletStatus(error && error.message ? error.message : "Баланс временно недоступен", "error");
    } finally {
      walletBalanceLoading = false;
      box.classList.remove("is-loading");
    }
  }
  async function grantWalletTestCoins(rawAmount) {
    if (walletBalanceLoading || !walletCatalog.test_topup_enabled) return;
    const minimum = Math.max(10, Number(walletCatalog.test_topup_min || 10));
    const maximum = Math.max(minimum, Number(walletCatalog.test_topup_max || 1000));
    const amount = Number(rawAmount || 0);
    if (!Number.isInteger(amount) || amount < minimum || amount > maximum) {
      setWalletStatus(`Введите сумму от ${formatCoins(minimum)} до ${formatCoins(maximum)} Монеток.`, "error");
      return;
    }
    const key = `settings-wallet-test-topup:${amount}`;
    walletBalanceLoading = true;
    document.querySelector("[data-zb-wallet-box]")?.classList.add("is-loading");
    setWalletStatus("Начисляем тестовые Монетки…", "info");
    try {
      const response = await fetch("/api/store/test-coins", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Accept": "application/json", "Content-Type": "application/json" },
        body: JSON.stringify({ amount: amount, client_action_id: walletActionId(key) })
      });
      const data = await response.json().catch(function () { return {}; });
      if (!response.ok) throw new Error(walletErrorMessage(data.detail));
      clearWalletAction(key);
      setWalletBalance(data.balance || 0);
      window.dispatchEvent(new CustomEvent("reader-wallet-updated", { detail: { balance: Number(data.balance || 0) } }));
      setWalletStatus(data.duplicate ? "Это пополнение уже выполнено. Баланс обновлён." : `Баланс пополнен на ${formatCoins(data.credited || amount)} Монеток.`, "success");
    } catch (error) {
      setWalletStatus(error && error.message ? error.message : "Не удалось пополнить баланс", "error");
    } finally {
      walletBalanceLoading = false;
      document.querySelector("[data-zb-wallet-box]")?.classList.remove("is-loading");
    }
  }
  let purchaseHistoryLoaded = false;
  let purchaseHistoryLoading = false;
  function purchaseTypeLabel(item) {
    if (item.product_type === "chapter_unlock") return "Глава";
    if (item.product_type === "novel_unlock") return "Вся новелла";
    if (item.product_type === "subscription") return "Подписка";
    return "Покупка";
  }
  function formatPurchaseDate(value) {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit"
    });
  }
  async function loadPurchaseHistory(force) {
    const box = document.querySelector("[data-zb-purchase-history]");
    if (!box || (purchaseHistoryLoaded && !force) || purchaseHistoryLoading) return;
    purchaseHistoryLoading = true;
    box.innerHTML = `<div class="zb-access-loading">Загружаем покупки…</div>`;
    try {
      const response = await fetch("/api/store/purchases?limit=50", { credentials: "same-origin" });
      const data = await response.json().catch(function () { return {}; });
      if (!response.ok) throw new Error(data.detail || "Не удалось получить историю покупок");
      purchaseHistoryLoaded = true;
      const items = Array.isArray(data.items) ? data.items : [];
      if (!items.length) {
        box.innerHTML = `<p class="zb-purchase-history-empty">Покупок за Монетки пока нет.</p>`;
      } else {
        box.innerHTML = `<div class="zb-purchase-history-list">${items.map(function (item) {
          return `<article class="zb-purchase-history-item"><div><small>${escapeHtml(purchaseTypeLabel(item))}</small><strong>${escapeHtml(item.title || item.product_code || "Покупка")}</strong><span>${escapeHtml(formatPurchaseDate(item.purchased_at))}</span></div><b>${Number(item.coin_price || 0).toLocaleString("ru-RU")} 🪙</b></article>`;
        }).join("")}</div>`;
      }
    } catch (error) {
      box.innerHTML = `<div class="zb-subscription-empty"><strong>Не удалось загрузить покупки</strong><span>${escapeHtml(error && error.message ? error.message : "Попробуйте ещё раз.")}</span><button type="button" class="zb-access-retry" data-zb-purchases-retry>Повторить</button></div>`;
    } finally {
      purchaseHistoryLoading = false;
    }
  }
  let personalStatsLoaded = false;
  let personalStatsLoading = false;
  function formatStatsDate(value) {
    if (!value) return "Пока нет данных";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleDateString("ru-RU", { day: "2-digit", month: "long", year: "numeric" });
  }
  async function loadPersonalStats(force) {
    const box = document.querySelector("[data-zb-personal-stats]");
    if (!box || (personalStatsLoaded && !force) || personalStatsLoading) return;
    personalStatsLoading = true;
    box.innerHTML = `<div class="zb-stats-loading">Собираем вашу статистику…</div>`;
    try {
      const response = await fetch("/api/user/stats", { credentials: "same-origin" });
      const data = await response.json().catch(function () { return {}; });
      if (!response.ok) throw new Error(data.detail || "Не удалось получить статистику");
      personalStatsLoaded = true;
      if (data && data.admin_preview) {
        box.innerHTML = `<div class="zb-subscription-status zb-subscription-status-active"><div><span>Режим администратора</span><strong>Статистика отключена</strong></div><div class="zb-subscription-status-meta"><span>Тестовое чтение через браузер не влияет на реальные показатели канала.</span></div></div>`;
        return;
      }
      box.innerHTML = `
        <div class="zb-personal-stats-grid">
          <article class="zb-personal-stat zb-personal-stat-main"><span>Прочитано глав</span><strong>${Number(data.chapters_read || 0).toLocaleString("ru-RU")}</strong></article>
          <article class="zb-personal-stat"><span>Новелл начато</span><strong>${Number(data.novels_started || 0).toLocaleString("ru-RU")}</strong></article>
          <article class="zb-personal-stat"><span>Сейчас читаю</span><strong>${Number(data.currently_reading || 0).toLocaleString("ru-RU")}</strong></article>
          <article class="zb-personal-stat"><span>Завершено</span><strong>${Number(data.novels_completed || 0).toLocaleString("ru-RU")}</strong></article>
        </div>
        <div class="zb-personal-stats-foot"><span>Последнее чтение</span><strong>${escapeHtml(formatStatsDate(data.last_read_at))}</strong></div>`;
    } catch (error) {
      box.innerHTML = `<div class="zb-subscription-empty"><strong>Не удалось загрузить статистику</strong><span>${escapeHtml(error && error.message ? error.message : "Попробуйте ещё раз.")}</span><button type="button" class="zb-access-retry" data-zb-stats-retry>Повторить</button></div>`;
    } finally {
      personalStatsLoading = false;
    }
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
          <button class="zb-settings-tab" type="button" data-zb-tab="stats">Статистика</button>
          <button class="zb-settings-tab" type="button" data-zb-tab="about">О проекте</button>
        </nav>
        <div class="zb-settings-body">
          <section class="zb-settings-pane is-active" data-zb-pane="reader">
            <div class="zb-compact-settings-list">
              ${compactSettingRow("Размер текста", "4–24 px", `<div class="zb-stepper zb-stepper-compact"><button type="button" data-zb-font-step="-1" aria-label="Уменьшить текст">A−</button><strong class="zb-setting-value" data-zb-font-value>16</strong><button type="button" data-zb-font-step="1" aria-label="Увеличить текст">A+</button></div>`)}
              ${compactSettingRow("Фон главы", "Отдельно от темы приложения", settingSelect("readerTheme", ["cream", "white", "sepia", "dark"]))}
              ${compactSettingRow("Ширина текста", "Комфортная или расширенная колонка", choiceRow("readerWidth", ["comfort", "full", "wide"]))}
              ${compactSettingRow("Межстрочный интервал", "Плотность строк", settingSelect("lineHeight", ["1.1", "1.2", "1.3", "1.45", "1.6", "1.75", "1.9"]))}
              ${compactSettingRow("Отступ между абзацами", "Вертикальный ритм", settingSelect("paragraphSpacing", ["0", "2", "4", "8", "12", "16", "20", "24"]))}
              ${compactSettingRow("Выравнивание", "Левый край или по ширине", choiceRow("textAlign", ["left", "justify"]))}
            </div>
            <section class="zb-reader-preview zb-reader-preview-compact" data-zb-reader-preview aria-label="Предпросмотр текста"><div class="zb-reader-preview-label">Предпросмотр</div><p>Так будет выглядеть основной текст главы с выбранными настройками.</p></section>
          </section>
          <section class="zb-settings-pane" data-zb-pane="app">
            <div class="zb-compact-settings-list">
              ${compactSettingRow("Тема приложения", "Светлая тема использует тёплый жёлтый градиент", choiceRow("siteTheme", ["light", "system", "dark"]))}
              ${compactSettingRow("Размер интерфейса", "Плотность карточек и элементов", choiceRow("appSize", ["compact", "normal", "large"]))}
              ${compactSettingRow("Акцент", "Цвет основных кнопок и активных элементов", accentSelect())}
            </div>
          </section>
          <section class="zb-settings-pane" data-zb-pane="access">
            <div class="zb-access-box zb-access-box-user zb-wallet-box" data-zb-wallet-box>
              <h3>Баланс</h3>
              <button class="zb-wallet-balance-card" type="button" data-zb-wallet-open aria-expanded="false">
                <span class="zb-wallet-coin" aria-hidden="true">🪙</span>
                <span class="zb-wallet-balance-copy"><small>Ваш баланс</small><strong><span data-zb-wallet-balance>—</span> Монеток</strong><em data-zb-wallet-hint>Нажмите, чтобы пополнить</em></span>
                <span class="zb-wallet-plus" aria-hidden="true">＋</span>
              </button>
              <div class="zb-wallet-topup" data-zb-wallet-topup hidden>
                <div class="zb-wallet-topup-head"><strong>Пополнить баланс</strong><span>Минимальная сумма — 10 Монеток</span></div>
                <section class="zb-wallet-method" data-zb-wallet-test-topup hidden>
                  <div class="zb-wallet-method-title"><strong>Бесплатно на время теста</strong><span>Зачисление сразу</span></div>
                  <div class="zb-wallet-presets">${[10, 50, 100, 250, 500, 1000].map(function (amount) { return `<button type="button" data-zb-wallet-test-amount="${amount}">+${amount}</button>`; }).join("")}</div>
                  <div class="zb-wallet-custom"><input type="number" min="10" max="1000" step="1" inputmode="numeric" placeholder="Своя сумма" data-zb-wallet-custom><button type="button" data-zb-wallet-custom-submit>Начислить</button></div>
                </section>
                <section class="zb-wallet-method zb-wallet-method-stars">
                  <div class="zb-wallet-method-title"><strong>Telegram Stars</strong><span>1 ⭐ = 1 Монетка</span></div>
                  <div class="zb-wallet-presets">${[10, 50, 100, 250, 500, 1000].map(function (amount) { return `<button type="button" data-zb-wallet-stars-amount="${amount}" disabled>${amount} ⭐</button>`; }).join("")}</div>
                  <div class="zb-wallet-custom"><input type="number" min="10" max="1000" step="1" inputmode="numeric" placeholder="Своя сумма" data-zb-wallet-stars-custom disabled><button type="button" data-zb-wallet-stars-submit disabled>Купить</button></div>
                  <p>Нативная оплата Stars появится здесь после подключения защищённого инвойса.</p>
                </section>
                <a class="zb-wallet-tribute" href="https://t.me/qinghe_rpg_bot" target="_blank" rel="noopener noreferrer" data-zb-wallet-tribute>Купить через Tribute в @qinghe_rpg_bot <span aria-hidden="true">↗</span></a>
              </div>
              <p class="zb-wallet-status" data-zb-wallet-status hidden role="status"></p>
            </div>
            <div class="zb-access-box zb-access-box-user"><h3>Подписки</h3><div data-zb-subscription-summary><div class="zb-access-loading">Откройте раздел, чтобы проверить подписки.</div></div></div>
            <div class="zb-access-box zb-access-box-user zb-purchase-history-box"><h3>История покупок</h3><div data-zb-purchase-history><div class="zb-access-loading">Откройте раздел, чтобы увидеть покупки.</div></div></div>
          </section>
          <section class="zb-settings-pane" data-zb-pane="stats">
            <div class="zb-personal-stats-box" data-zb-personal-stats><div class="zb-stats-loading">Откройте раздел, чтобы увидеть статистику чтения.</div></div>
          </section>
          <section class="zb-settings-pane" data-zb-pane="about">
            <div class="zb-about-box zb-about-box-project"><a class="zb-about-project-link" href="https://t.me/+Z5b3eeJjJTs0MTli" target="_blank" rel="noopener noreferrer" data-main-group-link><span>🥟</span><strong>Зефиркины баоцзы</strong><span aria-hidden="true">↗</span></a><p>Мини-читалка для наших переводов: выбирайте новеллы, возвращайтесь к последней главе и следите за обновлениями.</p></div>
          </section>
        </div>
        <footer class="zb-settings-footer"><button class="zb-reset-button" type="button" data-zb-reset>Сбросить оформление</button></footer>
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
    if (overlay.hidden) previousSettingsFocus = document.activeElement;
    overlay.hidden = false;
    setTab(tab || "reader");
    updateSheetState();
    document.body.classList.add("zb-settings-open");
    overlay.querySelector("[data-zb-settings-close]")?.focus();
  }
  let previousSettingsFocus = null;
  function closeSheet() {
    const overlay = document.querySelector("[data-zb-settings-overlay]");
    if (overlay) overlay.hidden = true;
    document.body.classList.remove("zb-settings-open");
    previousSettingsFocus?.focus?.();
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
    const titles = { reader: "Настройки чтения", app: "Настройки приложения", access: "Доступ", stats: "Статистика", about: "О проекте" };
    const subtitles = { reader: "Текст, фон и интервалы — без лишних экранов", app: "Тема, размер интерфейса и акцент", access: "Поддержка переводов и ваш текущий доступ", stats: "Ваше чтение в Mini App", about: "Информация о проекте" };
    if (title) title.textContent = titles[tab] || "Настройки";
    if (subtitle) subtitle.textContent = subtitles[tab] || "";
    if (tab === "access") {
      loadWalletBalance(true);
      loadSubscriptionSummary(false);
      loadPurchaseHistory(false);
    }
    if (tab === "stats") loadPersonalStats(false);
  }
  function bindSheet(overlay) {
    overlay.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        event.preventDefault();
        closeSheet();
      }
      if (event.key !== "Tab") return;
      const controls = Array.from(overlay.querySelectorAll("button:not(:disabled), input:not(:disabled), select:not(:disabled), a[href]"))
        .filter(function (node) { return node.getClientRects().length > 0; });
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    });
    overlay.addEventListener("click", function (event) {
      if (event.target === overlay) closeSheet();
    });
    overlay.querySelector("[data-zb-settings-close]").addEventListener("click", closeSheet);
    overlay.querySelectorAll("[data-zb-tab]").forEach(function (button) {
      button.addEventListener("click", function () { setTab(button.dataset.zbTab); updateSheetState(); });
    });
    overlay.addEventListener("change", function (event) {
      const select = event.target.closest("[data-zb-select-setting]");
      if (select) setSetting(select.dataset.zbSelectSetting, select.value);
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
      const retry = event.target.closest("[data-zb-access-retry]");
      if (retry) {
        subscriptionSummaryLoaded = false;
        loadSubscriptionSummary(true);
        return;
      }
      const statsRetry = event.target.closest("[data-zb-stats-retry]");
      if (statsRetry) {
        personalStatsLoaded = false;
        loadPersonalStats(true);
        return;
      }
      const purchasesRetry = event.target.closest("[data-zb-purchases-retry]");
      if (purchasesRetry) {
        purchaseHistoryLoaded = false;
        loadPurchaseHistory(true);
        return;
      }
      const walletOpen = event.target.closest("[data-zb-wallet-open]");
      if (walletOpen) {
        const panel = overlay.querySelector("[data-zb-wallet-topup]");
        const open = Boolean(panel && panel.hidden);
        if (panel) panel.hidden = !open;
        walletOpen.setAttribute("aria-expanded", open ? "true" : "false");
        if (open) {
          loadWalletBalance(false);
          window.setTimeout(function () {
            panel && panel.querySelector("button:not(:disabled), a[href]")?.focus();
          }, 30);
        }
        return;
      }
      const walletPreset = event.target.closest("[data-zb-wallet-test-amount]");
      if (walletPreset) {
        grantWalletTestCoins(walletPreset.dataset.zbWalletTestAmount);
        return;
      }
      const walletCustomSubmit = event.target.closest("[data-zb-wallet-custom-submit]");
      if (walletCustomSubmit) {
        const input = overlay.querySelector("[data-zb-wallet-custom]");
        grantWalletTestCoins(input && input.value);
        return;
      }
      const reset = event.target.closest("[data-zb-reset]");
      if (reset) {
        writeSettings(DEFAULTS);
        try { window.localStorage.removeItem(CONTROLS_KEY); } catch (error) {}
        document.body.classList.remove("reader-controls-hidden");
        applyCleanSettings();
        updateSheetState();
      }
    });
    overlay.querySelector("[data-zb-wallet-custom]")?.addEventListener("keydown", function (event) {
      if (event.key === "Enter") {
        event.preventDefault();
        grantWalletTestCoins(event.currentTarget.value);
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
    overlay.querySelectorAll("[data-zb-select-setting]").forEach(function (select) {
      if (Object.prototype.hasOwnProperty.call(settings, select.dataset.zbSelectSetting)) {
        select.value = String(settings[select.dataset.zbSelectSetting]);
      }
    });
    const accentPreview = overlay.querySelector("[data-zb-accent-preview]");
    if (accentPreview) accentPreview.style.setProperty("--zb-select-accent", settings.accentColor || DEFAULTS.accentColor);
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
    try { window.localStorage.removeItem(CONTROLS_KEY); } catch (error) {}
    document.body.classList.remove("reader-controls-hidden");
    [0, 150, 500, 1200].forEach(function (delay) {
      window.setTimeout(function () { applyCleanSettings(); ensureButtons(); cleanupOldUi(); updateSheetState(); }, delay);
    });
    try {
      const observer = new MutationObserver(function () { cleanupOldUi(); ensureButtons(); });
      observer.observe(document.body, { childList: true, subtree: true });
    } catch (error) {}
  }
  window.addEventListener("reader-wallet-updated", function (event) {
    const balance = Number(event.detail?.balance);
    if (Number.isFinite(balance) && balance >= 0) setWalletBalance(balance);
  });
  document.addEventListener("visibilitychange", function () {
    const overlay = document.querySelector("[data-zb-settings-overlay]");
    if (!document.hidden && overlay && !overlay.hidden && overlay.querySelector('[data-zb-pane="access"].is-active')) {
      loadWalletBalance(true);
    }
  });
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initCleanSettings);
  } else {
    initCleanSettings();
  }
})();
