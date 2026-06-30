(function () {
  'use strict';

  const tg = window.Telegram && window.Telegram.WebApp;
  if (tg) {
    try {
      tg.ready();
      tg.expand();
    } catch (_) {}
  }

  document.querySelectorAll('[data-spoiler]').forEach((button) => {
    button.addEventListener('click', () => {
      button.textContent = button.dataset.spoiler || 'спойлер';
      button.classList.remove('tag-spoiler-reveal');
      button.disabled = true;
    });
  });

  document.querySelectorAll('[data-collapsible-description]').forEach((root) => {
    const content = root.querySelector('[data-description-content]');
    const button = root.querySelector('[data-description-toggle]');
    if (!content || !button) return;
    const collapsedHeight = 168;
    if (content.scrollHeight <= collapsedHeight + 20) {
      button.hidden = true;
      return;
    }
    content.style.maxHeight = collapsedHeight + 'px';
    content.style.overflow = 'hidden';
    button.addEventListener('click', () => {
      const expanded = root.dataset.expanded === 'true';
      root.dataset.expanded = String(!expanded);
      content.style.maxHeight = expanded ? collapsedHeight + 'px' : 'none';
      button.textContent = expanded ? 'Ещё' : 'Свернуть';
    });
  });

  document.querySelectorAll('[data-chapter-jump]').forEach((button) => {
    button.addEventListener('click', () => {
      const targetId = button.dataset.chapterJump === 'end' ? 'chapterListEnd' : 'chapterListStart';
      document.getElementById(targetId)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });

  const sortButton = document.querySelector('[data-chapter-sort-toggle]');
  const chapterList = document.querySelector('[data-chapter-list]');
  if (sortButton && chapterList) {
    sortButton.addEventListener('click', () => {
      const rows = Array.from(chapterList.querySelectorAll('[data-chapter-row]'));
      const nextOrder = sortButton.dataset.sortOrder === 'asc' ? 'desc' : 'asc';
      sortButton.dataset.sortOrder = nextOrder;
      rows.sort((a, b) => {
        const av = Number(a.dataset.sortValue || 0);
        const bv = Number(b.dataset.sortValue || 0);
        return nextOrder === 'asc' ? av - bv : bv - av;
      });
      rows.forEach((row) => chapterList.appendChild(row));
      const label = sortButton.querySelector('[data-chapter-sort-label]');
      if (label) label.textContent = nextOrder === 'asc' ? 'Сортировка: по порядку' : 'Сортировка: с конца';
    });
  }

  const paidToggle = document.querySelector('[data-paid-toggle]');
  if (paidToggle) {
    paidToggle.addEventListener('click', () => {
      document.querySelectorAll('[data-paid-extra]').forEach((row) => { row.hidden = false; });
      paidToggle.closest('[data-paid-fade]')?.remove();
    });
  }

  const chapterPage = document.querySelector('[data-chapter-page]');
  if (chapterPage && chapterPage.dataset.isLocked !== 'true') {
    const payload = {
      novelId: chapterPage.dataset.novelId,
      novelTitle: chapterPage.dataset.novelTitle,
      chapterId: chapterPage.dataset.chapterId,
      chapterTitle: chapterPage.dataset.chapterTitle,
      updatedAt: new Date().toISOString()
    };
    try { localStorage.setItem('zbz:continue', JSON.stringify(payload)); } catch (_) {}
  }

  document.querySelectorAll('[data-refresh-access]').forEach((button) => {
    button.addEventListener('click', () => {
      button.textContent = 'Проверяем…';
      setTimeout(() => { button.textContent = 'Доступ не найден. Попробуйте позже'; }, 650);
    });
  });
})();
