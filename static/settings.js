(() => {
  'use strict';

  const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  if (tg) {
    try {
      tg.ready();
      tg.expand();
      document.documentElement.dataset.tgTheme = tg.colorScheme || 'light';
    } catch (_) {}
  }

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  function showToast(message) {
    const toast = $('[data-toast]') || document.createElement('div');
    if (!toast.dataset.toast) {
      toast.className = 'quiet-toast';
      toast.dataset.toast = '';
      document.body.appendChild(toast);
    }
    toast.textContent = message;
    toast.hidden = false;
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(() => { toast.hidden = true; }, 2000);
  }

  function hideOneTimeHint() {
    const hint = $('[data-one-time-hint]');
    if (!hint) return;
    const key = 'zbz-library-hint-seen-v111';
    try {
      if (localStorage.getItem(key) === '1') {
        hint.classList.add('is-hidden');
        return;
      }
      localStorage.setItem(key, '1');
    } catch (_) {
      hint.classList.add('is-hidden');
    }
  }

  function initCardMenus() {
    $$('[data-card-menu]').forEach((button) => {
      button.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopPropagation();
        showToast('Меню книги появится здесь, карточка не перекрывается.');
      });
    });
  }

  function initChapterSort() {
    const button = $('[data-chapter-sort-toggle]');
    const list = $('[data-chapter-list]');
    if (!button || !list) return;
    button.addEventListener('click', () => {
      const order = button.dataset.sortOrder === 'desc' ? 'asc' : 'desc';
      button.dataset.sortOrder = order;
      const label = $('[data-chapter-sort-label]', button);
      if (label) label.textContent = order === 'desc' ? 'Сортировка: с конца' : 'Сортировка: по порядку';
      const rows = $$('[data-chapter-row]', list);
      rows.sort((a, b) => {
        const av = Number(a.dataset.sortValue || 0);
        const bv = Number(b.dataset.sortValue || 0);
        return order === 'desc' ? bv - av : av - bv;
      }).forEach((row) => list.appendChild(row));
    });
  }

  function initChapterJump() {
    $$('[data-chapter-jump]').forEach((button) => {
      button.addEventListener('click', () => {
        const target = button.dataset.chapterJump === 'end' ? $('#chapterListEnd') : $('#chapterListStart');
        if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    });
  }

  function initReaderProgress() {
    const page = $('[data-chapter-page]');
    if (!page || page.dataset.isLocked === 'true') return;
    const key = `zbz-progress:${page.dataset.chapterId || location.pathname}`;
    let ticking = false;
    window.addEventListener('scroll', () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => {
        ticking = false;
        const max = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
        const progress = Math.min(1, Math.max(0, window.scrollY / max));
        try { localStorage.setItem(key, String(progress)); } catch (_) {}
      });
    }, { passive: true });
  }

  function initReadButton() {
    const button = $('#novelReadButton');
    if (!button) return;
    const novelPage = $('[data-novel-page]');
    if (!novelPage) return;
    const key = `zbz-last-chapter:${novelPage.dataset.novelId}`;
    try {
      const saved = localStorage.getItem(key);
      if (saved) {
        button.href = `/chapter/${encodeURIComponent(saved)}`;
        button.textContent = 'Продолжить чтение';
      }
    } catch (_) {}
  }

  document.addEventListener('DOMContentLoaded', () => {
    hideOneTimeHint();
    initCardMenus();
    initChapterSort();
    initChapterJump();
    initReaderProgress();
    initReadButton();
  });
})();
