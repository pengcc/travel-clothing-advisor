/* 穿衣小伙伴：只表达冷热。数据来自 /api/pal；没有可用数据时显示不可用状态，不显示示例或历史数据。 */
(function () {
  'use strict';
  const ICON = n => `/static/pal/sprites/warmth-l${n}.png`;
  const LABELS = {1: '清爽透气', 2: '轻薄衣物', 3: '薄外套', 4: '中等厚度', 5: '保暖外套', 6: '厚实保暖'};
  const SLOT_NAMES = ['早', '午', '晚'], SLOT_KEYS = ['morning', 'midday', 'evening'], SLOT_HOURS = [7, 13, 20];
  const POLL_MS = 30 * 60 * 1000, MAX_AGE_MS = 48 * 3600 * 1000, REQUEST_MS = 10000;
  const $ = id => document.getElementById(id);
  const CITY = document.body.dataset.city || 'berlin';          // 每个城市页的 HTML 自带城市 id
  const rand = (a, b) => a + Math.random() * (b - a);
  const reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------- 小图标（只是时间提示和冷热记号） ---------- */
  const SVG = {
    sunrise: '<svg viewBox="0 0 32 32"><path d="M2 25h28" stroke="#c98a5a" stroke-width="2.5" stroke-linecap="round"/><path d="M8 25a8 8 0 0 1 16 0z" fill="#ffb347"/><g stroke="#f5a623" stroke-width="2.5" stroke-linecap="round"><path d="M16 6v3M5 13l2 2M27 13l-2 2"/></g></svg>',
    noon: '<svg viewBox="0 0 32 32"><g stroke="#f5a623" stroke-width="2.5" stroke-linecap="round"><path d="M16 2v4M16 26v4M2 16h4M26 16h4M6 6l3 3M23 23l3 3M26 6l-3 3M9 23l-3 3"/></g><circle cx="16" cy="16" r="7" fill="#ffc93c"/></svg>',
    night: '<svg viewBox="0 0 32 32"><path d="M22 3a13 13 0 1 0 8 22A11 11 0 0 1 22 3z" fill="#ffe27a"/></svg>',
    heart: '<svg viewBox="0 0 24 22"><path d="M12 21C-4 10 3-2 12 6c9-8 16 4 0 15z" fill="#ff8fa3"/></svg>',
    swing: '<svg viewBox="0 0 26 26" fill="none" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M8 21V6M4 10l4-4 4 4" stroke="#e0613b"/><path d="M18 5v15M14 16l4 4 4-4" stroke="#3a7bd5"/></svg>',
    spkOn: '<svg viewBox="0 0 24 24" fill="none" stroke="#3a2f25" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9.5v5h3.8l5.2 4.2V5.3L6.8 9.5z" fill="#ffc93c"/><path class="w1" d="M15 9.6a3.4 3.4 0 0 1 0 4.8"/><path class="w2" d="M17.4 7.4a6.6 6.6 0 0 1 0 9.2"/><path class="w3" d="M19.8 5.2a9.8 9.8 0 0 1 0 13.6"/></svg>',
    spkOff: '<svg viewBox="0 0 24 24" fill="none" stroke="#6b625a" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9.5v5h3.8l5.2 4.2V5.3L6.8 9.5z" fill="#d3cdc6"/><path d="M15.5 9.5l5 5M20.5 9.5l-5 5" stroke="#e0613b" stroke-width="2.4"/></svg>',
  };
  const SLOT_ICONS = [SVG.sunrise, SVG.noon, SVG.night];
  const clockSVG = h => `<svg viewBox="0 0 24 24" fill="none" stroke="#3a2f25" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10" fill="#fff"/><path d="M12 12V5.5"/><path d="M12 12l4.6 0" transform="rotate(${(h % 12) * 30 - 90} 12 12)" stroke-width="2.6"/></svg>`;
  function thermoSVG(t) {
    const f = Math.min(1, Math.max(.12, (t + 5) / 40)), hue = Math.round(210 - 200 * Math.min(1, Math.max(0, (t + 5) / 40)));
    const top = 3 + 15 * (1 - f), col = `hsl(${hue} 80% 52%)`;
    return `<svg viewBox="0 0 12 26"><rect x="3.5" y="1.5" width="5" height="17" rx="2.5" fill="#fff" stroke="#3a2f25" stroke-width="1.4"/><circle cx="6" cy="21" r="4" fill="${col}" stroke="#3a2f25" stroke-width="1.4"/><rect x="5" y="${top.toFixed(1)}" width="2" height="${(19 - top).toFixed(1)}" rx="1" fill="${col}"/></svg>`;
  }
  const fmtT = t => (t < 0 ? '−' : '') + Math.abs(t) + '°';
  const dotsHTML = n => '<span class="dots">' + [1, 2, 3, 4, 5, 6].map(k => `<i class="${k > n ? 'off' : ''}"></i>`).join('') + '</span>';
  const tHue = t => Math.round(210 - 200 * Math.min(1, Math.max(0, (t + 5) / 40)));
  const tPos = t => Math.min(.97, Math.max(.03, (t + 5) / 40));

  /* ---------- 状态 ---------- */
  const S = {data: null, day: 0, slot: 1, auto: true, lastSrc: '', keyL: '', clockAngle: null};
  const berlinToday = () => new Intl.DateTimeFormat('en-CA', {timeZone: 'Europe/Berlin', year: 'numeric', month: '2-digit', day: '2-digit'}).format(new Date());
  const dayName = (i, date) => i === 0 ? '今天' : i === 1 ? '明天' : '周' + '日一二三四五六'[new Date(date + 'T12:00:00Z').getUTCDay()];
  const fmtStamp = iso => `${+iso.slice(5, 7)}月${+iso.slice(8, 10)}日 ${iso.slice(11, 16)}`;
  const avail = d => d.slots.map((s, i) => s.past ? null : i).filter(i => i !== null);
  const dayLevel = d => { const s = d.slots[1].past ? d.slots.find(x => !x.past) : d.slots[1]; return s ? s.level : null; };
  function pickSlot(d) {
    const open = avail(d);
    if (!open.length) return -1;
    const order = d.swing === 'large' ? [0, 1, 2] : [1, 0, 2];
    return order.find(i => open.includes(i));
  }
  const firstOpenDay = data => { const i = data.days.findIndex(d => avail(d).length); return i < 0 ? 0 : i; };
  const curDay = () => S.data.days[S.day];
  const curSlot = () => { const d = curDay(); return S.slot >= 0 ? d.slots[S.slot] : null; };
  const curLevel = () => { const s = curSlot(); return s ? s.level : 3; };

  /* ---------- 渲染 ---------- */
  function buildLevel(lv) {
    if (S.keyL === String(lv)) return;
    S.keyL = String(lv);
    const front = $('fxFront');
    front.replaceChildren();
    const FX = {
      1: [['sweat', 3, [56, 72], [34, 50]], ['heat', 3, [22, 70], [4, 22]]],
      2: [['spark', 5, [56, 92], [6, 38]]],
      3: [['heart', 3, [30, 70], [14, 40]]],
      4: [['puff', 1, [36, 42], [52, 58]]],
      5: [['puff', 2, [36, 44], [50, 58]]],
      6: [['puff', 3, [34, 44], [50, 58]]],
    }[lv] || [];
    for (const [cls, count, [l0, l1], [t0, t1]] of FX) {
      for (let i = 0; i < count; i++) {
        const el = document.createElement('i'); el.className = cls;
        if (cls === 'heart') el.innerHTML = SVG.heart;
        el.style.cssText = `left:${rand(l0, l1)}%;top:${rand(t0, t1)}%;animation-delay:${-rand(0, 3).toFixed(2)}s`;
        front.append(el);
      }
    }
  }

  function updateThermo(d) {
    const tube = $('tube');
    if (!tube.querySelector('.mk')) {
      [0, 1, 2].forEach(i => {
        const b = document.createElement('button'); b.className = 'mk'; b.type = 'button'; b.dataset.i = i; b.style.bottom = '50%';
        b.onclick = () => chooseSlot(i, true);
        tube.append(b);
      });
    }
    const open = avail(d), ts = open.map(i => d.slots[i].temperature_c);
    const marks = [...tube.querySelectorAll('.mk')];
    marks.forEach(b => { b.hidden = !open.includes(+b.dataset.i); });
    if (!open.length) { $('thRng').style.height = '0'; return; }
    const lo = Math.min(...ts), hi = Math.max(...ts), r = $('thRng');
    r.style.bottom = tPos(lo) * 100 + '%'; r.style.height = Math.max(1.2, (tPos(hi) - tPos(lo)) * 100) + '%';
    r.style.background = `linear-gradient(to top, hsl(${tHue(lo)} 85% 55%), hsl(${tHue(hi)} 85% 55%))`;
    const pos = {}; open.forEach(i => { pos[i] = tPos(d.slots[i].temperature_c); });
    let shift = 0;
    marks.forEach(b => {
      const i = +b.dataset.i;
      if (!open.includes(i)) return;
      const s = d.slots[i], on = i === S.slot;
      b.style.bottom = pos[i] * 100 + '%'; b.style.setProperty('--mc', `hsl(${tHue(s.temperature_c)} 80% 48%)`);
      b.classList.toggle('on', on);
      b.innerHTML = on ? `<b>${fmtT(s.temperature_c)}</b>` : SLOT_ICONS[i];
      b.setAttribute('aria-label', `${SLOT_NAMES[i]} ${s.label_time}：${fmtT(s.temperature_c)}`);
      let ox = 0;
      if (!on) {
        const clash = open.some(j => j !== i && Math.abs(pos[j] - pos[i]) < (j === S.slot ? .21 : .15));
        if (clash) { shift++; ox = -(5.5 + shift * 6.5); }
      }
      b.style.setProperty('--ox', ox + 'cqw');
    });
    const cur = curSlot();
    if (cur) {
      $('thTimeT').textContent = cur.label_time;
      const want = (SLOT_HOURS[S.slot] % 12) * 30;
      if (S.clockAngle === null) S.clockAngle = want;
      else S.clockAngle += ((want - S.clockAngle) % 360 + 360) % 360;       // 时针只向前走
      $('thHand').style.transform = `rotate(${S.clockAngle}deg)`;
      $('thBulb').style.background = `hsl(${tHue(cur.temperature_c)} 85% 55%)`;
    }
    $('thTime').hidden = !cur;
  }

  function tileHTML(d, i) {
    const lv = dayLevel(d), open = avail(d), ts = open.map(k => d.slots[k].temperature_c);
    const over = !open.length;
    const rng = over ? '已过' : (Math.min(...ts) === Math.max(...ts) ? fmtT(ts[0]) : fmtT(Math.min(...ts)) + '~' + fmtT(Math.max(...ts)));
    const badge = d.swing === 'large' ? `<span role="img" aria-label="早晚温差大">${SVG.swing}</span>` : '';
    return `<img alt="" src="${ICON(lv || 3)}"><span class="name">${dayName(i, d.date)}</span><span class="rng">${rng}</span><span class="badges">${badge}</span>`;
  }

  function render() {
    const data = S.data, d = curDay(), sc = $('scene'), cur = curSlot(), lv = cur ? cur.level : 0;
    document.body.dataset.state = 'ready';
    document.body.dataset.level = lv || 3;
    sc.dataset.slot = S.slot < 0 ? 1 : S.slot; sc.dataset.lv = lv;
    $('title').textContent = dayName(S.day, d.date);

    const img = $('heroImg'), src = ICON(lv || 3);
    if (src !== S.lastSrc) { img.src = src; S.lastSrc = src; img.classList.remove('pop'); void img.offsetWidth; img.classList.add('pop'); }
    img.alt = cur ? LABELS[lv] : '今天已过';
    buildLevel(lv);
    updateThermo(d);

    const big = d.swing === 'large';
    $('label').innerHTML = cur
      ? `${LABELS[lv]}<small>${cur.label_time} · ${fmtT(cur.temperature_c)}${big ? ' · 早晚温差大' : ''}</small>`
      : `${dayName(S.day, d.date)}已过<small>选明天看看</small>`;

    const slots = $('slots');
    slots.className = 'slots ready-only' + (big ? '' : ' calm');
    slots.innerHTML = d.slots.map((s, i) => s.past
      ? `<button class="slot" type="button" disabled aria-label="${SLOT_NAMES[i]} ${s.label_time}：已过"><span class="ti">${SLOT_ICONS[i]}</span><span class="tm">${clockSVG(SLOT_HOURS[i])}${s.label_time}</span><span class="past-mark">已过</span><span class="tp"></span></button>`
      : `<button class="slot" type="button" aria-pressed="${i === S.slot}" aria-label="${SLOT_NAMES[i]} ${s.label_time}：${fmtT(s.temperature_c)}，${LABELS[s.level]}${s.partial ? '，只含剩下的小时' : ''}"><span class="ti">${SLOT_ICONS[i]}</span><span class="tm">${clockSVG(SLOT_HOURS[i])}${s.label_time}</span><img alt="" src="${ICON(s.level)}"><span class="tp">${thermoSVG(s.temperature_c)}${fmtT(s.temperature_c)}</span>${dotsHTML(s.level)}</button>`).join('');
    slots.querySelectorAll('.slot:not([disabled])').forEach((b, k) => { const idx = avail(d)[k]; b.onclick = () => chooseSlot(idx, true); });

    const strip = $('strip');
    strip.innerHTML = '';
    data.days.forEach((dd, i) => {
      const b = document.createElement('button'); b.className = 'day' + (avail(dd).length ? '' : ' over'); b.type = 'button'; b.setAttribute('role', 'listitem');
      b.setAttribute('aria-pressed', i === S.day); b.innerHTML = tileHTML(dd, i);
      b.onclick = () => chooseDay(i);
      strip.append(b);
    });

    $('fixtureBanner').hidden = !data.fixture;
    $('dataTime').textContent = '数据时间 ' + fmtStamp(data.weather_fetched_at) + '（柏林时间）';
    $('caveat').textContent = data.caveat;
    const sb = $('staleBanner');
    sb.hidden = !data.stale;
    sb.textContent = data.stale ? `数据来自 ${fmtStamp(data.weather_fetched_at)}，新数据到了会自动更新` : '';
    window.PalAudio.sync(lv || 3);
  }

  function chooseSlot(i, user) {
    if (!S.data || i === S.slot) return;
    S.slot = i; if (user) S.auto = false;
    render();
    window.PalAudio.cue(i);
    if (user) window.PalAudio.replay(curLevel());
  }
  function chooseDay(i) {
    S.day = i; S.slot = pickSlot(curDay()); S.auto = true; S.keyL = '';
    render(); window.PalAudio.pop(); window.PalAudio.replay(curLevel());
  }
  setInterval(() => {
    if (reduced || !S.data || !S.auto || document.hidden) return;
    const d = curDay(), open = avail(d);
    if (d.swing !== 'large' || open.length < 2) return;
    chooseSlot(open[(open.indexOf(S.slot) + 1) % open.length], false);
  }, 3400);

  /* ---------- 数据读取与更新（D18） ---------- */
  function showUnavailable(note) {
    S.data = null; S.keyL = ''; S.lastSrc = '';
    document.body.dataset.state = 'unavailable';
    document.body.dataset.level = 3;
    $('title').textContent = '穿衣小伙伴';
    $('unavailableNote').textContent = note || '';
    window.PalAudio.setOn(false).then(() => setSoundUI(false));
  }
  const tooOld = () => S.data && Date.now() - Date.parse(S.data.weather_fetched_at) > MAX_AGE_MS;
  function transportFailed() {
    // 网络错误或超时：数据不超过 48 小时就保留当前画面；已超过则显示不可用。
    if (!S.data) return showUnavailable('现在读不到数据');
    if (tooOld()) showUnavailable('已经超过 48 小时没有新数据');
  }
  const validData = x => x && Array.isArray(x.days) && x.days.length > 0 && typeof x.weather_fetched_at === 'string' &&
    x.days.every(d => d && Array.isArray(d.slots) && d.slots.length === 3);
  function apply(data) {
    const prev = S.data, keepDate = prev ? prev.days[S.day].date : null;
    const changed = prev && prev.data_version !== data.data_version;
    S.data = data;
    let idx = keepDate ? data.days.findIndex(d => d.date === keepDate) : -1;
    if (idx < 0 || data.days[idx].date !== keepDate) idx = firstOpenDay(data);
    const dayChanged = idx !== S.day || !prev;
    S.day = idx;
    if (dayChanged || S.slot < 0 || curDay().slots[S.slot].past) { S.slot = pickSlot(curDay()); S.auto = true; }
    render();
    if (changed) toast();
  }
  let toastTimer = null;
  function toast() {
    const t = $('toast'); t.hidden = false;
    clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, 4000);
  }
  let loading = false;
  async function refresh() {
    if (loading) return;
    loading = true;
    const ctl = new AbortController(), timer = setTimeout(() => ctl.abort(), REQUEST_MS);
    try {
      let res;
      try { res = await fetch('/api/pal?city=' + encodeURIComponent(CITY), {cache: 'no-store', signal: ctl.signal}); }
      catch (e) { return transportFailed(); }
      if (res.status === 503) return showUnavailable('这个时间还没有可用的数据');
      // Only a rejected fetch (network error, abort/timeout) keeps the screen; any other bad response is not usable data.
      if (!res.ok) return showUnavailable('暂时无法读取数据');
      let data;
      try { data = await res.json(); } catch (e) { return showUnavailable('暂时无法读取数据'); }
      if (!validData(data)) return showUnavailable('暂时无法读取数据');
      if (Date.now() - Date.parse(data.weather_fetched_at) > MAX_AGE_MS) return showUnavailable('已经超过 48 小时没有新数据');
      apply(data);
    } finally { clearTimeout(timer); loading = false; }
  }
  setInterval(() => { if (!document.hidden) refresh(); }, POLL_MS);
  setInterval(() => {                       // 每分钟：柏林日期变了就立刻重读；数据超过 48 小时就不再显示
    if (!S.data) return;
    if (tooOld()) return showUnavailable('已经超过 48 小时没有新数据');
    if (berlinToday() !== S.data.days[0].date && !document.hidden) refresh();
  }, 60000);
  document.addEventListener('visibilitychange', () => {
    window.PalAudio.visibility(document.hidden);
    if (!document.hidden) refresh();
  });

  /* ---------- 声音开关 ---------- */
  function setSoundUI(on) {
    const b = $('bSound');
    b.setAttribute('aria-pressed', on); b.setAttribute('aria-label', on ? '关闭声音' : '打开声音'); b.title = b.getAttribute('aria-label');
    b.innerHTML = on ? SVG.spkOn : SVG.spkOff;
  }
  setSoundUI(false);
  window.PalAudio.onChange = setSoundUI;
  $('bSound').onclick = async () => {
    const want = !window.PalAudio.on;
    await window.PalAudio.setOn(want, curLevel());
    setSoundUI(window.PalAudio.on);
    const b = $('bSound'); b.classList.remove('burst');
    if (window.PalAudio.on) { void b.offsetWidth; b.classList.add('burst'); }
  };
  $('hero').addEventListener('click', () => {    // 点小动物：重听一遍；声音关着时，喇叭晃一下提醒
    if (window.PalAudio.on) return window.PalAudio.replay(curLevel());
    const b = $('bSound'); b.classList.remove('nudge'); void b.offsetWidth; b.classList.add('nudge');
  });
  $('hero').addEventListener('animationiteration', e => { if (e.target === $('hero') && S.data) window.PalAudio.heroLoop(curLevel()); });

  refresh();
})();
