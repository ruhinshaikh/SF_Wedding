// Works out whether two song entries are the same song, from the link (YouTube / Spotify id) or the title.

function linkKey(raw) {
  const s = (raw || '').trim()
  if (!s) return ''
  let u
  try { u = new URL(/^https?:\/\//i.test(s) ? s : `https://${s}`) } catch { return `url:${s.toLowerCase()}` }
  const host = u.hostname.toLowerCase().replace(/^(www|m|music)\./, '')
  const parts = u.pathname.split('/').filter(Boolean)
  if (host === 'youtu.be' && parts[0]) return `yt:${parts[0]}`
  if (host.endsWith('youtube.com')) {
    const v = u.searchParams.get('v')
    if (v) return `yt:${v}`
    const i = parts.findIndex((p) => ['shorts', 'embed', 'live', 'v'].includes(p))
    if (i >= 0 && parts[i + 1]) return `yt:${parts[i + 1]}`
  }
  if (host.endsWith('spotify.com')) {
    const i = parts.indexOf('track')
    if (i >= 0 && parts[i + 1]) return `sp:${parts[i + 1]}`
  }
  return `url:${host}/${parts.join('/').toLowerCase()}`
}

function titleKey(raw) {
  const t = (raw || '')
    .toLowerCase()
    .replace(/\([^)]*\)|\[[^\]]*\]/g, ' ') // drop "(Official Video)", "[Lyrics]"
    .replace(/[^\p{L}\p{N}]+/gu, ' ')
    .trim()
  return t.length >= 3 ? `t:${t}` : ''
}

export const songKeys = (s) => [linkKey(s.link), titleKey(s.title)].filter(Boolean)

export const sameSong = (a, b) => {
  const kb = songKeys(b)
  return songKeys(a).some((k) => kb.includes(k))
}

export const songLabel = (s) => {
  if (s.title && s.title.trim()) return s.title.trim()
  try { return new URL(s.link).hostname.replace(/^www\./, '') + ' link' } catch { return s.link || 'Untitled' }
}
