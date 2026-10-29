import { WarmthIcon, WarmthIndicator, CityCard, text, formatAdviceCopy } from './components.js';
const $ = id => document.getElementById(id);
const feelings = { cold: '怕冷', normal: '正常', hot: '怕热' };
// Personal form stays in its own DOM; history snapshots preserve it on reload without storage.
let personal = { city: null, preference: 'normal' };
let cities = [], snapshot = null, page = 0, current = null, requestVersion = 0, searchVersion = 0;
let context = null;
let featuredRequestVersion = 0;
const short = iso => iso.replace(/^(\d{4})-(\d{2})-(\d{2})$/, '$1年$2月$3日');
const range = (s, e) => `${short(s)}—${short(e)}`;
const scenario = () => $('demo').checked ? $('fixture').value : 'live';
const featuredScenario = () => context?.fixture_mode && scenario() === 'live' ? 'default' : scenario();
const cityParams = q => ({ q, ...(scenario() === 'live' ? {} : { fixture: scenario() }) });
async function api(path, params = {}) {
  let response, data;
  try {
    response = await fetch(path + '?' + new URLSearchParams(params));
    data = await response.json();
  } catch { throw new Error('暂时无法连接服务，请检查网络后重试。'); }
  if (!response.ok) throw Object.assign(new Error(data.error || '数据暂不可用，请重试。'), { code: data.code, status: response.status });
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
  syncDates();
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
    const data = await api('/api/cities', cityParams(q));
    if (version !== searchVersion) return;
    const box = $('cityOptions'); box.replaceChildren();
    for (const city of data.cities) {
      const button = text('button', `${city.zh} · ${city.name}`); button.type = 'button';
      button.append(text('small', city.state)); button.addEventListener('click', () => chooseCity(city)); box.append(button);
    }
    if (!data.cities.length) box.append(text('div', context?.data_delivery === 'manual_git_bundle' ? '首版仅支持精选十城，此城市不在支持范围内。' : '没找到这个德国城市，请尝试德文名称或加上联邦州。', 'empty'));
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
function syncDates() {
  if (!context) return;
  for (const id of ['start', 'end']) {
    $(id).min = context.today; $(id).max = context.max_date;
    if ($(id).value && ($(id).value < context.today || $(id).value > context.max_date)) $(id).value = '';
  }
  $('end').min = $('start').value || context.today;
  if ($('end').value && $('end').value < $('end').min) $('end').value = '';
}
['start', 'end'].forEach(id => {
  for (const event of ['input', 'change']) $(id).addEventListener(event, () => { syncDates(); saveForm(); });
});
async function refreshContext() {
  context = await api('/api/context');
  if (context.automatic_scope === 'featured_forecast_only') document.querySelector('.subnote span').textContent = '当前支持精选十城14天内预报；普通城市和历史资料暂不自动准备';
  syncDates();
  if (context.data_delivery === 'manual_git_bundle') document.querySelector('.subnote span').textContent = '首版支持精选十城；预报人工每日更新；历史仅已备齐范围可用';
  $('dateHint').textContent = `可选 ${short(context.today)} 至 ${short(context.max_date)}（德国当地日期）` + (context.data_delivery === 'manual_git_bundle' ? '；14天内优先使用当日预报，历史仅五年同期资料完整时可用；可选日期不保证都有资料。' : context.automatic_scope === 'featured_forecast_only' ? '；当前自动准备仅支持精选十城短期预报，普通城市和历史资料暂不自动补齐。' : '');
}
function renderFeatured() {
  const grid = $('featuredGrid'); grid.replaceChildren();
  if (!snapshot) return;
  if (!validFeaturedSnapshot(snapshot)) {
    featuredStatus('城市数据已过期或日期不匹配，暂无可用城市建议。'); return;
  }
  for (const data of snapshot.cities.slice(page * 4, page * 4 + 4)) {
    if (data.mode === 'unavailable') { grid.append(CityCard(data, '#')); continue; }
    const params = { view: 'city', city_id: data.city.id }, card = CityCard(data, link(params));
    card.addEventListener('click', e => { if (e.button === 0 && !e.ctrlKey && !e.metaKey && !e.shiftKey && !e.altKey) { e.preventDefault(); navigate(params); } });
    grid.append(card);
  }
  $('featuredDates').textContent = `${range(snapshot.today, snapshot.forecast_end)}${snapshot.fixture ? ' · 模拟数据，非真实天气' : ''}`;
  $('pageDisplay').textContent = `${page + 1} / 3`; $('prevPage').disabled = page === 0; $('nextPage').disabled = page === 2;
}
function validFeaturedSnapshot(data) {
  return context && data?.today === context.today && data.forecast_end === context.forecast_end &&
    (data.data_status === undefined || data.data_status === 'fresh') &&
    Array.isArray(data.cities) && data.cities.length === 10 && data.cities.every(city =>
      (city?.data_status === 'fresh' || (city?.mode === 'historical_reference' && city?.data_status === 'complete') || city?.data_status === 'unavailable') && city.start === context.today && city.end === context.forecast_end);
}
function featuredStatus(message) {
  snapshot = null; $('retryFeatured').classList.toggle('hidden', message === '正在加载城市参考…'); $('prevPage').disabled = true; $('nextPage').disabled = true;
  $('featuredDates').textContent = '暂无可用的完整城市参考'; $('pageDisplay').textContent = '';
  $('featuredGrid').replaceChildren(text('p', message));
}
async function loadFeatured() {
  const version = ++featuredRequestVersion;
  featuredStatus('正在加载城市参考…');
  const selected = featuredScenario();
  if (selected === 'loading') return;
  try {
    const data = await api('/api/featured', selected === 'live' ? {} : { fixture: selected });
    if (version !== featuredRequestVersion || selected !== featuredScenario()) return;
    if (!validFeaturedSnapshot(data)) {
      featuredStatus('城市数据已过期或日期不匹配，暂无可用城市建议。'); return;
    }
    snapshot = data; $('retryFeatured').classList.add('hidden'); renderFeatured();
  } catch (error) {
    if (version !== featuredRequestVersion || selected !== featuredScenario()) return;
    featuredStatus(error.message);
  }
}
$('retryFeatured').onclick = loadFeatured;
$('prevPage').addEventListener('click', () => { page = Math.max(0, page - 1); renderFeatured(); saveForm(); });
$('nextPage').addEventListener('click', () => { page = Math.min(2, page + 1); renderFeatured(); saveForm(); });
function resultStatus(message, error = false) {
  $('resultContent').classList.add('hidden'); $('resultStatus').classList.remove('hidden');
  $('resultStatus').replaceChildren(text('p', message));
  if (error === 'history_incomplete') {
    const retry = text('button', '重试查询', 'secondary-action'); retry.type = 'button'; retry.onclick = () => route(); $('resultStatus').append(retry);
    const edit = text('button', '修改行程', 'secondary-action'); edit.type = 'button'; edit.onclick = () => $('back').click(); $('resultStatus').append(edit);
  } else if (error && error !== 'invalid_request') { const retry = text('button', '重试查询', 'secondary-action'); retry.type = 'button'; retry.onclick = () => route(); $('resultStatus').append(retry); }
}
function focusHeading(id) { const el = $(id); el.tabIndex = -1; el.focus({ preventScroll: true }); }
async function showResult(params) {
  const version = ++requestVersion;
  $('home').classList.add('hidden'); $('result').classList.remove('hidden');
  const isCity = params.view === 'city', demo = (isCity ? featuredScenario() : scenario()) !== 'live'; current = null;
  $('back').textContent = isCity ? '← 返回精选城市' : '← 修改行程';
  $('resultKind').textContent = `${isCity ? '城市穿衣参考' : '行程穿衣建议'} · ${demo ? '模拟数据' : '真实气温参考'}`;
  // Featured browsing reads published sources only; never resolve through GeoNames.
  const featuredCity = isCity && validFeaturedSnapshot(snapshot)
    ? snapshot.cities.find(entry => entry.city.id === params.city_id)?.city : null;
  const knownCity = isCity ? featuredCity : personal.city?.id === params.city_id ? personal.city : null;
  const validDates = !isCity && /^\d{4}-\d{2}-\d{2}$/.test(params.start) && /^\d{4}-\d{2}-\d{2}$/.test(params.end);
  const historicalRequest = validDates && context && params.end > context.forecast_end;
  $('resultCity').textContent = knownCity ? `${knownCity.zh} · ${knownCity.name}` : '尚未确定城市';
  $('resultDates').textContent = validDates ? range(params.start, params.end) : '';
  if (!isCity && feelings[params.preference]) $('resultDates').append(text('span', '冷热偏好：' + feelings[params.preference], 'trip-preference'));
  $('resultMode').textContent = `${historicalRequest ? '过去五年同期参考，不是本次旅行预报' : isCity ? '今起14天气温预报' : validDates ? '所选日期气温预报' : '请检查链接'}${demo ? ' · 模拟' : ''}`;
  document.title = `${isCity ? '城市穿衣参考' : '行程穿衣建议'} · ${knownCity ? knownCity.zh : '尚未确定城市'}`;
  resultStatus(demo ? '正在加载模拟穿衣参考…' : '正在获取气温并生成建议…'); $('result').setAttribute('aria-busy', 'true'); focusHeading('resultCity');
  window.scrollTo(0, 0);
  const selected = isCity ? featuredScenario() : scenario();
  if (selected === 'loading') return;
  try {
    if (!knownCity && !isCity) {
      try {
        const city = demo ? cities.find(c => c.id === params.city_id) : (await api('/api/city', { city_id: params.city_id })).city;
        if (version !== requestVersion) return;
        if (city) {
          $('resultCity').textContent = `${city.zh} · ${city.name}`;
          document.title = `${isCity ? '城市穿衣参考' : '行程穿衣建议'} · ${city.zh}`;
          if (!isCity) { restoreForm({ city, cityText: `${city.zh} · ${city.name}`, start: params.start, end: params.end, preference: params.preference }); saveForm(); }
        }
      } catch (error) {
        if (version !== requestVersion) return;
        $('resultCity').textContent = '未能确定城市';
        if (error.code === 'invalid_request') throw error;
      }
    }
    const data = await api('/api/advice', { ...params, ...(demo ? { fixture: selected } : {}) });
    if (version !== requestVersion) return;
    current = data;
    const historical = data.mode === 'historical_reference';
    $('resultKind').textContent = `${isCity ? '城市穿衣参考' : '行程穿衣建议'} · ${data.fixture ? '模拟数据' : '真实气温参考'}`;
    const variationKind = ['cold', 'warm', 'mixed'].includes(data.packing_variation_kind) ? data.packing_variation_kind : null;
    const variationTitle = {cold:'偏冷提醒', warm:'偏暖提醒', mixed:'冷热变化提醒'}[variationKind] || '冷热变化提醒';
    document.querySelector('#spanRemind strong').textContent = historical ? '历史冷暖风险 · 非本次预报' : data.fixture ? `${variationTitle} · 示例` : variationTitle;
    $('resultCity').textContent = `${data.city.zh} · ${data.city.name}`;
    if (!isCity) { restoreForm({ city: data.city, cityText: `${data.city.zh} · ${data.city.name}`, start: data.start, end: data.end, preference: data.preference }); saveForm(); }
    $('resultDates').textContent = `${range(data.start, data.end)}${isCity ? ' · 今起14天' : ''}`;
    if (!isCity) $('resultDates').append(text('span', '冷热偏好：' + feelings[data.preference], 'trip-preference'));
    $('resultMode').textContent = historical ? `过去五年同期参考，不是本次旅行预报${data.fixture ? ' · 模拟' : ''}` : `${isCity ? '今起14天' : '所选日期'}气温预报${data.fixture ? ' · 模拟' : ''}`;
    document.title = `${isCity ? '城市穿衣参考' : '行程穿衣建议'} · ${data.city.zh}${data.fixture ? ' · 演示' : ''}`;
    if (data.data_status === 'stale') { current = null; resultStatus(`数据已过期，暂无有效建议。查询日期：${range(data.start, data.end)}；天气获取时间：${data.weather_fetched_at || '未获取（模拟数据）'}。`, true); return; }
    $('resultStatus').classList.add('hidden'); $('resultContent').classList.remove('hidden');
    $('coatLabel').textContent = historical && data.warmth_indicator_level !== null ? '通常准备的外套' : '外套建议';
    $('resultHeadline').textContent = data.headline;
    $('resultWarmthMark').replaceChildren(WarmthIndicator(data.warmth_indicator_level, Boolean(data.packing_variation_notice)));
    const variationBanner = $('spanRemind');
    // A previously shown result must never leak its direction to the next one.
    variationBanner.classList.remove('variation-banner--cold', 'variation-banner--warm', 'variation-banner--mixed');
    if (data.packing_variation_notice && variationKind) variationBanner.classList.add(`variation-banner--${variationKind}`);
    variationBanner.classList.toggle('hidden', !data.packing_variation_notice);
    $('spanText').textContent = data.packing_variation_notice || '';
    const variationArt = {cold:'alert-cold', warm:'alert-hot', mixed:'alert-variation'}[variationKind] || 'alert-variation';
    document.querySelector('#spanRemind .variation-icon').replaceChildren(...(data.packing_variation_notice ? [WarmthIcon(variationArt)] : []));
    $('resultLayers').textContent = data.layers;
    const guidance = data.packing_copy?.guidance;
    $('resultGuidance').replaceChildren(...['alternative', 'personal_layer', 'trousers_shoes']
      .filter(key => guidance?.[key]).map(key => text('p', guidance[key])));
    $('preferenceNote').classList.toggle('hidden', !isCity);
    $('preferenceNote').textContent = isCity ? '默认按正常冷热偏好推荐。' : '';
    $('tempTitle').textContent = historical ? '往年同期白天气温参考' : (data.fixture ? '白天的示例气温' : '白天气温参考');
    $('tempText').textContent = data.reference_temperature_c === null ? (data.daytime_temperature_range_c ? `${historical ? '过去五年同期样本' : '所选日期'}白天气温约 ${data.daytime_temperature_range_c[0]}–${data.daytime_temperature_range_c[1]}°C，冷暖差异较大，请按上方建议备衣。` : data.packing_variation_notice ? '白天冷暖差异较大，请按上方建议备衣。' : '今天白天已过，请参考剩余晚间的备衣建议。') : (data.fixture ? `模拟数值约 ${data.reference_temperature_c}°C，不代表真实气温。` : `${historical ? '过去五年同期样本' : '所选日期白天'}气温中间水平约 ${data.reference_temperature_c}°C。`);
    const notes = data.notices.filter(note => !note.includes('今天仅使用查询时刻之后') && !note.includes('保暖需求接近'));
    // General thickness-boundary advice is not evidence of cooler mornings/evenings.
    const onlyEdgeGuidance = notes.every(note => note.includes('较凉') || note.startsWith('早晚示例：'));
    $('edgeTitle').textContent = onlyEdgeGuidance ? '早晚注意分层' : '分层与厚度提示';
    $('edgeIcon').textContent = onlyEdgeGuidance ? '🌙' : '＋';
    $('edgeText').textContent = notes.join(' ');
    $('edgeNotice').classList.toggle('hidden', !notes.length);
    $('temperatureNotice').before($('edgeNotice'));
    $('noticeTitle').textContent = historical ? '这是往年参考，不是这次旅行的预报' : '出发前再确认';
    $('resultNotice').textContent = data.caveat;
    $('source').textContent = `来源：${data.source}。天气获取时间：未获取。模拟建议生成：${new Date(data.advice_generated_at).toLocaleString('zh-CN', { timeZone: 'Europe/Berlin', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false })}（德国当地时间）。非真实天气。`;
    if (!data.fixture) {
      const stamp = value => new Date(value).toLocaleString('zh-CN', { timeZone: 'Europe/Berlin', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });
      $('source').textContent = `来源：${data.source}。${historical ? '历史资料获取时间（最早）' : '天气获取时间'}：${stamp(data.weather_fetched_at)}；建议生成时间：${stamp(data.advice_generated_at)}（德国当地时间）。获取时间不代表提供方模型更新时间。`;
      if (historical) $('source').append(` 历史资料各月获取时间：${data.history_fetched_at.map(stamp).join('；')}。历史资料长期复用，无需每日刷新。`);
      $('source').append(' 依据气温计算的备衣参考；建议为本站加工结果。');
    }
  } catch (error) {
    if (version !== requestVersion) return;
    if ($('resultCity').textContent === '尚未确定城市') $('resultCity').textContent = '未能确定城市';
    // Only the city weather-missing response has this generic message. History,
    // configuration and dataset validation failures retain their API explanation.
    const missingWeather = context?.data_delivery === 'manual_git_bundle' && error.status === 503 &&
      error.code === 'temporarily_unavailable' && error.message === '数据暂缺';
    resultStatus(missingWeather ? '当日预报尚未更新或数据暂缺；当前没有可用建议。' : error.message, error.code || true);
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
    document.title = '旅途穿衣 · 德国旅行'; await refreshContext(); await loadFeatured(); return;
  }
  // Preserve duplicate parameters for the API's strict validation.
  const params = Object.fromEntries(query);
  if ([...query.keys()].some(k => query.getAll(k).length > 1) || !['trip', 'city'].includes(params.view) || Object.keys(params).some(k => !['view','city_id','start','end','preference'].includes(k))) {
    $('home').classList.add('hidden'); $('result').classList.remove('hidden');
    ++requestVersion; current = null; $('back').textContent = '← 返回首页'; $('resultKind').textContent = '无效链接';
    $('resultCity').textContent = '查询参数无效'; $('resultDates').textContent = ''; $('resultMode').textContent = '请检查链接';
    $('result').setAttribute('aria-busy', 'false'); focusHeading('resultCity');
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
$('fixture').onchange = () => { $('demo').checked = true; refreshContext(); if (location.search) route(); else loadFeatured(); };
$('demo').onchange = () => { refreshContext(); if (location.search) route(); else loadFeatured(); };
async function copy(value, message) {
  try { await navigator.clipboard.writeText(value); $('toast').textContent = message; }
  catch { $('toast').textContent = '浏览器未允许复制，请从地址栏复制链接。'; }
  $('toast').classList.add('show'); clearTimeout(copy.timer); copy.timer = setTimeout(() => $('toast').classList.remove('show'), 3000);
}
$('copyAdvice').onclick = () => { if (current) copy(formatAdviceCopy(current), '已复制建议'); };
$('shareTrip').onclick = () => { if (current) copy(location.origin + location.pathname + link({ ...current, city_id: current.city.id }), current.fixture ? '已复制链接；演示场景不随链接保存' : '已复制行程链接；打开时重新计算'); };
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
  await refreshContext();
  $('demo').checked = Boolean(context.fixture_mode);
  document.querySelector('.demo-tools').classList.toggle('hidden', !context.fixture_mode);
  await refreshContext();
  cities = (await api('/api/cities', cityParams(''))).cities;
  saveForm(); await refreshContext(); await route();
} catch (error) { $('formError').textContent = error.message; }
