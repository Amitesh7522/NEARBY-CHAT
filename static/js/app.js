/**
 * Nearby Chat — Global Application Core
 * Manages Drawer menu, Toasts, Modals, and notifications.
 */

document.addEventListener('DOMContentLoaded', () => {
  initDrawer();
  initModals();
  initNotificationSocket();
});

/* Hamburger Drawer Menu */
function initDrawer() {
  const toggleBtn = document.getElementById('drawer-toggle-btn');
  const drawer = document.getElementById('drawer-menu');
  const overlay = document.getElementById('drawer-overlay');
  const closeBtn = document.getElementById('drawer-close-btn');

  if (!toggleBtn || !drawer || !overlay) return;

  function openDrawer() {
    drawer.classList.add('active');
    overlay.classList.add('active');
    document.body.style.overflow = 'hidden';
  }

  function closeDrawer() {
    drawer.classList.remove('active');
    overlay.classList.remove('active');
    document.body.style.overflow = '';
  }

  toggleBtn.addEventListener('click', openDrawer);
  if (closeBtn) closeBtn.addEventListener('click', closeDrawer);
  overlay.addEventListener('click', closeDrawer);
}

/* Modal Dialogs */
function initModals() {
  window.openModal = function(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
      modal.classList.add('active');
      document.body.style.overflow = 'hidden';
    }
  };

  window.closeModal = function(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
      modal.classList.remove('active');
      document.body.style.overflow = '';
    }
  };

  document.querySelectorAll('.modal-overlay').forEach(overlay => {
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) {
        overlay.classList.remove('active');
        document.body.style.overflow = '';
      }
    });
  });
}

/* Toast Notifications */
window.showToast = function(message, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <span>${message}</span>
    <button onclick="this.parentElement.remove()" style="opacity:0.6;font-size:16px;">&times;</button>
  `;

  container.appendChild(toast);
  setTimeout(() => {
    if (toast.parentElement) toast.remove();
  }, 4000);
};

/* Realtime Notification & Online Presence Socket */
function initNotificationSocket() {
  if (!window.CURRENT_USER_ID) return;

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const socketUrl = `${protocol}//${window.location.host}/ws/notifications/`;
  
  let ws = null;
  function connect() {
    ws = new WebSocket(socketUrl);
    ws.onmessage = (e) => {
      const data = JSON.parse(e.data);
      if (data.type === 'notification') {
        window.showToast(data.title + ': ' + data.message, 'info');
      }
    };
    ws.onclose = () => {
      setTimeout(connect, 3000);
    };
  }
  connect();
}
