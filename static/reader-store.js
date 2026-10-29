(function () {
  "use strict";

  const roots = Array.from(document.querySelectorAll("[data-reader-store]"));
  const balanceNodes = Array.from(document.querySelectorAll("[data-reader-coins-balance]"));
  if (!roots.length && !balanceNodes.length) return;

  function actionId() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") return window.crypto.randomUUID();
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (char) {
      const value = Math.random() * 16 | 0;
      return (char === "x" ? value : (value & 3 | 8)).toString(16);
    });
  }

  function pendingActionId(key) {
    try {
      const existing = window.sessionStorage.getItem(key);
      if (existing) return existing;
      const created = actionId();
      window.sessionStorage.setItem(key, created);
      return created;
    } catch (_) {
      return actionId();
    }
  }

  function clearPendingAction(key) {
    try { window.sessionStorage.removeItem(key); } catch (_) {}
  }

  function requestMayHaveCommitted(error) {
    return !error || !error.status || Number(error.status) >= 500;
  }

  async function api(url, options) {
    const response = await fetch(url, Object.assign({ credentials: "same-origin" }, options || {}));
    let data = {};
    try { data = await response.json(); } catch (_) {}
    if (!response.ok) {
      const error = new Error(String(data.detail || "store_request_failed"));
      error.status = response.status;
      throw error;
    }
    return data;
  }

  function formatCoins(value) {
    return Number(value || 0).toLocaleString("ru-RU");
  }

  function setBalance(value) {
    balanceNodes.forEach(function (node) { node.textContent = formatCoins(value); });
  }

  function message(root, text, tone) {
    const node = root.querySelector("[data-reader-store-message]");
    if (!node) return;
    node.textContent = text || "";
    node.dataset.tone = tone || "info";
    node.hidden = !text;
  }

  function humanError(error) {
    const code = String(error && error.message || "");
    if (code.includes("insufficient_reader_coins")) return "Недостаточно Монеток на балансе.";
    if (code.includes("store_product_already_owned")) return "Этот доступ уже куплен.";
    if (code.includes("test_purchases_disabled")) return "Тестовые покупки сейчас отключены.";
    if (code.includes("test_coin_topup_disabled")) return "Бесплатное тестовое пополнение отключено.";
    if (code.includes("amount_must_be_between")) return "Введите допустимую сумму Монеток.";
    return "Не удалось выполнить операцию. Попробуйте ещё раз.";
  }

  function typeLabel(product) {
    if (product.product_type === "chapter_unlock") return "Глава";
    if (product.product_type === "novel_unlock") return "Вся книга";
    if (product.product_type === "subscription_upgrade") return "Повышение подписки";
    return "Подписка";
  }

  function renderProducts(root, data) {
    const list = root.querySelector("[data-reader-store-products]");
    if (!list) return;
    list.replaceChildren();
    let products = Array.isArray(data.items) ? data.items : [];
    if (root.dataset.storeScope === "subscriptions") {
      products = products.filter(function (product) {
        return product.product_type === "subscription" || product.product_type === "subscription_upgrade";
      });
    }
    products.forEach(function (product) {
      const card = document.createElement("article");
      card.className = "reader-store-product";
      const copy = document.createElement("div");
      const kind = document.createElement("span");
      kind.className = "reader-store-product-type";
      kind.textContent = typeLabel(product);
      const title = document.createElement("strong");
      title.textContent = product.title;
      const details = document.createElement("small");
      details.textContent = product.duration_days ? product.duration_days + " дн." : "Доступ без срока";
      copy.append(kind, title, details);

      const button = document.createElement("button");
      button.type = "button";
      button.className = "reader-store-buy";
      button.textContent = formatCoins(product.coin_price) + " 🪙";
      button.disabled = !data.purchases_enabled;
      button.addEventListener("click", async function () {
        if (!window.confirm("Купить «" + product.title + "» за " + formatCoins(product.coin_price) + " Монеток?")) return;
        const pendingKey = "reader-store:purchase:" + product.product_code;
        const clientActionId = pendingActionId(pendingKey);
        button.disabled = true;
        message(root, "Проверяем баланс…", "info");
        try {
          const result = await api("/api/store/purchase", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ product_code: product.product_code, client_action_id: clientActionId })
          });
          clearPendingAction(pendingKey);
          setBalance(result.balance);
          message(root, "Покупка выполнена. Доступ открыт.", "success");
          window.setTimeout(function () { window.location.reload(); }, 650);
        } catch (error) {
          if (!requestMayHaveCommitted(error)) clearPendingAction(pendingKey);
          message(root, humanError(error), "error");
          button.disabled = !data.purchases_enabled;
        }
      });
      card.append(copy, button);
      list.appendChild(card);
    });
    const empty = root.querySelector("[data-reader-store-empty]");
    if (empty) empty.hidden = products.length > 0;
  }

  function bindTopup(root, data) {
    const topup = root.querySelector("[data-reader-test-topup]");
    if (!topup) return;
    topup.hidden = !data.test_topup_enabled;
    if (!data.test_topup_enabled) return;
    const input = topup.querySelector("[data-reader-topup-custom]");
    if (input) {
      input.min = String(data.test_topup_min || 10);
      input.max = String(data.test_topup_max || 100000);
    }
    topup.addEventListener("click", async function (event) {
      const button = event.target.closest("[data-reader-topup-amount], [data-reader-topup-submit]");
      if (!button) return;
      const amount = button.hasAttribute("data-reader-topup-amount")
        ? Number(button.dataset.readerTopupAmount)
        : Number(input && input.value);
      if (!Number.isInteger(amount) || amount < Number(data.test_topup_min || 10) || amount > Number(data.test_topup_max || 100000)) {
        message(root, "Минимум 10 Монеток; проверьте введённую сумму.", "error");
        return;
      }
      const pendingKey = "reader-store:test-topup:" + amount;
      const clientActionId = pendingActionId(pendingKey);
      button.disabled = true;
      try {
        const result = await api("/api/store/test-coins", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ amount: amount, client_action_id: clientActionId })
        });
        clearPendingAction(pendingKey);
        setBalance(result.balance);
        message(root, "Тестовый баланс пополнен на " + formatCoins(result.credited) + " Монеток.", "success");
      } catch (error) {
        if (!requestMayHaveCommitted(error)) clearPendingAction(pendingKey);
        message(root, humanError(error), "error");
      } finally {
        button.disabled = false;
      }
    });
  }

  async function initRoot(root) {
    const params = new URLSearchParams();
    if (root.dataset.novelId) params.set("novel_id", root.dataset.novelId);
    if (root.dataset.chapterId) params.set("chapter_id", root.dataset.chapterId);
    try {
      const data = await api("/api/store/products" + (params.size ? "?" + params.toString() : ""));
      root.hidden = false;
      renderProducts(root, data);
      bindTopup(root, data);
    } catch (_) {
      root.hidden = true;
    }
  }

  api("/api/store/wallet")
    .then(function (wallet) { setBalance(wallet.balance); })
    .catch(function () { balanceNodes.forEach(function (node) { node.textContent = "—"; }); });
  roots.forEach(initRoot);
})();
