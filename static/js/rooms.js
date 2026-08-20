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
    this.initExistingMessages();
    this.scrollToBottom();
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

  initEventListeners() {
    if (this.formEl) {
      this.formEl.addEventListener('submit', (e) => {
        e.preventDefault();
        this.sendMessage();
      });
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

  scrollToBottom() {
    if (this.streamEl) {
      this.streamEl.scrollTop = this.streamEl.scrollHeight;
    }
  }

  escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }
}

window.RoomChatClient = RoomChatClient;
