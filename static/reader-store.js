(() => {
  const root = document.querySelector("[data-reader-store]");
  const modal = document.querySelector("[data-reader-transaction]");
  if (!root || !modal) return;

  const openButton = root.querySelector("[data-reader-transaction-open]");
  const offerLabel = root.querySelector("[data-reader-offer-label]");
  const offerPrice = root.querySelector("[data-reader-offer-price]");
  const rootMessage = root.querySelector("[data-reader-store-message]");
  const dialog = modal.querySelector(".reader-transaction-dialog");
  const title = modal.querySelector("#readerTransactionTitle");
  const closeButton = modal.querySelector("[data-reader-transaction-close]");
  const chooser = modal.querySelector("[data-reader-transaction-chooser]");
  const confirmation = modal.querySelector("[data-reader-transaction-confirm]");
  const topup = modal.querySelector("[data-reader-transaction-topup]");
  const productsContainer = modal.querySelector("[data-reader-transaction-products]");
  const balanceNodes = modal.querySelectorAll("[data-reader-coins-balance]");
  const balanceButton = modal.querySelector("[data-reader-topup-open]");
  const message = modal.querySelector("[data-reader-transaction-message]");
  const confirmType = modal.querySelector("[data-reader-confirm-type]");
  const confirmTitle = modal.querySelector("[data-reader-confirm-title]");
  const confirmPrice = modal.querySelector("[data-reader-confirm-price]");
  const confirmAfter = modal.querySelector("[data-reader-confirm-after]");
  const shortage = modal.querySelector("[data-reader-confirm-shortage]");
  const purchaseButton = modal.querySelector("[data-reader-confirm-purchase]");
  const insufficientButton = modal.querySelector("[data-reader-confirm-topup]");
  const confirmBack = modal.querySelector("[data-reader-confirm-back]");
  const topupBack = modal.querySelector("[data-reader-topup-back]");
  const testTopup = modal.querySelector("[data-reader-test-topup]");
  const topupMinNode = modal.querySelector("[data-reader-topup-min]");
  const topupCustom = modal.querySelector("[data-reader-topup-custom]");
  const topupSubmit = modal.querySelector("[data-reader-topup-submit]");
  const shopLink = modal.querySelector("[data-reader-topup-shop]");
  const topupUnavailable = modal.querySelector("[data-reader-topup-unavailable]");

  const state = {
    balance: 0,
    products: [],
    selected: null,
    purchasesEnabled: false,
    testTopupEnabled: false,
    topupMin: 10,
    topupMax: 1000,
    topupUrl: "",
    previousFocus: null,
    busy: false,
  };

  function number(value) {
    return new Intl.NumberFormat("ru-RU").format(Number(value || 0));
  }

  function safeTopupUrl(value) {
    try {
      const url = new URL(String(value || ""), window.location.origin);
      return ["https:", "http:", "tg:"].includes(url.protocol) ? url.href : "";
    } catch (_error) {
      return "";
    }
  }

  function actionId(storageKey) {
    const existing = window.sessionStorage.getItem(storageKey);
    if (existing) return existing;
    const created = window.crypto?.randomUUID?.()
      || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    window.sessionStorage.setItem(storageKey, created);
    return created;
  }

  function clearAction(storageKey) {
    window.sessionStorage.removeItem(storageKey);
  }

  async function requestJson(url, options = {}) {
    const response = await window.fetch(url, {
      credentials: "same-origin",
      ...options,
      headers: {
        Accept: "application/json",
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...(options.headers || {}),
      },
    });
    let payload = {};
    try {
      payload = await response.json();
    } catch (_error) {
      payload = {};
    }
    if (!response.ok) {
      const error = new Error(String(payload.detail || `HTTP ${response.status}`));
      error.status = response.status;
      error.detail = String(payload.detail || "");
      throw error;
    }
    return payload;
  }

  function humanError(error) {
    const detail = String(error?.detail || error?.message || "");
    const known = {
      insufficient_reader_coins: "На балансе недостаточно Монеток.",
      store_product_already_owned: "Этот доступ уже куплен. Обновляем страницу…",
      store_product_not_found: "Предложение больше недоступно. Обновите страницу.",
      test_coin_topup_disabled: "Тестовое пополнение сейчас выключено.",
      test_purchases_disabled: "Покупки сейчас временно выключены.",
      store_temporarily_unavailable: "Магазин временно недоступен. Попробуйте ещё раз.",
      wallet_temporarily_unavailable: "Не удалось загрузить баланс. Попробуйте ещё раз.",
    };
    return known[detail] || "Не удалось выполнить операцию. Попробуйте ещё раз.";
  }

  function showRootMessage(text, tone = "error") {
    if (!rootMessage) return;
    rootMessage.textContent = text;
    rootMessage.dataset.tone = tone;
    rootMessage.hidden = !text;
  }

  function showMessage(text, tone = "error") {
    if (!message) return;
    message.textContent = text;
    message.dataset.tone = tone;
    message.hidden = !text;
  }

  function renderBalance() {
    balanceNodes.forEach((node) => { node.textContent = number(state.balance); });
  }

  function showView(view) {
    chooser.hidden = view !== "chooser";
    confirmation.hidden = view !== "confirm";
    topup.hidden = view !== "topup";
    showMessage("");
    if (view === "chooser") title.textContent = "Выберите доступ";
    if (view === "confirm") title.textContent = "Подтверждение покупки";
    if (view === "topup") title.textContent = "Пополнение баланса";
  }

  function productKind(product) {
    return product.product_type === "chapter_unlock" ? "Глава" : "Вся новелла";
  }

  function productAction(product) {
    return product.product_type === "chapter_unlock" ? "Купить эту главу" : "Купить всю новеллу";
  }

  function relevantProducts(items) {
    return (Array.isArray(items) ? items : [])
      .filter((item) => item.product_type === "chapter_unlock" || item.product_type === "novel_unlock")
      .sort((left, right) => {
        const order = { chapter_unlock: 0, novel_unlock: 1 };
        return (order[left.product_type] ?? 9) - (order[right.product_type] ?? 9);
      });
  }

  function renderProducts() {
    productsContainer.replaceChildren();
    state.products.forEach((product) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "reader-transaction-product";

      const copy = document.createElement("span");
      copy.className = "reader-transaction-product-copy";
      const kind = document.createElement("small");
      kind.textContent = productKind(product);
      const action = document.createElement("strong");
      action.textContent = productAction(product);
      const description = document.createElement("span");
      description.textContent = product.product_type === "chapter_unlock"
        ? "Доступ к главе без срока"
        : "Все текущие и будущие главы без срока";
      copy.append(kind, action, description);

      const price = document.createElement("b");
      price.textContent = `${number(product.coin_price)} 🪙`;
      button.append(copy, price);
      button.addEventListener("click", () => showConfirmation(product));
      productsContainer.append(button);
    });
  }

  function showConfirmation(product) {
    state.selected = product;
    confirmType.textContent = productKind(product);
    confirmTitle.textContent = product.title || productAction(product);
    confirmPrice.textContent = number(product.coin_price);
    const enough = state.balance >= Number(product.coin_price || 0);
    confirmAfter.textContent = enough ? number(state.balance - Number(product.coin_price || 0)) : "—";
    shortage.hidden = enough;
    shortage.textContent = enough
      ? ""
      : `Не хватает ${number(Number(product.coin_price || 0) - state.balance)} Монеток.`;
    purchaseButton.hidden = !enough;
    purchaseButton.disabled = !state.purchasesEnabled || state.busy;
    purchaseButton.textContent = state.purchasesEnabled
      ? `Подтвердить · ${number(product.coin_price)} 🪙`
      : "Покупки временно выключены";
    insufficientButton.hidden = enough;
    showView("confirm");
    (enough ? purchaseButton : insufficientButton).focus();
  }

  function showChooser() {
    showView("chooser");
    productsContainer.querySelector("button")?.focus();
  }

  function showTopup() {
    showView("topup");
    testTopup.hidden = !state.testTopupEnabled;
    topupMinNode.textContent = number(state.topupMin);
    topupCustom.min = String(state.topupMin);
    topupCustom.max = String(state.topupMax);
    if (shopLink && state.topupUrl) {
      shopLink.href = state.topupUrl;
      shopLink.hidden = false;
    } else if (shopLink) {
      shopLink.hidden = true;
    }
    topupUnavailable.hidden = state.testTopupEnabled || Boolean(state.topupUrl);
    const firstPreset = state.testTopupEnabled
      ? testTopup.querySelector("[data-reader-topup-amount]:not(:disabled)")
      : null;
    const shopTarget = shopLink && !shopLink.hidden ? shopLink : null;
    (firstPreset || shopTarget || topupBack)?.focus();
  }

  function openModal() {
    state.previousFocus = document.activeElement;
    renderBalance();
    renderProducts();
    showView("chooser");
    modal.hidden = false;
    document.body.classList.add("reader-transaction-open");
    window.requestAnimationFrame(() => dialog.focus());
  }

  function closeModal() {
    if (state.busy) return;
    modal.hidden = true;
    document.body.classList.remove("reader-transaction-open");
    state.previousFocus?.focus?.();
  }

  function setBusy(busy) {
    state.busy = busy;
    purchaseButton.disabled = busy || !state.purchasesEnabled;
    topupSubmit.disabled = busy;
    modal.querySelectorAll("[data-reader-topup-amount]").forEach((button) => {
      button.disabled = busy || Number(button.dataset.readerTopupAmount || 0) > state.topupMax;
    });
  }

  async function purchaseSelected() {
    const product = state.selected;
    if (!product || state.busy || !state.purchasesEnabled) return;
    if (state.balance < Number(product.coin_price || 0)) {
      showTopup();
      return;
    }
    const storageKey = `reader-purchase:${product.product_code}`;
    setBusy(true);
    showMessage("Проводим покупку…", "info");
    try {
      const result = await requestJson("/api/store/purchase", {
        method: "POST",
        body: JSON.stringify({
          product_code: product.product_code,
          client_action_id: actionId(storageKey),
        }),
      });
      clearAction(storageKey);
      state.balance = Number(result.balance || 0);
      renderBalance();
      showMessage("Готово! Открываем купленный доступ…", "success");
      window.setTimeout(() => window.location.reload(), 650);
    } catch (error) {
      if (String(error.detail || "") === "insufficient_reader_coins") {
        showTopup();
        showMessage(humanError(error), "error");
      } else if (String(error.detail || "") === "store_product_already_owned") {
        showMessage(humanError(error), "success");
        window.setTimeout(() => window.location.reload(), 650);
      } else {
        showMessage(humanError(error), "error");
      }
    } finally {
      setBusy(false);
    }
  }

  async function grantTestCoins(amount) {
    const value = Number(amount || 0);
    if (!Number.isInteger(value) || value < state.topupMin || value > state.topupMax) {
      showMessage(`Введите сумму от ${number(state.topupMin)} до ${number(state.topupMax)} Монеток.`, "error");
      return;
    }
    const storageKey = `reader-test-topup:${value}`;
    setBusy(true);
    showMessage("Начисляем тестовые Монетки…", "info");
    try {
      const result = await requestJson("/api/store/test-coins", {
        method: "POST",
        body: JSON.stringify({ amount: value, client_action_id: actionId(storageKey) }),
      });
      clearAction(storageKey);
      state.balance = Number(result.balance || 0);
      renderBalance();
      if (state.selected) {
        showConfirmation(state.selected);
      } else {
        showChooser();
      }
      showMessage(`Баланс пополнен на ${number(result.credited || value)} Монеток.`, "success");
    } catch (error) {
      showMessage(humanError(error), "error");
    } finally {
      setBusy(false);
    }
  }

  function bindEvents() {
    openButton.addEventListener("click", openModal);
    closeButton.addEventListener("click", closeModal);
    modal.addEventListener("click", (event) => {
      if (event.target === modal) closeModal();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !modal.hidden) closeModal();
    });
    balanceButton.addEventListener("click", showTopup);
    confirmBack.addEventListener("click", showChooser);
    topupBack.addEventListener("click", () => {
      if (state.selected) showConfirmation(state.selected);
      else showChooser();
    });
    purchaseButton.addEventListener("click", purchaseSelected);
    insufficientButton.addEventListener("click", showTopup);
    modal.querySelectorAll("[data-reader-topup-amount]").forEach((button) => {
      button.addEventListener("click", () => grantTestCoins(button.dataset.readerTopupAmount));
    });
    topupSubmit.addEventListener("click", () => grantTestCoins(topupCustom.value));
    topupCustom.addEventListener("keydown", (event) => {
      if (event.key === "Enter") grantTestCoins(topupCustom.value);
    });
  }

  async function initialize() {
    bindEvents();
    const novelId = root.dataset.novelId || "";
    const chapterId = root.dataset.chapterId || "";
    const query = new URLSearchParams({ novel_id: novelId, chapter_id: chapterId });
    try {
      const [catalog, wallet] = await Promise.all([
        requestJson(`/api/store/products?${query.toString()}`),
        requestJson("/api/store/wallet"),
      ]);
      state.balance = Number(wallet.balance || 0);
      state.products = relevantProducts(catalog.items);
      state.purchasesEnabled = Boolean(catalog.purchases_enabled);
      state.testTopupEnabled = Boolean(catalog.test_topup_enabled);
      state.topupMin = Math.max(10, Number(catalog.test_topup_min || 10));
      state.topupMax = Math.max(state.topupMin, Number(catalog.test_topup_max || 1000));
      state.topupUrl = safeTopupUrl(catalog.topup_url);
      renderBalance();
      modal.querySelectorAll("[data-reader-topup-amount]").forEach((button) => {
        button.disabled = Number(button.dataset.readerTopupAmount || 0) > state.topupMax;
      });

      const chapterProduct = state.products.find((item) => item.product_type === "chapter_unlock");
      const primaryProduct = chapterProduct || state.products[0];
      if (!primaryProduct) return;
      offerLabel.textContent = chapterProduct ? "Купить главу" : "Купить всю новеллу";
      offerPrice.textContent = number(primaryProduct.coin_price);
      root.hidden = false;
    } catch (error) {
      root.hidden = false;
      openButton.disabled = true;
      offerLabel.textContent = "Покупка временно недоступна";
      offerPrice.textContent = "—";
      showRootMessage(humanError(error), "error");
    }
  }

  initialize();
})();
