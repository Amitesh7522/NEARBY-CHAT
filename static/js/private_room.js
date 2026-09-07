/**
 * Nearby Chat — Private Room Client (v2.0 E2EE)
 * 
 * Production End-to-End Encryption Client:
 * - Ephemeral ECDH P-256 session key exchange
 * - Zero plaintext stored or transmitted to server
 * - AES-GCM-256 text & media encryption with AAD binding
 * - Pre-peer gating (composer locked until both participants establish keys)
 * - Safe DOM text node rendering (XSS prevention)
 * - Encrypted file/voice note uploads & authenticated media streaming
 * - Optional out-of-band verification fingerprint (12 decimal digits)
 */

class PrivateRoomClient {
  constructor(config) {
    this.roomId = config.roomId;
    this.currentParticipantId = config.currentParticipantId;
    this.currentTempName = config.currentTempName;
    this.currentAvatarColor = config.currentAvatarColor;
    this.myRole = config.myRole || 'guest';
    this.sessionState = config.sessionState || 'WAITING_FOR_PEER';
    this.myPublicKey = config.myPublicKey || null;
    this.peerPublicKey = config.peerPublicKey || null;
    this.uploadUrl = config.uploadUrl;
    this.timeRemaining = config.initialTimeRemaining || 0;
    this.csrfToken = config.csrfToken;

    // Cryptographic Engine
    this.crypto = new window.PrivateRoomCrypto(this.roomId);

    // DOM Elements
    this.streamEl = document.getElementById('message-stream');
    this.inputEl = document.getElementById('chat-input');
    this.formEl = document.getElementById('chat-form');
    this.sendBtn = document.getElementById('chat-send-btn');
    this.imageBtn = document.getElementById('image-upload-btn');
    this.fileBtn = document.getElementById('file-upload-btn');
    this.voiceBtn = document.getElementById('voice-record-btn');
    this.imageInput = document.getElementById('image-upload-input');
    this.fileInput = document.getElementById('file-upload-input');
    this.waitingBanner = document.getElementById('waiting-peer-banner');
    this.typingEl = document.getElementById('typing-indicator');
    this.timerEl = document.getElementById('room-countdown-timer');
    this.verifyBadge = document.getElementById('verify-e2ee-badge');

    // State Tracking
    this.mediaRecorder = null;
    this.audioChunks = [];
    this.isRecording = false;
    this.renderedMsgIds = new Set();
    this.decryptedHistory = []; // Decrypted messages for user-consented reporting evidence
    this.typingTimeout = null;

    // Initialize lifecycle
    this.initVisualViewportHandler();
    this.initCryptoAndKeyExchange();
    this.initWebSocket();
    this.initEventListeners();
    this.initTimer();
    this.initExistingMessages();
    this.updateGatingState();
    this.scrollToBottom();
    setTimeout(() => this.scrollToBottom(), 100);
  }

  // ============================================================================
  // Mobile Visual Viewport Handling (Sticky Header & Keyboard Resizing)
  // ============================================================================
  initVisualViewportHandler() {
    if (!window.visualViewport) return;

    const onResize = () => {
      const vh = window.visualViewport.height;
      document.documentElement.style.setProperty('--visual-viewport-height', `${vh}px`);
      if (document.activeElement === this.inputEl) {
        setTimeout(() => this.scrollToBottom(), 60);
      }
    };

    window.visualViewport.addEventListener('resize', onResize);
    window.visualViewport.addEventListener('scroll', onResize);
    onResize();
  }

  // ============================================================================
  // Cryptographic Lifecycle & Key Exchange
  // ============================================================================
  async initCryptoAndKeyExchange() {
    try {
      const generatedPubB64 = await this.crypto.init();

      // Check if server already has a registered public key for this participant
      // that does not match local storage (e.g. user cleared IndexedDB)
      if (this.myPublicKey && this.myPublicKey !== generatedPubB64) {
        console.warn("Local encryption key mismatch: server key differs from local storage.");
        if (typeof window.openLostKeyModal === 'function') {
          window.openLostKeyModal();
        }
        return;
      }

      this.myPublicKey = generatedPubB64;

      // If peer public key is already available from server context, establish session now
      if (this.peerPublicKey && this.sessionState === 'E2EE_ESTABLISHED') {
        await this.crypto.establishSessionWithPeer(this.peerPublicKey);
        this.updateGatingState();
        this.decryptAllPendingMessages();
        this.decryptAllPendingMedia();
      }

      // If WebSocket is open or queued, send public key announcement
      if (this.socket) {
        this.sendKeyExchange();
      }
    } catch (err) {
      console.error("Cryptographic initialization failed:", err);
      if (typeof window.showToast === 'function') {
        window.showToast("Encryption initialization error: " + err.message, "error");
      }
    }
  }

  sendKeyExchange() {
    if (!this.myPublicKey || !this.socket) return;
    this.socket.send({
      action: 'key_exchange',
      public_key: this.myPublicKey
    });
  }

  async handlePeerPublicKey(peerPubKeyB64) {
    if (!peerPubKeyB64 || (peerPubKeyB64 === this.peerPublicKey && this.crypto.messageKey)) {
      return;
    }

    try {
      this.peerPublicKey = peerPubKeyB64;
      await this.crypto.establishSessionWithPeer(peerPubKeyB64);
      this.sessionState = 'E2EE_ESTABLISHED';
      this.updateGatingState();
      await this.decryptAllPendingMessages();
      await this.decryptAllPendingMedia();

      // Update verify modal fingerprint display if open
      const fpDisplay = document.getElementById('verify-fingerprint-display');
      if (fpDisplay && this.crypto.safetyFingerprint) {
        fpDisplay.textContent = this.crypto.safetyFingerprint;
      }
    } catch (err) {
      console.error("Failed to establish E2EE session with peer:", err);
      if (typeof window.showToast === 'function') {
        window.showToast("E2EE key agreement failed: " + err.message, "error");
      }
    }
  }

  // ============================================================================
  // Pre-Peer Gating State Management
  // ============================================================================
  updateGatingState() {
    const isReady = (this.sessionState === 'E2EE_ESTABLISHED' && !!this.crypto.messageKey);

    if (isReady) {
      if (this.waitingBanner) this.waitingBanner.style.display = 'none';
      if (this.inputEl) {
        this.inputEl.disabled = false;
        this.inputEl.placeholder = "Type a private encrypted message...";
      }
      if (this.sendBtn) {
        this.sendBtn.disabled = false;
        this.sendBtn.style.opacity = '';
        this.sendBtn.style.cursor = '';
      }
      if (this.imageBtn) {
        this.imageBtn.disabled = false;
        this.imageBtn.style.opacity = '';
        this.imageBtn.style.cursor = '';
      }
      if (this.fileBtn) {
        this.fileBtn.disabled = false;
        this.fileBtn.style.opacity = '';
        this.fileBtn.style.cursor = '';
      }
      if (this.voiceBtn) {
        this.voiceBtn.disabled = false;
        this.voiceBtn.style.opacity = '';
        this.voiceBtn.style.cursor = '';
      }
      if (this.imageInput) this.imageInput.disabled = false;
      if (this.fileInput) this.fileInput.disabled = false;
    } else {
      if (this.waitingBanner) this.waitingBanner.style.display = 'block';
      if (this.inputEl) {
        this.inputEl.disabled = true;
        this.inputEl.placeholder = "Waiting for partner to establish encrypted session...";
      }
      if (this.sendBtn) {
        this.sendBtn.disabled = true;
        this.sendBtn.style.opacity = '0.5';
        this.sendBtn.style.cursor = 'not-allowed';
      }
      if (this.imageBtn) {
        this.imageBtn.disabled = true;
        this.imageBtn.style.opacity = '0.5';
        this.imageBtn.style.cursor = 'not-allowed';
      }
      if (this.fileBtn) {
        this.fileBtn.disabled = true;
        this.fileBtn.style.opacity = '0.5';
        this.fileBtn.style.cursor = 'not-allowed';
      }
      if (this.voiceBtn) {
        this.voiceBtn.disabled = true;
        this.voiceBtn.style.opacity = '0.5';
        this.voiceBtn.style.cursor = 'not-allowed';
      }
      if (this.imageInput) this.imageInput.disabled = true;
      if (this.fileInput) this.fileInput.disabled = true;
    }
  }

  // ============================================================================
  // WebSocket Connection & Dispatcher
  // ============================================================================
  initWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/private-room/${this.roomId}/`;

    this.socket = new RobustWebSocket(wsUrl);

    this.socket.on('open', () => {
      if (this.myPublicKey) {
        this.sendKeyExchange();
      }
    });

    this.socket.on('connect', () => {
      if (this.myPublicKey) {
        this.sendKeyExchange();
      }
    });

    this.socket.on('room_status', async (data) => {
      if (this.myPublicKey) {
        this.sendKeyExchange();
      }
      if (data.time_remaining_seconds !== undefined) {
        this.timeRemaining = data.time_remaining_seconds;
      }
      if (data.my_public_key) {
        this.myPublicKey = data.my_public_key;
      }
      if (data.peer_temp_name) {
        this.updatePartnerHeader(data.peer_temp_name);
      }
      if (data.peer_public_key) {
        await this.handlePeerPublicKey(data.peer_public_key);
      }
      if (data.session_state) {
        this.sessionState = data.session_state;
        this.updateGatingState();
      }
    });

    const handleParticipantJoined = async (data) => {
      const senderId = data.participant_id || data.sender_id;
      if (senderId && senderId === this.currentParticipantId) {
        return;
      }

      // 1. Display join system message in chat stream
      const joinMsg = data.message || `👋 ${data.temp_name || 'Guest'} joined the private room.`;
      this.appendSystemMessage(joinMsg);

      // 2. Update partner header online badge & name
      this.updatePartnerHeader(data.temp_name || 'Partner');

      // 3. Immediately exchange our public key with the newly joined participant
      if (this.myPublicKey) {
        this.sendKeyExchange();
      }

      // 4. If peer provided their public key in the event, establish session
      if (data.public_key) {
        await this.handlePeerPublicKey(data.public_key);
      }
    };

    this.socket.on('participant_joined', handleParticipantJoined);
    this.socket.on('peer_joined', handleParticipantJoined);

    this.socket.on('e2ee_established', async (data) => {
      const peerKey = (this.myRole === 'creator') ? data.guest_public_key : data.creator_public_key;
      if (peerKey) {
        await this.handlePeerPublicKey(peerKey);
      }
    });

    this.socket.on('peer_key_announced', async (data) => {
      if (data.public_key) {
        await this.handlePeerPublicKey(data.public_key);
      }
    });

    this.socket.on('peer_left', (data) => {
      this.appendSystemMessage(`👋 ${data.temp_name || 'Partner'} left the room.`);
      const wrapper = document.getElementById('header-partner-wrapper');
      if (wrapper) wrapper.style.display = 'none';
    });

    this.socket.on('chat_message', async (data) => {
      await this.handleIncomingMessage(data);
    });

    this.socket.on('typing', (data) => {
      this.handleTyping(data);
    });

    this.socket.on('system_event', (data) => {
      this.handleSystemEvent(data);
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
        if (this.sessionState !== 'E2EE_ESTABLISHED') return;
        this.socket.send({ action: 'typing', is_typing: true });
        clearTimeout(this.typingTimeout);
        this.typingTimeout = setTimeout(() => {
          this.socket.send({ action: 'typing', is_typing: false });
        }, 1500);
      });
    }

    // Image Upload
    if (this.imageInput) {
      this.imageInput.addEventListener('change', () => {
        if (this.imageInput.files && this.imageInput.files[0]) {
          this.uploadFile(this.imageInput.files[0], 'image');
          this.imageInput.value = '';
        }
      });
    }

    // Document / File Upload
    if (this.fileInput) {
      this.fileInput.addEventListener('change', () => {
        if (this.fileInput.files && this.fileInput.files[0]) {
          this.uploadFile(this.fileInput.files[0], 'file');
          this.fileInput.value = '';
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

  // ============================================================================
  // Message Sending (E2EE Client-Side Encryption)
  // ============================================================================
  async sendMessage() {
    const text = this.inputEl.value.trim();
    if (!text) return;

    if (this.sessionState !== 'E2EE_ESTABLISHED' || !this.crypto.messageKey) {
      if (typeof window.showToast === 'function') {
        window.showToast("Cannot send message until both participants are connected.", "info");
      }
      return;
    }

    // Content moderation guard
    if (window.ContentModerator && window.ContentModerator.isAbusive(text)) {
      const warningText = "⚠️ Message blocked: Please avoid abusive language.";
      if (typeof window.showToast === 'function') window.showToast(warningText, 'error');
      return;
    }

    try {
      // 1. Generate client_msg_id
      const clientMsgId = 'pr_' + Date.now() + '_' + (window.crypto.randomUUID ? window.crypto.randomUUID() : Math.random().toString(36).substr(2, 9));

      // 2. Encrypt plaintext under message key with AAD
      const ciphertextJson = await this.crypto.encryptText(text, this.myRole);

      // 3. Transmit only ciphertext envelope to blind server relay
      this.socket.send({
        action: 'send_message',
        content: ciphertextJson,
        client_msg_id: clientMsgId
      });

      this.inputEl.value = '';
    } catch (err) {
      console.error("Failed to encrypt message:", err);
      if (typeof window.showToast === 'function') {
        window.showToast("Encryption failed: " + err.message, "error");
      }
    }
  }

  // ============================================================================
  // Encrypted Media Upload (File Key Wrapping & AAD Binding)
  // ============================================================================
  async uploadFile(file, messageType) {
    if (this.sessionState !== 'E2EE_ESTABLISHED' || !this.crypto.fileWrapKey) {
      if (typeof window.showToast === 'function') {
        window.showToast("Waiting for partner to connect before sharing files.", "info");
      }
      return;
    }

    // File size limits (10MB for image/file, 5MB for audio)
    const maxSizeBytes = (messageType === 'audio') ? (5 * 1024 * 1024) : (10 * 1024 * 1024);
    if (file.size > maxSizeBytes) {
      const limitMb = maxSizeBytes / (1024 * 1024);
      const msg = `File size exceeds the ${limitMb}MB limit for private rooms.`;
      if (typeof window.showToast === 'function') window.showToast(msg, "error");
      else alert(msg);
      return;
    }

    // Temporary upload progress bubble
    const uploadId = 'upload_' + Date.now();
    const pendingRow = document.createElement('div');
    pendingRow.id = uploadId;
    pendingRow.className = 'message-bubble-row outgoing';
    const label = messageType === 'image' ? 'photo' : (messageType === 'audio' ? 'voice message' : 'document');
    pendingRow.innerHTML = `
      <div class="message-bubble" style="opacity: 0.85; display: inline-flex; align-items: center; gap: 8px; padding: 8px 14px;">
        <span style="width: 14px; height: 14px; border: 2px solid currentColor; border-top-color: transparent; border-radius: 50%; display: inline-block; animation: spin 0.8s linear infinite;"></span>
        <span style="font-size: 11px;">Encrypting & uploading ${label}...</span>
      </div>
    `;
    this.streamEl.appendChild(pendingRow);
    this.scrollToBottom();

    try {
      // 1. Read binary buffer
      const fileBuffer = await file.arrayBuffer();

      // 2. Generate clientMsgId
      const clientMsgId = 'pr_file_' + Date.now() + '_' + (window.crypto.randomUUID ? window.crypto.randomUUID() : Math.random().toString(36).substr(2, 9));

      // 3. Encrypt file binary and wrap key under KW
      const { encryptedBlob, encryptedFileKey, fileIV } = await this.crypto.encryptMedia(fileBuffer, clientMsgId);

      // 4. Send encrypted blob to server
      const formData = new FormData();
      formData.append('file', encryptedBlob, file.name);
      formData.append('message_type', messageType);
      formData.append('client_msg_id', clientMsgId);
      formData.append('encrypted_file_key', encryptedFileKey);
      formData.append('file_iv', fileIV);

      const response = await fetch(this.uploadUrl, {
        method: 'POST',
        headers: {
          'X-CSRFToken': this.csrfToken,
        },
        body: formData
      });

      const data = await response.json();
      const el = document.getElementById(uploadId);
      if (el) el.remove();

      if (!data.success) {
        if (typeof window.showToast === 'function') {
          window.showToast(data.error || "Upload failed.", "error");
        } else {
          alert(data.error || "Upload failed.");
        }
      }
    } catch (err) {
      console.error("Media encryption/upload error:", err);
      const el = document.getElementById(uploadId);
      if (el) el.remove();

      if (typeof window.showToast === 'function') {
        window.showToast("Upload error: " + err.message, "error");
      } else {
        alert("Upload error: " + err.message);
      }
    }
  }

  // ============================================================================
  // Message Decryption & Safe DOM Rendering
  // ============================================================================
  async handleIncomingMessage(data) {
    if (data.message_id && this.renderedMsgIds.has(data.message_id)) return;
    if (data.message_id) this.renderedMsgIds.add(data.message_id);

    const emptyState = document.getElementById('empty-state');
    if (emptyState) emptyState.remove();

    const isOutgoing = (data.sender_id === this.currentParticipantId);
    const row = document.createElement('div');
    row.className = `message-bubble-row ${isOutgoing ? 'outgoing' : 'incoming'}`;
    if (data.message_id) row.dataset.messageId = data.message_id;

    // Avatar
    if (!isOutgoing) {
      const color = data.sender_avatar_color || '#06b6d4';
      const initials = data.sender_initials || 'PR';
      const avatarDiv = document.createElement('div');
      avatarDiv.className = 'private-avatar-badge';
      avatarDiv.style.cssText = `width: 32px; height: 32px; border-radius: var(--radius-full); background: linear-gradient(135deg, ${color}, #1e1b4b); color: #ffffff; display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 800; letter-spacing: 0.5px; flex-shrink: 0; margin-right: 8px; box-shadow: 0 2px 6px rgba(0,0,0,0.15); border: 1.5px solid rgba(255,255,255,0.2);`;
      avatarDiv.textContent = initials;
      row.appendChild(avatarDiv);
    }

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';

    // Sender Name Header
    if (!isOutgoing) {
      const color = data.sender_avatar_color || '#06b6d4';
      const nameDiv = document.createElement('div');
      nameDiv.style.cssText = `font-size: 11px; font-weight: 700; color: ${color}; margin-bottom: 2px; display: flex; align-items: center; gap: 4px;`;
      
      const nameSpan = document.createElement('span');
      nameSpan.textContent = data.sender_temp_name || 'Anonymous';
      nameDiv.appendChild(nameSpan);

      const tagSpan = document.createElement('span');
      tagSpan.style.cssText = 'font-size: 9px; font-weight: 500; color: var(--text-muted);';
      tagSpan.textContent = '· Joined';
      nameDiv.appendChild(tagSpan);

      bubble.appendChild(nameDiv);
    }

    // Content: Text or Media
    if (data.message_type === 'image' || data.message_type === 'audio' || data.message_type === 'file') {
      const mediaContainer = document.createElement('div');
      mediaContainer.className = 'private-media-container';
      mediaContainer.style.cssText = 'margin: 2px 0 4px 0; min-height: 40px;';
      mediaContainer.innerHTML = `<span style="font-size: 11px; color: var(--text-muted);">🔒 Decrypting ${data.message_type}...</span>`;
      bubble.appendChild(mediaContainer);
      row.appendChild(bubble);
      this.streamEl.appendChild(row);
      this.scrollToBottom();

      // Decrypt media asynchronously
      this.decryptAndDisplayMedia(mediaContainer, data);
      return;
    }

    // Decrypt Text
    let plaintext = data.content;
    if (this.crypto && this.crypto.messageKey) {
      try {
        plaintext = await this.crypto.decryptText(data.content, data.sender_role);
      } catch (e) {
        console.error("Text decryption failed:", e);
        plaintext = "🔒 [Encrypted message - could not be decrypted]";
      }
    }

    // Save decrypted text for user-consented safety reports
    this.recordDecryptedHistory(data.sender_temp_name || 'Partner', plaintext, data.created_at);

    // Safe DOM text node insertion (prevents DOM XSS)
    const textDiv = document.createElement('div');
    textDiv.className = 'message-text';
    textDiv.appendChild(document.createTextNode(plaintext));
    bubble.appendChild(textDiv);

    // Timestamp Meta
    const metaDiv = document.createElement('div');
    metaDiv.className = 'message-meta';
    metaDiv.style.cssText = 'font-size: 10px; opacity: 0.7; margin-top: 2px; text-align: right;';
    const timeSpan = document.createElement('span');
    timeSpan.textContent = data.created_at || 'Just now';
    metaDiv.appendChild(timeSpan);
    bubble.appendChild(metaDiv);

    row.appendChild(bubble);
    this.streamEl.appendChild(row);
    this.scrollToBottom();
  }

  // ============================================================================
  // Media Decryption & Object URL Rendering
  // ============================================================================
  async decryptAndDisplayMedia(container, data) {
    if (!this.crypto || !this.crypto.fileWrapKey) {
      container.innerHTML = `<span style="font-size: 11px; color: var(--text-muted);">🔒 [Media encrypted - waiting for session]</span>`;
      return;
    }

    try {
      const response = await fetch(data.file_url);
      if (!response.ok) throw new Error("Could not retrieve media file.");

      const encryptedBuffer = await response.arrayBuffer();
      const fileKey = data.encrypted_file_key || response.headers.get('X-Encrypted-File-Key');
      const fileIV = data.file_iv || response.headers.get('X-File-IV');

      if (!fileKey || !fileIV) {
        // Unencrypted fallback for legacy media
        this.renderDirectMedia(container, data.file_url, data.message_type, data.file_name);
        return;
      }

      const mimeType = data.file_mime_type || (data.message_type === 'image' ? 'image/jpeg' : (data.message_type === 'audio' ? 'audio/webm' : 'application/octet-stream'));
      const decryptedBlob = await this.crypto.decryptMedia(
        encryptedBuffer,
        fileKey,
        fileIV,
        data.client_msg_id,
        mimeType
      );

      const blobUrl = URL.createObjectURL(decryptedBlob);
      this.renderDirectMedia(container, blobUrl, data.message_type, data.file_name);
    } catch (err) {
      console.error("Media decryption failure:", err);
      container.innerHTML = `<span style="font-size: 11px; color: var(--error);">⚠️ Failed to decrypt media</span>`;
    }
  }

  renderDirectMedia(container, url, messageType, fileName) {
    container.innerHTML = '';
    if (messageType === 'image') {
      const img = document.createElement('img');
      img.src = url;
      img.alt = 'Decrypted Photo';
      img.style.cssText = 'max-width: 100%; max-height: 260px; width: auto; height: auto; object-fit: cover; display: block; border-radius: var(--radius-md); cursor: zoom-in;';
      img.onclick = () => {
        if (typeof window.openImageLightbox === 'function') window.openImageLightbox(url);
      };
      container.appendChild(img);
    } else if (messageType === 'audio') {
      const audio = document.createElement('audio');
      audio.controls = true;
      audio.setAttribute('controlsList', 'nodownload');
      audio.src = url;
      audio.style.cssText = 'width: 220px; max-width: 100%; height: 36px; margin: 4px 0;';
      container.appendChild(audio);
    } else {
      const link = document.createElement('a');
      link.href = url;
      link.download = fileName || 'private_file';
      link.className = 'btn btn-sm btn-secondary';
      link.style.cssText = 'display: inline-flex; align-items: center; gap: 6px; text-decoration: none; padding: 6px 12px; margin: 4px 0; font-size: 11px;';
      link.innerHTML = `📄 <span>${this.escapeHtml(fileName || 'Download File')}</span>`;
      container.appendChild(link);
    }
    this.scrollToBottom();
  }

  // ============================================================================
  // Initial Page Decryption (Historical Messages & Media)
  // ============================================================================
  async decryptAllPendingMessages() {
    if (!this.crypto || !this.crypto.messageKey) return;

    const pendingNodes = document.querySelectorAll('.e2ee-text-pending');
    for (const node of pendingNodes) {
      const cipher = node.dataset.cipher;
      const senderRole = node.dataset.senderRole || 'guest';
      if (!cipher) continue;

      try {
        const plaintext = await this.crypto.decryptText(cipher, senderRole);
        node.textContent = '';
        node.appendChild(document.createTextNode(plaintext));
        node.classList.remove('e2ee-text-pending');

        this.recordDecryptedHistory(senderRole === this.myRole ? 'You' : 'Partner', plaintext);
      } catch (err) {
        node.textContent = '🔒 [Encrypted message - could not be decrypted]';
        node.classList.remove('e2ee-text-pending');
      }
    }
  }

  async decryptAllPendingMedia() {
    if (!this.crypto || !this.crypto.fileWrapKey) return;

    const pendingMedia = document.querySelectorAll('.e2ee-media-pending');
    for (const el of pendingMedia) {
      const mediaUrl = el.dataset.mediaUrl;
      const clientMsgId = el.dataset.clientMsgId;
      const fileKey = el.dataset.fileKey;
      const fileIv = el.dataset.fileIv;
      const mediaType = el.dataset.mediaType;
      const mimeType = el.dataset.mimeType;
      const fileName = el.dataset.fileName;

      if (!mediaUrl || !fileKey || !fileIv) continue;

      try {
        const res = await fetch(mediaUrl);
        if (!res.ok) continue;

        const buffer = await res.arrayBuffer();
        const decryptedBlob = await this.crypto.decryptMedia(buffer, fileKey, fileIv, clientMsgId, mimeType);
        const blobUrl = URL.createObjectURL(decryptedBlob);

        el.classList.remove('e2ee-media-pending');
        this.renderDirectMedia(el, blobUrl, mediaType, fileName);
      } catch (err) {
        console.error("Historical media decryption failed:", err);
        el.innerHTML = `<span style="font-size: 11px; color: var(--error);">⚠️ Decryption failed</span>`;
      }
    }
  }

  // ============================================================================
  // User-Consented Reporting Evidence Helper
  // ============================================================================
  recordDecryptedHistory(sender, text, time) {
    this.decryptedHistory.push({
      sender: sender || 'User',
      text: text,
      time: time || new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    });
    if (this.decryptedHistory.length > 50) {
      this.decryptedHistory.shift();
    }
  }

  getRecentDecryptedEvidence() {
    if (!this.decryptedHistory.length) return "No messages available.";
    return this.decryptedHistory.slice(-20).map(m => `[${m.time}] ${m.sender}: ${m.text}`).join('\n');
  }

  // ============================================================================
  // WebSocket System & UI Handlers
  // ============================================================================
  updatePartnerHeader(tempName) {
    const wrapper = document.getElementById('header-partner-wrapper');
    const nameEl = document.getElementById('header-partner-name');
    const statusEl = document.getElementById('header-partner-status');
    if (nameEl) nameEl.textContent = tempName || 'Partner';
    if (wrapper) wrapper.style.display = 'inline-flex';
    if (statusEl) statusEl.style.display = 'inline-flex';
  }

  appendSystemMessage(msg) {
    if (!msg) return;
    const emptyState = document.getElementById('empty-state');
    if (emptyState) emptyState.remove();

    const row = document.createElement('div');
    row.className = 'system-message-row';
    row.style.cssText = 'text-align: center; margin: 6px 0;';
    row.innerHTML = `<span style="font-size: 11px; color: var(--text-muted); background: var(--bg-subtle); padding: 3px 10px; border-radius: 999px; border: 1px solid var(--border-color);">${this.escapeHtml(msg)}</span>`;
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
      this.appendSystemMessage(data.message);
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

// ============================================================================
// Voice Note Helpers (Microphone Recording)
// ============================================================================
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
        window.showToast("Recording encrypted audio... Tap microphone again to send.", "info");
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

window.PrivateRoomClient = PrivateRoomClient;