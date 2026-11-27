export function initializeWaitlist() {
  const form = document.getElementById('waitlist-form');
  if (!form) return;
  const status = document.getElementById('waitlist-status');
  const email = document.getElementById('waitlist-email');
  const consent = document.getElementById('waitlist-consent');
  const submit = form.querySelector('button[type="submit"]');
  if (!status || !email || !consent || !submit) return;

  const fields = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term'];
  const campaignKey = 'vipi-first-touch-campaign-v1';
  const visitorKey = 'vipi-visitor-id-v1';
  class SubmissionError extends Error {}

  function readSession(key) {
    try {
      return sessionStorage.getItem(key);
    } catch (_) {
      return null;
    }
  }

  function writeSession(key, value) {
    try {
      sessionStorage.setItem(key, value);
    } catch (_) {
      /* Storage can be unavailable. */
    }
  }

  function currentCampaign() {
    const params = new URLSearchParams(location.search);
    const incoming = {};
    for (const field of fields) {
      const value = params.get(field);
      if (value) incoming[field] = value.slice(0, 120);
    }
    if (Object.keys(incoming).length) {
      const firstTouch = {
        ...incoming,
        landing_path: location.pathname,
        referrer: document.referrer || '',
        captured_at: new Date().toISOString(),
      };
      writeSession(campaignKey, JSON.stringify(firstTouch));
      return firstTouch;
    }
    try {
      const saved = JSON.parse(readSession(campaignKey) || 'null');
      if (saved && typeof saved === 'object') return saved;
    } catch (_) {
      /* Fall through to an unattributed visit. */
    }
    return { landing_path: location.pathname, referrer: document.referrer || '' };
  }

  function visitorId() {
    let id = readSession(visitorKey);
    if (id) return id;
    if (crypto.randomUUID) id = crypto.randomUUID();
    else {
      const bytes = crypto.getRandomValues(new Uint8Array(16));
      id = [...bytes].map((value) => value.toString(16).padStart(2, '0')).join('');
    }
    writeSession(visitorKey, id);
    return id;
  }

  const campaign = currentCampaign();
  const visitor = visitorId();
  for (const field of fields) {
    const input = form.elements.namedItem(field);
    if (input) input.value = campaign[field] || '';
  }
  const landingPath = form.elements.namedItem('landing_path');
  const referrer = form.elements.namedItem('referrer');
  if (landingPath) landingPath.value = campaign.landing_path || location.pathname;
  if (referrer) referrer.value = campaign.referrer || document.referrer || '';

  function record(event) {
    const body = {
      event,
      visitor_id: visitor,
      path: location.pathname,
      referrer: campaign.referrer || '',
    };
    for (const field of fields) body[field] = campaign[field] || '';
    fetch('/api/marketing/event', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(body),
      keepalive: true,
    }).catch(() => {});
  }

  record('page_view');
  document.addEventListener('click', (event) => {
    const link = event.target.closest && event.target.closest('a[href="#waitlist"]');
    if (link) record('waitlist_click');
  });

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    status.textContent = '';
    status.removeAttribute('data-state');
    if (!form.reportValidity()) return;

    const payload = {};
    for (const [name, value] of new FormData(form)) payload[name] = value;
    payload.email = payload.email || email.value.trim();
    payload.consent = consent.checked ? 'yes' : '';
    payload.landing_path = campaign.landing_path || location.pathname;
    payload.referrer = campaign.referrer || document.referrer || '';
    for (const field of fields) payload[field] = campaign[field] || '';

    const originalLabel = submit.textContent;
    submit.disabled = true;
    submit.textContent = 'Saving…';
    email.readOnly = true;
    status.textContent = 'Saving your email…';

    try {
      const response = await fetch('/api/waitlist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify(payload),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok || !result.ok) {
        throw new SubmissionError(
          result.error || 'Email signup is temporarily unavailable. Try again.',
        );
      }
      status.dataset.state = 'success';
      status.textContent = 'You’re in. We’ll email you when Vipi opens on iPhone and Android.';
      submit.textContent = 'You’re in';
      consent.disabled = true;
      record('waitlist_submit_success');
    } catch (error) {
      status.dataset.state = 'error';
      status.textContent =
        error instanceof SubmissionError
          ? error.message
          : 'Couldn’t save your email. Check your connection and try again.';
      submit.disabled = false;
      submit.textContent = originalLabel;
      email.readOnly = false;
      record('waitlist_submit_error');
    }
  });
}
