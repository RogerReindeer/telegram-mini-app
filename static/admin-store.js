(function () {
  "use strict";

  const root = document.querySelector("[data-admin-store]");
  if (!root) return;

  const form = root.querySelector("[data-admin-store-form]");
  const rows = root.querySelector("[data-admin-store-rows]");
  const status = root.querySelector("[data-admin-store-status]");
  const bulkForm = root.querySelector("[data-admin-bulk-pricing-form]");
  const bulkStatus = root.querySelector("[data-admin-bulk-pricing-status]");
  const chapterForm = root.querySelector("[data-admin-chapter-pricing-form]");
  const chapterStatus = root.querySelector("[data-admin-chapter-pricing-status]");
  const novelList = root.querySelector("[data-admin-novel-list]");
  const chapterList = root.querySelector("[data-admin-chapter-list]");
  const novelSearch = root.querySelector("[data-admin-novel-search]");
  const chapterSearch = root.querySelector("[data-admin-chapter-search]");
  const novelCount = root.querySelector("[data-admin-novel-selected-count]");
  const chapterCount = root.querySelector("[data-admin-chapter-selected-count]");

  const state = {
    novels: [],
    chapters: [],
    selectedNovels: new Set(),
    selectedChapters: new Set(),
    lastNovelIndex: null,
    lastChapterIndex: null
  };

  function errorMessage(detail) {
    if (Array.isArray(detail)) {
      return detail.map(function (item) { return item && item.msg ? item.msg : String(item); }).join("; ");
    }
    return String(detail || "request_failed");
  }

  async function api(url, options) {
    const response = await fetch(url, Object.assign({ credentials: "same-origin" }, options || {}));
    let data = {};
    try { data = await response.json(); } catch (_) {}
    if (!response.ok) throw new Error(errorMessage(data.detail));
    return data;
  }

  function value(name) {
    return String(form.elements[name] && form.elements[name].value || "").trim();
  }

  function bulkValue(name) {
    return String(bulkForm.elements[name] && bulkForm.elements[name].value || "").trim();
  }

  function nullableInt(name) {
    const text = value(name);
    return text ? Number(text) : null;
  }

  function setMessage(node, text, error) {
    if (!node) return;
    node.textContent = text || "";
    node.dataset.tone = error ? "error" : "success";
  }

  function show(text, error) { setMessage(status, text, error); }
  function showBulk(text, error) { setMessage(bulkStatus, text, error); }
  function showChapter(text, error) { setMessage(chapterStatus, text, error); }

  function cell(text) {
    const td = document.createElement("td");
    td.textContent = text == null || text === "" ? "—" : String(text);
    return td;
  }

  function renderProducts(items) {
    rows.replaceChildren();
    (items || []).forEach(function (item) {
      const tr = document.createElement("tr");
      tr.append(
        cell(item.product_code), cell(item.product_type), cell(item.title),
        cell(item.coin_price + " 🪙"), cell(item.novel_id), cell(item.chapter_id),
        cell(item.subscription_role), cell(item.duration_days), cell(item.is_active ? "да" : "нет")
      );
      tr.addEventListener("click", function () {
        Object.keys(item).forEach(function (key) {
          const control = form.elements[key];
          if (!control) return;
          if (control.type === "checkbox") control.checked = Boolean(item[key]);
          else control.value = item[key] == null ? "" : item[key];
        });
        const advanced = root.querySelector(".admin-advanced-pricing");
        if (advanced) advanced.open = true;
      });
      rows.appendChild(tr);
    });
    if (!items || !items.length) {
      const tr = document.createElement("tr");
      const td = cell("Товары ещё не настроены.");
      td.colSpan = 9;
      tr.appendChild(td);
      rows.appendChild(tr);
    }
  }

  function normalizedSearch(input) {
    return String(input && input.value || "").trim().toLocaleLowerCase("ru");
  }

  function filteredNovels() {
    const query = normalizedSearch(novelSearch);
    if (!query) return state.novels;
    return state.novels.filter(function (novel) {
      return [novel.title, novel.code, novel.novel_id].some(function (part) {
        return String(part == null ? "" : part).toLocaleLowerCase("ru").includes(query);
      });
    });
  }

  function selectedNovelChapters() {
    const query = normalizedSearch(chapterSearch);
    const novelTitles = new Map(state.novels.map(function (novel) {
      return [Number(novel.novel_id), novel.title];
    }));
    return state.chapters.filter(function (chapter) {
      if (!state.selectedNovels.has(Number(chapter.novel_id))) return false;
      if (!query) return true;
      return [chapter.title, chapter.chapter_id, novelTitles.get(Number(chapter.novel_id))].some(function (part) {
        return String(part == null ? "" : part).toLocaleLowerCase("ru").includes(query);
      });
    });
  }

  function checkboxCard(kind, id, checked, title, details, priceText, tone) {
    const label = document.createElement("label");
    label.className = "admin-pricing-option";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.checked = checked;
    input.dataset.pricingKind = kind;
    input.dataset.pricingId = String(id);
    const copy = document.createElement("span");
    copy.className = "admin-pricing-option-copy";
    const strong = document.createElement("strong");
    strong.textContent = title;
    const small = document.createElement("small");
    small.textContent = details;
    copy.append(strong, small);
    const price = document.createElement("span");
    price.className = "admin-pricing-price";
    if (tone) price.dataset.tone = tone;
    price.textContent = priceText;
    label.append(input, copy, price);
    return label;
  }

  function updateCounts() {
    novelCount.textContent = "Выбрано новелл: " + state.selectedNovels.size;
    chapterCount.textContent = "Выбрано глав: " + state.selectedChapters.size;
  }

  function renderNovels() {
    const novels = filteredNovels();
    novelList.replaceChildren();
    novels.forEach(function (novel) {
      const hasPrice = novel.has_pricing_rule;
      const priceText = hasPrice
        ? "глава " + novel.chapter_coin_price + " 🪙 · книга " + novel.bundle_coin_price + " 🪙"
        : "цена не задана";
      const details = "ID " + novel.novel_id + " · глав: " + novel.chapter_count
        + (novel.is_visible ? "" : " · скрыта в каталоге");
      novelList.appendChild(checkboxCard(
        "novel", novel.novel_id, state.selectedNovels.has(Number(novel.novel_id)),
        novel.title, details, priceText, hasPrice ? "default" : "empty"
      ));
    });
    if (!novels.length) {
      const empty = document.createElement("p");
      empty.className = "admin-muted";
      empty.textContent = "Новеллы по этому запросу не найдены.";
      novelList.appendChild(empty);
    }
    state.lastNovelIndex = null;
    updateCounts();
  }

  function renderChapters() {
    const chapters = selectedNovelChapters();
    const novelTitles = new Map(state.novels.map(function (novel) {
      return [Number(novel.novel_id), novel.title];
    }));
    chapterList.replaceChildren();
    chapters.forEach(function (chapter) {
      let priceText = "цена не задана";
      let tone = "empty";
      if (chapter.has_override) {
        priceText = chapter.override_coin_price + " 🪙 · отдельная";
        tone = "override";
      } else if (chapter.effective_coin_price != null) {
        priceText = chapter.effective_coin_price + " 🪙 · общая";
        tone = "default";
      }
      const details = (novelTitles.get(Number(chapter.novel_id)) || "Новелла " + chapter.novel_id)
        + " · ID " + chapter.chapter_id;
      chapterList.appendChild(checkboxCard(
        "chapter", chapter.chapter_id, state.selectedChapters.has(String(chapter.chapter_id)),
        chapter.title, details, priceText, tone
      ));
    });
    if (!state.selectedNovels.size) {
      const empty = document.createElement("p");
      empty.className = "admin-muted";
      empty.textContent = "Выберите хотя бы одну новеллу.";
      chapterList.appendChild(empty);
    } else if (!chapters.length) {
      const empty = document.createElement("p");
      empty.className = "admin-muted";
      empty.textContent = "В выбранных новеллах нет глав по этому запросу.";
      chapterList.appendChild(empty);
    }
    state.lastChapterIndex = null;
    updateCounts();
  }

  function applyCheckboxSelection(input, set, converter) {
    const id = converter(input.dataset.pricingId);
    if (input.checked) set.add(id);
    else set.delete(id);
  }

  function handleShiftClick(event, kind) {
    const input = event.target.closest('input[data-pricing-kind="' + kind + '"]');
    if (!input) return;
    const container = kind === "novel" ? novelList : chapterList;
    const inputs = Array.from(container.querySelectorAll('input[data-pricing-kind="' + kind + '"]'));
    const currentIndex = inputs.indexOf(input);
    const lastKey = kind === "novel" ? "lastNovelIndex" : "lastChapterIndex";
    const set = kind === "novel" ? state.selectedNovels : state.selectedChapters;
    const converter = kind === "novel" ? Number : String;
    if (event.shiftKey && state[lastKey] != null && currentIndex >= 0) {
      const start = Math.min(state[lastKey], currentIndex);
      const end = Math.max(state[lastKey], currentIndex);
      for (let index = start; index <= end; index += 1) {
        inputs[index].checked = input.checked;
        applyCheckboxSelection(inputs[index], set, converter);
      }
    } else {
      applyCheckboxSelection(input, set, converter);
    }
    state[lastKey] = currentIndex;
    if (kind === "novel") {
      state.chapters.forEach(function (chapter) {
        if (!state.selectedNovels.has(Number(chapter.novel_id))) {
          state.selectedChapters.delete(String(chapter.chapter_id));
        }
      });
      renderChapters();
    } else {
      updateCounts();
    }
  }

  async function loadProducts() {
    try {
      const data = await api("/api/admin/store/products");
      renderProducts(data.items);
    } catch (error) {
      show("Не удалось загрузить товары: " + error.message, true);
    }
  }

  async function loadPricingCatalog() {
    try {
      const data = await api("/api/admin/store/pricing-catalog");
      state.novels = Array.isArray(data.novels) ? data.novels : [];
      state.chapters = Array.isArray(data.chapters) ? data.chapters : [];
      const validNovels = new Set(state.novels.map(function (novel) { return Number(novel.novel_id); }));
      const validChapters = new Set(state.chapters.map(function (chapter) { return String(chapter.chapter_id); }));
      state.selectedNovels.forEach(function (id) { if (!validNovels.has(id)) state.selectedNovels.delete(id); });
      state.selectedChapters.forEach(function (id) { if (!validChapters.has(id)) state.selectedChapters.delete(id); });
      renderNovels();
      renderChapters();
    } catch (error) {
      novelList.replaceChildren();
      chapterList.replaceChildren();
      showBulk("Не удалось загрузить новеллы и главы: " + error.message, true);
    }
  }

  async function load() {
    await Promise.all([loadProducts(), loadPricingCatalog()]);
  }

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    const code = value("product_code");
    const payload = {
      product_type: value("product_type"),
      title: value("title"),
      coin_price: Number(value("coin_price")),
      novel_id: nullableInt("novel_id"),
      chapter_id: value("chapter_id") || null,
      subscription_role: value("subscription_role") || null,
      duration_days: nullableInt("duration_days"),
      upgrade_from_role: value("upgrade_from_role") || null,
      is_active: Boolean(form.elements.is_active.checked),
      sort_order: Number(value("sort_order") || 0)
    };
    try {
      await api("/api/admin/store/products/" + encodeURIComponent(code), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      show("Товар сохранён. Цена в Монетках равна цене в рублях.", false);
      await Promise.all([loadProducts(), loadPricingCatalog()]);
    } catch (error) {
      show("Не удалось сохранить: " + error.message, true);
    }
  });

  novelSearch.addEventListener("input", renderNovels);
  chapterSearch.addEventListener("input", renderChapters);
  novelList.addEventListener("click", function (event) { handleShiftClick(event, "novel"); });
  chapterList.addEventListener("click", function (event) { handleShiftClick(event, "chapter"); });

  root.querySelector("[data-admin-novel-select-visible]").addEventListener("click", function () {
    filteredNovels().forEach(function (novel) { state.selectedNovels.add(Number(novel.novel_id)); });
    renderNovels();
    renderChapters();
  });
  root.querySelector("[data-admin-novel-clear]").addEventListener("click", function () {
    state.selectedNovels.clear();
    state.selectedChapters.clear();
    renderNovels();
    renderChapters();
  });
  root.querySelector("[data-admin-chapter-select-visible]").addEventListener("click", function () {
    selectedNovelChapters().forEach(function (chapter) { state.selectedChapters.add(String(chapter.chapter_id)); });
    renderChapters();
  });
  root.querySelector("[data-admin-chapter-clear]").addEventListener("click", function () {
    state.selectedChapters.clear();
    renderChapters();
  });

  bulkForm.addEventListener("submit", async function (event) {
    event.preventDefault();
    const novelIds = Array.from(state.selectedNovels).sort(function (a, b) { return a - b; });
    if (!novelIds.length) {
      showBulk("Сначала отметьте хотя бы одну новеллу.", true);
      return;
    }
    if (novelIds.length > 100) {
      showBulk("За один раз можно настроить не больше 100 новелл.", true);
      return;
    }
    const chapterPrice = Number(bulkValue("chapter_coin_price"));
    const bundlePrice = Number(bulkValue("bundle_coin_price"));
    const confirmation = "Применить к " + novelIds.length + " новелл. цену каждой главы "
      + chapterPrice + " 🪙 и всей книги " + bundlePrice + " 🪙? Индивидуальные цены глав сохранятся.";
    if (!window.confirm(confirmation)) return;
    const submit = bulkForm.querySelector('button[type="submit"]');
    submit.disabled = true;
    showBulk("Применяем цены ко всем главам…", false);
    try {
      const result = await api("/api/admin/store/bulk-pricing", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          novel_ids: novelIds.join(","),
          chapter_coin_price: chapterPrice,
          bundle_coin_price: bundlePrice
        })
      });
      showBulk(
        "Готово: новелл — " + result.novels_updated
          + ", глав — " + result.chapters_priced
          + ", книжных бандлов — " + result.bundles_priced + ".",
        false
      );
      await Promise.all([loadProducts(), loadPricingCatalog()]);
    } catch (error) {
      showBulk("Не удалось выставить цены: " + error.message, true);
    } finally {
      submit.disabled = false;
    }
  });

  async function saveSelectedChapterPrices(resetToDefault) {
    const chapterIds = Array.from(state.selectedChapters);
    if (!chapterIds.length) {
      showChapter("Сначала отметьте хотя бы одну главу.", true);
      return;
    }
    if (chapterIds.length > 500) {
      showChapter("За один раз можно изменить не больше 500 глав.", true);
      return;
    }
    const price = Number(chapterForm.elements.coin_price.value);
    const actionText = resetToDefault
      ? "Вернуть общую цену у " + chapterIds.length + " выбранных глав?"
      : "Установить цену " + price + " 🪙 для " + chapterIds.length + " выбранных глав?";
    if (!window.confirm(actionText)) return;
    const buttons = chapterForm.querySelectorAll("button");
    buttons.forEach(function (button) { button.disabled = true; });
    showChapter(resetToDefault ? "Возвращаем общие цены…" : "Сохраняем отдельные цены…", false);
    try {
      const result = await api("/api/admin/store/chapter-pricing", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          chapter_ids: chapterIds,
          coin_price: resetToDefault ? null : price,
          reset_to_default: resetToDefault
        })
      });
      showChapter(
        (resetToDefault ? "Общая цена восстановлена" : "Отдельная цена установлена")
          + ": глав — " + result.chapters_priced + ".",
        false
      );
      await Promise.all([loadProducts(), loadPricingCatalog()]);
    } catch (error) {
      showChapter("Не удалось изменить цены: " + error.message, true);
    } finally {
      buttons.forEach(function (button) { button.disabled = false; });
    }
  }

  chapterForm.addEventListener("submit", function (event) {
    event.preventDefault();
    saveSelectedChapterPrices(false);
  });
  root.querySelector("[data-admin-chapter-reset]").addEventListener("click", function () {
    saveSelectedChapterPrices(true);
  });

  root.querySelector("[data-admin-store-rollback]").addEventListener("click", async function () {
    const userInput = window.prompt("Telegram user ID для точечного отката. Оставьте пустым, чтобы откатить ВСЕ тестовые покупки.", "");
    if (userInput === null) return;
    const userId = String(userInput || "").trim();
    const scope = userId ? "покупки пользователя " + userId : "ВСЕ тестовые покупки";
    if (!window.confirm("Откатить " + scope + "? Доступы будут отозваны, Монетки возвращены.")) return;
    try {
      const result = await api("/api/admin/store/rollback-test-purchases", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          confirmation: "ROLLBACK_TEST_PURCHASES",
          telegram_user_id: userId ? Number(userId) : null
        })
      });
      show("Откат завершён: покупок — " + result.reversed_purchases + ", возвращено — " + result.refunded_coins + " 🪙.", false);
    } catch (error) {
      show("Откат не выполнен: " + error.message, true);
    }
  });

  root.querySelector("[data-admin-store-finish-test]").addEventListener("click", async function () {
    const confirmation = window.prompt(
      "Это отключит бесплатный тест, обнулит ВСЕ тестовые балансы и отзовёт ВСЕ тестовые доступы. Для подтверждения введите: ЗАВЕРШИТЬ ТЕСТ",
      ""
    );
    if (confirmation === null) return;
    if (String(confirmation).trim() !== "ЗАВЕРШИТЬ ТЕСТ") {
      show("Завершение теста отменено: контрольная фраза не совпала.", true);
      return;
    }
    if (!window.confirm("Последнее подтверждение: завершить тест Reader Coins для всех пользователей?")) return;
    const button = root.querySelector("[data-admin-store-finish-test]");
    button.disabled = true;
    try {
      const result = await api("/api/admin/store/finish-test-commerce", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirmation: "FINISH_READER_COMMERCE_TEST" })
      });
      show(
        "Тест завершён: кошельков — " + result.reset_wallets
          + ", списано тестовых Монеток — " + result.cleared_coins
          + ", покупок отозвано — " + result.reversed_purchases
          + ", доступов отозвано — " + result.revoked_entitlements + ".",
        false
      );
    } catch (error) {
      show("Завершение теста не выполнено: " + error.message, true);
    } finally {
      button.disabled = false;
    }
  });

  load();
})();
