/**
 * Robust Reconnecting WebSocket Manager with Backoff and Event Dispatch
 */
class RobustWebSocket {
  constructor(url, options = {}) {
    this.url = url;
    this.options = Object.assign({
      maxRetries: 10,
      initialDelay: 1000,
      maxDelay: 10000,
      heartbeatInterval: 30000,
    }, options);

    this.ws = null;
    this.retryCount = 0;
    this.isClosedManually = false;
    this.listeners = {};
    this.messageQueue = [];

    this.connect();
  }

  connect() {
    try {
      this.ws = new WebSocket(this.url);
      
      this.ws.onopen = (e) => {
        this.retryCount = 0;
        this._dispatch('open', e);
        this._flushQueue();
      };

      this.ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          this._dispatch('message', data);
          if (data.type) {
            this._dispatch(data.type, data);
          }
        } catch (err) {
          console.error("Malformed WebSocket message:", err);
        }
      };

      this.ws.onerror = (e) => {
        this._dispatch('error', e);
      };

      this.ws.onclose = (e) => {
        this._dispatch('close', e);
        if (!this.isClosedManually) {
          this._scheduleReconnect();
        }
      };
    } catch (err) {
      this._scheduleReconnect();
    }
  }

  send(data) {
    const payload = typeof data === 'string' ? data : JSON.stringify(data);
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(payload);
    } else {
      this.messageQueue.push(payload);
    }
  }

  _flushQueue() {
    while (this.messageQueue.length > 0 && this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(this.messageQueue.shift());
    }
  }

  _scheduleReconnect() {
    if (this.retryCount >= this.options.maxRetries) {
      console.warn("Max WebSocket reconnection retries reached.");
      return;
    }
    const delay = Math.min(
      this.options.initialDelay * Math.pow(1.5, this.retryCount),
      this.options.maxDelay
    );
    this.retryCount++;
    setTimeout(() => this.connect(), delay);
  }

  on(event, callback) {
    if (!this.listeners[event]) {
      this.listeners[event] = [];
    }
    this.listeners[event].push(callback);
  }

  _dispatch(event, data) {
    if (this.listeners[event]) {
      this.listeners[event].forEach(cb => {
        try { cb(data); } catch (e) { console.error(e); }
      });
    }
  }

  close() {
    this.isClosedManually = true;
    if (this.ws) {
      this.ws.close();
    }
  }
}

window.RobustWebSocket = RobustWebSocket;
