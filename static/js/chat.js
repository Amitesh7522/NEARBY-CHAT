/**
 * Nearby Chat — 1-on-1 Direct Chat Client
 */

class ChatClient {
  constructor(config) {
    this.conversationId = config.conversationId;
    this.currentUserId = config.currentUserId;
    this.streamEl = document.getElementById('message-stream');
    this.inputEl = document.getElementById('chat-input');
    this.formEl = document.getElementById('chat-form');
    this.typingEl = document.getElementById('typing-indicator');
    this.loadMoreBtn = document.getElementById('load-more-btn');

    this.renderedMsgIds = new Set();
    this.typingTimeout = null;
    this.isLoadingMore = false;
    this.hasMoreMessages = true;

    this.initWebSocket();
    this.initEventListeners();
    this.initViewportHandler();
    this.initExistingMessages();
    this.scrollToBottom();
    // Multi-pass scroll ensures images/fonts that load asynchronously keep scroll at bottom
    requestAnimationFrame(() => this.scrollToBottom());
    setTimeout(() => this.scrollToBottom(), 60);
    setTimeout(() => this.scrollToBottom(), 250);
  }

  initWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/chat/${this.conversationId}/`;

    this.socket = new RobustWebSocket(wsUrl);

    this.socket.on('open', () => {
      this.sendReadReceipt();
    });

    this.socket.on('chat_message', (data) => {
      this.handleIncomingMessage(data);
    });

    this.socket.on('read_receipt', (data) => {
      this.handleReadReceipt(data);
    });

    this.socket.on('typing', (data) => {
      this.handleTyping(data);
    });

    this.socket.on('error', (data) => {
      this.handleErrorMessage(data);
    });
  }

  initExistingMessages() {
    document.querySelectorAll('.message-bubble-row').forEach(row => {
      const msgId = row.dataset.messageId;
      if (msgId) this.renderedMsgIds.add(msgId);
    });
  }

  initEventListeners() {
    if (this.formEl) {
      this.formEl.addEventListener('submit', (e) => {
        e.preventDefault();
        this.sendMessage();
      });
    }

    if (this.inputEl) {
      this.inputEl.addEventListener('input', () => {
        this.socket.send({ action: 'typing', is_typing: true });
        clearTimeout(this.typingTimeout);
        this.typingTimeout = setTimeout(() => {
          this.socket.send({ action: 'typing', is_typing: false });
        }, 1500);
      });

      this.inputEl.addEventListener('focus', () => {
        setTimeout(() => this.scrollToBottom(), 120);
        setTimeout(() => this.scrollToBottom(), 300);
      });
    }

    if (this.loadMoreBtn) {
      this.loadMoreBtn.addEventListener('click', () => {
        this.loadOlderMessages();
      });
    }

    if (this.streamEl) {
      this.streamEl.addEventListener('scroll', () => {
        if (this.streamEl.scrollTop === 0 && this.hasMoreMessages && !this.isLoadingMore) {
          this.loadOlderMessages();
        }
      });
    }
  }

  sendMessage() {
    const text = this.inputEl.value.trim();
    if (!text) return;

    // Instant Real-Time Content Moderation Guard
    if (window.ContentModerator && window.ContentModerator.isAbusive(text)) {
      const warningText = "⚠️ Message blocked: Please keep conversations respectful and avoid abusive language or slurs.";
      if (typeof window.showToast === 'function') {
        window.showToast(warningText, 'error');
      } else {
        alert(warningText);
      }
      this.inputEl.style.borderColor = 'var(--error)';
      setTimeout(() => {
        if (this.inputEl) this.inputEl.style.borderColor = '';
      }, 2000);
      return;
    }

    const clientMsgId = 'c_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    
    // Clear input immediately
    this.inputEl.value = '';

    // Optimistic render
    this.renderMessageRow({
      message_id: clientMsgId,
      client_msg_id: clientMsgId,
      sender_id: this.currentUserId,
      content: text,
      created_at: new Date().toISOString(),
      is_pending: true,
    }, true);

    this.scrollToBottom();

    // Dispatch over socket
    this.socket.send({
      action: 'send_message',
      content: text,
      client_msg_id: clientMsgId,
    });
  }

  handleIncomingMessage(data) {
    // If we optimistically rendered it with client_msg_id, update it
    if (data.client_msg_id) {
      const pendingRow = document.querySelector(`[data-message-id="${data.client_msg_id}"]`);
      if (pendingRow) {
        pendingRow.dataset.messageId = data.message_id;
        const tickEl = pendingRow.querySelector('.status-tick');
        if (tickEl) tickEl.innerHTML = '✓';
        this.renderedMsgIds.add(data.message_id);
        return;
      }
    }

    if (this.renderedMsgIds.has(data.message_id)) return;

    this.renderMessageRow(data, true);
    this.renderedMsgIds.add(data.message_id);
    this.scrollToBottom();

    // Mark read if incoming from other user
    if (data.sender_id !== this.currentUserId) {
      this.sendReadReceipt();
    }
  }

  handleErrorMessage(data) {
    const errorText = data.message || "Message could not be sent.";

    // Find and highlight the blocked/failed optimistic message bubble
    if (data.client_msg_id) {
      const pendingRow = document.querySelector(`[data-message-id="${data.client_msg_id}"]`);
      if (pendingRow) {
        const bubble = pendingRow.querySelector('.message-bubble');
        if (bubble) {
          bubble.style.border = '1px solid var(--error)';
          bubble.style.background = 'rgba(239, 68, 68, 0.12)';
        }
        const tickEl = pendingRow.querySelector('.status-tick');
        if (tickEl) {
          tickEl.innerHTML = '<span style="color:var(--error);font-weight:700;font-size:11px;" title="' + this.escapeHtml(errorText) + '">⚠️ Blocked</span>';
        }
      }
    }

    if (typeof window.showToast === 'function') {
      window.showToast(errorText, 'error');
    } else {
      alert(errorText);
    }
  }

  handleReadReceipt(data) {
    if (data.user_id !== this.currentUserId) {
      // Mark all our sent ticks as double check (read)
      document.querySelectorAll('.outgoing .status-tick').forEach(tick => {
        tick.innerHTML = '✓✓';
        tick.style.color = '#38bdf8';
      });
    }
  }

  handleTyping(data) {
    if (this.typingEl) {
      if (data.is_typing) {
        this.typingEl.classList.add('active');
        this.scrollToBottom();
      } else {
        this.typingEl.classList.remove('active');
      }
    }
  }

  sendReadReceipt() {
    this.socket.send({ action: 'read_receipt' });
  }

  renderMessageRow(data, append = true) {
    const isOutgoing = String(data.sender_id) === String(this.currentUserId);
    const row = document.createElement('div');
    row.className = `message-bubble-row ${isOutgoing ? 'outgoing' : 'incoming'}`;
    row.dataset.messageId = data.message_id || data.client_msg_id;

    const timeStr = new Date(data.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const tickHtml = isOutgoing ? `<span class="status-tick">${data.is_pending ? '🕒' : '✓'}</span>` : '';

    row.innerHTML = `
      <div class="message-bubble">
        <div class="message-text">${this.escapeHtml(data.content)}</div>
        <div class="message-meta">
          <span>${timeStr}</span>
          ${tickHtml}
        </div>
      </div>
    `;

    if (append) {
      this.streamEl.appendChild(row);
    } else {
      // Insert after load-more button at top
      if (this.loadMoreBtn && this.loadMoreBtn.nextSibling) {
        this.streamEl.insertBefore(row, this.loadMoreBtn.nextSibling);
      } else {
        this.streamEl.insertBefore(row, this.streamEl.firstChild);
      }
    }
  }

  async loadOlderMessages() {
    if (this.isLoadingMore || !this.hasMoreMessages) return;
    this.isLoadingMore = true;

    const firstMsgRow = this.streamEl.querySelector('.message-bubble-row');
    const firstMsgId = firstMsgRow ? firstMsgRow.dataset.messageId : '';
    if (!firstMsgId) {
      this.isLoadingMore = false;
      return;
    }

    const previousScrollHeight = this.streamEl.scrollHeight;

    try {
      const res = await fetch(`/chats/api/${this.conversationId}/messages/?before_id=${firstMsgId}`);
      const data = await res.json();
      
      if (data.messages && data.messages.length > 0) {
        // Prepend older messages
        data.messages.reverse().forEach(msg => {
          if (!this.renderedMsgIds.has(msg.id)) {
            this.renderMessageRow({
              message_id: msg.id,
              client_msg_id: msg.client_msg_id,
              sender_id: msg.sender_id,
              content: msg.content,
              created_at: msg.created_at,
            }, false);
            this.renderedMsgIds.add(msg.id);
          }
        });

        // Restore scroll position
        const newScrollHeight = this.streamEl.scrollHeight;
        this.streamEl.scrollTop = newScrollHeight - previousScrollHeight;
      }

      this.hasMoreMessages = data.has_more;
      if (!this.hasMoreMessages && this.loadMoreBtn) {
        this.loadMoreBtn.style.display = 'none';
      }
    } catch (err) {
      console.error("Failed to load older messages:", err);
    } finally {
      this.isLoadingMore = false;
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

  scrollToBottom(smooth = false) {
    if (!this.streamEl) return;
    const targetScroll = this.streamEl.scrollHeight;
    if (smooth) {
      this.streamEl.scrollTo({ top: targetScroll, behavior: 'smooth' });
    } else {
      this.streamEl.scrollTop = targetScroll;
    }
    // Double-pass ensures late font/image rendering still places scroll at bottom
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

window.ChatClient = ChatClient;
