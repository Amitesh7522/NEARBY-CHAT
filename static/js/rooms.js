/**
 * Nearby Chat — Community Rooms Real-time Client
 */

class RoomChatClient {
  constructor(config) {
    this.roomId = config.roomId;
    this.currentUserId = config.currentUserId;
    this.streamEl = document.getElementById('room-message-stream');
    this.inputEl = document.getElementById('room-chat-input');
    this.formEl = document.getElementById('room-chat-form');

    this.renderedMsgIds = new Set();
    this.initWebSocket();
    this.initEventListeners();
    this.initViewportHandler();
    this.initExistingMessages();
    this.scrollToBottom();
    requestAnimationFrame(() => this.scrollToBottom());
    setTimeout(() => this.scrollToBottom(), 60);
    setTimeout(() => this.scrollToBottom(), 250);
  }

  initWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/rooms/${this.roomId}/`;

    this.socket = new RobustWebSocket(wsUrl);

    this.socket.on('room_message', (data) => {
      this.handleIncomingMessage(data);
    });

    this.socket.on('error', (data) => {
      const errorText = data.message || "Message blocked: Please keep conversations respectful and avoid abusive language or slurs.";
      if (typeof window.showToast === 'function') {
        window.showToast(errorText, 'error');
      } else {
        alert(errorText);
      }
    });
  }

  initExistingMessages() {
    document.querySelectorAll('.room-msg-item').forEach(el => {
      const id = el.dataset.messageId;
      if (id) this.renderedMsgIds.add(id);
    });
  }

    if (this.formEl) {
      this.formEl.addEventListener('submit', (e) => {
        e.preventDefault();
        this.sendMessage();
      });
    }

    if (this.inputEl) {
      this.inputEl.addEventListener('focus', () => {
        setTimeout(() => this.scrollToBottom(), 120);
        setTimeout(() => this.scrollToBottom(), 300);
      });
    }
  }

  initViewportHandler() {
    if (window.visualViewport) {
      const handleResize = () => {
        if (window.innerWidth <= 767) {
          const appHeader = document.querySelector('.app-header');
          const headerH = appHeader ? appHeader.offsetHeight : 0;
          const usableH = window.visualViewport.height - headerH;
          const chatWindow = document.querySelector('.chat-window');
          if (chatWindow && usableH > 150) {
            chatWindow.style.height = `${usableH}px`;
          }
        }
        this.scrollToBottom();
      };
      window.visualViewport.addEventListener('resize', handleResize);
      window.visualViewport.addEventListener('scroll', handleResize);
    }
  }

  sendMessage() {
    const text = this.inputEl.value.trim();
    if (!text) return;

    const clientMsgId = 'rm_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    this.inputEl.value = '';

    this.socket.send({
      action: 'send_message',
      content: text,
      client_msg_id: clientMsgId,
    });
  }

  handleIncomingMessage(data) {
    if (this.renderedMsgIds.has(data.message_id)) return;

    const isOutgoing = String(data.sender_id) === String(this.currentUserId);
    const row = document.createElement('div');
    row.className = `message-bubble-row ${isOutgoing ? 'outgoing' : 'incoming'} room-msg-item`;
    row.dataset.messageId = data.message_id;

    const timeStr = new Date(data.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const senderHeader = !isOutgoing ? `<div style="font-size:11px;font-weight:700;margin-bottom:2px;color:var(--primary);">${this.escapeHtml(data.sender_name)}</div>` : '';

    row.innerHTML = `
      <div class="message-bubble">
        ${senderHeader}
        <div class="message-text">${this.escapeHtml(data.content)}</div>
        <div class="message-meta">
          <span>${timeStr}</span>
        </div>
      </div>
    `;

    this.streamEl.appendChild(row);
    this.renderedMsgIds.add(data.message_id);
    this.scrollToBottom();
  }

  scrollToBottom(smooth = false) {
    if (!this.streamEl) return;
    const targetScroll = this.streamEl.scrollHeight;
    if (smooth) {
      this.streamEl.scrollTo({ top: targetScroll, behavior: 'smooth' });
    } else {
      this.streamEl.scrollTop = targetScroll;
    }
    requestAnimationFrame(() => {
      if (this.streamEl) this.streamEl.scrollTop = this.streamEl.scrollHeight;
    });
  }

  escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }
}

window.RoomChatClient = RoomChatClient;
