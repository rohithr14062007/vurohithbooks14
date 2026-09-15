function switchAuthSubTab(mode) {
  const loginTab = document.getElementById('auth-tab-login');
  const signupTab = document.getElementById('auth-tab-signup');
  const loginSub = document.getElementById('auth-sub-login');
  const signupSub = document.getElementById('auth-sub-signup');

  if (mode === 'signup') {
    if (loginTab) loginTab.classList.remove('active');
    if (signupTab) signupTab.classList.add('active');
    if (loginSub) {
      loginSub.style.display = 'none';
      loginSub.classList.remove('active');
    }
    if (signupSub) {
      signupSub.style.display = 'block';
      signupSub.classList.add('active');
    }
  } else {
    if (loginTab) loginTab.classList.add('active');
    if (signupTab) signupTab.classList.remove('active');
    if (loginSub) {
      loginSub.style.display = 'block';
      loginSub.classList.add('active');
    }
    if (signupSub) {
      signupSub.style.display = 'none';
      signupSub.classList.remove('active');
    }
  }
}

function showSection(id) {
  let targetId = id;
  let subMode = null;

  if (id === 'login' || id === 'signup') {
    targetId = 'auth';
    subMode = id;
  }

  const sections = document.querySelectorAll('.panel');
  sections.forEach((section) => section.classList.remove('active'));

  const target = document.getElementById(targetId);
  if (target) target.classList.add('active');

  document.querySelectorAll('.nav-link').forEach((button) => {
    const isActive = button.dataset.section === id || button.dataset.section === targetId;
    button.classList.toggle('active', isActive);
  });

  if (subMode) {
    switchAuthSubTab(subMode);
  }

  if (id === 'favorites') {
    renderFavorites();
  }
}

function getBookmarks() {
  try {
    return JSON.parse(localStorage.getItem('vurohith_bookmarks') || '[]');
  } catch (e) {
    return [];
  }
}

function saveBookmarks(bookmarks) {
  try {
    localStorage.setItem('vurohith_bookmarks', JSON.stringify(bookmarks));
  } catch (e) {}
}

function toggleBookmark(bookId) {
  let bookmarks = getBookmarks();
  const index = bookmarks.indexOf(bookId.toString());
  if (index >= 0) {
    bookmarks.splice(index, 1);
  } else {
    bookmarks.push(bookId.toString());
  }
  saveBookmarks(bookmarks);
  updateBookmarkUI();
}

function updateBookmarkUI() {
  const bookmarks = getBookmarks();
  document.querySelectorAll('.bookmark-btn').forEach((btn) => {
    const bid = btn.dataset.bookId;
    const isBookmarked = bookmarks.includes(bid.toString());
    btn.classList.toggle('active', isBookmarked);
    btn.textContent = isBookmarked ? '❤️' : '♡';
  });
}

function renderFavorites() {
  const bookmarks = getBookmarks();
  const favContainer = document.getElementById('favorites-grid-container');
  const noFavMsg = document.getElementById('no-favorites-msg');
  if (!favContainer) return;

  const allBookCards = document.querySelectorAll('#books-grid-container .book-card');
  let count = 0;

  favContainer.querySelectorAll('.book-card').forEach((card) => card.remove());

  allBookCards.forEach((card) => {
    const bid = card.dataset.bookId;
    if (bookmarks.includes(bid.toString())) {
      const clone = card.cloneNode(true);
      const bookmarkBtn = clone.querySelector('.bookmark-btn');
      if (bookmarkBtn) {
        bookmarkBtn.addEventListener('click', () => {
          toggleBookmark(bid);
          renderFavorites();
        });
      }
      const previewBtn = clone.querySelector('.preview-trigger');
      if (previewBtn) {
        previewBtn.addEventListener('click', () => {
          const title = previewBtn.dataset.bookTitle || 'Book';
          openPreviewModal(bid, title);
        });
      }
      favContainer.appendChild(clone);
      count++;
    }
  });

  if (noFavMsg) {
    noFavMsg.style.display = count === 0 ? 'block' : 'none';
  }
}

function openPreviewModal(bookId, title) {
  const previewModal = document.getElementById('preview-modal');
  const previewFrame = document.getElementById('preview-frame');
  const modalTitle = document.getElementById('modal-title');
  const newtabBtn = document.getElementById('preview-newtab-btn');

  if (!previewModal || !previewFrame) return;
  const previewUrl = `/preview/${bookId}`;
  previewFrame.src = previewUrl;
  if (modalTitle) modalTitle.textContent = title ? `Preview — ${title}` : 'Book Preview';
  if (newtabBtn) newtabBtn.href = previewUrl;
  previewModal.classList.remove('hidden');
}

function closePreviewModal() {
  const previewModal = document.getElementById('preview-modal');
  const previewFrame = document.getElementById('preview-frame');
  if (previewModal) previewModal.classList.add('hidden');
  if (previewFrame) previewFrame.src = '';
}

function populateEditModal(btn) {
  const modal = document.getElementById('edit-book-modal');
  const form = document.getElementById('edit-book-form');
  if (!modal || !form) return;

  const id = btn.dataset.bookId;
  form.action = `/admin/edit-book/${id}`;
  document.getElementById('edit-book-title').value = btn.dataset.title || '';
  document.getElementById('edit-book-author').value = btn.dataset.author || '';
  document.getElementById('edit-book-category').value = btn.dataset.categoryId || '';
  document.getElementById('edit-book-description').value = btn.dataset.description || '';

  modal.classList.remove('hidden');
}

function closeEditModal() {
  const modal = document.getElementById('edit-book-modal');
  if (modal) modal.classList.add('hidden');
}

document.addEventListener('DOMContentLoaded', () => {
  const isMainPage = document.getElementById('landing') || document.getElementById('books') || document.getElementById('auth');
  if (isMainPage) {
    const defaultSection = document.body.dataset.defaultSection || (document.body.classList.contains('logged-in') ? 'books' : 'landing');
    showSection(defaultSection);
  }

  document.querySelectorAll('.nav-link').forEach((button) => {
    button.addEventListener('click', () => {
      const target = button.dataset.section;
      if (target) showSection(target);
    });
  });

  const tabGroups = [
    {
      tabs: document.querySelectorAll('.admin-tab'),
      panels: document.querySelectorAll('.admin-panel'),
    },
    {
      tabs: document.querySelectorAll('.settings-tab'),
      panels: document.querySelectorAll('.settings-panel'),
    },
  ];

  tabGroups.forEach(({ tabs, panels }) => {
    tabs.forEach((tab) => {
      tab.addEventListener('click', () => {
        const target = tab.dataset.target;
        if (!target) return;

        tabs.forEach((item) => item.classList.toggle('active', item === tab));
        panels.forEach((panel) => {
          panel.classList.toggle('active', panel.id === target);
        });
      });
    });
  });

  // Bookmark initialization & event handlers
  updateBookmarkUI();
  document.querySelectorAll('.bookmark-btn').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleBookmark(btn.dataset.bookId);
    });
  });

  // Auto-dismiss flash alerts after 5 seconds
  document.querySelectorAll('.flash').forEach((flashEl) => {
    setTimeout(() => {
      flashEl.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
      flashEl.style.opacity = '0';
      flashEl.style.transform = 'translateY(-6px)';
      setTimeout(() => {
        if (flashEl.parentNode) flashEl.remove();
      }, 500);
    }, 5000);
  });

  // Preview modal handlers
  document.querySelectorAll('.preview-trigger').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      openPreviewModal(btn.dataset.bookId, btn.dataset.bookTitle);
    });
  });

  const closePreviewBtn = document.getElementById('close-preview-modal');
  if (closePreviewBtn) closePreviewBtn.addEventListener('click', closePreviewModal);

  const previewModal = document.getElementById('preview-modal');
  if (previewModal) {
    previewModal.addEventListener('click', (e) => {
      if (e.target === previewModal) closePreviewModal();
    });
  }

  // Edit modal handlers
  document.querySelectorAll('.edit-book-trigger').forEach((btn) => {
    btn.addEventListener('click', () => populateEditModal(btn));
  });

  const closeEditBtn = document.getElementById('close-edit-modal');
  if (closeEditBtn) closeEditBtn.addEventListener('click', closeEditModal);

  // Theme Toggle (Dark / Light Mode)
  const themeBtn = document.getElementById('theme-toggle');
  const savedTheme = localStorage.getItem('vurohith_theme') || 'dark';

  if (savedTheme === 'light') {
    document.body.classList.add('light-theme');
    if (themeBtn) themeBtn.textContent = '☀️ Light';
  } else {
    if (themeBtn) themeBtn.textContent = '🌙 Dark';
  }

  if (themeBtn) {
    themeBtn.addEventListener('click', () => {
      document.body.classList.toggle('light-theme');
      const isLight = document.body.classList.contains('light-theme');
      themeBtn.textContent = isLight ? '☀️ Light' : '🌙 Dark';
      localStorage.setItem('vurohith_theme', isLight ? 'light' : 'dark');
    });
  }

  // Preview Modal Fullscreen Toggle
  const fsBtn = document.getElementById('preview-fullscreen-btn');
  const modalBox = document.getElementById('preview-modal-box');
  if (fsBtn && modalBox) {
    fsBtn.addEventListener('click', () => {
      modalBox.classList.toggle('is-fullscreen');
      fsBtn.textContent = modalBox.classList.contains('is-fullscreen') ? '🗗 Compress' : '⛶ Fullscreen';
    });
  }

  // Reading Status Tracker Logic
  function getReadingStatuses() {
    try {
      return JSON.parse(localStorage.getItem('vurohith_reading_status') || '{}');
    } catch (e) {
      return {};
    }
  }

  function updateReadingStatusUI() {
    const statuses = getReadingStatuses();
    document.querySelectorAll('.status-select').forEach((select) => {
      const bid = select.dataset.bookId;
      const status = statuses[bid] || '';
      select.value = status;

      const badge = document.getElementById(`status-pill-${bid}`);
      if (badge) {
        if (status === 'reading') {
          badge.textContent = '📖 Reading';
          badge.className = 'status-pill-badge reading';
          badge.style.display = 'inline-block';
        } else if (status === 'completed') {
          badge.textContent = '✅ Completed';
          badge.className = 'status-pill-badge completed';
          badge.style.display = 'inline-block';
        } else if (status === 'want') {
          badge.textContent = '📌 Want to Read';
          badge.className = 'status-pill-badge want';
          badge.style.display = 'inline-block';
        } else {
          badge.style.display = 'none';
        }
      }
    });
  }

  updateReadingStatusUI();

  document.querySelectorAll('.status-select').forEach((select) => {
    select.addEventListener('change', () => {
      const bid = select.dataset.bookId;
      const val = select.value;
      const statuses = getReadingStatuses();
      if (val) {
        statuses[bid] = val;
      } else {
        delete statuses[bid];
      }
      localStorage.setItem('vurohith_reading_status', JSON.stringify(statuses));
      updateReadingStatusUI();
    });
  });

  // Live client-side search & category filtering
  const searchInput = document.getElementById('live-search-input');
  const sortSelect = document.getElementById('sort-books-select');
  const catPills = document.querySelectorAll('.cat-pill');
  const bookGrid = document.getElementById('books-grid-container');
  const bookCountBadge = document.getElementById('book-count-badge');

  function filterAndSortBooks() {
    if (!bookGrid) return;
    const query = (searchInput?.value || '').toLowerCase().trim();
    const activePill = document.querySelector('.cat-pill.active');
    const selectedCategory = activePill ? activePill.dataset.category : 'ALL';
    const sortVal = sortSelect?.value || 'recent';

    const cards = Array.from(bookGrid.querySelectorAll('.book-card'));
    let visibleCount = 0;

    cards.forEach((card) => {
      const text = card.textContent.toLowerCase();
      const cardCategory = card.dataset.category || '';
      const matchesSearch = !query || text.includes(query);
      const matchesCategory = selectedCategory === 'ALL' || cardCategory === selectedCategory;

      if (matchesSearch && matchesCategory) {
        card.style.display = 'flex';
        visibleCount++;
      } else {
        card.style.display = 'none';
      }
    });

    cards.sort((a, b) => {
      if (sortVal === 'rating') {
        return (parseFloat(b.dataset.rating) || 0) - (parseFloat(a.dataset.rating) || 0);
      } else if (sortVal === 'downloads') {
        return (parseInt(b.dataset.downloads) || 0) - (parseInt(a.dataset.downloads) || 0);
      } else if (sortVal === 'title') {
        return (a.dataset.title || '').localeCompare(b.dataset.title || '');
      } else if (sortVal === 'author') {
        return (a.dataset.author || '').localeCompare(b.dataset.author || '');
      } else {
        return (parseInt(b.dataset.bookId) || 0) - (parseInt(a.dataset.bookId) || 0);
      }
    });

    cards.forEach((card) => bookGrid.appendChild(card));

    if (bookCountBadge) {
      bookCountBadge.textContent = `${visibleCount} title${visibleCount === 1 ? '' : 's'}`;
    }
  }

  if (searchInput) searchInput.addEventListener('input', filterAndSortBooks);
  if (sortSelect) sortSelect.addEventListener('change', filterAndSortBooks);

  catPills.forEach((pill) => {
    pill.addEventListener('click', () => {
      catPills.forEach((p) => p.classList.remove('active'));
      pill.classList.add('active');
      filterAndSortBooks();
    });
  });
});

// Digital Visitor ID Card Modal functions
function openIdCardModal(name, no, inst, phone) {
  const modal = document.getElementById('idcard-modal');
  if (!modal) return;

  if (name) document.getElementById('card-student-name').textContent = name;
  if (no) document.getElementById('card-student-no').textContent = no;
  if (inst) document.getElementById('card-institution').textContent = inst;
  if (phone) document.getElementById('card-phone').textContent = phone;

  modal.classList.remove('hidden');
}

function closeIdCardModal() {
  const modal = document.getElementById('idcard-modal');
  if (modal) modal.classList.add('hidden');
}

// Forgot Password Modal functions
function openForgotPasswordModal() {
  const modal = document.getElementById('forgot-password-modal');
  if (modal) {
    modal.classList.remove('hidden');
    modal.style.display = 'flex';
  }
}

function closeForgotPasswordModal() {
  const modal = document.getElementById('forgot-password-modal');
  if (modal) {
    modal.classList.add('hidden');
    modal.style.display = 'none';
  }
}

// Recent Activity Modal functions
function openActivityModal() {
  const modal = document.getElementById('activity-modal');
  if (modal) modal.classList.remove('hidden');
}

function closeActivityModal() {
  const modal = document.getElementById('activity-modal');
  if (modal) modal.classList.add('hidden');
}

// Register PWA Service Worker & Install Prompt
let deferredPrompt = null;

window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  deferredPrompt = e;
  const btn = document.getElementById('install-app-btn');
  if (btn) {
    btn.style.display = 'inline-flex';
  }
});

function triggerAppInstall() {
  if (deferredPrompt) {
    deferredPrompt.prompt();
    deferredPrompt.userChoice.then((choiceResult) => {
      if (choiceResult.outcome === 'accepted') {
        console.log('User installed V.U Rohith Books app');
      }
      deferredPrompt = null;
    });
  } else {
    openInstallAppModal();
  }
}

function openInstallAppModal() {
  const modal = document.getElementById('install-app-modal');
  if (modal) {
    modal.classList.remove('hidden');
    modal.style.display = 'flex';
  }
}

function closeInstallAppModal() {
  const modal = document.getElementById('install-app-modal');
  if (modal) {
    modal.classList.add('hidden');
    modal.style.display = 'none';
  }
}

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js')
      .then((reg) => console.log('PWA Service Worker registered:', reg.scope))
      .catch((err) => console.log('Service Worker registration failed:', err));
  });
}