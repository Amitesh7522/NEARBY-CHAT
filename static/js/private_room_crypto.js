/**
 * Nearby Chat — Private Room E2EE Cryptographic Engine
 * Built on native W3C Web Cryptography API (window.crypto.subtle).
 * 
 * Standards & Primitives:
 * - Asymmetric Key Agreement: ECDH P-256 (secp256r1)
 * - Key Derivation: HKDF-SHA256 with domain context separation
 * - Symmetric Authenticated Encryption: AES-GCM-256 with 96-bit random IVs and AAD binding
 * - Secure Storage: Non-extractable keys in browser IndexedDB
 */

class PrivateRoomCrypto {
  constructor(roomId) {
    this.roomId = roomId;
    this.keyPair = null;
    this.myPublicKeyB64 = null;
    this.peerPublicKey = null;
    this.peerPublicKeyB64 = null;
    
    // Domain-separated subkeys
    this.messageKey = null;     // KM: AES-GCM-256
    this.fileWrapKey = null;    // KW: AES-GCM-256
    this.verifyKey = null;      // KV: HMAC-SHA256
    this.safetyFingerprint = null; // 12-digit verification code
    
    this.dbName = 'nc_e2ee_db';
    this.storeName = 'keystore';
  }

  // ============================================================================
  // Utility Conversions (Base64 <-> ArrayBuffer)
  // ============================================================================
  static arrayBufferToBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = '';
    const len = bytes.byteLength;
    for (let i = 0; i < len; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return window.btoa(binary);
  }

  static base64ToArrayBuffer(base64) {
    const binary = window.atob(base64);
    const len = binary.length;
    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
      bytes[i] = binary.charCodeAt(i);
    }
    return bytes.buffer;
  }

  // ============================================================================
  // IndexedDB Ephemeral Key Persistence
  // ============================================================================
  async openDB() {
    return new Promise((resolve, reject) => {
      if (!window.indexedDB) {
        return reject(new Error("IndexedDB is not supported in this browser."));
      }
      const request = window.indexedDB.open(this.dbName, 1);
      request.onupgradeneeded = (e) => {
        const db = e.target.result;
        if (!db.objectStoreNames.contains(this.storeName)) {
          db.createObjectStore(this.storeName, { keyPath: 'id' });
        }
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }

  async loadStoredKeyPair() {
    try {
      const db = await this.openDB();
      return new Promise((resolve, reject) => {
        const tx = db.transaction(this.storeName, 'readonly');
        const store = tx.objectStore(this.storeName);
        const req = store.get(`room_${this.roomId}`);
        req.onsuccess = () => resolve(req.result || null);
        req.onerror = () => reject(req.error);
      });
    } catch (e) {
      console.warn("Could not access IndexedDB for key loading:", e);
      return null;
    }
  }

  async saveStoredKeyPair(keyPair, pubB64) {
    try {
      const db = await this.openDB();
      return new Promise((resolve, reject) => {
        const tx = db.transaction(this.storeName, 'readwrite');
        const store = tx.objectStore(this.storeName);
        const req = store.put({
          id: `room_${this.roomId}`,
          keyPair: keyPair,
          publicKeyB64: pubB64,
          createdAt: Date.now()
        });
        req.onsuccess = () => resolve();
        req.onerror = () => reject(req.error);
      });
    } catch (e) {
      console.warn("Could not persist keypair to IndexedDB:", e);
    }
  }

  async purgeStoredKey() {
    try {
      const db = await this.openDB();
      return new Promise((resolve) => {
        const tx = db.transaction(this.storeName, 'readwrite');
        const store = tx.objectStore(this.storeName);
        store.delete(`room_${this.roomId}`);
        tx.oncomplete = () => resolve();
      });
    } catch (e) {
      // Ignore cleanup error
    }
  }

  // ============================================================================
  // Key Generation & Initialization
  // ============================================================================
  async init() {
    // 1. Try to load existing non-extractable keypair from IndexedDB
    const stored = await this.loadStoredKeyPair();
    if (stored && stored.keyPair && stored.publicKeyB64) {
      this.keyPair = stored.keyPair;
      this.myPublicKeyB64 = stored.publicKeyB64;
      return this.myPublicKeyB64;
    }

    // 2. Generate new ephemeral ECDH P-256 keypair
    // Note: privateKey is non-extractable to prevent raw key leakage
    this.keyPair = await window.crypto.subtle.generateKey(
      {
        name: "ECDH",
        namedCurve: "P-256"
      },
      false, // non-extractable private key
      ["deriveKey", "deriveBits"]
    );

    // Export raw public key to Base64
    const rawPub = await window.crypto.subtle.exportKey("raw", this.keyPair.publicKey);
    this.myPublicKeyB64 = PrivateRoomCrypto.arrayBufferToBase64(rawPub);

    // Persist in IndexedDB for session lifetime
    await this.saveStoredKeyPair(this.keyPair, this.myPublicKeyB64);

    return this.myPublicKeyB64;
  }

  // ============================================================================
  // Public Key Registration & Session Key Derivation
  // ============================================================================
  async establishSessionWithPeer(peerPublicKeyB64) {
    if (!peerPublicKeyB64) {
      throw new Error("Peer public key cannot be empty.");
    }
    if (!this.keyPair) {
      await this.init();
    }

    // Import peer public key from raw base64
    const rawPeerBytes = PrivateRoomCrypto.base64ToArrayBuffer(peerPublicKeyB64);
    this.peerPublicKey = await window.crypto.subtle.importKey(
      "raw",
      rawPeerBytes,
      {
        name: "ECDH",
        namedCurve: "P-256"
      },
      false,
      []
    );
    this.peerPublicKeyB64 = peerPublicKeyB64;

    // 1. Compute ECDH 256-bit raw shared secret
    const sharedSecretBits = await window.crypto.subtle.deriveBits(
      {
        name: "ECDH",
        public: this.peerPublicKey
      },
      this.keyPair.privateKey,
      256
    );

    // 2. Import shared secret as HKDF master key
    const hkdfKey = await window.crypto.subtle.importKey(
      "raw",
      sharedSecretBits,
      "HKDF",
      false,
      ["deriveKey"]
    );

    // 3. Compute deterministic salt: SHA-256(NearbyChat-Salt-v1|roomId|minPub|maxPub)
    const [pubA, pubB] = [this.myPublicKeyB64, this.peerPublicKeyB64].sort();
    const saltContext = `NearbyChat-Salt-v1|${this.roomId}|${pubA}|${pubB}`;
    const saltBytes = await window.crypto.subtle.digest("SHA-256", new TextEncoder().encode(saltContext));

    // 4. Derive Message Encryption Key (KM: AES-GCM-256)
    this.messageKey = await window.crypto.subtle.deriveKey(
      {
        name: "HKDF",
        hash: "SHA-256",
        salt: saltBytes,
        info: new TextEncoder().encode("NearbyChat-PrivateRoom-v1|message-encryption")
      },
      hkdfKey,
      { name: "AES-GCM", length: 256 },
      false,
      ["encrypt", "decrypt"]
    );

    // 5. Derive File Key Wrapping Key (KW: AES-GCM-256)
    this.fileWrapKey = await window.crypto.subtle.deriveKey(
      {
        name: "HKDF",
        hash: "SHA-256",
        salt: saltBytes,
        info: new TextEncoder().encode("NearbyChat-PrivateRoom-v1|file-key-wrapping")
      },
      hkdfKey,
      { name: "AES-GCM", length: 256 },
      false,
      ["encrypt", "decrypt"]
    );

    // 6. Derive Verification Key (KV: HMAC-SHA256)
    this.verifyKey = await window.crypto.subtle.deriveKey(
      {
        name: "HKDF",
        hash: "SHA-256",
        salt: saltBytes,
        info: new TextEncoder().encode("NearbyChat-PrivateRoom-v1|verification-fingerprint")
      },
      hkdfKey,
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["sign"]
    );

    // 7. Compute deterministic 12-digit Safety Fingerprint
    await this.computeSafetyFingerprint(pubA, pubB);

    return {
      sessionEstablished: true,
      safetyFingerprint: this.safetyFingerprint
    };
  }

  async computeSafetyFingerprint(pubA, pubB) {
    const transcript = `NearbyChat-Verify-v1|${this.roomId}|${pubA}|${pubB}`;
    const sigBuffer = await window.crypto.subtle.sign(
      "HMAC",
      this.verifyKey,
      new TextEncoder().encode(transcript)
    );
    const bytes = new Uint8Array(sigBuffer);

    // Format into 12 decimal digits (3 groups of 4 digits)
    const part1 = String(((bytes[0] << 24) | (bytes[1] << 16) | (bytes[2] << 8) | bytes[3]) >>> 0).slice(-4).padStart(4, '0');
    const part2 = String(((bytes[4] << 24) | (bytes[5] << 16) | (bytes[6] << 8) | bytes[7]) >>> 0).slice(-4).padStart(4, '0');
    const part3 = String(((bytes[8] << 24) | (bytes[9] << 16) | (bytes[10] << 8) | bytes[11]) >>> 0).slice(-4).padStart(4, '0');

    this.safetyFingerprint = `${part1} ${part2} ${part3}`;
    return this.safetyFingerprint;
  }

  // ============================================================================
  // Message Encryption & Decryption (with AES-GCM AAD Binding)
  // ============================================================================
  async encryptText(plaintext, myRole) {
    if (!this.messageKey) {
      throw new Error("E2EE session not established. Cannot encrypt message.");
    }
    const role = (myRole === 'creator') ? 'creator' : 'guest';
    const aadString = `NearbyChat-Msg-v1|${this.roomId}|${role}|text`;
    const aadBytes = new TextEncoder().encode(aadString);

    // 96-bit (12-byte) cryptographically secure random IV
    const iv = window.crypto.getRandomValues(new Uint8Array(12));
    const plaintextBytes = new TextEncoder().encode(plaintext);

    const ciphertextBuffer = await window.crypto.subtle.encrypt(
      {
        name: "AES-GCM",
        iv: iv,
        additionalData: aadBytes
      },
      this.messageKey,
      plaintextBytes
    );

    return JSON.stringify({
      v: 1,
      iv: PrivateRoomCrypto.arrayBufferToBase64(iv),
      ciphertext: PrivateRoomCrypto.arrayBufferToBase64(ciphertextBuffer)
    });
  }

  async decryptText(envelopeJsonString, senderRole) {
    if (!this.messageKey) {
      throw new Error("E2EE session not established. Cannot decrypt message.");
    }

    let parsed;
    try {
      parsed = JSON.parse(envelopeJsonString);
    } catch (e) {
      // Fallback if message was plaintext from pre-E2EE
      return envelopeJsonString;
    }

    if (!parsed || !parsed.iv || !parsed.ciphertext) {
      return envelopeJsonString;
    }

    const role = (senderRole === 'creator') ? 'creator' : 'guest';
    const aadString = `NearbyChat-Msg-v1|${this.roomId}|${role}|text`;
    const aadBytes = new TextEncoder().encode(aadString);

    const ivBytes = PrivateRoomCrypto.base64ToArrayBuffer(parsed.iv);
    const ciphertextBytes = PrivateRoomCrypto.base64ToArrayBuffer(parsed.ciphertext);

    try {
      const decryptedBuffer = await window.crypto.subtle.decrypt(
        {
          name: "AES-GCM",
          iv: ivBytes,
          additionalData: aadBytes
        },
        this.messageKey,
        ciphertextBytes
      );
      return new TextDecoder().decode(decryptedBuffer);
    } catch (e) {
      console.error("AES-GCM Decryption failure (authentication tag or AAD mismatch):", e);
      throw new Error("Message authentication failed. Ciphertext could not be decrypted.");
    }
  }

  // ============================================================================
  // Media / File Encryption & Decryption (with Key Wrapping & AAD)
  // ============================================================================
  async encryptMedia(fileBuffer, clientMsgId) {
    if (!this.fileWrapKey) {
      throw new Error("E2EE session not established. Cannot encrypt media.");
    }

    // 1. Generate unique 256-bit AES-GCM file key
    const fileKey = await window.crypto.subtle.generateKey(
      { name: "AES-GCM", length: 256 },
      true, // extractable so we can wrap it under KW
      ["encrypt", "decrypt"]
    );

    // 2. Encrypt file binary buffer
    const fileIV = window.crypto.getRandomValues(new Uint8Array(12));
    const encryptedFileBuffer = await window.crypto.subtle.encrypt(
      {
        name: "AES-GCM",
        iv: fileIV
      },
      fileKey,
      fileBuffer
    );

    // 3. Wrap fileKey using KW with AAD binding to clientMsgId
    const rawKeyBytes = await window.crypto.subtle.exportKey("raw", fileKey);
    const wrapIV = window.crypto.getRandomValues(new Uint8Array(12));
    const fileAad = `NearbyChat-FileKey-v1|${this.roomId}|${clientMsgId}`;
    const wrappedKeyBuffer = await window.crypto.subtle.encrypt(
      {
        name: "AES-GCM",
        iv: wrapIV,
        additionalData: new TextEncoder().encode(fileAad)
      },
      this.fileWrapKey,
      rawKeyBytes
    );

    // Combine wrapIV (12 bytes) + wrapped key ciphertext into single base64 string
    const combinedWrapBytes = new Uint8Array(wrapIV.byteLength + wrappedKeyBuffer.byteLength);
    combinedWrapBytes.set(wrapIV, 0);
    combinedWrapBytes.set(new Uint8Array(wrappedKeyBuffer), wrapIV.byteLength);

    return {
      encryptedBlob: new Blob([encryptedFileBuffer], { type: 'application/octet-stream' }),
      encryptedFileKey: PrivateRoomCrypto.arrayBufferToBase64(combinedWrapBytes.buffer),
      fileIV: PrivateRoomCrypto.arrayBufferToBase64(fileIV.buffer)
    };
  }

  async decryptMedia(encryptedFileBuffer, encryptedFileKeyB64, fileIvB64, clientMsgId, mimeType) {
    if (!this.fileWrapKey) {
      throw new Error("E2EE session not established. Cannot decrypt media.");
    }

    // 1. Unwrap fileKey
    const combinedWrapBytes = new Uint8Array(PrivateRoomCrypto.base64ToArrayBuffer(encryptedFileKeyB64));
    const wrapIV = combinedWrapBytes.slice(0, 12);
    const wrappedKeyCiphertext = combinedWrapBytes.slice(12);

    const fileAad = `NearbyChat-FileKey-v1|${this.roomId}|${clientMsgId}`;
    const rawKeyBuffer = await window.crypto.subtle.decrypt(
      {
        name: "AES-GCM",
        iv: wrapIV,
        additionalData: new TextEncoder().encode(fileAad)
      },
      this.fileWrapKey,
      wrappedKeyCiphertext
    );

    const fileKey = await window.crypto.subtle.importKey(
      "raw",
      rawKeyBuffer,
      { name: "AES-GCM", length: 256 },
      false,
      ["decrypt"]
    );

    // 2. Decrypt file binary buffer
    const fileIV = new Uint8Array(PrivateRoomCrypto.base64ToArrayBuffer(fileIvB64));
    const decryptedBuffer = await window.crypto.subtle.decrypt(
      {
        name: "AES-GCM",
        iv: fileIV
      },
      fileKey,
      encryptedFileBuffer
    );

    return new Blob([decryptedBuffer], { type: mimeType || 'application/octet-stream' });
  }
}

window.PrivateRoomCrypto = PrivateRoomCrypto;
