/**
 * Nearby Chat — PWA Registration, Install Prompt & Push Notification Sync
 */

let deferredInstallPrompt = null;

// Register Service Worker
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js')
      .then((reg) => {
        window.SW_REGISTRATION = reg;
      })
      .catch((err) => {
        console.warn('Service worker registration failed:', err);
      });
  });
}

// Capture BeforeInstallPrompt Event for Mobile / Desktop PWA installation
window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  deferredInstallPrompt = e;

  // Show tasteful install prompt banner if not already dismissed in this session
  if (!sessionStorage.getItem('pwa_install_dismissed')) {
    showPWAInstallBanner();
  }
});

function showPWAInstallBanner() {
  const existing = document.getElementById('pwa-install-banner');
  if (existing) return;

  const banner = document.createElement('div');
  banner.id = 'pwa-install-banner';
  banner.style.cssText = `
    position: fixed;
    bottom: 72px;
    left: 50%;
    transform: translateX(-50%);
    width: calc(100% - 32px);
    max-width: 480px;
    background: var(--bg-surface);
    border: 1px solid var(--primary);
    border-radius: var(--radius-xl);
    padding: 12px 16px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.4);
    z-index: 1000;
    animation: slideUp 0.3s cubic-bezier(0.16, 1, 0.3, 1);
  `;

  banner.innerHTML = `
    <div style="display: flex; align-items: center; gap: 10px; min-width: 0;">
      <img src="/static/images/icon.svg" style="width: 32px; height: 32px; border-radius: 8px; flex-shrink: 0;" alt="App Icon">
      <div style="min-width: 0;">
        <div style="font-weight: 700; font-size: 13px; color: var(--text-primary);">Install Nearby Chat</div>
        <div style="font-size: 11px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">Fast, native experience & alerts</div>
      </div>
    </div>
    <div style="display: flex; align-items: center; gap: 8px; flex-shrink: 0;">
      <button type="button" id="btn-pwa-install" class="btn btn-sm btn-primary" style="font-size: 12px; padding: 6px 12px;">Install</button>
      <button type="button" id="btn-pwa-dismiss" class="btn-icon" style="font-size: 16px; color: var(--text-muted); border: none; background: transparent; cursor: pointer;">&times;</button>
    </div>
  `;

  document.body.appendChild(banner);

  document.getElementById('btn-pwa-install').addEventListener('click', () => {
    if (deferredInstallPrompt) {
      deferredInstallPrompt.prompt();
      deferredInstallPrompt.userChoice.then((choiceResult) => {
        if (choiceResult.outcome === 'accepted') {
          banner.remove();
        }
        deferredInstallPrompt = null;
      });
    }
  });

  document.getElementById('btn-pwa-dismiss').addEventListener('click', () => {
    banner.remove();
    sessionStorage.setItem('pwa_install_dismissed', 'true');
  });
}

// Push Notification Helper
window.requestPushNotifications = async function() {
  if (!('Notification' in window) || !('serviceWorker' in navigator)) {
    if (typeof window.showToast === 'function') {
      window.showToast("Push notifications are not supported by your browser.", "info");
    }
    return false;
  }

  const permission = await Notification.requestPermission();
  if (permission === 'granted') {
    if (typeof window.showToast === 'function') {
      window.showToast("Push notifications enabled!", "success");
    }
    
    // Sync with backend subscription API
    try {
      const reg = await navigator.serviceWorker.ready;
      let sub = await reg.pushManager.getSubscription();
      if (!sub) {
        sub = await reg.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: 'BEl62iUYgUivxIkv69yViEuiBIa-Ib9-SkvMeAtA3LFgDzkrxZJjSgSnfckjBJuBkr3qBUYIHBQFLXYp5Nksh8U'
        }).catch(() => null);
      }

      if (sub) {
        const subData = sub.toJSON();
        await fetch('/notifications/push-subscribe/', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken') || '',
          },
          body: JSON.stringify({
            endpoint: sub.endpoint,
            p256dh: subData.keys ? subData.keys.p256dh : '',
            auth: subData.keys ? subData.keys.auth : '',
          })
        });
      }
    } catch (err) {
      console.warn("Could not sync push subscription:", err);
    }
    return true;
  } else {
    if (typeof window.showToast === 'function') {
      window.showToast("Notification permissions were not granted.", "info");
    }
    return false;
  }
};

function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}
