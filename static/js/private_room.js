/**
 * Nearby Chat — Private Room Client
 * Isolated real-time messaging, countdown timer, media attachments, and voice notes.
 */

class PrivateRoomClient {
  constructor(config) {
    this.roomId = config.roomId;
    this.currentParticipantId = config.currentParticipantId;
    this.currentTempName = config.currentTempName;
    this.currentAvatarColor = config.currentAvatarColor;
    this.uploadUrl = config.uploadUrl;
    this.timeRemaining = config.initialTimeRemaining || 0;
    this.csrfToken = config.csrfToken;

    this.streamEl = document.getElementById('message-stream');
    this.inputEl = document.getElementById('chat-input');
    this.formEl = document.getElementById('chat-form');
    this.typingEl = document.getElementById('typing-indicator');
    this.timerEl = document.getElementById('room-countdown-timer');

    this.mediaRecorder = null;
    this.audioChunks = [];
    this.isRecording = false;
    this.renderedMsgIds = new Set();
    this.typingTimeout = null;

    this.initWebSocket();
    this.initEventListeners();
    this.initTimer();
    this.initExistingMessages();
    this.scrollToBottom();
    setTimeout(() => this.scrollToBottom(), 100);
  }

  initWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/private-room/${this.roomId}/`;

    this.socket = new RobustWebSocket(wsUrl);

    this.socket.on('chat_message', (data) => {
      this.handleIncomingMessage(data);
    });

    this.socket.on('typing', (data) => {
      this.handleTyping(data);
    });

    this.socket.on('system_event', (data) => {
      this.handleSystemEvent(data);
    });

    this.socket.on('room_status', (data) => {
      if (data.time_remaining_seconds !== undefined) {
        this.timeRemaining = data.time_remaining_seconds;
      }
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
    }

    // Image Upload
    const imageInput = document.getElementById('image-upload-input');
    if (imageInput) {
      imageInput.addEventListener('change', () => {
        if (imageInput.files && imageInput.files[0]) {
          this.uploadFile(imageInput.files[0], 'image');
          imageInput.value = '';
        }
      });
    }

    // Document / File Upload
    const fileInput = document.getElementById('file-upload-input');
    if (fileInput) {
      fileInput.addEventListener('change', () => {
        if (fileInput.files && fileInput.files[0]) {
          this.uploadFile(fileInput.files[0], 'file');
          fileInput.value = '';
        }
      });
    }
  }

  initTimer() {
    this.updateTimerDisplay();
    this.timerInterval = setInterval(() => {
      if (this.timeRemaining > 0) {
        this.timeRemaining--;
        this.updateTimerDisplay();
      } else {
        clearInterval(this.timerInterval);
        if (this.timerEl) this.timerEl.textContent = "Expired";
        if (this.formEl) {
          this.formEl.innerHTML = `<div style="padding: 10px; text-align: center; color: var(--text-muted); font-size: 12px; width: 100%;">🔒 This private room has expired.</div>`;
        }
      }
    }, 1000);
  }

  updateTimerDisplay() {
    if (!this.timerEl) return;
    if (this.timeRemaining <= 0) {
      this.timerEl.textContent = "Expired";
      return;
    }
    const hours = Math.floor(this.timeRemaining / 3600);
    const minutes = Math.floor((this.timeRemaining % 3600) / 60);
    const seconds = this.timeRemaining % 60;
    
    if (hours > 0) {
      this.timerEl.textContent = `${hours}h ${minutes}m ${seconds}s`;
    } else {
      this.timerEl.textContent = `${minutes}m ${seconds}s`;
    }
  }

  sendMessage() {
    const text = this.inputEl.value.trim();
    if (!text) return;

    // Content moderation guard
    if (window.ContentModerator && window.ContentModerator.isAbusive(text)) {
      const warningText = "⚠️ Message blocked: Please avoid abusive language.";
      if (typeof window.showToast === 'function') window.showToast(warningText, 'error');
      return;
    }

    const clientMsgId = 'pr_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    this.socket.send({
      action: 'send_message',
      content: text,
      client_msg_id: clientMsgId
    });

    this.inputEl.value = '';
  }

  uploadFile(file, messageType) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('message_type', messageType);

    if (typeof window.showToast === 'function') {
      window.showToast("Uploading attachment...", "info");
    }

    fetch(this.uploadUrl, {
      method: 'POST',
      headers: {
        'X-CSRFToken': this.csrfToken,
      },
      body: formData
    })
    .then(res => res.json())
    .then(data => {
      if (!data.success) {
        if (typeof window.showToast === 'function') {
          window.showToast(data.error || "Upload failed.", "error");
        }
      }
    })
    .catch(err => {
      if (typeof window.showToast === 'function') {
        window.showToast("Upload error: " + err.message, "error");
      }
    });
  }

  handleIncomingMessage(data) {
    if (data.message_id && this.renderedMsgIds.has(data.message_id)) return;
    if (data.message_id) this.renderedMsgIds.add(data.message_id);

    const emptyState = document.getElementById('empty-state');
    if (emptyState) emptyState.remove();

    const isOutgoing = (data.sender_id === this.currentParticipantId);
    const row = document.createElement('div');
    row.className = `message-bubble-row ${isOutgoing ? 'outgoing' : 'incoming'}`;
    if (data.message_id) row.dataset.messageId = data.message_id;

    let mediaContent = '';
    if (data.message_type === 'image' && data.file_url) {
      mediaContent = `<img src="${data.file_url}" alt="Image" style="max-width: 100%; max-height: 240px; border-radius: var(--radius-md); display: block; margin-bottom: 4px;" loading="lazy">`;
    } else if (data.message_type === 'audio' && data.file_url) {
      mediaContent = `<audio controls src="${data.file_url}" style="width: 220px; max-width: 100%; height: 36px; margin: 4px 0;"></audio>`;
    } else if (data.message_type === 'file' && data.file_url) {
      mediaContent = `<a href="${data.file_url}" class="btn btn-sm btn-secondary" style="display: inline-flex; align-items: center; gap: 6px; text-decoration: none; padding: 6px 12px; margin: 4px 0; font-size: 11px;">📄 <span>${data.file_name || 'Download File'}</span></a>`;
    } else {
      mediaContent = `<div class="message-text">${this.escapeHtml(data.content)}</div>`;
    }

    let avatarHtml = '';
    let senderNameHtml = '';
    if (!isOutgoing) {
      const color = data.sender_avatar_color || '#06b6d4';
      const initials = data.sender_initials || 'PR';
      avatarHtml = `<div style="width: 28px; height: 28px; border-radius: var(--radius-full); background: ${color}; color: white; display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 700; flex-shrink: 0; margin-right: 6px;">${initials}</div>`;
      senderNameHtml = `<div style="font-size: 10px; font-weight: 700; color: ${color}; margin-bottom: 2px;">${this.escapeHtml(data.sender_temp_name || 'Anonymous')}</div>`;
    }

    row.innerHTML = `
      ${avatarHtml}
      <div class="message-bubble">
        ${senderNameHtml}
        ${mediaContent}
        <div class="message-meta" style="font-size: 10px; opacity: 0.7; margin-top: 2px; text-align: right;">
          <span>${data.created_at || 'Just now'}</span>
        </div>
      </div>
    `;

    this.streamEl.appendChild(row);
    this.scrollToBottom();
  }

  handleTyping(data) {
    if (!this.typingEl) return;
    if (data.is_typing) {
      const nameEl = document.getElementById('typing-name');
      if (nameEl) nameEl.textContent = data.sender_temp_name || 'Someone';
      this.typingEl.style.display = 'block';
    } else {
      this.typingEl.style.display = 'none';
    }
  }

  handleSystemEvent(data) {
    if (data.event === 'deleted') {
      alert("This private room was deleted by its creator.");
      window.location.reload();
    } else if (data.event === 'blocked') {
      alert("This private room session has been blocked.");
      window.location.reload();
    } else if (data.message) {
      const row = document.createElement('div');
      row.className = 'system-message-row';
      row.style.cssText = 'text-align: center; margin: 4px 0;';
      row.innerHTML = `<span style="font-size: 11px; color: var(--text-muted); background: var(--bg-subtle); padding: 3px 10px; border-radius: 999px;">${this.escapeHtml(data.message)}</span>`;
      this.streamEl.appendChild(row);
      this.scrollToBottom();
    }
  }

  scrollToBottom() {
    if (this.streamEl) {
      this.streamEl.scrollTop = this.streamEl.scrollHeight;
    }
  }

  escapeHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }
}

function getSupportedAudioMimeType() {
  if (typeof MediaRecorder === 'undefined') return '';
  const candidateTypes = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/ogg;codecs=opus',
    'audio/ogg',
    'audio/mp4',
    'audio/aac'
  ];
  for (const type of candidateTypes) {
    if (MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(type)) {
      return type;
    }
  }
  return '';
}

// Voice Recording Helper
function toggleVoiceRecording() {
  const btn = document.getElementById('voice-record-btn');
  if (!window.privateRoomClient) return;

  if (window.privateRoomClient.isRecording) {
    stopRecording(btn);
  } else {
    startRecording(btn);
  }
}

function startRecording(btn) {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    alert("Voice recording is not supported on this browser/device.");
    return;
  }

  navigator.mediaDevices.getUserMedia({ audio: true })
    .then(stream => {
      const mimeType = getSupportedAudioMimeType();
      const options = mimeType ? { mimeType } : undefined;
      const recorder = options ? new MediaRecorder(stream, options) : new MediaRecorder(stream);

      window.privateRoomClient.mediaRecorder = recorder;
      window.privateRoomClient.audioChunks = [];
      window.privateRoomClient.isRecording = true;

      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) window.privateRoomClient.audioChunks.push(e.data);
      };

      recorder.onstop = () => {
        const actualType = mimeType || 'audio/webm';
        const ext = actualType.includes('ogg') ? '.ogg' : (actualType.includes('mp4') ? '.mp4' : '.webm');
        const audioBlob = new Blob(window.privateRoomClient.audioChunks, { type: actualType });
        const audioFile = new File([audioBlob], `voice_${Date.now()}${ext}`, { type: actualType });
        window.privateRoomClient.uploadFile(audioFile, 'audio');
        stream.getTracks().forEach(track => track.stop());
      };

      recorder.start();
      if (btn) {
        btn.style.color = 'var(--error)';
        btn.style.background = 'rgba(239, 68, 68, 0.15)';
      }
      if (typeof window.showToast === 'function') {
        window.showToast("Recording audio... Tap microphone again to send.", "info");
      }
    })
    .catch(err => {
      alert("Microphone permission was denied or is unavailable.");
    });
}

function stopRecording(btn) {
  if (window.privateRoomClient.mediaRecorder && window.privateRoomClient.isRecording) {
    window.privateRoomClient.mediaRecorder.stop();
    window.privateRoomClient.isRecording = false;
    if (btn) {
      btn.style.color = '';
      btn.style.background = '';
    }
  }
}