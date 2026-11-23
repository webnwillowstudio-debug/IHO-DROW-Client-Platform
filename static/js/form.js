/* DROW client form: steps, checks, review and draft saving. */
(function () {
  'use strict';
  var form = document.getElementById('drow-form');
  if (!form) return;

  var steps = Array.prototype.slice.call(form.querySelectorAll('.step'));
  var dots = document.querySelectorAll('[data-step-dot]');
  var fillBar = document.getElementById('stepper-fill');
  var nextBtn = document.getElementById('next-btn');
  var backBtn = document.getElementById('back-btn');
  var submitBtn = document.getElementById('submit-btn');
  var DRAFT_KEY = 'drow-draft-v1';
  var current = 0;

  /* ---------------- helpers ---------------- */
  function $(sel, root) { return (root || form).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || form).querySelectorAll(sel)); }
  function val(name) { var el = form.elements[name]; return el ? (el.value || '').trim() : ''; }
  function checkedVals(name) { return $$('input[name="' + name + '"]:checked').map(function (i) { return i.value; }); }

  function setError(field, msg) {
    var box = field.closest('.field') || field;
    box.classList.add('has-error');
    var p = box.querySelector('.field-error.js-err');
    if (!p) {
      p = document.createElement('p');
      p.className = 'field-error js-err';
      p.setAttribute('role', 'alert');
      box.appendChild(p);
    }
    p.textContent = msg;
  }
  function clearErrors(root) {
    $$('.js-err', root).forEach(function (p) { p.remove(); });
    $$('.has-error', root).forEach(function (b) { b.classList.remove('has-error'); });
  }

  /* ---------------- step checks ---------------- */
  function digits(s) { return (s.match(/\d/g) || []).length; }
  function num(s) { return s.replace(/,/g, '').trim(); }

  var checks = {
    1: function () {
      var bad = [];
      if (val('client_name').length < 2) bad.push([form.elements.client_name, 'Please enter your full name.']);
      var d = digits(val('phone'));
      if (d < 7 || d > 15) bad.push([form.elements.phone, 'Please enter a valid phone / WhatsApp number with country code.']);
      if (!val('project_location')) bad.push([form.elements.project_location, 'Please tell us where the house will be built.']);
      return bad;
    },
    2: function () {
      var bad = [];
      var any = checkedVals('inside_amenities').length + checkedVals('outer_amenities').length;
      if (!any && !val('inside_other') && !val('outer_other'))
        bad.push([document.getElementById('amenities-field'), 'Please choose at least one amenity you want.']);
      if (!val('arch_style')) bad.push([form.elements.arch_style, "Please choose a design style (or 'Not sure')."]);
      return bad;
    },
    3: function () {
      var bad = [];
      if (!checkedVals('land_owner').length)
        bad.push([document.getElementById('land-owner-field'), 'Please tell us whose name the land is in.']);
      var a = val('plot_area');
      if (a && (isNaN(a) || +a < 0)) bad.push([form.elements.plot_area, 'Please enter the plot area as a number.']);
      var b = num(val('budget_amount'));
      if (!b || isNaN(b) || +b <= 0) bad.push([form.elements.budget_amount, 'Please enter your estimated total budget as a number.']);
      return bad;
    },
    4: function () {
      var c = form.elements.consent;
      return c.checked ? [] : [[c, 'Please agree so our team can contact you.']];
    }
  };

  function validateStep(n) {
    var step = steps[n - 1];
    clearErrors(step);
    var bad = checks[n] ? checks[n]() : [];
    bad.forEach(function (b) { setError(b[0], b[1]); });
    if (bad.length) {
      var first = bad[0][0];
      (first.closest('.field') || first).scrollIntoView({ behavior: 'smooth', block: 'center' });
      if (first.focus && first.tagName !== 'DIV') setTimeout(function () { first.focus({ preventScroll: true }); }, 300);
    }
    return !bad.length;
  }

  /* ---------------- navigation ---------------- */
  function show(i, scroll) {
    current = Math.max(0, Math.min(steps.length - 1, i));
    steps.forEach(function (s, k) { s.classList.toggle('active', k === current); });
    Array.prototype.forEach.call(dots, function (d, k) {
      d.classList.toggle('active', k === current);
      d.classList.toggle('done', k < current);
    });
    fillBar.style.width = ((current + 1) / steps.length * 100) + '%';
    backBtn.style.display = current === 0 ? 'none' : '';
    var last = current === steps.length - 1;
    nextBtn.style.display = last ? 'none' : '';
    submitBtn.style.display = last ? 'inline-flex' : 'none';
    if (last) buildReview();
    if (scroll) document.querySelector('.stepper').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  nextBtn.addEventListener('click', function () {
    if (validateStep(current + 1)) show(current + 1, true);
  });
  backBtn.addEventListener('click', function () { show(current - 1, true); });

  form.addEventListener('submit', function (e) {
    for (var n = 1; n <= steps.length; n++) {
      if (!validateStep(n)) { e.preventDefault(); show(n - 1, false); validateStep(n); return; }
    }
    submitBtn.disabled = true;
    submitBtn.textContent = 'Sending...';
    var signUrl = form.getAttribute('data-upload-urls');
    if (signUrl && picked.length) {
      e.preventDefault();
      sending.open('Uploading your files', 'Starting...', 0);
      uploadDirect(signUrl).then(function () {
        sending.open('Saving your details', 'Almost done...', 100);
        fileInput.disabled = true; // files are already stored; don't send them again
        HTMLFormElement.prototype.submit.call(form);
      }, function () {
        sending.close();
        submitBtn.disabled = false;
        submitBtn.textContent = 'Send my DROW';
        fileErr.hidden = false;
        fileErr.textContent = 'Could not upload the files. Check your connection and try again, or remove the files to send without them.';
        show(1, false);
        fileErr.scrollIntoView({ behavior: 'smooth', block: 'center' });
      });
    } else {
      // no progress events for a normal form post, so the bar just moves on its own
      sending.open(picked.length ? 'Uploading your files' : 'Sending your DROW',
                   picked.length ? 'This can take a minute on mobile data' : 'Just a moment...', null);
    }
  });

  /* ---------------- "sending" screen ---------------- */
  var sending = (function () {
    var box = document.createElement('div');
    box.className = 'sending';
    box.setAttribute('role', 'alertdialog');
    box.setAttribute('aria-live', 'polite');
    box.setAttribute('aria-label', 'Sending your form');
    box.hidden = true;
    box.innerHTML =
      '<div class="sending-card">' +
        '<div class="sending-spin" aria-hidden="true"><svg viewBox="0 0 64 64" width="44" height="44">' +
          '<path d="M14 31 32 16l18 15" fill="none" stroke="#E6C15A" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>' +
          '<path d="M19 29v18h26V29" fill="none" stroke="#fff" stroke-width="4" stroke-linejoin="round"/></svg></div>' +
        '<p class="sending-title"></p>' +
        '<div class="sending-bar"><span></span></div>' +
        '<p class="sending-sub"></p>' +
        '<p class="sending-note">Please keep this page open.</p>' +
      '</div>';
    document.body.appendChild(box);
    var title = box.querySelector('.sending-title'), sub = box.querySelector('.sending-sub');
    var bar = box.querySelector('.sending-bar'), fill = bar.querySelector('span');
    return {
      open: function (t, s, pct) {
        title.textContent = t; sub.textContent = s;
        bar.classList.toggle('indeterminate', pct === null);
        if (pct !== null) fill.style.width = Math.max(3, pct) + '%';
        box.hidden = false;
        document.documentElement.classList.add('is-sending');
      },
      close: function () { box.hidden = true; document.documentElement.classList.remove('is-sending'); }
    };
  })();

  // coming back with the browser's Back button: don't leave the screen stuck
  window.addEventListener('pageshow', function (ev) {
    if (ev.persisted) {
      sending.close();
      submitBtn.disabled = false;
      submitBtn.textContent = 'Send my DROW';
    }
  });

  function mb(n) { return (n / 1048576).toFixed(1) + ' MB'; }

  // Cloud mode: ask the server for signed URLs, then send each file straight to storage
  function uploadDirect(signUrl) {
    $$('input[name="uploaded"]').forEach(function (i) { i.remove(); });
    var total = picked.reduce(function (a, f) { return a + f.size; }, 0) || 1;
    var sent = picked.map(function () { return 0; });
    var done = 0;
    function report() {
      var bytes = sent.reduce(function (a, b) { return a + b; }, 0);
      var pct = Math.min(99, Math.round(bytes / total * 100));
      sending.open('Uploading your files',
        done + ' of ' + picked.length + ' file' + (picked.length > 1 ? 's' : '') + ' done  ·  ' +
        mb(bytes) + ' of ' + mb(total) + '  ·  ' + pct + '%', pct);
    }
    report();
    return fetch(signUrl, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': form.elements._csrf.value },
      body: JSON.stringify({ files: picked.map(function (f) { return { name: f.name, size: f.size }; }) })
    }).then(function (r) { if (!r.ok) throw new Error('sign'); return r.json(); })
      .then(function (res) {
        return Promise.all(picked.map(function (f, i) {
          var slot = res.files[i];
          if (!slot) { sent[i] = f.size; done++; report(); return null; }
          return new Promise(function (resolve, reject) {
            // XMLHttpRequest (not fetch) so we can show upload progress
            var x = new XMLHttpRequest();
            x.open('PUT', slot.url);
            x.setRequestHeader('Content-Type', f.type || 'application/octet-stream');
            x.setRequestHeader('x-upsert', 'false');
            x.upload.onprogress = function (ev) { if (ev.lengthComputable) { sent[i] = ev.loaded; report(); } };
            x.onload = function () {
              if (x.status < 200 || x.status >= 300) return reject(new Error('upload'));
              sent[i] = f.size; done++; report();
              var h = document.createElement('input');
              h.type = 'hidden'; h.name = 'uploaded'; h.value = slot.path;
              form.appendChild(h);
              resolve();
            };
            x.onerror = x.onabort = function () { reject(new Error('upload')); };
            x.send(f);
          });
        }));
      });
  }

  // Enter key in a text input goes to the next step instead of submitting
  form.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && e.target.tagName === 'INPUT' && current < steps.length - 1) {
      e.preventDefault();
      nextBtn.click();
    }
  });

  // clear a field's error as soon as the person changes it
  form.addEventListener('input', function (e) {
    var box = e.target.closest && e.target.closest('.field');
    if (box && box.classList.contains('has-error')) {
      box.classList.remove('has-error');
      $$('.field-error', box).forEach(function (p) { if (p.id !== 'file-error') p.remove(); });
    }
  });

  /* ---------------- style "Other" ---------------- */
  var styleSel = form.elements.arch_style, styleOther = document.getElementById('arch_style_other');
  function toggleOther() { styleOther.hidden = styleSel.value !== 'Other'; }
  styleSel.addEventListener('change', toggleOther);

  /* ---------------- budget in words ---------------- */
  var budgetWords = document.getElementById('budget-words');
  function indian(n) {
    var s = String(Math.round(n)); if (s.length <= 3) return s;
    var tail = s.slice(-3), head = s.slice(0, -3);
    return head.replace(/\B(?=(\d{2})+(?!\d))/g, ',') + ',' + tail;
  }
  function trimNum(x) { return (+x.toFixed(2)).toString(); }
  function updateBudget() {
    var raw = num(val('budget_amount')), cur = val('budget_currency');
    if (!raw || isNaN(raw)) { budgetWords.textContent = ''; return; }
    var n = +raw, txt;
    if (cur === 'INR') {
      txt = '₹ ' + indian(n);
      if (n >= 1e7) txt += '  =  ' + trimNum(n / 1e7) + ' Crore';
      else if (n >= 1e5) txt += '  =  ' + trimNum(n / 1e5) + ' Lakh';
    } else {
      txt = cur + ' ' + n.toLocaleString('en-US', { maximumFractionDigits: 0 });
      if (n >= 1e6) txt += '  =  ' + trimNum(n / 1e6) + ' million';
    }
    budgetWords.textContent = txt;
  }
  form.elements.budget_amount.addEventListener('input', updateBudget);
  form.elements.budget_currency.addEventListener('change', updateBudget);

  /* ---------------- file upload list ---------------- */
  var fileInput = document.getElementById('references');
  var fileList = document.getElementById('file-list');
  var fileErr = document.getElementById('file-error');
  var drop = fileInput.closest('.drop');
  var MAX_FILES = 6, MAX_MB = 8;
  var picked = [];
  var canEditFiles = typeof DataTransfer !== 'undefined';

  function syncFiles() {
    if (canEditFiles) {
      var dt = new DataTransfer();
      picked.forEach(function (f) { dt.items.add(f); });
      fileInput.files = dt.files;
    }
    fileList.innerHTML = '';
    picked.forEach(function (f, i) {
      var li = document.createElement('li');
      var thumb;
      if (/^image\//.test(f.type) && window.URL) {
        thumb = document.createElement('img');
        thumb.src = URL.createObjectURL(f);
        thumb.alt = '';
      } else {
        thumb = document.createElement('span');
        thumb.className = 'fi';
        thumb.textContent = (f.name.split('.').pop() || 'FILE').toUpperCase().slice(0, 4);
      }
      var name = document.createElement('span');
      name.textContent = f.name + '  (' + (f.size / 1048576).toFixed(1) + ' MB)';
      li.appendChild(thumb); li.appendChild(name);
      if (canEditFiles) {
        var x = document.createElement('button');
        x.type = 'button'; x.setAttribute('aria-label', 'Remove ' + f.name); x.textContent = '×';
        x.addEventListener('click', function () { picked.splice(i, 1); syncFiles(); });
        li.appendChild(x);
      }
      fileList.appendChild(li);
    });
  }

  function addFiles(list) {
    var msgs = [];
    Array.prototype.forEach.call(list, function (f) {
      if (!/\.(jpe?g|png|webp|heic|pdf)$/i.test(f.name)) { msgs.push(f.name + ': only photos or PDF'); return; }
      if (f.size > MAX_MB * 1048576) { msgs.push(f.name + ': larger than ' + MAX_MB + ' MB'); return; }
      if (picked.length >= MAX_FILES) { msgs.push('Maximum ' + MAX_FILES + ' files'); return; }
      picked.push(f);
    });
    fileErr.hidden = !msgs.length;
    fileErr.textContent = msgs.join(' · ');
    syncFiles();
  }

  fileInput.addEventListener('change', function () {
    if (!canEditFiles) { picked = Array.prototype.slice.call(fileInput.files); syncFiles(); return; }
    var fresh = Array.prototype.slice.call(fileInput.files);
    // the input now only holds the new pick; merge with earlier picks
    var dt = new DataTransfer(); picked.forEach(function (f) { dt.items.add(f); }); fileInput.files = dt.files;
    addFiles(fresh);
  });
  ['dragenter', 'dragover'].forEach(function (ev) {
    drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.add('drag'); });
  });
  ['dragleave', 'drop'].forEach(function (ev) {
    drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.remove('drag'); });
  });
  drop.addEventListener('drop', function (e) { if (e.dataTransfer && e.dataTransfer.files) addFiles(e.dataTransfer.files); });

  /* ---------------- review ---------------- */
  function esc(s) { var d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
  function listWithOther(name, other) {
    var a = checkedVals(name);
    val(other).split(',').forEach(function (x) { x = x.trim(); if (x) a.push(x); });
    return a.join(', ');
  }
  function buildReview() {
    var style = val('arch_style') === 'Other' && val('arch_style_other') ? 'Other: ' + val('arch_style_other') : val('arch_style');
    var area = val('plot_area') ? val('plot_area') + ' ' + val('plot_unit') : '';
    var sections = [
      ['About you', 1, [
        ['Name', val('client_name')], ['Phone / WhatsApp', val('phone')],
        ['Project location', val('project_location')]
      ]],
      ['D — Dream Home', 2, [
        ['Inside', listWithOther('inside_amenities', 'inside_other')],
        ['Outer', listWithOther('outer_amenities', 'outer_other')],
        ['Style', style],
        ['References & notes', val('design_notes')],
        ['Files', picked.length ? picked.length + ' file(s) attached' : '']
      ]],
      ['R — Resources', 3, [
        ['Land in your own name?', checkedVals('land_owner').join('')],
        ['Plot area', area], ['Plot details & site conditions', val('site_conditions')],
        ['Budget', budgetWords.textContent || (val('budget_currency') + ' ' + val('budget_amount'))]
      ]]
    ];
    var html = sections.map(function (s) {
      var rows = s[2].filter(function (r) { return r[1]; }).map(function (r) {
        return '<div><dt>' + esc(r[0]) + '</dt><dd>' + esc(r[1]) + '</dd></div>';
      }).join('');
      return '<section><header><span>' + esc(s[0]) + '</span><button type="button" data-goto="' + (s[1] - 1) + '">Edit</button></header><dl>' + rows + '</dl></section>';
    }).join('');
    var box = document.getElementById('review');
    box.innerHTML = html;
    $$('[data-goto]', box).forEach(function (b) {
      b.addEventListener('click', function () { show(+b.getAttribute('data-goto'), true); });
    });
  }

  /* ---------------- draft saved on this device ---------------- */
  var savedNote = document.getElementById('saved-note');
  var SKIP = { _csrf: 1, website: 1, references: 1 };
  function saveDraft() {
    try {
      var out = {};
      $$('input, select, textarea').forEach(function (el) {
        if (!el.name || SKIP[el.name] || el.type === 'file') return;
        if (el.type === 'checkbox' || el.type === 'radio') {
          if (!out[el.name]) out[el.name] = [];
          if (el.checked) out[el.name].push(el.value);
        } else out[el.name] = el.value;
      });
      localStorage.setItem(DRAFT_KEY, JSON.stringify(out));
      savedNote.hidden = false;
    } catch (e) { /* storage not available: fine */ }
  }
  function loadDraft() {
    try {
      var raw = localStorage.getItem(DRAFT_KEY);
      if (!raw) return;
      var d = JSON.parse(raw);
      $$('input, select, textarea').forEach(function (el) {
        if (!el.name || SKIP[el.name] || !(el.name in d)) return;
        if (el.type === 'checkbox' || el.type === 'radio') el.checked = d[el.name].indexOf(el.value) !== -1;
        else el.value = d[el.name];
      });
      savedNote.hidden = false;
    } catch (e) { /* ignore broken drafts */ }
  }
  var t;
  form.addEventListener('input', function () { clearTimeout(t); t = setTimeout(saveDraft, 400); });
  form.addEventListener('change', function () { clearTimeout(t); t = setTimeout(saveDraft, 200); });

  /* ---------------- start ---------------- */
  var serverErrors = !!document.getElementById('error-summary');
  if (!serverErrors) loadDraft();
  toggleOther();
  updateBudget();

  var start = 0;
  if (serverErrors) {
    var firstBad = form.querySelector('.has-error');
    var st = firstBad && firstBad.closest('.step');
    if (st) start = steps.indexOf(st);
  }
  show(start, false);
})();
