// Presentation only. This module never infers clothing levels from temperature.
export function text(tag, value, className = '') {
  const node = document.createElement(tag);
  node.textContent = value;
  node.className = className;
  return node;
}
export function WarmthIndicator(level) {
  const meta = {
    1: ['轻薄', 1, '#9A4C39', '#FBEDE3'], 2: ['轻薄', 1, '#9A4C39', '#FBEDE3'],
    3: ['薄外层', 2, '#8B5F20', '#FCF0DA'], 4: ['适中保暖', 3, '#586B40', '#EDF2E7'],
    5: ['加强保暖', 4, '#27677B', '#E6F0F4'], 6: ['冬季保暖', 5, '#36547D', '#E9EFF8'],
  };
  if (level === null) return text('span', '冷热变化大', 'warmth-mark');
  const m = meta[level];
  if (!m) throw new Error('无效保暖标记');
  const chip = text('span', '', 'warmth-mark');
  chip.setAttribute('aria-label', `保暖程度：${m[0]}`);
  chip.style.setProperty('--mark-ink', m[2]); chip.style.setProperty('--mark-bg', m[3]);
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 30 17'); svg.setAttribute('aria-hidden', 'true');
  for (let i = 0; i < 5; i++) {
    const bar = document.createElementNS(svg.namespaceURI, 'rect');
    Object.entries({ x: 1 + i * 6, y: 11 - i * 2.5, width: 4, height: 6 + i * 2.5, rx: 1.8,
      fill: i < m[1] ? m[2] : '#CABFB6', 'fill-opacity': i < m[1] ? 1 : .45 })
      .forEach(([k, v]) => bar.setAttribute(k, String(v)));
    svg.append(bar);
  }
  chip.append(svg, text('span', m[0], 'warmth-name'));
  return chip;
}
export function CityCard(data, href) {
  const c = data.city, card = text('a', '', 'city-card'); card.href = href;
  card.append(text('span', c.name, 'eng'), text('span', c.zh, 'city-name'));
  const host = text('span', '', 'warmth-host'); host.append(WarmthIndicator(data.warmth_indicator_level));
  card.append(host, text('span', data.headline, 'coat'));
  if (data.packing_variation_summary) card.append(text('span', data.packing_variation_summary, 'card-variation'));
  if (data.fixture) card.append(text('span', '模拟数据 · 非真实天气', 'card-source'));
  card.append(text('span', '查看14天建议 →', 'go'));
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
  lines.push('', `个人调整：${adjust}`);
  if (data.reference_temperature_c !== null) lines.push(`白天气温参考：约 ${data.reference_temperature_c}°C${historical ? '（历史样本）' : ''}，不是最高或最低气温。`);
  let caveat = '仅按气温，未评估雨、雪、风；出发前请复查。';
  if (historical) caveat = '历史冷暖不能预测此次旅行的具体日期。' + caveat;
  else if (data.caveat.includes('第8–14天')) caveat += '第8–14天不确定性更大，冷暖日期可能改变。';
  lines.push(`提醒：${caveat}`, data.fixture ? '来源：人工编写的模拟数据，未获取真实天气或历史资料。' :
    `来源：Open-Meteo${historical ? ' / ERA5' : ''}（CC BY 4.0）；GeoNames。`);
  return lines.join('\n');
}
