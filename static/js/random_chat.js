/**
 * Nearby Chat — Random Chat Matchmaking Controller
 */

class MatchmakingClient {
  constructor(config = {}) {
    this.config = config;
    this.statusTextEl = document.getElementById('radar-status-text');
    this.cancelBtn = document.getElementById('btn-cancel-search');
    this.retryBtn = document.getElementById('btn-retry-search');
    this.exitBtn = document.getElementById('btn-exit-search');
    this.radarAnimation = document.getElementById('radar-animation');
    this.matchCard = document.getElementById('match-card');
    
    this.timeoutTimer = null;
    this.initWebSocket();
    this.initEventListeners();
  }

  initWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/matching/`;

    this.socket = new RobustWebSocket(wsUrl);

    this.socket.on('open', () => {
      this.startMatching();
    });

    this.socket.on('match_found', (data) => {
      this.handleMatchFound(data);
    });

    this.socket.on('searching', (data) => {
      // Keep customized searching text if present
      if (this.statusTextEl && !this.statusTextEl.textContent.includes('Searching')) {
        this.statusTextEl.textContent = data.message;
      }
    });

    this.socket.on('queue_cancelled', () => {
      if (this.statusTextEl) this.statusTextEl.textContent = "Search cancelled.";
    });
  }

  initEventListeners() {
    if (this.cancelBtn) {
      this.cancelBtn.addEventListener('click', () => {
        this.cancelMatching();
      });
    }

    if (this.retryBtn) {
      this.retryBtn.addEventListener('click', () => {
        this.startMatching();
      });
    }
  }

  startMatching() {
    if (this.radarAnimation) this.radarAnimation.style.display = 'flex';
    if (this.cancelBtn) this.cancelBtn.style.display = 'inline-flex';
    if (this.retryBtn) this.retryBtn.style.display = 'none';
    if (this.exitBtn) this.exitBtn.style.display = 'none';
    if (this.matchCard) this.matchCard.style.display = 'none';

    this.socket.send({
      action: 'join_queue',
      mode: this.config.mode || 'interests',
      interest: this.config.interest || ''
    });

    // Set 25-second timeout for graceful prompt
    clearTimeout(this.timeoutTimer);
    this.timeoutTimer = setTimeout(() => {
      this.handleTimeout();
    }, 25000);
  }

  cancelMatching() {
    clearTimeout(this.timeoutTimer);
    this.socket.send({ action: 'cancel_queue' });
    if (this.statusTextEl) this.statusTextEl.textContent = "Search cancelled.";
    if (this.radarAnimation) this.radarAnimation.style.display = 'none';
    if (this.cancelBtn) this.cancelBtn.style.display = 'none';
    if (this.retryBtn) this.retryBtn.style.display = 'inline-flex';
    if (this.exitBtn) this.exitBtn.style.display = 'inline-flex';
  }

  handleTimeout() {
    this.socket.send({ action: 'cancel_queue' });
    if (this.statusTextEl) this.statusTextEl.textContent = "No one is available right now with these filters. Try again or explore Community Rooms!";
    if (this.radarAnimation) this.radarAnimation.style.display = 'none';
    if (this.cancelBtn) this.cancelBtn.style.display = 'none';
    if (this.retryBtn) this.retryBtn.style.display = 'inline-flex';
    if (this.exitBtn) this.exitBtn.style.display = 'inline-flex';
  }

  handleMatchFound(data) {
    clearTimeout(this.timeoutTimer);
    if (this.statusTextEl) this.statusTextEl.textContent = `Match found with ${data.partner_name}! Connecting...`;
    if (this.radarAnimation) this.radarAnimation.style.display = 'none';
    if (this.cancelBtn) this.cancelBtn.style.display = 'none';
    if (this.exitBtn) this.exitBtn.style.display = 'none';

    if (this.matchCard) {
      this.matchCard.style.display = 'flex';
      const nameEl = document.getElementById('match-partner-name');
      const avatarEl = document.getElementById('match-partner-avatar');
      if (nameEl) nameEl.textContent = data.partner_name;
      if (avatarEl) avatarEl.src = data.partner_avatar;
    }

    // Seamless redirect to the newly created direct/random conversation
    setTimeout(() => {
      window.location.href = `/chats/${data.conversation_id}/`;
    }, 1200);
  }
}

window.MatchmakingClient = MatchmakingClient;
