// Presentation only. This module never infers clothing levels from temperature.
export function text(tag, value, className = '') {
  const node = document.createElement(tag);
  node.textContent = value;
  node.className = className;
  return node;
}
// Images are decorative: the adjacent text remains the accessible fallback.
export function WarmthIcon(name) {
  const picture = document.createElement('picture');
  picture.className = 'warmth-icon';
  picture.setAttribute('aria-hidden', 'true');
  const path = density => `/static/icons/warmth/${density}/${name}`;
  const source = document.createElement('source');
  source.type = 'image/webp';
  source.srcset = `${path('1x')}.webp 1x, ${path('2x')}.webp 2x`;
  const img = document.createElement('img');
  img.alt = ''; img.width = 64; img.height = 64;
  img.addEventListener('error', () => {
    // Retry PNG if the selected WebP is missing; keep text if PNG also fails.
    if (picture.contains(source)) {
      source.remove();
      img.srcset = `${path('1x')}.png 1x, ${path('2x')}.png 2x`;
      img.src = `${path('1x')}.png`;
    } else picture.hidden = true;
  });
  // Attach the picture before assigning URLs so only the selected format loads.
  picture.append(source, img);
  img.srcset = `${path('1x')}.png 1x, ${path('2x')}.png 2x`;
  img.src = `${path('1x')}.png`;
  return picture;
}
export function WarmthIndicator(level, hasVariation = true, context = 'result') {
  const names = {1: '清爽透气', 2: '轻薄衣物', 3: '薄外套', 4: '中等厚度', 5: '保暖外套', 6: '厚实保暖'};
  const label = level === null ? (hasVariation ? '冷热变化大' : '暂无白天参考') : names[level];
  if (!label) throw new Error('无效保暖标记');
  const chip = text('span', '', 'warmth-mark');
  if (level !== null) chip.setAttribute('aria-label', `保暖程度：${label}`);
  if (level !== null || hasVariation) chip.append(WarmthIcon(level === null ? (context === 'featured' ? 'alert-variation-landscape' : 'alert-variation') : `warmth-l${level}`));
  chip.append(text('span', label, 'warmth-name'));
  return chip;
}
export function CityCard(data, href) {
  const c = data.city, card = text(data.mode === 'unavailable' ? 'div' : 'a', '', 'city-card');
  if (data.mode !== 'unavailable') card.href = href;
  card.append(text('span', c.name, 'eng'), text('span', c.zh, 'city-name'));
  const host = text('span', '', 'warmth-host'); host.append(WarmthIndicator(data.warmth_indicator_level, Boolean(data.packing_variation_summary || data.packing_variation_notice), 'featured'));
  // Style only the server-selected state; shared detail labels remain unchanged.
  host.firstElementChild.classList.add(data.warmth_indicator_level === null
    ? (data.packing_variation_summary || data.packing_variation_notice ? 'warmth-variation' : 'warmth-unavailable')
    : `warmth-level-${data.warmth_indicator_level}`);
  card.append(host, text('span', data.headline, 'coat'));
  if (data.packing_variation_summary) {
    const warning = text('span', '', 'card-variation');
    // Direction is service-provided metadata; never guess from translated copy.
    if (['cold', 'warm', 'mixed'].includes(data.packing_variation_kind)) {
      warning.classList.add(`card-variation--${data.packing_variation_kind}`);
    }
    warning.append(text('span', data.packing_variation_summary));
    card.append(warning);
  }
  // The featured section identifies fixtures once next to its shared date range.
  card.append(text('span', data.mode === 'historical_reference' ? '历史备衣参考（非预报） →' : data.mode === 'unavailable' ? '当日预报尚未更新或数据暂缺；当前没有可用建议' : '查看14天预报 →', 'go'));
  return card;
}

// Export fields deliberately: page provenance details are not a packing summary.
export function formatAdviceCopy(data) {
  const historical = data.mode === 'historical_reference';
  const feelings = { cold: '怕冷', normal: '正常', hot: '怕热' };
  const personal = data.view !== 'city';
  const plan = data.packing_copy;
  const lines = [data.fixture ? '【演示数据，非真实天气】' : personal ? '【德国旅行备衣建议】' : '【德国城市穿衣参考】',
    `城市：${data.city.zh} · ${data.city.name}`,
    `日期：${data.start}—${data.end}`,
    personal ? `冷热偏好：${feelings[data.preference]}` : '冷热偏好：正常（城市默认）',
    `资料：${historical ? '过去五年同期参考，非这趟行程的预报' : '所选日期气温预报'}${data.fixture ? ' · 模拟示例' : ''}`, ''];
  if (plan) {
    lines.push(`【${plan.title}】`, `外套：${plan.outer}。`, `内搭：${plan.inner}。`);
    if (plan.guidance) lines.push(...['alternative', 'personal_layer', 'trousers_shoes'].map(key => plan.guidance[key]).filter(Boolean));
    if (plan.risks.length) lines.push('', '【冷暖提醒】', ...plan.risks);
    if (plan.boundary) lines.push(`厚度提示：${plan.boundary}`);
  } else {
    // Legacy/fixture responses retain their safety copy; never invent missing advice.
    lines.push('【备衣建议】', `外套：${data.headline}`, `内搭：${data.layers}`);
    if (data.packing_variation_notice) lines.push('【冷暖提醒】', data.packing_variation_notice);
    const notes = data.notices.filter(note => !note.includes('今天仅使用查询时刻之后') && !note.includes('保暖需求接近'));
    if (notes.length) lines.push('补充提醒：' + notes.join(' '));
  }
  const adjustment = { cold: '怕冷可多备一层。', normal: '冷热感受因人而异，请按体感调整。', hot: '怕热可减薄内搭，中间层方便脱下。' };
  const adjust = data.preference === 'hot' && plan?.risks.some(risk => risk.includes('减薄内搭')) ? '怕热时可按上述偏暖方式调整。' : adjustment[data.preference];
  if (!plan?.guidance) lines.push('', `个人调整：${adjust}`);
  else lines.push('');
  if (data.reference_temperature_c !== null) lines.push(`白天气温参考：约 ${data.reference_temperature_c}°C${historical ? '（历史样本）' : ''}，不是最高或最低气温。`);
  let caveat = '仅按气温，未评估雨、雪、风；出发前请复查。';
  if (historical) caveat = '历史冷暖不能预测此次旅行的具体日期。' + caveat;
  else if (data.caveat.includes('第8–14天')) caveat += '第8–14天不确定性更大，冷暖日期可能改变。';
  lines.push(`提醒：${caveat}`, data.fixture ? '来源：人工编写的模拟数据，未获取真实天气或历史资料。' :
    `来源：Open-Meteo${historical ? ' / ERA5' : ''}（CC BY 4.0）；GeoNames。`);
  if (!data.fixture) lines.push('资料获取时间：' + data.weather_fetched_at + '（不代表模型更新时间）。',
    '依据气温计算的备衣参考，建议为本站加工结果。',
    'https://open-meteo.com/ · https://creativecommons.org/licenses/by/4.0/ · https://www.geonames.org/');
  return lines.join('\n');
}
