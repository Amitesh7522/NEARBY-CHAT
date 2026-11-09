let cooldownTimer = null;

export function isCooldownActive() {
  const expiry = parseInt(sessionStorage.getItem('nearby_otp_expiry') || '0', 10);
  return expiry > Date.now();
}

export function setFeedback(state, message, tone = 'error') {
  if (!state?.feedback) return;
  state.feedback.style.display = 'block';
  state.feedback.style.color = tone === 'success' ? 'var(--success, #10b981)' : 'var(--error)';
  state.feedback.innerText = message;
}

export function clearOtpCooldown(sessionStorage) {
  if (sessionStorage && typeof sessionStorage.removeItem === 'function') {
    sessionStorage.removeItem('nearby_otp_expiry');
  }
}

export function startCooldown(expiryTimestamp) {
  const sendBtn = document.getElementById('send-otp-btn');
  const sendText = document.getElementById('send-otp-text');
  const sendSpinner = document.getElementById('send-otp-spinner');
  const resendBtn = document.getElementById('resend-otp-btn');

  if (!sendBtn || !sendText || !sendSpinner || !resendBtn) return;

  sendSpinner.style.display = 'none';
  sendText.style.display = 'inline';
  sendBtn.disabled = true;
  resendBtn.style.display = 'inline';

  if (cooldownTimer) clearInterval(cooldownTimer);

  function update() {
    const now = Date.now();
    const remainingSeconds = Math.max(0, Math.ceil((expiryTimestamp - now) / 1000));
    if (remainingSeconds > 0) {
      sendText.innerText = `(${remainingSeconds}s)`;
      resendBtn.innerText = `Resend in (${remainingSeconds}s)`;
      resendBtn.style.opacity = '0.6';
      resendBtn.style.pointerEvents = 'none';
    } else {
      clearInterval(cooldownTimer);
      cooldownTimer = null;
      sessionStorage.removeItem('nearby_otp_expiry');
      sendBtn.disabled = false;
      sendText.innerText = 'Send OTP';
      resendBtn.innerText = 'Resend Code';
      resendBtn.style.opacity = '1';
      resendBtn.style.pointerEvents = 'auto';
    }
  }

  update();
  cooldownTimer = setInterval(update, 500);
}

export function restoreCooldownIfActive() {
  const expiry = parseInt(sessionStorage.getItem('nearby_otp_expiry') || '0', 10);
  if (expiry > Date.now()) {
    startCooldown(expiry);
  }
}

export async function requestOTP() {
  if (isCooldownActive()) return;

  const emailInput = document.getElementById('id_email');
  const email = emailInput.value.trim().toLowerCase();
  const feedback = document.getElementById('otp-feedback');
  const sendBtn = document.getElementById('send-otp-btn');
  const sendText = document.getElementById('send-otp-text');
  const sendSpinner = document.getElementById('send-otp-spinner');

  if (!email) {
    setFeedback({ feedback }, 'Please enter your email address first.', 'error');
    emailInput.focus();
    return;
  }

  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!emailRegex.test(email)) {
    setFeedback({ feedback }, 'Please enter a valid email address.', 'error');
    emailInput.focus();
    return;
  }

  sendBtn.disabled = true;
  sendText.style.display = 'none';
  sendSpinner.style.display = 'inline-block';
  feedback.style.display = 'none';

  try {
    const csrfToken = typeof document !== 'undefined'
      ? document.querySelector('input[name="csrfmiddlewaretoken"]')?.value || ''
      : '';

    const response = await fetch('/accounts/api/otp/send/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken,
      },
      body: JSON.stringify({ identifier: email, email, purpose: 'signup' }),
    });

    let data = {};
    try {
      data = await response.json();
    } catch (error) {
      data = {};
    }

    handleOtpResponse({ response, data, state: { feedback, sendBtn, sendText, sendSpinner }, sessionStorage, clearCooldown: () => clearOtpCooldown(sessionStorage), startCooldown });
  } catch (error) {
    setFeedback({ feedback }, 'Network error. Please check your connection.', 'error');
    sendBtn.disabled = false;
    sendText.style.display = 'inline';
    sendSpinner.style.display = 'none';
  }
}

export function handleOtpResponse({ response, data = {}, state, sessionStorage, clearCooldown = () => clearOtpCooldown(sessionStorage), startCooldown }) {
  const { feedback, sendBtn, sendText, sendSpinner } = state || {};

  if (response && response.ok && data && data.success) {
    setFeedback(state, `✓ ${data.message || 'Verification code sent to your email.'}`, 'success');
    const otpInput = typeof document !== 'undefined' ? document.getElementById('id_otp') : null;
    if (otpInput && typeof otpInput.focus === 'function') otpInput.focus();
    const cooldown = data.cooldown || 60;
    const expiry = Date.now() + cooldown * 1000;
    sessionStorage.setItem('nearby_otp_expiry', String(expiry));
    startCooldown(expiry);
    return;
  }

  if (response && response.status === 503) {
    setFeedback(state, 'Verification service is temporarily unavailable. Please try again later.', 'error');
    clearCooldown();
    if (sendBtn) sendBtn.disabled = false;
    if (sendText) sendText.style.display = 'inline';
    if (sendSpinner) sendSpinner.style.display = 'none';
    if (state?.sendText) state.sendText.innerText = 'Send OTP';
    return;
  }

  const fallbackMessage = data?.error || data?.detail || 'Failed to send code. Please try again.';
  setFeedback(state, fallbackMessage, 'error');

  if (data?.cooldown && data.cooldown > 0) {
    const expiry = Date.now() + data.cooldown * 1000;
    sessionStorage.setItem('nearby_otp_expiry', String(expiry));
    startCooldown(expiry);
  } else {
    if (sendBtn) sendBtn.disabled = false;
    if (sendText) sendText.style.display = 'inline';
    if (sendSpinner) sendSpinner.style.display = 'none';
  }

  if (state?.sendText && !data?.cooldown) {
    state.sendText.innerText = 'Send OTP';
  }
}

if (typeof window !== 'undefined') {
  window.requestOTP = requestOTP;
  window.startCooldown = startCooldown;
  window.restoreCooldownIfActive = restoreCooldownIfActive;
  window.addEventListener('pageshow', restoreCooldownIfActive);
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      restoreCooldownIfActive();
    }
  });

  document.addEventListener('DOMContentLoaded', () => {
    const sendBtn = document.getElementById('send-otp-btn');
    const resendBtn = document.getElementById('resend-otp-btn');
    if (sendBtn) sendBtn.addEventListener('click', requestOTP);
    if (resendBtn) resendBtn.addEventListener('click', requestOTP);
    restoreCooldownIfActive();
  });
}
