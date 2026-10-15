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
  chip.setAttribute('aria-label', `临时保暖标记：${m[0]}`);
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
  card.append(text('span', '查看14天建议 →', 'go'));
  return card;
}
