/* 声音：Web Audio 实时合成，没有音频文件。默认关闭，只有点击喇叭后才创建 AudioContext。
   只做冷热相关的声音：冷的打颤、热的蝉鸣和扇子声、L2 落地声，以及早/午/晚的切换提示。
   每次操作播一小段（约 7 秒）后淡出；页面隐藏时挂起，回到前台若恢复失败则开关回到关闭。 */
(function () {
  'use strict';
  const A = {ctx: null, on: false, n: {}, vol: .7, env: 0, t0: -1e9, dur: 7000, silent: null, timer: null,
             nx: {chat: 0, plip: 0}, level: 3, onChange: null, first: false};

  const MAKEUP = 3;                          // 整体补偿增益（约 +9.5 dB）
  const bq = (type, f, q = 1) => { const b = A.ctx.createBiquadFilter(); b.type = type; b.frequency.value = f; b.Q.value = q; return b; };
  const gn = v => { const g = A.ctx.createGain(); g.gain.value = v; return g; };
  const ramp = (param, v, tc = .35) => param.setTargetAtTime(v, A.ctx.currentTime, tc);
  const chain = (...nodes) => { for (let i = 0; i < nodes.length - 1; i++) nodes[i].connect(nodes[i + 1]); };

  function makeBuffers(ctx) {
    const sr = ctx.sampleRate, len = sr * 4;
    const mk = fill => { const b = ctx.createBuffer(2, len, sr); for (let c = 0; c < 2; c++) fill(b.getChannelData(c)); return b; };
    return {
      white: mk(d => { for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1; }),
      pink: mk(d => { let b0 = 0, b1 = 0, b2 = 0, b3 = 0, b4 = 0, b5 = 0, b6 = 0;
        for (let i = 0; i < d.length; i++) { const w = Math.random() * 2 - 1;
          b0 = .99886 * b0 + w * .0555179; b1 = .99332 * b1 + w * .0750759; b2 = .969 * b2 + w * .153852;
          b3 = .8665 * b3 + w * .3104856; b4 = .55 * b4 + w * .5329522; b5 = -.7616 * b5 - w * .016898;
          d[i] = (b0 + b1 + b2 + b3 + b4 + b5 + b6 + w * .5362) * .11; b6 = w * .115926; } }),
    };
  }

  // 让 iOS 把页面声音当作“播放”类，减少被侧面静音键吞掉的情况（未在真机验证）
  function unlockSilent() {
    try {
      if (navigator.audioSession) navigator.audioSession.type = 'playback';
      const sr = 8000, n = 800, b = new ArrayBuffer(44 + n), v = new DataView(b);
      const w = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
      w(0, 'RIFF'); v.setUint32(4, 36 + n, true); w(8, 'WAVE'); w(12, 'fmt '); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
      v.setUint32(24, sr, true); v.setUint32(28, sr, true); v.setUint16(32, 1, true); v.setUint16(34, 8, true); w(36, 'data'); v.setUint32(40, n, true);
      for (let i = 0; i < n; i++) v.setUint8(44 + i, 128);
      A.silent = new Audio(URL.createObjectURL(new Blob([b], {type: 'audio/wav'}))); A.silent.loop = true;
    } catch (e) { /* 没有也不影响 */ }
  }

  function init() {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    A.ctx = new Ctx();
    unlockSilent();
    const n = A.n;
    n.master = gn(0);
    const comp = A.ctx.createDynamicsCompressor();
    comp.threshold.value = -20; comp.knee.value = 24; comp.ratio.value = 6; comp.attack.value = .01; comp.release.value = .3;
    // 听感响度：压缩后补偿增益，再接一个限幅器，保证不削波（实测峰值见 tests/web/pal-browser.cjs）
    n.out = gn(MAKEUP);
    const lim = A.ctx.createDynamicsCompressor();
    lim.threshold.value = -3; lim.knee.value = 0; lim.ratio.value = 20; lim.attack.value = .002; lim.release.value = .1;
    chain(n.master, comp, n.out, lim, A.ctx.destination);
    n.B = makeBuffers(A.ctx);
    // 蝉鸣（只在最热一档）
    n.cicOsc = A.ctx.createOscillator(); n.cicOsc.frequency.value = 4000;
    n.cicAM = gn(.5); n.cicPulse = gn(.5); n.cicG = gn(0);
    const f1 = A.ctx.createOscillator(); f1.frequency.value = 34; const f1g = gn(.5); chain(f1, f1g, n.cicAM.gain);
    const f2 = A.ctx.createOscillator(); f2.frequency.value = .7; const f2g = gn(.5); chain(f2, f2g, n.cicPulse.gain);
    chain(n.cicOsc, n.cicAM, n.cicPulse, n.cicG, n.master);
    n.cicOsc.start(); f1.start(); f2.start();
    A.timer = setInterval(tick, 120);
  }

  function blip(freq, dur, gain, o = {}) {
    const c = A.ctx, t = c.currentTime + (o.at || 0), osc = c.createOscillator(), g = c.createGain();
    osc.type = o.type || 'sine'; osc.frequency.setValueAtTime(freq, t);
    if (o.to) osc.frequency.exponentialRampToValueAtTime(o.to, t + dur);
    g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(gain, t + .008); g.gain.exponentialRampToValueAtTime(.0001, t + dur);
    chain(osc, g, A.n.master); osc.start(t); osc.stop(t + dur + .05);
  }
  function noiseHit(buf, freq, q, gain, dur, at = 0) {
    const c = A.ctx, t = c.currentTime + at, s = c.createBufferSource(), f = bq('bandpass', freq, q), g = c.createGain();
    s.buffer = buf; g.gain.setValueAtTime(gain, t); g.gain.exponentialRampToValueAtTime(.0001, t + dur);
    chain(s, f, g, A.n.master); s.start(t, Math.random() * 3); s.stop(t + dur + .05);
  }
  const chatter = (gain, freq, at) => noiseHit(A.n.B.white, freq, 1.2, gain, .03, at);

  function whoosh() {                       // 扇子呼扇（L1）
    const c = A.ctx, t = c.currentTime, s = c.createBufferSource(), f = bq('bandpass', 500, 1.2), g = c.createGain();
    s.buffer = A.n.B.pink; f.frequency.setValueAtTime(500, t); f.frequency.exponentialRampToValueAtTime(1700, t + .3);
    g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(.14, t + .12); g.gain.exponentialRampToValueAtTime(.0001, t + .34);
    chain(s, f, g, A.n.master); s.start(t, Math.random() * 3); s.stop(t + .4);
  }
  function boing() { blip(240, .16, .12, {to: 150}); blip(1400, .1, .04, {at: .02}); }   // 落地“噗”（L2）
  function brr() {                          // 冷得“呜～”
    const c = A.ctx, t = c.currentTime, o = c.createOscillator(), lp = bq('lowpass', 750), am = gn(.5), env = c.createGain();
    o.type = 'sawtooth'; o.frequency.setValueAtTime(150, t); o.frequency.linearRampToValueAtTime(175, t + .7);
    const l = c.createOscillator(); l.frequency.value = 17; const lg = gn(.5); chain(l, lg, am.gain);
    env.gain.setValueAtTime(0, t); env.gain.linearRampToValueAtTime(.08, t + .08); env.gain.setValueAtTime(.08, t + .55); env.gain.exponentialRampToValueAtTime(.0001, t + .75);
    chain(o, lp, am, env, A.n.master); o.start(t); l.start(t); o.stop(t + .8); l.stop(t + .8);
  }
  function cue(slot) {                      // 早/午/晚切换提示
    if (!A.on || A.env < .05) return;
    if (slot === 0) { blip(2300, .11, .06, {to: 3400}); blip(2500, .11, .06, {to: 3600, at: .16}); blip(2300, .1, .05, {to: 3300, at: .34}); }
    else if (slot === 1) { blip(880, .5, .07); blip(1320, .5, .04, {at: .05}); }
    else { for (let i = 0; i < 3; i++) { blip(4300, .03, .035, {at: i * .2}); blip(4300, .03, .035, {at: i * .2 + .06}); } }
  }

  function sync(level) {
    A.level = level;
    if (!A.ctx) return;
    ramp(A.n.master.gain, A.on ? A.vol * A.env : 0, .1);
    ramp(A.n.cicG.gain, level === 1 ? .03 : 0, .6);
  }
  function replay(level) {                   // 用户操作才重新播一段
    A.level = level == null ? A.level : level;
    A.t0 = performance.now(); A.env = 1; A.first = true;
    for (const k in A.nx) A.nx[k] = 0;
    if (A.ctx) sync(A.level);
    if (A.ctx && A.on) { if (A.level === 2) boing(); else if (A.level === 1) whoosh(); }   // 操作后立刻有一声
  }
  function tick() {                          // 每 120ms：随机类的声音，并计算淡出
    if (!A.on || !A.ctx) return;
    const now = performance.now(), el = now - A.t0, lv = A.level;
    A.env = el < A.dur ? 1 : Math.max(0, 1 - (el - A.dur) / 2500);
    ramp(A.n.master.gain, A.vol * A.env, .12);
    if (A.env < .02) return;
    if ((lv === 5 || lv === 6) && now > A.nx.chat) {   // 冷：牙齿打颤 + 偶尔“呜～”
      const cnt = lv === 6 ? 7 : 5, gap = lv === 6 ? .04 : .055;
      if (A.first || Math.random() < (lv === 6 ? .6 : .35)) brr();
      A.first = false;
      for (let i = 0; i < cnt; i++) chatter(lv === 6 ? .22 : .16, 2200 + Math.random() * 600, .1 + i * gap);
      A.nx.chat = now + (lv === 6 ? 1500 : 2500) + Math.random() * 800;
    }
    if (lv === 1 && now > A.nx.plip) { blip(1300, .09, .08, {to: 700}); A.nx.plip = now + 1500 + Math.random() * 2000; }   // 热：汗滴“啪嗒”
  }
  function heroLoop(level) {                 // 与画面同步：小动物每循环一次响一次
    if (!A.on || !A.ctx || A.env < .2) return;
    if (level === 2) boing(); else if (level === 1) whoosh();
  }
  function pop() { if (A.on && A.ctx && A.env > .05) blip(520, .08, .05, {to: 900}); }

  async function setOn(on, level) {
    if (on) {
      if (!A.ctx) init();
      try { await A.ctx.resume(); } catch (e) { A.on = false; return false; }
      A.on = true;
      if (A.silent) A.silent.play().catch(() => {});
      replay(level);
      const g = A.n.master.gain, now = A.ctx.currentTime;          // 开机提示音要立刻听得见，不等增益缓升
      g.cancelScheduledValues(now); g.setValueAtTime(A.vol * A.env, now);
      blip(660, .18, .3);
    } else {
      A.on = false;
      if (A.silent) A.silent.pause();
      if (A.ctx) sync(A.level);
    }
    return true;
  }
  // 页面隐藏时挂起；回到前台时若恢复失败，开关回到关闭
  async function visibility(hidden) {
    if (!A.ctx) return;
    if (hidden) { try { await A.ctx.suspend(); } catch (e) { /* 忽略 */ } return; }
    if (!A.on) return;
    let failed = false;
    try { await A.ctx.resume(); failed = A.ctx.state === 'suspended' || A.ctx.state === 'interrupted'; } catch (e) { failed = true; }
    if (failed) { A.on = false; if (A.silent) A.silent.pause(); if (A.onChange) A.onChange(false); }
  }

  window.PalAudio = {
    get on() { return A.on; },
    setOn, replay, sync, cue, pop, heroLoop, visibility,
    set onChange(fn) { A.onChange = fn; },
  };
})();
