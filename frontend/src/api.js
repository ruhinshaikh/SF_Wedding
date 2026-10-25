const TOKEN_KEY = 'wedding_admin_token'

export const adminToken = {
  get: () => localStorage.getItem(TOKEN_KEY) || '',
  set: (t) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
}

const GUEST_KEY = 'wedding_guest_token'
const INVITES_KEY = 'wedding_guest_invites'

// A guest signs in with the mobile number on the guest list. The admin's own login also opens every page.
export const guestToken = {
  get: () => localStorage.getItem(GUEST_KEY) || '',
  set: (t, invites = []) => {
    localStorage.setItem(GUEST_KEY, t)
    localStorage.setItem(INVITES_KEY, JSON.stringify(invites))
  },
  invites: () => {
    try { return JSON.parse(localStorage.getItem(INVITES_KEY) || '[]') } catch { return [] }
  },
  clear: () => {
    localStorage.removeItem(GUEST_KEY)
    localStorage.removeItem(INVITES_KEY)
  },
}
export const isLoggedIn = () => !!(guestToken.get() || adminToken.get())

async function request(path, { method = 'GET', body, form, admin = false } = {}) {
  const headers = {}
  const sent = admin ? adminToken.get() : adminToken.get() || guestToken.get()
  if (sent || admin) headers.Authorization = `Bearer ${sent}`
  let payload
  if (form) payload = form
  else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  const res = await fetch(`/api${path}`, { method, headers, body: payload })
  if (res.status === 401 && admin) {
    adminToken.clear()
    window.dispatchEvent(new Event('admin-logout'))
  } else if (res.status === 401 && !path.startsWith('/login')) {
    // the guest session expired or is invalid
    if (adminToken.get()) adminToken.clear()
    else guestToken.clear()
    window.dispatchEvent(new Event('guest-logout'))
  }
  if (!res.ok) {
    let msg = `Request failed (${res.status})`
    try {
      const data = await res.json()
      if (typeof data.detail === 'string') msg = data.detail
      else if (Array.isArray(data.detail)) msg = data.detail.map((d) => d.msg).join('; ')
    } catch {}
    throw new Error(msg)
  }
  return res.json()
}

export const api = {
  publicInvite: () => request('/public/invite'),
  guestLogin: (phone) => request('/login', { method: 'POST', body: { phone } }),
  invite: (token) => request(`/invite/${token}`),
  ping: (token) => request(`/invite/${token}/ping`, { method: 'POST' }).catch(() => {}),
  active: () => request('/admin/active', { admin: true }),
  rsvp: (token, body) => request(`/invite/${token}/rsvp`, { method: 'POST', body }),
  inviteGroups: (token) => request(`/invite/${token}/groups`),
  login: (password) => request('/admin/login', { method: 'POST', body: { password } }),
  config: () => request('/config'),
  summary: () => request('/admin/summary', { admin: true }),
  guests: () => request('/admin/guests', { admin: true }),
  saveGuest: (g) =>
    request(g.id ? `/admin/guests/${g.id}` : '/admin/guests', {
      method: g.id ? 'PUT' : 'POST',
      body: g,
      admin: true,
    }),
  deleteGuest: (id) => request(`/admin/guests/${id}`, { method: 'DELETE', admin: true }),
  markSent: (id, sent) => request(`/admin/guests/${id}/sent?sent=${sent}`, { method: 'POST', admin: true }),
  importGuests: (file) => {
    const form = new FormData()
    form.append('file', file)
    return request('/admin/guests/import', { method: 'POST', form, admin: true })
  },
  groups: () => request('/admin/groups', { admin: true }),
  markGroup: (gid, guestId, done) => request(`/admin/groups/${gid}/guests/${guestId}?done=${done}`, { method: 'POST', admin: true }),
  songs: () => request('/admin/songs', { admin: true }),
  danceGroups: () => request('/admin/dance-groups', { admin: true }),
  saveDanceGroup: (g) =>
    request(g.id ? `/admin/dance-groups/${g.id}` : '/admin/dance-groups', { method: g.id ? 'PUT' : 'POST', body: g, admin: true }),
  deleteDanceGroup: (id) => request(`/admin/dance-groups/${id}`, { method: 'DELETE', admin: true }),
  assignDanceGroup: (guestId, groupId) =>
    request(`/admin/guests/${guestId}/dance-group`, { method: 'POST', body: { group_id: groupId }, admin: true }),
  vendors: () => request('/admin/vendors', { admin: true }),
  saveVendor: (v) =>
    request(v.id ? `/admin/vendors/${v.id}` : '/admin/vendors', {
      method: v.id ? 'PUT' : 'POST',
      body: v,
      admin: true,
    }),
  deleteVendor: (id) => request(`/admin/vendors/${id}`, { method: 'DELETE', admin: true }),
}

// Authenticated downloads (CSV) and image URLs use the token as a query param.
export const adminUrl = (path) => `/api${path}${path.includes('?') ? '&' : '?'}t=${encodeURIComponent(adminToken.get())}`

export const fmtDate = (iso) =>
  new Date(iso + 'T00:00:00').toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long' })
export const dayParts = (iso) => {
  const d = new Date(iso + 'T00:00:00')
  return { day: d.getDate(), month: d.toLocaleDateString('en-IN', { month: 'short' }), weekday: d.toLocaleDateString('en-IN', { weekday: 'long' }) }
}
export const fmtDateLong = (iso) =>
  new Date(iso + 'T00:00:00').toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })
