import { WarmthIndicator, CityCard, text } from './components.js';
const $ = id => document.getElementById(id);
const feelings = { cold: '怕冷', normal: '一般', hot: '怕热' };
// Personal form stays in its own DOM; history snapshots preserve it on reload without storage.
let personal = { city: null, preference: 'normal' };
let cities = [], snapshot = null, page = 0, current = null, requestVersion = 0, searchVersion = 0;
let context = null;
let featuredRequestVersion = 0;
const short = iso => iso.replace(/^(\d{4})-(\d{2})-(\d{2})$/, '$1年$2月$3日');
const range = (s, e) => `${short(s)}—${short(e)}`;
const scenario = () => $('fixture').value;
async function api(path, params = {}) {
  const response = await fetch(path + '?' + new URLSearchParams(params));
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '模拟数据暂不可用，请重试。');
  return data;
}
function formState() {
  return { ...personal, cityText: $('city').value, start: $('start').value, end: $('end').value, page };
}
function saveForm() { history.replaceState({ ...history.state, form: formState() }, '', location.href); }
function restoreForm(state) {
  if (!state) return;
  personal = { city: state.city, preference: state.preference || 'normal' };
  $('city').value = state.cityText || ''; $('start').value = state.start || ''; $('end').value = state.end || '';
  page = state.page || 0;
  document.querySelectorAll('[data-feeling]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.feeling === personal.preference)));
}
function link(params) {
  const p = params.view === 'city' ? { view: 'city', city_id: params.city_id } :
    { view: 'trip', city_id: params.city_id, start: params.start, end: params.end, preference: params.preference };
  return '?' + new URLSearchParams(p);
}
function closeSearch() { $('cityOptions').classList.add('hidden'); $('city').setAttribute('aria-expanded', 'false'); }
function chooseCity(city) {
  personal.city = city; $('city').value = `${city.zh} · ${city.name}`;
  $('cityError').textContent = ''; $('city').setAttribute('aria-invalid', 'false'); closeSearch(); saveForm(); $('city').focus();
}
async function search() {
  personal.city = null; saveForm();
  const version = ++searchVersion, q = $('city').value.trim();
  if (!q) { closeSearch(); return; }
  try {
    const data = await api('/api/cities', { q });
    if (version !== searchVersion) return;
    const box = $('cityOptions'); box.replaceChildren();
    for (const city of data.cities) {
      const button = text('button', `${city.zh} · ${city.name}`); button.type = 'button';
      button.append(text('small', city.state)); button.addEventListener('click', () => chooseCity(city)); box.append(button);
    }
    if (!data.cities.length) box.append(text('div', '没找到这个城市。演示目录有限，请试试柏林 Berlin。', 'empty'));
    box.classList.remove('hidden'); $('city').setAttribute('aria-expanded', 'true');
  } catch (error) { $('cityError').textContent = error.message; }
}
// Native buttons in a labelled suggestions group support Tab, arrows, Enter and Escape.
$('cityOptions').setAttribute('role', 'group'); $('cityOptions').setAttribute('aria-label', '城市建议，含联邦州');
$('city').removeAttribute('role'); $('city').removeAttribute('aria-autocomplete');
$('city').addEventListener('input', search);
$('city').addEventListener('keydown', e => {
  if (e.key === 'ArrowDown') { e.preventDefault(); $('cityOptions').querySelector('button')?.focus(); }
  if (e.key === 'Escape') closeSearch();
});
$('cityOptions').addEventListener('keydown', e => {
  const buttons = [...$('cityOptions').querySelectorAll('button')], i = buttons.indexOf(document.activeElement);
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); buttons[(i + (e.key === 'ArrowDown' ? 1 : buttons.length - 1)) % buttons.length]?.focus(); }
  if (e.key === 'Escape') { closeSearch(); $('city').focus(); }
});
document.addEventListener('click', e => { if (!e.target.closest('.input-wrap')) closeSearch(); });
document.querySelectorAll('[data-feeling]').forEach(b => b.addEventListener('click', () => {
  personal.preference = b.dataset.feeling;
  document.querySelectorAll('[data-feeling]').forEach(el => el.setAttribute('aria-pressed', String(el === b))); saveForm();
}));
['start', 'end'].forEach(id => $(id).addEventListener('input', saveForm));
async function refreshContext() {
  context = await api('/api/context');
  for (const id of ['start', 'end']) { $(id).min = context.today; $(id).max = context.max_date; }
  $('dateHint').textContent = `可选 ${short(context.today)} 至 ${short(context.max_date)}（德国当地日期）`;
}
function renderFeatured() {
  const grid = $('featuredGrid'); grid.replaceChildren();
  if (!snapshot) return;
  if (!validFeaturedSnapshot(snapshot)) {
    featuredStatus('模拟数据已过期或日期不匹配，暂无可用城市建议。'); return;
  }
  for (const data of snapshot.cities.slice(page * 4, page * 4 + 4)) {
    const params = { view: 'city', city_id: data.city.id }, card = CityCard(data, link(params));
    card.addEventListener('click', e => { if (e.button === 0 && !e.ctrlKey && !e.metaKey && !e.shiftKey && !e.altKey) { e.preventDefault(); navigate(params); } });
    grid.append(card);
  }
  $('featuredDates').textContent = `${range(snapshot.today, snapshot.forecast_end)} · 一般体感 · 未获取真实天气数据`;
  $('pageDisplay').textContent = `${page + 1} / 3`; $('prevPage').disabled = page === 0; $('nextPage').disabled = page === 2;
}
function validFeaturedSnapshot(data) {
  return context && data?.today === context.today && data.forecast_end === context.forecast_end &&
    (data.data_status === undefined || data.data_status === 'fresh') &&
    Array.isArray(data.cities) && data.cities.length > 0 && data.cities.every(city =>
      city?.data_status === 'fresh' && city.start === context.today && city.end === context.forecast_end);
}
function featuredStatus(message) {
  snapshot = null; $('prevPage').disabled = true; $('nextPage').disabled = true;
  $('featuredDates').textContent = '未获取真实天气数据'; $('pageDisplay').textContent = '';
  $('featuredGrid').replaceChildren(text('p', message));
}
async function loadFeatured() {
  const version = ++featuredRequestVersion;
  featuredStatus('正在加载模拟城市参考…');
  const selected = scenario();
  if (selected === 'loading') return;
  try {
    const data = await api('/api/featured', { fixture: selected });
    if (version !== featuredRequestVersion || selected !== scenario()) return;
    if (!validFeaturedSnapshot(data)) {
      featuredStatus('模拟数据已过期或日期不匹配，暂无可用城市建议。'); return;
    }
    snapshot = data; renderFeatured();
  } catch (error) {
    if (version !== featuredRequestVersion || selected !== scenario()) return;
    featuredStatus(error.message);
  }
}
$('prevPage').addEventListener('click', () => { page = Math.max(0, page - 1); renderFeatured(); saveForm(); });
$('nextPage').addEventListener('click', () => { page = Math.min(2, page + 1); renderFeatured(); saveForm(); });
function resultStatus(message, error = false) {
  $('resultContent').classList.add('hidden'); $('resultStatus').classList.remove('hidden');
  $('resultStatus').replaceChildren(text('p', message));
  if (error) { const retry = text('button', '重试模拟查询', 'secondary-action'); retry.type = 'button'; retry.onclick = () => route(); $('resultStatus').append(retry); }
}
function focusHeading(id) { const el = $(id); el.tabIndex = -1; el.focus({ preventScroll: true }); }
async function showResult(params) {
  const version = ++requestVersion;
  $('home').classList.add('hidden'); $('result').classList.remove('hidden');
  const isCity = params.view === 'city'; current = null;
  $('back').textContent = isCity ? '← 返回精选城市' : '← 修改行程';
  $('resultKind').textContent = isCity ? '城市穿衣参考 · 模拟数据' : '行程穿衣建议 · 模拟数据';
  $('resultCity').textContent = '加载中'; $('resultDates').textContent = ''; $('resultMode').textContent = '模拟响应';
  resultStatus('正在加载模拟穿衣参考…'); $('result').setAttribute('aria-busy', 'true'); focusHeading('resultCity');
  window.scrollTo(0, 0);
  const selected = scenario();
  if (selected === 'loading') return;
  try {
    const data = await api('/api/advice', { ...params, fixture: selected });
    if (version !== requestVersion) return;
    current = data;
    const historical = data.mode === 'historical_reference';
    $('resultCity').textContent = `${data.city.zh} · ${data.city.name}`;
    $('resultDates').textContent = `${range(data.start, data.end)} · ${isCity ? '今起14天 · ' : ''}${feelings[data.preference]}体感`;
    $('resultMode').textContent = historical ? '过去8年同期气温参考 · 模拟' : `${isCity ? '今起14天' : '所选日期'}气温预报 · 模拟`;
    document.title = `${isCity ? '城市穿衣参考' : '行程穿衣建议'} · ${data.city.zh} · 演示`;
    if (data.data_status === 'stale') { current = null; resultStatus('模拟数据已过期，暂无有效建议。保留查询日期，未获取真实天气数据。', true); return; }
    $('resultStatus').classList.add('hidden'); $('resultContent').classList.remove('hidden');
    $('resultHeadline').textContent = data.headline;
    $('resultWarmthMark').replaceChildren(WarmthIndicator(data.warmth_indicator_level));
    $('spanRemind').classList.toggle('hidden', !data.packing_variation_notice);
    $('spanText').textContent = data.packing_variation_notice || '';
    $('resultLayers').textContent = data.layers;
    $('tempTitle').textContent = historical ? '往年同期白天气温参考' : '白天的示例气温';
    $('tempText').textContent = data.reference_temperature_c === null ? '冷暖分化，无单一代表气温。' : `模拟数值约 ${data.reference_temperature_c}°C，不代表真实气温。`;
    $('edgeText').textContent = data.notices.join(' ');
    $('noticeTitle').textContent = historical ? '这是往年参考，不是这次旅行的预报' : '出发前再确认';
    $('resultNotice').textContent = data.caveat;
    $('source').textContent = `来源：${data.source}。天气获取时间：未获取。模拟建议生成：${new Date(data.advice_generated_at).toLocaleString('zh-CN', { timeZone: 'Europe/Berlin', hour12: false })}（德国当地时间）。状态：模拟响应可用；非真实天气新鲜度。临时保暖标记，尚未接入真实服务。`;
  } catch (error) {
    if (version !== requestVersion) return;
    $('resultCity').textContent = '暂时无法显示建议'; resultStatus(error.message, true);
  } finally { if (version === requestVersion) $('result').setAttribute('aria-busy', 'false'); }
}
function navigate(params) {
  saveForm(); history.pushState({ form: formState() }, '', params ? link(params) : location.pathname);
  route();
}
async function route() {
  const query = new URLSearchParams(location.search);
  if (!query.size) {
    ++requestVersion; current = null; $('result').classList.add('hidden'); $('home').classList.remove('hidden');
    document.title = '旅途穿衣 · 演示'; await refreshContext(); await loadFeatured(); return;
  }
  // Preserve duplicate parameters for the API's strict validation.
  const params = Object.fromEntries(query);
  if ([...query.keys()].some(k => query.getAll(k).length > 1) || !['trip', 'city'].includes(params.view)) {
    $('home').classList.add('hidden'); $('result').classList.remove('hidden');
    ++requestVersion; current = null; $('back').textContent = '← 返回首页'; $('resultKind').textContent = '无效链接';
    $('resultCity').textContent = '查询参数无效'; $('resultDates').textContent = ''; $('resultMode').textContent = '请检查链接';
    resultStatus('链接参数无效或重复，请返回首页重新查询。'); return;
  }
  // City navigation deliberately discards any personal trip parameters.
  if (params.view === 'city') {
    const canonical = { view: 'city', city_id: params.city_id || '' };
    if (location.search !== link(canonical)) history.replaceState(history.state, '', link(canonical));
    return showResult(canonical);
  }
  const canonical = { view: 'trip', city_id: params.city_id || '', start: params.start || '', end: params.end || '', preference: params.preference || '' };
  return showResult(canonical);
}
$('tripForm').addEventListener('submit', async e => {
  e.preventDefault(); $('cityError').textContent = ''; $('dateError').textContent = ''; $('formError').textContent = '';
  if (!personal.city) { $('cityError').textContent = '请先从列表选一个德国城市'; $('city').setAttribute('aria-invalid', 'true'); $('city').focus(); return; }
  const submit = $('tripForm').querySelector('[type="submit"]'); submit.disabled = true;
  try {
    await refreshContext();
    const start = $('start').value, end = $('end').value;
    if (!start || !end || start < context.today || end > context.max_date || end < start) {
      $('dateError').textContent = '请选择德国今天起30天内的有效日期，离开日期不能早于到达日期。';
      $('start').focus(); return;
    }
    navigate({ view: 'trip', city_id: personal.city.id, start, end, preference: personal.preference });
  } catch (error) { $('formError').textContent = error.message; }
  finally { submit.disabled = false; }
});
$('back').onclick = () => { const city = new URLSearchParams(location.search).get('view') === 'city'; navigate(null); requestAnimationFrame(() => { focusHeading(city ? 'featuredTitle' : 'city'); $(city ? 'featuredTitle' : 'city').scrollIntoView({ block: 'start' }); }); };
window.addEventListener('popstate', () => { restoreForm(history.state?.form); route(); });
$('fixture').onchange = () => { if (location.search) route(); else loadFeatured(); };
async function copy(value, message) {
  try { await navigator.clipboard.writeText(value); $('toast').textContent = message; }
  catch { $('toast').textContent = '浏览器未允许复制，请从地址栏复制链接。'; }
  $('toast').classList.add('show'); clearTimeout(copy.timer); copy.timer = setTimeout(() => $('toast').classList.remove('show'), 3000);
}
$('copyAdvice').onclick = () => { if (current) copy(['【演示数据，非真实天气】', $('resultKind').textContent, $('resultCity').textContent, $('resultDates').textContent, $('resultMode').textContent, current.headline, current.packing_variation_notice, current.layers, ...current.notices, current.caveat].filter(Boolean).join('\n'), '已复制演示建议'); };
$('shareTrip').onclick = () => { if (current) copy(location.origin + location.pathname + link({ ...current, city_id: current.city.id }), '已复制演示链接；重新打开仍为模拟数据'); };
// Revalidate after backgrounding or crossing German midnight; never reuse yesterday's window.
async function revalidateDay() {
  const previous = context?.today;
  try { await refreshContext(); if (previous && previous !== context.today) await route(); } catch { /* Retry on next focus or navigation. */ }
}
window.addEventListener('focus', revalidateDay);
document.addEventListener('visibilitychange', () => { if (!document.hidden) revalidateDay(); });
setInterval(revalidateDay, 30000);
restoreForm(history.state?.form);
try {
  cities = (await api('/api/cities')).cities;
  // A directly opened personal link can be edited without entering it twice.
  if (!history.state?.form && new URLSearchParams(location.search).get('view') === 'trip') {
    const q = new URLSearchParams(location.search), city = cities.find(c => c.id === q.get('city_id'));
    if (city) restoreForm({ city, cityText: `${city.zh} · ${city.name}`, start: q.get('start'), end: q.get('end'), preference: feelings[q.get('preference')] ? q.get('preference') : 'normal' });
  }
  saveForm(); await refreshContext(); await route();
} catch (error) { $('formError').textContent = error.message; }
