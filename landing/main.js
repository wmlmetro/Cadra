/* Cadra landing page. No framework; everything here is progressive enhancement. */
(function () {
  'use strict';

  // Where a demo request goes. The design shows "Request received" on submit;
  // nothing may say that unless a request was actually delivered somewhere.
  //   endpoint — POSTed as JSON {name, organisation, email, source}; a 2xx counts as received.
  //   email    — used when there is no endpoint: opens the visitor's mail app, pre-filled.
  // With neither set, the form says it is not connected rather than pretending.
  var CONTACT = { endpoint: '', email: '' };

  var root = document.documentElement;
  var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function store(key, value) { try { localStorage.setItem(key, value); } catch (e) {} }

  /* Theme */
  var themeBtn = document.getElementById('theme-toggle');
  function syncThemeButton() {
    var label = root.getAttribute('data-theme') === 'light' ? 'Switch to dark theme' : 'Switch to light theme';
    themeBtn.setAttribute('aria-label', label);
    themeBtn.setAttribute('title', label);
  }
  themeBtn.addEventListener('click', function () {
    var next = root.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
    root.setAttribute('data-theme', next);
    store('cadra-theme', next);
    syncThemeButton();
  });
  syncThemeButton();

  /* Mobile menu */
  var menuBtn = document.getElementById('menu-toggle');
  var mobileNav = document.getElementById('mobile-nav');
  function setMenu(open) {
    mobileNav.hidden = !open;
    menuBtn.setAttribute('aria-expanded', String(open));
  }
  menuBtn.addEventListener('click', function () { setMenu(mobileNav.hidden); });
  mobileNav.addEventListener('click', function (e) { if (e.target.closest('a')) setMenu(false); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !mobileNav.hidden) { setMenu(false); menuBtn.focus(); } });
  window.addEventListener('resize', function () { if (window.innerWidth >= 900) setMenu(false); });

  /* Console: laid out at 1144px, scaled down to the width available */
  var slot = document.getElementById('console-slot');
  var box = document.getElementById('console-box');
  var consoleEl = document.getElementById('console');
  var CONSOLE_W = 1144, CONSOLE_H = 604;
  function fitConsole() {
    var w = slot.clientWidth;
    if (!w) return;
    var scale = Math.min(1, w / CONSOLE_W);
    consoleEl.style.transform = 'scale(' + scale + ')';
    box.style.height = Math.round(CONSOLE_H * scale) + 'px';
  }
  if ('ResizeObserver' in window) new ResizeObserver(fitConsole).observe(slot);
  else window.addEventListener('resize', fitConsole);
  fitConsole();

  /* Event stream */
  var POOL = [
    ['asset.transferred', 'blue', 'HQ-IT-004218 · Store B → Room 204'],
    ['request.opened', 'amber', 'REQ-10492 · AC not cooling · via WhatsApp'],
    ['po.received', 'accent', 'SAP PO 4500018812 · 24 pre-assets created'],
    ['tag.printed', 'accent', '24 tags · Station 01 · Receiving'],
    ['request.resolved', 'accent', 'REQ-10477 · Generator service · 2h 14m'],
    ['approval.pending', 'amber', 'Disposal batch D-031 · 12 assets'],
    ['asset.deployed', 'blue', 'HQ-VH-000093 · Toyota Hilux · Fleet depot'],
    ['connector.sync', 'muted', 'Vendra · 3 purchase orders · OK'],
    ['audit.room', 'blue', 'Abuja HQ · F3 · 41 of 41 scanned'],
    ['request.assigned', 'muted', 'REQ-10490 · Printer · IT support']
  ];
  var eventsEl = document.getElementById('events');
  var latestEl = document.getElementById('latest-event');
  var tick = 0;

  function eventNode(e, when, opacity) {
    var row = document.createElement('div');
    row.className = 'event';
    row.style.opacity = opacity;
    var top = document.createElement('div');
    top.className = 'event-top';
    var type = document.createElement('span');
    type.className = 'ev-' + e[1];
    type.textContent = e[0];
    var time = document.createElement('span');
    time.className = 'when';
    time.textContent = when;
    top.append(type, time);
    var text = document.createElement('div');
    text.className = 'event-text';
    text.textContent = e[2];
    row.append(top, text);
    return row;
  }

  function renderEvents() {
    var rows = [];
    for (var i = 0; i < 9; i++) {
      var e = POOL[(tick + POOL.length - i) % POOL.length];
      rows.push(eventNode(e, i === 0 ? 'now' : (i * 2 + 1) + 'm', i === 0 ? 1 : Math.max(0.35, 1 - i * 0.08)));
    }
    eventsEl.replaceChildren.apply(eventsEl, rows);
    var latest = eventNode(POOL[tick % POOL.length], 'now', 1);
    latest.className = '';
    latestEl.replaceChildren(latest);
  }
  renderEvents();
  if (!reduceMotion) {
    setInterval(function () {
      if (document.hidden) return;
      tick++;
      renderEvents();
    }, 2600);
  }

  /* Lifecycle: the step under the pointer is the highlighted one */
  var steps = Array.prototype.slice.call(document.querySelectorAll('#steps .step'));
  steps.forEach(function (step) {
    step.addEventListener('mouseenter', function () {
      steps.forEach(function (s) { s.classList.toggle('is-active', s === step); });
    });
  });

  /* Request channel tabs */
  var CHANNELS = {
    WhatsApp: { label: 'WhatsApp', addr: '+234 · service line', inbound: 'AC not cooling in HQ-F2-R204' },
    Email: { label: 'Email', addr: 'facilities@fmw.gov.ng', inbound: 'Subject: Room 204 air conditioning. Since this morning the unit has been blowing warm air.' },
    Portal: { label: 'Staff portal', addr: 'portal / new request', inbound: 'Category: HVAC · Location: HQ › F2 › R204 · "Unit not cooling"' }
  };
  var tabs = Array.prototype.slice.call(document.querySelectorAll('[role="tab"][data-channel]'));
  var panel = document.getElementById('channel-panel');
  function pickChannel(tab, focus) {
    var ch = CHANNELS[tab.dataset.channel];
    tabs.forEach(function (t) {
      var on = t === tab;
      t.setAttribute('aria-selected', String(on));
      t.tabIndex = on ? 0 : -1;
    });
    panel.setAttribute('aria-labelledby', tab.id);
    document.getElementById('channel-label').textContent = ch.label;
    document.getElementById('channel-addr').textContent = ch.addr;
    document.getElementById('channel-inbound').textContent = ch.inbound;
    if (focus) tab.focus();
  }
  tabs.forEach(function (tab, i) {
    tab.addEventListener('click', function () { pickChannel(tab, false); });
    tab.addEventListener('keydown', function (e) {
      var d = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
      if (!d) return;
      e.preventDefault();
      pickChannel(tabs[(i + d + tabs.length) % tabs.length], true);
    });
  });

  /* Tag artwork: decorative barcode and QR, seeded so they never change */
  var BARS = [2,1,1,3,1,2,1,1,3,2,1,1,2,3,1,1,2,1,3,1,1,2,2,1,3,1,2,1,1,3,1,2,1,2,1,3,1,1,2,2];
  var barcode = document.getElementById('barcode');
  BARS.forEach(function (w) {
    var s = document.createElement('span');
    s.style.width = w + 'px';
    barcode.appendChild(s);
  });
  var qr = document.getElementById('qr');
  var seed = 7;
  function rnd() { seed = (seed * 9301 + 49297) % 233280; return seed / 233280; }
  for (var i = 0; i < 81; i++) {
    var r = Math.floor(i / 9), c = i % 9;
    var finder = (r < 3 && c < 3) || (r < 3 && c > 5) || (r > 5 && c < 3);
    var on = finder ? !(r % 3 === 1 && c % 3 === 1) : rnd() > 0.5;
    var cell = document.createElement('span');
    if (on) cell.className = 'on';
    qr.appendChild(cell);
  }

  /* Demo request */
  var form = document.getElementById('demo-form');
  var errorEl = document.getElementById('demo-error');
  var done = document.getElementById('demo-done');

  function showError(msg) {
    errorEl.textContent = msg;
    errorEl.hidden = false;
  }
  function showDone(kicker, body) {
    done.querySelector('.mono').textContent = kicker;
    done.querySelector('p').textContent = body;
    form.hidden = true;
    done.hidden = false;
    done.focus();
  }
  function mailtoHref(data) {
    var body = 'Name: ' + data.name + '\nAgency or organisation: ' + data.organisation + '\nWork email: ' + data.email + '\n';
    return 'mailto:' + CONTACT.email + '?subject=' + encodeURIComponent('Cadra demo request — ' + data.organisation) + '&body=' + encodeURIComponent(body);
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    errorEl.hidden = true;
    var invalid = null;
    Array.prototype.forEach.call(form.elements, function (el) {
      if (el.tagName !== 'INPUT') return;
      var ok = el.checkValidity() && el.value.trim() !== '';
      el.setAttribute('aria-invalid', String(!ok));
      if (!ok && !invalid) invalid = el;
    });
    if (invalid) {
      showError(invalid.type === 'email' && invalid.value ? 'Please enter a valid work email.' : 'Please fill in all three fields.');
      invalid.focus();
      return;
    }
    var data = {
      name: form.elements.name.value.trim(),
      organisation: form.elements.organisation.value.trim(),
      email: form.elements.email.value.trim(),
      source: 'cadra-landing'
    };

    if (CONTACT.endpoint) {
      var btn = form.querySelector('button[type="submit"]');
      btn.disabled = true;
      fetch(CONTACT.endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })
        .then(function (res) {
          if (!res.ok) throw new Error('HTTP ' + res.status);
          showDone('REQUEST RECEIVED', "Thanks. We'll contact you within two working days to schedule your demo.");
        })
        .catch(function () {
          btn.disabled = false;
          showError(CONTACT.email
            ? 'We could not send your request. Please email ' + CONTACT.email + ' instead.'
            : 'We could not send your request. Please try again in a moment.');
        });
      return;
    }
    if (CONTACT.email) {
      window.location.href = mailtoHref(data);
      showDone('ALMOST THERE', 'Your email app should open with the request filled in. Send it and we will contact you within two working days.');
      return;
    }
    showError('Demo requests are not connected on this page yet.');
  });
})();
