import { i18n } from './i18n/index.js'

const zh = () => i18n.global.locale.value === 'zh'
const pad = n => String(n).padStart(2, '0')

export function hm(ts) {
  const d = new Date(ts * 1000)
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export function md(ts) {
  const d = new Date(ts * 1000)
  return zh() ? `${d.getMonth() + 1}月${d.getDate()}日` : d.toLocaleDateString('en', { month: 'short', day: 'numeric' })
}

export function longDate(ts) {
  const d = new Date(ts * 1000)
  if (zh()) return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日 星期${'日一二三四五六'[d.getDay()]}`
  return d.toLocaleDateString('en', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })
}

export function datetime(ts) {
  if (!ts) return '-'
  return `${md(ts)} ${hm(ts)}`
}

// 时间窗口：同一天只写一次日期
export function span(a, b) {
  const da = new Date(a * 1000), db = new Date(b * 1000)
  return da.toDateString() === db.toDateString() ? `${md(a)} ${hm(a)}–${hm(b)}` : `${datetime(a)} – ${datetime(b)}`
}

export function ago(ts) {
  const s = Math.max(0, Date.now() / 1000 - ts)
  const t = i18n.global.t
  if (s < 60) return t('time.now')
  if (s < 3600) return t('time.min', { n: Math.floor(s / 60) })
  if (s < 86400) return t('time.hour', { n: Math.floor(s / 3600) })
  return t('time.day', { n: Math.floor(s / 86400) })
}
