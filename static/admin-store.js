(function () {
  "use strict";
  const root = document.querySelector("[data-admin-store]");
  if (!root) return;
  const form = root.querySelector("[data-admin-store-form]");
  const rows = root.querySelector("[data-admin-store-rows]");
  const status = root.querySelector("[data-admin-store-status]");

  async function api(url, options) {
    const response = await fetch(url, Object.assign({ credentials: "same-origin" }, options || {}));
    let data = {};
    try { data = await response.json(); } catch (_) {}
    if (!response.ok) throw new Error(String(data.detail || "request_failed"));
    return data;
  }

  function value(name) {
    return String(form.elements[name] && form.elements[name].value || "").trim();
  }

  function nullableInt(name) {
    const text = value(name);
    return text ? Number(text) : null;
  }

  function show(text, error) {
    status.textContent = text || "";
    status.dataset.tone = error ? "error" : "success";
  }

  function cell(text) {
    const td = document.createElement("td");
    td.textContent = text == null || text === "" ? "—" : String(text);
    return td;
  }

  function render(items) {
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

  async function load() {
    try {
      const data = await api("/api/admin/store/products");
      render(data.items);
    } catch (error) {
      show("Не удалось загрузить товары: " + error.message, true);
    }
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
      await load();
    } catch (error) {
      show("Не удалось сохранить: " + error.message, true);
    }
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

  load();
})();
