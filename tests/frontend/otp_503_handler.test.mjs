import test from 'node:test';
import assert from 'node:assert/strict';

import { handleOtpResponse } from '../../static/js/otp.js';

function createState() {
  return {
    feedback: { style: {}, innerText: '' },
    sendBtn: { disabled: false },
    sendText: { style: {}, innerText: 'Send OTP' },
    sendSpinner: { style: {} },
    resendBtn: { style: {}, innerText: 'Resend Code' },
    otpInput: { focus() {} },
  };
}

function createSessionStorage() {
  const store = new Map();
  return {
    getItem(key) { return store.has(key) ? String(store.get(key)) : null; },
    setItem(key, value) { store.set(key, value); },
    removeItem(key) { store.delete(key); },
  };
}

test('503 response shows a friendly temporary outage message without exposing technical details', () => {
  const state = createState();
  const sessionStorage = createSessionStorage();
  sessionStorage.setItem('nearby_otp_expiry', '9999999999999');

  const clearCooldown = () => {
    sessionStorage.removeItem('nearby_otp_expiry');
  };

  handleOtpResponse({
    response: { status: 503, ok: false },
    data: { error: 'Redis unavailable', detail: 'Pool is down' },
    state,
    sessionStorage,
    clearCooldown,
    startCooldown: () => { throw new Error('startCooldown should not run for 503'); },
  });

  assert.equal(state.feedback.style.display, 'block');
  assert.equal(state.feedback.style.color, 'var(--error)');
  assert.match(state.feedback.innerText, /temporarily unavailable/i);
  assert.doesNotMatch(state.feedback.innerText, /redis|pool|detail|technical/i);
  assert.equal(state.sendBtn.disabled, false);
  assert.equal(sessionStorage.getItem('nearby_otp_expiry'), null);
});

test('503 response does not start a countdown or leave stale cooldown state behind', () => {
  const state = createState();
  const sessionStorage = createSessionStorage();
  sessionStorage.setItem('nearby_otp_expiry', '9999999999999');

  let cooldownStarted = false;
  handleOtpResponse({
    response: { status: 503, ok: false },
    data: {},
    state,
    sessionStorage,
    clearCooldown: () => sessionStorage.removeItem('nearby_otp_expiry'),
    startCooldown: () => { cooldownStarted = true; },
  });

  assert.equal(cooldownStarted, false);
  assert.equal(sessionStorage.getItem('nearby_otp_expiry'), null);
  assert.equal(state.sendText.innerText, 'Send OTP');
});

test('after a 503 outage, a later successful OTP retry restores the normal countdown flow', () => {
  const state = createState();
  const sessionStorage = createSessionStorage();
  let retryExpiry = null;

  handleOtpResponse({
    response: { status: 503, ok: false },
    data: {},
    state,
    sessionStorage,
    clearCooldown: () => sessionStorage.removeItem('nearby_otp_expiry'),
    startCooldown: () => { throw new Error('cooldown should not start after 503'); },
  });

  handleOtpResponse({
    response: { status: 200, ok: true },
    data: { success: true, message: 'Verification code sent to your email.', cooldown: 60 },
    state,
    sessionStorage,
    clearCooldown: () => sessionStorage.removeItem('nearby_otp_expiry'),
    startCooldown: (expiry) => {
      retryExpiry = expiry;
    },
  });

  assert.ok(retryExpiry > Date.now());
  assert.equal(state.feedback.style.color, 'var(--success, #10b981)');
  assert.match(state.feedback.innerText, /Verification code sent/i);
  assert.ok(Number(sessionStorage.getItem('nearby_otp_expiry')) > Date.now());
});
