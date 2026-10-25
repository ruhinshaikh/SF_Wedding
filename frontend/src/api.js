const TOKEN_KEY = 'wedding_admin_token'

export const adminToken = {
  get: () => localStorage.getItem(TOKEN_KEY) || '',
  set: (t) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
}

async function request(path, { method = 'GET', body, form, admin = false } = {}) {
  const headers = {}
  if (admin) headers.Authorization = `Bearer ${adminToken.get()}`
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
  invite: (token) => request(`/invite/${token}`),
  rsvp: (token, body) => request(`/invite/${token}/rsvp`, { method: 'POST', body }),
  uploadPhotos: (token, files) => {
    const form = new FormData()
    files.forEach((f) => form.append('files', f))
    return request(`/invite/${token}/photos`, { method: 'POST', form })
  },
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
  vendors: () => request('/admin/vendors', { admin: true }),
  saveVendor: (v) =>
    request(v.id ? `/admin/vendors/${v.id}` : '/admin/vendors', {
      method: v.id ? 'PUT' : 'POST',
      body: v,
      admin: true,
    }),
  deleteVendor: (id) => request(`/admin/vendors/${id}`, { method: 'DELETE', admin: true }),
  photos: () => request('/admin/photos', { admin: true }),
  syncPhotos: () => request('/admin/photos/sync', { method: 'POST', admin: true }),
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
