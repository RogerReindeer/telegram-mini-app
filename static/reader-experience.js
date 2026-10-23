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
    const activeAccent = settings.accentColor || DEFAULTS.accentColor;
    document.documentElement.style.setProperty("--accent", activeAccent);
    document.documentElement.style.setProperty("--zb-accent", activeAccent);
    document.documentElement.style.setProperty("--site-accent", activeAccent);
    document.documentElement.style.setProperty("--app-accent", activeAccent);
    document.documentElement.style.setProperty("--accent-color", activeAccent);
    document.documentElement.style.setProperty("--accent-soft", `color-mix(in srgb, ${activeAccent} 12%, transparent)`);
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

    function absoluteUrl(value) {
      if (!value) return "";
      try { return new URL(value, window.location.origin).href; }
      catch (error) { return ""; }
    }

    function escapeChapterHeading(value) {
      return String(value == null ? '' : value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    }

    let previousUrl = absoluteUrl(page.dataset.previousUrl || document.querySelector('.reader-floating-prev')?.getAttribute('href'));
    let nextUrl = absoluteUrl(page.dataset.nextUrl || document.querySelector('.reader-floating-next')?.getAttribute('href'));
    let loadingPrevious = false;
    let loadingNext = false;
    let stoppedPrevious = !previousUrl;
    let stoppedNext = !nextUrl;

    const loadedChapterIds = new Set();
    if (page.dataset.chapterId) loadedChapterIds.add(String(page.dataset.chapterId));

    const topRow = page.querySelector('.chapter-top-row');
    const currentHeader = page.querySelector('.chapter-header');
    const footerFox = page.querySelector('.chapter-footer-fox-wrap');

    const topStatus = document.createElement('div');
    topStatus.className = 'chapter-infinite-status chapter-infinite-status-top';
    topStatus.dataset.chapterInfiniteTopStatus = 'true';
    topStatus.hidden = true;

    const bottomStatus = document.createElement('div');
    bottomStatus.className = 'chapter-infinite-status chapter-infinite-status-bottom';
    bottomStatus.dataset.chapterInfiniteBottomStatus = 'true';
    bottomStatus.hidden = true;

    if (currentHeader && currentHeader.parentNode) {
      currentHeader.parentNode.insertBefore(topStatus, currentHeader);
    } else if (topRow && topRow.parentNode) {
      topRow.insertAdjacentElement('afterend', topStatus);
    }

    if (footerFox && footerFox.parentNode) {
      footerFox.parentNode.insertBefore(bottomStatus, footerFox);
    } else {
      page.appendChild(bottomStatus);
    }

    function setStatus(status, html, preservePosition) {
      const hasContent = Boolean(String(html || '').trim());
      const mutate = function () {
        status.innerHTML = hasContent ? html : '';
        status.hidden = !hasContent;
        status.classList.toggle('is-empty', !hasContent);
        status.setAttribute('aria-hidden', hasContent ? 'false' : 'true');
      };
      if (preservePosition) mutateAbovePreservingScroll(mutate);
      else mutate();
    }

    function mutateAbovePreservingScroll(mutate) {
      const root = document.documentElement;
      const oldHeight = root.scrollHeight;
      const oldY = window.scrollY;
      const previousOverflowAnchor = root.style.overflowAnchor;
      root.style.overflowAnchor = 'none';
      mutate();
      window.requestAnimationFrame(function () {
        const delta = root.scrollHeight - oldHeight;
        window.scrollTo(0, Math.max(0, oldY + delta));
        root.style.overflowAnchor = previousOverflowAnchor;
      });
    }

    function extractDirectionUrl(doc, direction) {
      const nextPage = doc.querySelector('[data-chapter-page]');
      if (nextPage) {
        const value = direction === 'previous' ? nextPage.dataset.previousUrl : nextPage.dataset.nextUrl;
        if (value) return absoluteUrl(value);
      }
      const selector = direction === 'previous' ? '.reader-floating-prev' : '.reader-floating-next';
      const link = doc.querySelector(selector);
      return link ? absoluteUrl(link.getAttribute('href')) : '';
    }

    function buildChapterSection(doc, url, direction) {
      const nextPage = doc.querySelector('[data-chapter-page]');
      if (!nextPage) return { invalid: true, page: null };
      if (nextPage.dataset.isLocked === 'true') return { locked: true, page: nextPage };

      const content = doc.querySelector('[data-cache-chapter-content]');
      const title = doc.querySelector('.chapter-header h1');
      const endGate = doc.querySelector('[data-reader-end-gate]');
      if (!content) return { invalid: true, page: nextPage };

      const chapterId = String(nextPage.dataset.chapterId || '');
      if (chapterId && loadedChapterIds.has(chapterId)) return { duplicate: true, page: nextPage };

      const wrap = document.createElement('section');
      wrap.className = `chapter-infinite-item chapter-infinite-item-${direction}`;
      wrap.dataset.chapterInfiniteItem = 'true';
      wrap.dataset.chapterInfiniteDirection = direction;
      wrap.dataset.novelId = nextPage.dataset.novelId || page.dataset.novelId || '';
      wrap.dataset.novelSlug = nextPage.dataset.novelSlug || page.dataset.novelSlug || '';
      wrap.dataset.novelTitle = nextPage.dataset.novelTitle || page.dataset.novelTitle || '';
      wrap.dataset.chapterId = chapterId;
      wrap.dataset.chapterTitle = nextPage.dataset.chapterTitle || (title ? title.textContent : '');
      wrap.dataset.chapterIndex = nextPage.dataset.chapterIndex || '0';
      wrap.dataset.availableChapters = nextPage.dataset.availableChapters || page.dataset.availableChapters || '0';
      wrap.dataset.chapterUrl = url;
      wrap.dataset.previousUrl = extractDirectionUrl(doc, 'previous');
      wrap.dataset.nextUrl = extractDirectionUrl(doc, 'next');
      const heading = escapeChapterHeading(title ? title.textContent : 'Глава');
      const endGateHtml = endGate ? endGate.outerHTML : '';
      wrap.innerHTML = `<header class="chapter-infinite-head"><span>${direction === 'previous' ? 'Предыдущая глава' : 'Следующая глава'}</span><h2>${heading}</h2></header><article class="chapter-content chapter-content-infinite">${content.innerHTML}</article>${endGateHtml}`;

      if (chapterId) loadedChapterIds.add(chapterId);
      return { wrap: wrap, page: nextPage, hasEndGate: Boolean(endGate) };
    }

    function dispatchChapterAdded(wrap, direction) {
      try {
        document.dispatchEvent(new CustomEvent('zefirki:chapter-appended', { detail: {
          novelId: wrap.dataset.novelId,
          chapterId: wrap.dataset.chapterId,
          chapterTitle: wrap.dataset.chapterTitle,
          chapterIndex: wrap.dataset.chapterIndex,
          availableChapters: wrap.dataset.availableChapters,
          direction: direction,
          element: wrap
        }}));
      } catch (error) {}
    }

    function insertPrevious(result, finalStatusHtml) {
      const wrap = result.wrap;
      if (!wrap) return;
      mutateAbovePreservingScroll(function () {
        setStatus(topStatus, finalStatusHtml || '', false);
        const firstPrevious = page.querySelector('.chapter-infinite-item-previous');
        if (firstPrevious && firstPrevious.parentNode) firstPrevious.parentNode.insertBefore(wrap, firstPrevious);
        else if (currentHeader && currentHeader.parentNode) currentHeader.parentNode.insertBefore(wrap, currentHeader);
        else page.insertBefore(wrap, page.firstChild);
      });
      dispatchChapterAdded(wrap, 'previous');
    }

    function insertNext(result) {
      const wrap = result.wrap;
      if (!wrap) return;
      if (bottomStatus.parentNode) bottomStatus.parentNode.insertBefore(wrap, bottomStatus);
      else page.appendChild(wrap);
      setStatus(bottomStatus, '', false);
      dispatchChapterAdded(wrap, 'next');
    }

    function loadPrevious() {
      if (loadingPrevious || stoppedPrevious || !previousUrl) return;
      loadingPrevious = true;
      setStatus(topStatus, '<span class="chapter-loading-spinner" aria-hidden="true"></span><span>Загружаю предыдущую главу…</span>', true);
      const currentUrl = previousUrl;
      fetch(currentUrl, { credentials: 'same-origin' })
        .then(function (response) { if (!response.ok) throw new Error(String(response.status)); return response.text(); })
        .then(function (html) {
          const doc = new DOMParser().parseFromString(html, 'text/html');
          const result = buildChapterSection(doc, currentUrl, 'previous');
          if (result.locked) {
            stoppedPrevious = true;
            setStatus(topStatus, '<span class="chapter-loading-stop" aria-hidden="true">🔒</span><span>Выше начинается закрытая глава</span>', true);
            return;
          }
          if (result.invalid || result.duplicate) {
            stoppedPrevious = true;
            setStatus(topStatus, '<span class="chapter-loading-done" aria-hidden="true">✓</span><span>Это первая доступная глава</span>', true);
            return;
          }
          previousUrl = extractDirectionUrl(doc, 'previous');
          if (!previousUrl || previousUrl === currentUrl) stoppedPrevious = true;
          insertPrevious(
            result,
            stoppedPrevious
              ? '<span class="chapter-loading-done" aria-hidden="true">✓</span><span>Это первая доступная глава</span>'
              : ''
          );
        })
        .catch(function () {
          stoppedPrevious = true;
          setStatus(topStatus, '<span class="chapter-loading-stop" aria-hidden="true">!</span><span>Не удалось автоматически загрузить предыдущую главу</span>', true);
        })
        .finally(function () { loadingPrevious = false; });
    }

    function loadNext() {
      if (loadingNext || stoppedNext || !nextUrl) return;
      loadingNext = true;
      setStatus(bottomStatus, '<span class="chapter-loading-spinner" aria-hidden="true"></span><span>Загружаю следующую главу…</span>', false);
      const currentUrl = nextUrl;
      fetch(currentUrl, { credentials: 'same-origin' })
        .then(function (response) { if (!response.ok) throw new Error(String(response.status)); return response.text(); })
        .then(function (html) {
          const doc = new DOMParser().parseFromString(html, 'text/html');
          const result = buildChapterSection(doc, currentUrl, 'next');
          if (result.locked) {
            stoppedNext = true;
            setStatus(bottomStatus, '<span class="chapter-loading-stop" aria-hidden="true">🔒</span><span>Дальше начинается закрытая или платная глава</span>', false);
            return;
          }
          if (result.invalid || result.duplicate) {
            stoppedNext = true;
            setStatus(bottomStatus, '<span class="chapter-loading-done" aria-hidden="true">✓</span><span>Доступные главы закончились</span>', false);
            return;
          }
          nextUrl = extractDirectionUrl(doc, 'next');
          if (!nextUrl || nextUrl === currentUrl) stoppedNext = true;
          insertNext(result);
          if (stoppedNext && !result.hasEndGate) {
            setStatus(bottomStatus, '<span class="chapter-loading-done" aria-hidden="true">✓</span><span>Доступные главы закончились</span>', false);
          }
        })
        .catch(function () {
          stoppedNext = true;
          setStatus(bottomStatus, '<span class="chapter-loading-stop" aria-hidden="true">!</span><span>Не удалось автоматически загрузить следующую главу</span>', false);
        })
        .finally(function () { loadingNext = false; });
    }

    function maybeLoad() {
      const root = document.documentElement;
      if (!loadingPrevious && !stoppedPrevious && window.scrollY < 1000) loadPrevious();
      const remaining = root.scrollHeight - (window.scrollY + window.innerHeight);
      if (!loadingNext && !stoppedNext && remaining < 1000) loadNext();
    }

    window.addEventListener('scroll', maybeLoad, { passive: true });
    window.addEventListener('resize', maybeLoad, { passive: true });
    window.setTimeout(maybeLoad, 700);
  }
  function initChapterVerticalSwipeNavigation() {
    const page = document.querySelector('[data-chapter-page]');
    const source = document.querySelector('[data-cache-chapter-content]');
    if (!page || !source || page.dataset.isLocked === "true") return;

    const surface = page;
    const previousUrl = String(page.dataset.previousUrl || '');
    const nextUrl = String(page.dataset.nextUrl || page.dataset.lockedNextUrl || '');
    const EDGE_TOLERANCE = 18;
    const MIN_DRAG = 64;
    const MAX_DURATION = 1200;

    // The chapter itself must never grow by silently appending neighbours.
    // Navigation happens only after an explicit edge pull from the reader.
    document.documentElement.style.overscrollBehaviorY = 'none';
    document.body.style.overscrollBehaviorY = 'none';
    surface.style.setProperty('--chapter-swipe-y', '0px');

    let hint = document.querySelector('[data-chapter-swipe-hint]');
    if (!hint) {
      hint = document.createElement('div');
      hint.className = 'chapter-swipe-hint';
      hint.dataset.chapterSwipeHint = 'true';
      hint.setAttribute('aria-hidden', 'true');
      hint.innerHTML = `
        <span class="chapter-swipe-hint-icon" data-chapter-swipe-icon aria-hidden="true">↑</span>
        <span class="chapter-swipe-hint-copy">
          <strong data-chapter-swipe-title>Следующая глава</strong>
          <small data-chapter-swipe-state>Потяните дальше</small>
        </span>
        <span class="chapter-swipe-hint-track" aria-hidden="true"><span></span></span>
      `;
      document.body.appendChild(hint);
    }

    function haptic(kind) {
      try {
        const h = window.Telegram?.WebApp?.HapticFeedback;
        if (!h) return;
        if (kind === 'ready' && typeof h.selectionChanged === 'function') h.selectionChanged();
        if (kind === 'commit' && typeof h.impactOccurred === 'function') h.impactOccurred('light');
        if (kind === 'cancel' && typeof h.notificationOccurred === 'function') h.notificationOccurred('warning');
      } catch (error) {}
    }

    function atTop() {
      return window.scrollY <= EDGE_TOLERANCE;
    }

    function atBottom() {
      const root = document.documentElement;
      return root.scrollHeight - (window.scrollY + window.innerHeight) <= EDGE_TOLERANCE;
    }

    function destination(direction) {
      if (direction === 'previous') {
        return {
          direction,
          path: previousUrl,
          title: previousUrl ? 'Предыдущая глава' : 'Это первая доступная глава',
          icon: '↓',
          side: 'top'
        };
      }
      return {
        direction: 'next',
        path: nextUrl,
        title: nextUrl ? 'Следующая глава' : 'Доступные главы закончились',
        icon: '↑',
        side: 'bottom'
      };
    }

    function updateHint(target, progress, ready) {
      if (!hint || !target) return;
      hint.classList.toggle('is-from-top', target.side === 'top');
      hint.classList.toggle('is-from-bottom', target.side === 'bottom');
      hint.classList.toggle('is-disabled', !target.path);
      hint.classList.toggle('is-ready', Boolean(target.path && ready));
      hint.classList.add('is-visible');
      hint.style.setProperty('--chapter-swipe-progress', String(Math.max(0, Math.min(1, progress))));
      const icon = hint.querySelector('[data-chapter-swipe-icon]');
      const title = hint.querySelector('[data-chapter-swipe-title]');
      const state = hint.querySelector('[data-chapter-swipe-state]');
      if (icon) icon.textContent = target.icon;
      if (title) title.textContent = target.title;
      if (state) {
        state.textContent = !target.path
          ? (target.direction === 'previous' ? 'Вы уже в начале' : 'Больше доступных глав нет')
          : (ready ? 'Отпустите, чтобы перейти' : 'Потяните дальше');
      }
    }

    function reset(cancelled) {
      document.body.classList.remove('chapter-swipe-dragging');
      document.body.classList.add('chapter-swipe-resetting');
      surface.style.setProperty('--chapter-swipe-y', '0px');
      surface.classList.remove('is-chapter-swipe-up', 'is-chapter-swipe-down');
      if (hint) {
        hint.classList.remove('is-ready', 'is-committing');
        hint.classList.toggle('is-cancelled', Boolean(cancelled));
      }
      window.setTimeout(function () {
        document.body.classList.remove('chapter-swipe-resetting');
        if (hint) {
          hint.classList.remove('is-visible', 'is-from-top', 'is-from-bottom', 'is-disabled', 'is-cancelled');
          hint.style.setProperty('--chapter-swipe-progress', '0');
        }
      }, 250);
    }

    function commit(target, deltaY) {
      if (!target || !target.path) return reset(true);
      haptic('commit');
      try {
        document.dispatchEvent(new CustomEvent('zefirki:chapter-swipe-navigate', {
          detail: { direction: target.direction, path: target.path }
        }));
      } catch (error) {}
      document.body.classList.remove('chapter-swipe-dragging', 'chapter-swipe-resetting');
      document.body.classList.add('gesture-navigation-active', 'chapter-swipe-committing');
      if (hint) {
        hint.classList.add('is-visible', 'is-ready', 'is-committing');
        const state = hint.querySelector('[data-chapter-swipe-state]');
        if (state) state.textContent = 'Открываю главу…';
      }
      const offscreen = (deltaY > 0 ? 1 : -1) * (window.innerHeight + 100);
      surface.style.setProperty('--chapter-swipe-y', `${offscreen}px`);
      window.setTimeout(function () { window.location.assign(target.path); }, 190);
    }

    let startX = 0;
    let startY = 0;
    let startTime = 0;
    let tracking = false;
    let blocked = false;
    let startedAtTop = false;
    let startedAtBottom = false;
    let verticalIntent = false;
    let activeTarget = null;
    let readyTriggered = false;
    let suppressClickUntil = 0;

    document.addEventListener('click', function (event) {
      if (Date.now() < suppressClickUntil) {
        event.preventDefault();
        event.stopPropagation();
      }
    }, true);

    document.addEventListener('touchstart', function (event) {
      if (event.touches.length !== 1 || document.body.classList.contains('chapter-swipe-committing')) {
        tracking = false;
        return;
      }
      const target = event.target;
      blocked = Boolean(target && target.closest && target.closest(
        'a, button, input, textarea, select, summary, [contenteditable="true"], [data-no-chapter-swipe]'
      ));
      const touch = event.touches[0];
      startX = touch.clientX;
      startY = touch.clientY;
      startTime = Date.now();
      startedAtTop = atTop();
      startedAtBottom = atBottom();
      verticalIntent = false;
      activeTarget = null;
      readyTriggered = false;
      tracking = !blocked && (startedAtTop || startedAtBottom);
      surface.style.setProperty('--chapter-swipe-y', '0px');
    }, { passive: true });

    document.addEventListener('touchmove', function (event) {
      if (!tracking || blocked || event.touches.length !== 1) return;
      const touch = event.touches[0];
      const deltaX = touch.clientX - startX;
      const deltaY = touch.clientY - startY;

      // Only overscroll-like pulls switch chapters:
      // pull down at the very top -> previous, pull up at the very bottom -> next.
      const direction = startedAtTop && deltaY > 0
        ? 'previous'
        : (startedAtBottom && deltaY < 0 ? 'next' : '');

      if (!direction) {
        // A normal scroll back into the current chapter must stay native.
        if (Math.abs(deltaY) > 12) tracking = false;
        return;
      }

      if (!verticalIntent) {
        if (Math.abs(deltaX) > 18 && Math.abs(deltaX) > Math.abs(deltaY) * 1.1) {
          tracking = false;
          return;
        }
        if (Math.abs(deltaY) > 16 && Math.abs(deltaY) > Math.abs(deltaX) * 1.08) verticalIntent = true;
      }
      if (!verticalIntent) return;

      event.preventDefault();
      activeTarget = destination(direction);
      document.body.classList.add('chapter-swipe-dragging');
      const threshold = Math.max(82, Math.min(126, window.innerHeight * 0.14));
      const progress = Math.min(1, Math.abs(deltaY) / threshold);
      const maxShift = Math.min(180, window.innerHeight * 0.22);
      const resistance = activeTarget.path ? 0.62 : 0.24;
      const shift = Math.sign(deltaY || 1) * Math.min(maxShift, Math.abs(deltaY) * resistance);
      const ready = Boolean(activeTarget.path && Math.abs(deltaY) >= threshold);

      surface.style.setProperty('--chapter-swipe-y', `${shift}px`);
      surface.classList.toggle('is-chapter-swipe-down', deltaY > 0);
      surface.classList.toggle('is-chapter-swipe-up', deltaY < 0);
      updateHint(activeTarget, progress, ready);

      if (ready && !readyTriggered) {
        readyTriggered = true;
        haptic('ready');
      } else if (!ready) {
        readyTriggered = false;
      }
    }, { passive: false });

    document.addEventListener('touchend', function (event) {
      if (!tracking || blocked || !event.changedTouches.length) {
        if (verticalIntent) reset(true);
        tracking = false;
        return;
      }
      tracking = false;
      const touch = event.changedTouches[0];
      const deltaX = touch.clientX - startX;
      const deltaY = touch.clientY - startY;
      const duration = Math.max(1, Date.now() - startTime);
      const velocity = Math.abs(deltaY) / duration;
      const threshold = Math.max(82, Math.min(126, window.innerHeight * 0.14));
      const directional = Math.abs(deltaY) > Math.abs(deltaX) * 1.15;
      const passedDistance = Math.abs(deltaY) >= threshold;
      const passedFlick = Math.abs(deltaY) >= MIN_DRAG && velocity >= 0.34;
      const shouldNavigate = verticalIntent && directional && duration <= MAX_DURATION
        && activeTarget && activeTarget.path && (passedDistance || passedFlick);

      suppressClickUntil = verticalIntent ? Date.now() + 360 : 0;
      if (shouldNavigate) commit(activeTarget, deltaY);
      else {
        if (verticalIntent && activeTarget?.path && Math.abs(deltaY) > 42) haptic('cancel');
        reset(verticalIntent);
      }
    }, { passive: true });

    document.addEventListener('touchcancel', function () {
      if (!tracking && !verticalIntent) return;
      tracking = false;
      reset(true);
    }, { passive: true });
  }

  function initV134() {
    initSystemThemeWatcher();
    initSettingsPreview();
    initChapterVerticalSwipeNavigation();
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
      novelTitle: element.dataset.novelShortTitle || page.dataset.novelShortTitle || element.dataset.novelTitle || page.dataset.novelTitle || meta.novelShort || meta.novelTitle || "",
      novelShort: element.dataset.novelShortTitle || page.dataset.novelShortTitle || meta.novelShort || "",
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
      completed: Number(item.scrollPosition || 0) >= 0.9,
      read_chapter_ids: Array.isArray(readIds) ? readIds.slice(-3000) : [],
    };
    window.fetch("/api/user/progress", {
      method: "PUT",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).catch(function () {});
  }

  function updateFloatingChapterNavigation(element) {
    if (!element) return;
    const controls = document.querySelector('[data-reader-floating-controls]');
    if (!controls) return;

    let previous = controls.querySelector('.reader-floating-prev');
    let next = controls.querySelector('.reader-floating-next');
    const scrollUp = controls.querySelector('[data-scroll-up]');

    if (!previous) {
      previous = document.createElement('a');
      previous.className = 'reader-floating-button reader-floating-prev';
      previous.setAttribute('aria-label', 'Прошлая глава');
      previous.setAttribute('title', 'Прошлая глава');
      previous.textContent = '‹';
      if (scrollUp) controls.insertBefore(previous, scrollUp);
      else controls.appendChild(previous);
    }

    if (!next) {
      next = document.createElement('a');
      next.className = 'reader-floating-button reader-floating-next is-primary';
      next.setAttribute('aria-label', 'Следующая глава');
      next.setAttribute('title', 'Следующая глава');
      next.textContent = '›';
      controls.appendChild(next);
    }

    const previousUrl = element.dataset.previousUrl || '';
    const nextUrl = element.dataset.nextUrl || '';
    previous.hidden = !previousUrl;
    next.hidden = !nextUrl;
    if (previousUrl) previous.href = previousUrl;
    else previous.removeAttribute('href');
    if (nextUrl) next.href = nextUrl;
    else next.removeAttribute('href');
  }

  function saveVisibleProgress(element, options) {
    updateFloatingChapterNavigation(element);
    const item = buildHistoryItemFromElement(element);
    if (!item) return;
    document.dispatchEvent(new CustomEvent("zefirki:analytics-progress", { detail: item }));
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
    original.dataset.previousUrl = page.dataset.previousUrl || "";
    original.dataset.nextUrl = page.dataset.nextUrl || "";
    original.dataset.chapterUrl = window.location.href;
    return original;
  }

  function allChapterProgressElements() {
    const original = registerOriginalChapterElement();
    const items = Array.from(document.querySelectorAll("[data-chapter-infinite-item]"));
    if (original && !items.includes(original)) items.push(original);
    items.sort(function (a, b) {
      if (a === b) return 0;
      return a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1;
    });
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
    const original = registerOriginalChapterElement();
    updateFloatingChapterNavigation(original);
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

/* v149 — completed novels with locked paid tail stay in reading as waiting_new */


/* v156 — contextual floating TOC and reader controls */
(function () {
  const TOC_HIDDEN_KEY = "zefirki_toc_controls_hidden";
  const READER_HIDDEN_KEY = "zefirki_reader_controls_hidden";
  function qs(selector, root) { return (root || document).querySelector(selector); }
  function scrollToTarget(id, block) { const target = document.getElementById(id); if (target) target.scrollIntoView({ behavior: "smooth", block: block || "start" }); }
  function isTopReadButtonVisible(sourceButton) {
    if (!sourceButton) return false;
    const rect = sourceButton.getBoundingClientRect();
    return rect.bottom > 10 && rect.top < window.innerHeight - 72;
  }
  function applyTocHidden(hidden) {
    document.body.classList.toggle("toc-floating-controls-hidden", hidden);
    const controls = qs("[data-toc-floating-controls]");
    const toggle = qs("[data-toc-controls-toggle]");
    if (controls) controls.setAttribute("aria-hidden", hidden ? "true" : "false");
    if (toggle) {
      toggle.textContent = hidden ? "☰" : "×";
      toggle.classList.toggle("is-cross-icon", !hidden);
      toggle.setAttribute("aria-pressed", hidden ? "true" : "false");
      toggle.setAttribute("aria-label", hidden ? "Показать кнопки оглавления" : "Скрыть кнопки оглавления");
    }
  }
  function applyReaderHidden(hidden) {
    const controls = qs("[data-reader-floating-controls]");
    const toggle = qs("[data-reader-controls-visibility-toggle]");
    document.body.classList.toggle("reader-controls-hidden", hidden);
    if (controls) controls.setAttribute("aria-hidden", hidden ? "true" : "false");
    if (toggle) {
      toggle.textContent = hidden ? "☰" : "×";
      toggle.classList.toggle("is-cross-icon", !hidden);
      toggle.setAttribute("aria-pressed", hidden ? "true" : "false");
      toggle.setAttribute("aria-label", hidden ? "Показать кнопки читалки" : "Скрыть кнопки читалки");
    }
  }
  function initFloatingTocControls() {
    const page = qs("[data-novel-page]");
    const sourceButton = qs("#novelReadButton");
    const chapterList = qs("[data-chapter-list]");
    if (!page || !sourceButton || qs("[data-toc-floating-controls]")) return;
    const controls = document.createElement("aside");
    controls.className = "toc-floating-controls";
    controls.dataset.tocFloatingControls = "true";
    controls.setAttribute("aria-label", "Быстрая навигация по оглавлению");
    const cta = document.createElement("a");
    cta.className = "toc-floating-main-button";
    cta.dataset.tocFloatingRead = "true";
    cta.href = sourceButton.href || "#chapterListStart";
    cta.textContent = sourceButton.textContent.trim() || "Начать читать";
    const top = document.createElement("button");
    top.className = "toc-floating-nav-button";
    top.type = "button";
    top.textContent = "↑";
    top.setAttribute("aria-label", "К началу оглавления");
    const bottom = document.createElement("button");
    bottom.className = "toc-floating-nav-button";
    bottom.type = "button";
    bottom.textContent = "↓";
    bottom.setAttribute("aria-label", "В конец оглавления");
    controls.appendChild(cta);
    controls.appendChild(top);
    controls.appendChild(bottom);
    document.body.appendChild(controls);
    const toggle = document.createElement("button");
    toggle.className = "toc-controls-visibility-toggle";
    toggle.type = "button";
    toggle.dataset.tocControlsToggle = "true";
    document.body.appendChild(toggle);
    const syncCta = function () {
      cta.href = sourceButton.href || cta.href;
      cta.textContent = sourceButton.textContent.trim() || cta.textContent;
    };
    const syncVisibility = function () {
      const topButtonVisible = isTopReadButtonVisible(sourceButton);
      document.body.classList.toggle("toc-floating-controls-suppressed", topButtonVisible);
      controls.setAttribute("data-suppressed-by-top-button", topButtonVisible ? "true" : "false");
      toggle.setAttribute("data-suppressed-by-top-button", topButtonVisible ? "true" : "false");
    };
    syncCta();
    syncVisibility();
    try { new MutationObserver(function () { syncCta(); syncVisibility(); }).observe(sourceButton, { attributes: true, childList: true, subtree: true, characterData: true }); } catch (error) {}
    top.addEventListener("click", function (event) { event.stopPropagation(); scrollToTarget("chapterListStart", "start"); });
    bottom.addEventListener("click", function (event) { event.stopPropagation(); scrollToTarget("chapterListEnd", chapterList ? "end" : "start"); });
    controls.addEventListener("click", function (event) { event.stopPropagation(); });
    toggle.addEventListener("click", function (event) { event.stopPropagation(); applyTocHidden(!document.body.classList.contains("toc-floating-controls-hidden")); });
    window.addEventListener("scroll", syncVisibility, { passive: true });
    window.addEventListener("resize", syncVisibility, { passive: true });
    if ("IntersectionObserver" in window) {
      try { new IntersectionObserver(syncVisibility, { threshold: [0, .1, .45, .9, 1] }).observe(sourceButton); } catch (error) {}
    }
    try { window.localStorage.removeItem(TOC_HIDDEN_KEY); } catch (error) {}
    applyTocHidden(false);
  }
  function initReaderEmptySpaceCollapse() {
    const page = qs("[data-chapter-page]");
    const controls = qs("[data-reader-floating-controls]");
    const toggle = qs("[data-reader-controls-visibility-toggle]");
    if (!page || !controls || !toggle) return;
    try { window.localStorage.removeItem(READER_HIDDEN_KEY); } catch (error) {}
    applyReaderHidden(false);
    controls.addEventListener("click", function (event) { event.stopPropagation(); });
    toggle.addEventListener("click", function (event) { event.stopPropagation(); applyReaderHidden(!document.body.classList.contains("reader-controls-hidden")); });
    document.addEventListener("zefirki:chapter-appended", function () { applyReaderHidden(false); });
  }
  function initEmptySpaceCollapse() {
    document.addEventListener("click", function (event) {
      const target = event.target;
      if (!target || !target.closest) return;
      if (target.closest("a, button, input, select, textarea, summary, [role='button'], .settings-overlay, .zb-settings-sheet, .reader-quick-settings, [data-toc-floating-controls], [data-reader-floating-controls], [data-toc-controls-toggle], [data-reader-controls-visibility-toggle]")) return;
      if (document.body.classList.contains("page-novel") && qs("[data-toc-floating-controls]")) applyTocHidden(true);
      if (document.body.classList.contains("page-chapter") && qs("[data-reader-floating-controls]")) applyReaderHidden(true);
    }, false);
  }
  function initV156() { initFloatingTocControls(); initReaderEmptySpaceCollapse(); initEmptySpaceCollapse(); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initV156); else initV156();
})();

/* access labels: 🌱 Странствующий читатель · 📜 Хранитель свитков · v151-floating-toc-gold-groups */

/* v168 — dock reader Aa settings button into the same floating rail */
(function () {
  function dockReaderSettingsButton() {
    if (!document.body.classList.contains("page-chapter")) return false;
    const controls = document.querySelector("[data-reader-floating-controls]");
    const button = document.querySelector("[data-zb-reader-settings]");
    if (!controls || !button) return false;
    if (button.parentElement !== controls) {
      controls.appendChild(button);
    }
    button.classList.add("reader-settings-docked");
    button.classList.add("reader-floating-button");
    button.setAttribute("data-reader-settings-docked", "true");
    button.setAttribute("title", "Настройки чтения");
    return true;
  }

  function initDockedReaderSettingsButton() {
    if (dockReaderSettingsButton()) return;
    let attempts = 0;
    const timer = window.setInterval(function () {
      attempts += 1;
      if (dockReaderSettingsButton() || attempts > 30) {
        window.clearInterval(timer);
      }
    }, 120);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initDockedReaderSettingsButton);
  } else {
    initDockedReaderSettingsButton();
  }
})();


/* =====================================================================
   v200 — remove legacy chapter arrows and add horizontal navigation gestures
   ===================================================================== */
(function () {
  "use strict";

  const READING_HISTORY_KEY = "zefirki_reading_history";
  const LEGACY_CHAPTER_NAV_RE = /^[\s〰~\-—–_=]*🦊[\s〰~\-—–_=]*(?:глава|chapter)\s*\d+(?:[.,\-–—/]\d+)?(?:\s*(?:-?>|→|➡|⟶|⇢))?[\s〰~\-—–_=]*$/i;

  function normalizeServiceText(value) {
    return String(value == null ? "" : value)
      .replace(/\uFE0F/g, "")
      .replace(/\u200D/g, "")
      .replace(/\u00A0/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function removeLegacyChapterNavigation(root) {
    const scope = root && root.querySelectorAll ? root : document;
    const articles = [];
    if (scope.matches && scope.matches(".chapter-content")) articles.push(scope);
    scope.querySelectorAll(".chapter-content").forEach(function (article) { articles.push(article); });

    articles.forEach(function (article) {
      article.querySelectorAll("p, div, h1, h2, h3, h4, blockquote, li, a").forEach(function (node) {
        const text = normalizeServiceText(node.textContent);
        if (text.length <= 120 && LEGACY_CHAPTER_NAV_RE.test(text)) node.remove();
      });
    });
  }

  function readHistory() {
    try {
      const value = JSON.parse(window.localStorage.getItem(READING_HISTORY_KEY) || "[]");
      return Array.isArray(value) ? value : [];
    } catch (error) {
      return [];
    }
  }

  function sameOriginPath(href) {
    if (!href) return "";
    try {
      const url = new URL(href, window.location.href);
      if (url.origin !== window.location.origin) return "";
      return `${url.pathname}${url.search}${url.hash}`;
    } catch (error) {
      return "";
    }
  }

  function novelForwardDestination(page) {
    if (!page) return "";
    const novelId = String(page.dataset.novelId || "");
    const availableRows = Array.from(document.querySelectorAll("[data-chapter-row]:not(.chapter-row-locked)"));
    if (!availableRows.length) return "";

    const historyItem = readHistory().find(function (item) {
      return String(item && item.novelId || "") === novelId;
    });

    if (historyItem && historyItem.chapterId) {
      const currentIndex = availableRows.findIndex(function (row) {
        return String(row.dataset.chapterId || "") === String(historyItem.chapterId);
      });
      if (currentIndex >= 0 && currentIndex + 1 < availableRows.length) {
        const nextUnread = availableRows.slice(currentIndex + 1).find(function (row) {
          return !row.classList.contains("chapter-row-read");
        });
        if (nextUnread) return sameOriginPath(nextUnread.getAttribute("href"));
      }
      const currentRow = currentIndex >= 0 ? availableRows[currentIndex] : null;
      if (currentRow) return sameOriginPath(currentRow.getAttribute("href"));
    }

    const readButton = document.getElementById("novelReadButton");
    const buttonPath = readButton ? sameOriginPath(readButton.getAttribute("href")) : "";
    if (buttonPath) return buttonPath;
    return sameOriginPath(availableRows[0].getAttribute("href"));
  }

  function pageGestureHaptic(kind) {
    try {
      const haptic = window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.HapticFeedback;
      if (!haptic) return;
      if (kind === "ready" && typeof haptic.selectionChanged === "function") haptic.selectionChanged();
      if (kind === "commit" && typeof haptic.impactOccurred === "function") haptic.impactOccurred("light");
      if (kind === "cancel" && typeof haptic.notificationOccurred === "function") haptic.notificationOccurred("warning");
    } catch (error) {}
  }

  function ensurePageSwipeHint() {
    let hint = document.querySelector("[data-page-swipe-hint]");
    if (hint) return hint;

    hint = document.createElement("div");
    hint.className = "page-swipe-hint";
    hint.setAttribute("data-page-swipe-hint", "");
    hint.setAttribute("aria-hidden", "true");
    hint.innerHTML = `
      <span class="page-swipe-hint-icon" data-page-swipe-icon aria-hidden="true">→</span>
      <span class="page-swipe-hint-copy">
        <strong data-page-swipe-title>Переход</strong>
        <small data-page-swipe-state>Потяните дальше</small>
      </span>
      <span class="page-swipe-hint-track" aria-hidden="true"><span></span></span>
    `;
    document.body.appendChild(hint);
    return hint;
  }

  function showPageSwipeCoach(chapterPage, novelPage) {
    if (!("ontouchstart" in window) && Number(navigator.maxTouchPoints || 0) <= 0) return;
    let alreadyShown = false;
    try {
      alreadyShown = window.sessionStorage.getItem("zefirki_swipe_coach_v202") === "1";
      if (!alreadyShown) window.sessionStorage.setItem("zefirki_swipe_coach_v202", "1");
    } catch (error) {}
    if (alreadyShown) return;

    const coach = document.createElement("div");
    coach.className = "page-swipe-coach";
    coach.setAttribute("aria-live", "polite");
    coach.innerHTML = chapterPage
      ? '<span aria-hidden="true">↕</span><span>Вправо — оглавление · у края вверх/вниз — сменить главу</span>'
      : '<span aria-hidden="true">↔</span><span>Вправо — библиотека, влево — продолжить чтение</span>';
    document.body.appendChild(coach);
    window.setTimeout(function () { coach.classList.add("is-visible"); }, 120);
    window.setTimeout(function () {
      coach.classList.remove("is-visible");
      window.setTimeout(function () { coach.remove(); }, 260);
    }, novelPage ? 3200 : 2600);
  }

  function pageGestureDestination(chapterPage, novelPage, deltaX) {
    if (deltaX > 0 && chapterPage) {
      const slug = chapterPage.dataset.novelSlug || "";
      return {
        path: slug ? `/novel/${encodeURIComponent(slug)}` : "",
        title: "К оглавлению",
        icon: "📖",
        side: "left",
      };
    }

    if (deltaX > 0 && novelPage) {
      return {
        path: "/library",
        title: "В библиотеку",
        icon: "←",
        side: "left",
      };
    }

    if (deltaX < 0 && novelPage) {
      const path = novelForwardDestination(novelPage);
      return {
        path: path,
        title: path ? "Продолжить чтение" : "Нет доступной главы",
        icon: path ? "→" : "⛔",
        side: "right",
      };
    }

    return {
      path: "",
      title: chapterPage ? "В читалке свайпните вправо" : "Переход недоступен",
      icon: "↩",
      side: deltaX < 0 ? "right" : "left",
    };
  }

  function navigateWithGesture(path, surface, hint, direction) {
    if (!path) return;
    pageGestureHaptic("commit");
    document.body.classList.remove("page-swipe-dragging", "page-swipe-resetting");
    document.body.classList.add("gesture-navigation-active", "page-swipe-committing");
    if (hint) {
      hint.classList.add("is-visible", "is-ready", "is-committing");
      const state = hint.querySelector("[data-page-swipe-state]");
      if (state) state.textContent = "Переходим…";
    }
    if (surface) {
      const offscreen = (direction > 0 ? 1 : -1) * (window.innerWidth + 80);
      surface.style.setProperty("--page-swipe-x", `${offscreen}px`);
    }
    window.setTimeout(function () { window.location.assign(path); }, 185);
  }

  function initHorizontalPageGestures() {
    const chapterPage = document.querySelector("[data-chapter-page]");
    const novelPage = document.querySelector("[data-novel-page]");
    if (!chapterPage && !novelPage) return;

    const surface = chapterPage || novelPage;
    const hint = ensurePageSwipeHint();
    surface.classList.add("page-swipe-surface");
    showPageSwipeCoach(chapterPage, novelPage);

    let startX = 0;
    let startY = 0;
    let lastX = 0;
    let startTime = 0;
    let tracking = false;
    let blocked = false;
    let horizontalIntent = false;
    let readyTriggered = false;
    let suppressClickUntil = 0;
    let activeDestination = null;

    function updateHint(destination, progress, ready) {
      if (!hint || !destination) return;
      hint.classList.toggle("is-from-left", destination.side === "left");
      hint.classList.toggle("is-from-right", destination.side === "right");
      hint.classList.toggle("is-disabled", !destination.path);
      hint.classList.toggle("is-ready", Boolean(destination.path && ready));
      hint.classList.add("is-visible");
      hint.style.setProperty("--swipe-progress", String(Math.max(0, Math.min(1, progress))));

      const icon = hint.querySelector("[data-page-swipe-icon]");
      const title = hint.querySelector("[data-page-swipe-title]");
      const state = hint.querySelector("[data-page-swipe-state]");
      if (icon) icon.textContent = destination.icon;
      if (title) title.textContent = destination.title;
      if (state) {
        state.textContent = !destination.path
          ? "Этот переход здесь недоступен"
          : (ready ? "Отпустите, чтобы перейти" : "Потяните дальше");
      }
    }

    function clearSwipeVisuals(cancelled) {
      document.body.classList.remove("page-swipe-dragging");
      document.body.classList.add("page-swipe-resetting");
      surface.style.setProperty("--page-swipe-x", "0px");
      if (hint) {
        hint.classList.remove("is-ready", "is-committing");
        hint.classList.toggle("is-cancelled", Boolean(cancelled));
      }
      window.setTimeout(function () {
        document.body.classList.remove("page-swipe-resetting");
        if (hint) {
          hint.classList.remove("is-visible", "is-from-left", "is-from-right", "is-disabled", "is-cancelled");
          hint.style.setProperty("--swipe-progress", "0");
        }
      }, 250);
    }

    document.addEventListener("click", function (event) {
      if (Date.now() < suppressClickUntil) {
        event.preventDefault();
        event.stopPropagation();
      }
    }, true);

    document.addEventListener("touchstart", function (event) {
      if (event.touches.length !== 1 || document.body.classList.contains("page-swipe-committing")) {
        tracking = false;
        return;
      }
      const target = event.target;
      blocked = Boolean(target && target.closest && target.closest("input, textarea, select, button, [contenteditable='true'], [data-no-page-swipe]"));
      const touch = event.touches[0];
      startX = touch.clientX;
      startY = touch.clientY;
      lastX = startX;
      startTime = Date.now();
      horizontalIntent = false;
      readyTriggered = false;
      activeDestination = null;
      tracking = true;
      surface.style.setProperty("--page-swipe-x", "0px");
    }, { passive: true });

    document.addEventListener("touchmove", function (event) {
      if (!tracking || blocked || event.touches.length !== 1) return;
      const touch = event.touches[0];
      const deltaX = touch.clientX - startX;
      const deltaY = touch.clientY - startY;
      lastX = touch.clientX;

      if (!horizontalIntent) {
        if (Math.abs(deltaY) > 18 && Math.abs(deltaY) > Math.abs(deltaX)) {
          tracking = false;
          return;
        }
        if (Math.abs(deltaX) > 18 && Math.abs(deltaX) > Math.abs(deltaY) * 1.15) horizontalIntent = true;
      }

      if (!horizontalIntent) return;
      event.preventDefault();
      document.body.classList.add("page-swipe-dragging");

      activeDestination = pageGestureDestination(chapterPage, novelPage, deltaX);
      const threshold = Math.max(82, Math.min(118, window.innerWidth * 0.24));
      const progress = Math.min(1, Math.abs(deltaX) / threshold);
      const maxShift = Math.min(190, window.innerWidth * 0.38);
      const resistance = activeDestination.path ? 0.72 : 0.28;
      const shift = Math.sign(deltaX || 1) * Math.min(maxShift, Math.abs(deltaX) * resistance);
      const ready = Boolean(activeDestination.path && Math.abs(deltaX) >= threshold);

      surface.style.setProperty("--page-swipe-x", `${shift}px`);
      surface.classList.toggle("is-swipe-right", deltaX > 0);
      surface.classList.toggle("is-swipe-left", deltaX < 0);
      updateHint(activeDestination, progress, ready);

      if (ready && !readyTriggered) {
        readyTriggered = true;
        pageGestureHaptic("ready");
      } else if (!ready) {
        readyTriggered = false;
      }
    }, { passive: false });

    document.addEventListener("touchend", function (event) {
      if (!tracking || blocked || !event.changedTouches.length) {
        tracking = false;
        if (horizontalIntent) clearSwipeVisuals(true);
        return;
      }

      tracking = false;
      const touch = event.changedTouches[0];
      const deltaX = touch.clientX - startX;
      const deltaY = touch.clientY - startY;
      const duration = Math.max(1, Date.now() - startTime);
      const velocity = Math.abs(deltaX) / duration;
      const threshold = Math.max(82, Math.min(118, window.innerWidth * 0.24));
      const destination = activeDestination || pageGestureDestination(chapterPage, novelPage, deltaX);
      const directional = Math.abs(deltaX) > Math.abs(deltaY) * 1.2;
      const passedDistance = Math.abs(deltaX) >= threshold;
      const passedFlick = Math.abs(deltaX) >= 58 && velocity >= 0.35;
      const shouldNavigate = horizontalIntent && directional && duration <= 1100 && destination.path && (passedDistance || passedFlick);

      surface.classList.remove("is-swipe-right", "is-swipe-left");
      suppressClickUntil = horizontalIntent ? Date.now() + 360 : 0;

      if (shouldNavigate) {
        navigateWithGesture(destination.path, surface, hint, deltaX);
      } else {
        if (horizontalIntent && destination.path && Math.abs(deltaX) > 42) pageGestureHaptic("cancel");
        clearSwipeVisuals(horizontalIntent);
      }
    }, { passive: true });

    document.addEventListener("touchcancel", function () {
      if (!tracking && !horizontalIntent) return;
      tracking = false;
      surface.classList.remove("is-swipe-right", "is-swipe-left");
      clearSwipeVisuals(true);
    }, { passive: true });
  }

  function initV200() {
    removeLegacyChapterNavigation(document);
    initHorizontalPageGestures();

    document.addEventListener("zefirki:chapter-appended", function (event) {
      removeLegacyChapterNavigation(event.detail && event.detail.element ? event.detail.element : document);
    });

    const chapterPage = document.querySelector("[data-chapter-page]");
    if (chapterPage && window.MutationObserver) {
      const observer = new MutationObserver(function (mutations) {
        mutations.forEach(function (mutation) {
          mutation.addedNodes.forEach(function (node) {
            if (node && node.nodeType === 1) removeLegacyChapterNavigation(node);
          });
        });
      });
      observer.observe(chapterPage, { childList: true, subtree: true });
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initV200);
  else initV200();
})();


/* v214 — hide floating reader controls while the end-of-chapter access card is visible. */
(function initV214EndGateControls() {
  function start() {
    const gate = document.querySelector("[data-reader-end-gate]");
    const controls = document.querySelector("[data-reader-floating-controls]");
    if (!gate || !controls || !window.IntersectionObserver) return;
    const observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        controls.classList.toggle("is-end-gate-visible", entry.isIntersecting && entry.intersectionRatio > 0.18);
      });
    }, { threshold: [0, 0.18, 0.45] });
    observer.observe(gate);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();

/* =====================================================================
   v226 — persistent product analytics + personal reading statistics
   ===================================================================== */
(function () {
  const viewer = window.ZEFIRKI_VIEWER || {};
  const userId = Number(viewer.user_id || viewer.userId || 0);
  if (!userId) return;

  const SESSION_KEY = "zefirki_analytics_session_id";
  const SOURCE_KEY = "zefirki_analytics_source";
  const FIRST_SOURCE_KEY = "zefirki_analytics_first_source";
  const pageStartedAt = Date.now();
  const progressSent = new Map();
  const completedSent = new Set();
  const openedChapters = new Set();

  function uuid() {
    try { if (window.crypto && typeof window.crypto.randomUUID === "function") return window.crypto.randomUUID(); } catch (error) {}
    return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
  }
  function safeStorage(storage, method, key, value) {
    try { return value === undefined ? storage[method](key) : storage[method](key, value); } catch (error) { return null; }
  }
  let sessionId = safeStorage(window.sessionStorage, "getItem", SESSION_KEY);
  const newSession = !sessionId;
  if (!sessionId) {
    sessionId = uuid();
    safeStorage(window.sessionStorage, "setItem", SESSION_KEY, sessionId);
  }
  function resolveSource() {
    const cached = safeStorage(window.sessionStorage, "getItem", SOURCE_KEY);
    if (cached) return cached;
    let source = "";
    try { source = String(window.Telegram?.WebApp?.initDataUnsafe?.start_param || "").trim(); } catch (error) {}
    if (!source) {
      try {
        const params = new URLSearchParams(window.location.search || "");
        source = String(params.get("startapp") || params.get("utm_source") || "").trim();
      } catch (error) {}
    }
    if (!source) source = "direct";
    source = source.slice(0, 120);
    safeStorage(window.sessionStorage, "setItem", SOURCE_KEY, source);
    if (!safeStorage(window.localStorage, "getItem", FIRST_SOURCE_KEY)) {
      safeStorage(window.localStorage, "setItem", FIRST_SOURCE_KEY, source);
    }
    return source;
  }
  const source = resolveSource();

  function pageNovelId() {
    const root = document.querySelector("[data-novel-page], [data-chapter-page]");
    return Number(root?.dataset?.novelId || 0) || null;
  }
  function pageChapterId() {
    return String(document.querySelector("[data-chapter-page]")?.dataset?.chapterId || "") || null;
  }
  function send(eventName, extra) {
    const data = extra || {};
    const payload = {
      event_id: uuid(),
      session_id: String(sessionId || ""),
      event_name: eventName,
      novel_id: data.novel_id || pageNovelId(),
      chapter_id: data.chapter_id || pageChapterId(),
      source,
      section: data.section || "",
      action: data.action || "",
      access_type: data.access_type || String(viewer.app_access_source || ""),
      subscription_type: data.subscription_type || String(viewer.role || ""),
      value_int: Number.isFinite(data.value_int) ? Math.trunc(data.value_int) : null,
      value_float: Number.isFinite(data.value_float) ? Number(data.value_float) : null,
      value_text: data.value_text == null ? null : String(data.value_text).slice(0, 300),
      metadata: data.metadata && typeof data.metadata === "object" ? data.metadata : {}
    };
    try {
      window.fetch("/api/analytics/event", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        keepalive: Boolean(data.keepalive)
      }).catch(function () {});
    } catch (error) {}
  }

  function trackChapterOpen(chapterId, novelId, metadata) {
    const key = String(chapterId || "");
    if (!key || openedChapters.has(key)) return;
    openedChapters.add(key);
    send("chapter_open", { chapter_id: key, novel_id: Number(novelId || 0) || null, section: "reader", metadata: metadata || {} });
  }

  if (newSession) send("app_open", { section: "app" });
  if (document.body.classList.contains("page-access-gate")) {
    send("main_group_gate_view", { section: "access_gate" });
  }
  if (document.body.classList.contains("page-library")) {
    send("library_view", { section: "library" });
    const seenCards = new Set();
    const cards = Array.from(document.querySelectorAll("[data-library-novel-card]"));
    if ("IntersectionObserver" in window) {
      const observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          const card = entry.target;
          const novelId = Number(card.dataset.novelId || 0);
          if (!novelId || seenCards.has(novelId)) return;
          seenCards.add(novelId);
          send("novel_impression", { novel_id: novelId, section: card.closest("[data-library-section]")?.dataset?.librarySection || "library" });
          observer.unobserve(card);
        });
      }, { threshold: 0.35 });
      cards.forEach(function (card) { observer.observe(card); });
    }
    let searchTimer = null;
    document.getElementById("librarySearchInput")?.addEventListener("input", function (event) {
      window.clearTimeout(searchTimer);
      searchTimer = window.setTimeout(function () {
        const value = String(event.target.value || "").trim();
        if (value) send("library_search", { section: "library", value_text: value, value_int: value.length });
      }, 650);
    });
  }
  if (document.body.classList.contains("page-novel")) {
    send("toc_open", { section: "toc" });
  }
  if (document.body.classList.contains("page-chapter")) {
    const page = document.querySelector("[data-chapter-page]");
    if (page?.dataset?.isLocked === "true") {
      send("access_denied", { section: "reader", action: "chapter_locked" });
      send("paywall_view", { section: "paywall" });
    } else if (page) {
      trackChapterOpen(page.dataset.chapterId, page.dataset.novelId, { initial: true });
    }
  }

  document.addEventListener("zefirki:reading-progress-visible", function (event) {
    const item = event.detail || {};
    trackChapterOpen(item.chapterId, item.novelId, { reader_progress: true });
  });
  document.addEventListener("zefirki:chapter-swipe-navigate", function (event) {
    const direction = String(event.detail?.direction || "");
    if (direction === "previous") send("chapter_previous", { section: "reader", action: "vertical_swipe" });
    if (direction === "next") send("chapter_next", { section: "reader", action: "vertical_swipe" });
  });
  document.addEventListener("zefirki:analytics-progress", function (event) {
    const item = event.detail || {};
    const chapterId = String(item.chapterId || "");
    const novelId = Number(item.novelId || 0) || null;
    const progress = Math.max(0, Math.min(1, Number(item.scrollPosition || 0)));
    if (!chapterId) return;
    trackChapterOpen(chapterId, novelId, { progress_detected: true });
    const percent = Math.round(progress * 100);
    const checkpoints = [10, 25, 50, 75, 90, 100];
    const last = progressSent.get(chapterId) || 0;
    checkpoints.forEach(function (checkpoint) {
      if (percent >= checkpoint && last < checkpoint) {
        send("chapter_progress", { novel_id: novelId, chapter_id: chapterId, section: "reader", value_int: checkpoint, value_float: progress });
      }
    });
    progressSent.set(chapterId, Math.max(last, percent));
    if (percent >= 90 && !completedSent.has(chapterId)) {
      completedSent.add(chapterId);
      send("chapter_complete", { novel_id: novelId, chapter_id: chapterId, section: "reader", value_int: percent, value_float: progress });
    }
  });

  document.addEventListener("click", function (event) {
    const target = event.target;
    if (!target || !target.closest) return;
    const subscribe = target.closest("[data-access-subscribe]");
    if (subscribe) send("main_group_join_click", { section: "access_gate", action: "subscribe" });

    const card = target.closest("[data-library-novel-card]");
    if (card && !target.closest("[data-card-menu-button], button")) {
      send("novel_open", { novel_id: Number(card.dataset.novelId || 0) || null, section: "library" });
    }
    const filter = target.closest("[data-quick-filter], [data-filter-chip]");
    if (filter) {
      send("library_filter", { section: "library", value_text: filter.dataset.quickFilter || filter.dataset.filterChip || filter.textContent || "" });
    }
    const readButton = target.closest("#novelReadButton");
    if (readButton) {
      const continueReading = /продолж/i.test(String(readButton.textContent || ""));
      send(continueReading ? "continue_reading_click" : "start_reading_click", { section: "toc" });
    }
    const chapterRow = target.closest("[data-chapter-row]");
    if (chapterRow) {
      const href = String(chapterRow.getAttribute("href") || "");
      send("start_reading_click", { section: "toc", chapter_id: String(chapterRow.dataset.chapterId || "") || null, action: href ? "chapter_select" : "" });
    }
    const subscriptionLink = target.closest(".chapter-access-purchase-button, [data-paywall-unlock-open]");
    if (subscriptionLink) {
      send("subscription_click", { section: "paywall", action: subscriptionLink.matches("[data-paywall-unlock-open]") ? "open_options" : "purchase_link" });
    }
    const previous = target.closest(".reader-floating-prev");
    if (previous) send("chapter_previous", { section: "reader" });
    const next = target.closest(".reader-floating-next");
    if (next) send("chapter_next", { section: "reader" });
    const settingsOpen = target.closest("[data-zb-global-settings], [data-zb-reader-settings], [data-reader-settings-toggle]");
    if (settingsOpen) send("settings_open", { section: "settings" });
    const statsTab = target.closest('[data-zb-tab="stats"]');
    if (statsTab) send("stats_view", { section: "settings" });
    const setting = target.closest("[data-zb-setting]");
    if (setting) send("setting_change", { section: "settings", action: String(setting.dataset.zbSetting || ""), value_text: String(setting.dataset.zbValue || "") });
    const menuAction = target.closest("[data-card-menu-action]");
    if (menuAction) {
      const action = String(menuAction.dataset.cardMenuAction || "");
      const mapping = { favorite: "favorite_add", "remove-favorite": "favorite_remove", "mark-read": "completed_add", "unmark-read": "completed_remove" };
      if (mapping[action]) send(mapping[action], { section: "library", action });
    }
  }, true);

  document.addEventListener("change", function (event) {
    const select = event.target?.closest?.("[data-zb-select-setting]");
    if (select) send("setting_change", { section: "settings", action: String(select.dataset.zbSelectSetting || ""), value_text: String(select.value || "") });
  }, true);

  window.addEventListener("pagehide", function () {
    const seconds = Math.max(0, Math.round((Date.now() - pageStartedAt) / 1000));
    send("app_close", { section: "app", value_int: seconds, keepalive: true });
  });
})();
