import { useCallback, useEffect, useMemo, useState } from 'react'
import { adminToken, adminUrl, api, fmtDate } from './api.js'
import { sameSong } from './songs.js'

const TABS = [
  ['overview', 'Overview'],
  ['guests', 'Guests'],
  ['groups', 'WhatsApp groups'],
  ['sangeet', 'Sangeet dances'],
  ['vendors', 'Vendors'],
]

export default function Admin() {
  const [authed, setAuthed] = useState(!!adminToken.get())
  const [tab, setTab] = useState('overview')
  const [config, setConfig] = useState(null)

  useEffect(() => {
    const out = () => setAuthed(false)
    window.addEventListener('admin-logout', out)
    return () => window.removeEventListener('admin-logout', out)
  }, [])
  useEffect(() => {
    if (authed) api.config().then(setConfig)
  }, [authed])

  if (!authed) return <Login onDone={() => setAuthed(true)} />
  if (!config) return <main className="admin muted">Loading…</main>

  return (
    <div className="admin">
      <header className="admin-head">
        <h1 className="display">{config.couple.title}</h1>
        <nav aria-label="Dashboard sections" className="tabs">
          {TABS.map(([id, label]) => (
            <button key={id} className={`tab ${tab === id ? 'on' : ''}`} aria-current={tab === id ? 'page' : undefined} onClick={() => setTab(id)}>
              {label}
            </button>
          ))}
        </nav>
        <a className="link-btn" href="/preview" target="_blank" rel="noreferrer">
          Preview invitation
        </a>
        <button
          className="link-btn"
          onClick={() => {
            adminToken.clear()
            setAuthed(false)
          }}
        >
          Log out
        </button>
      </header>
      <main>
        {tab === 'overview' && <Overview config={config} goto={setTab} />}
        {tab === 'guests' && <Guests config={config} />}
        {tab === 'groups' && <Groups />}
        {tab === 'sangeet' && <Songs />}
        {tab === 'vendors' && <Vendors config={config} />}
      </main>
    </div>
  )
}

function Login({ onDone }) {
  const [pw, setPw] = useState('')
  const [err, setErr] = useState('')
  async function go(e) {
    e.preventDefault()
    setErr('')
    try {
      const { token } = await api.login(pw)
      adminToken.set(token)
      onDone()
    } catch (e) {
      setErr(e.message)
    }
  }
  return (
    <main className="narrow center-page">
      <h1 className="display">Family dashboard</h1>
      <form onSubmit={go} className="stack login">
        <label className="field">
          <span>Password</span>
          <input type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoFocus autoComplete="current-password" />
        </label>
        {err && <p className="error" role="alert">{err}</p>}
        <button className="btn btn-rani">Log in</button>
      </form>
    </main>
  )
}

/* ---------------------------------------------------------------- shared */

function useLoad(fn) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const load = useCallback(() => fn().then(setData).catch((e) => setError(e.message)), [fn])
  useEffect(() => {
    load()
  }, [load])
  return [data, load, error]
}

function Modal({ title, onClose, children }) {
  useEffect(() => {
    const k = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [onClose])
  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal-head">
          <h2 className="display h3">{title}</h2>
          <button className="icon-btn" onClick={onClose} aria-label="Close">×</button>
        </div>
        {children}
      </div>
    </div>
  )
}

const inr = (n) => '₹' + Math.round(n).toLocaleString('en-IN')

/* ---------------------------------------------------------------- overview */

function ago(sec) {
  if (sec < 60) return 'just now'
  if (sec < 3600) return `${Math.floor(sec / 60)} min ago`
  if (sec < 86400) return `${Math.floor(sec / 3600)} h ago`
  return `${Math.floor(sec / 86400)} d ago`
}

function ActiveNow() {
  const [d, setD] = useState(null)
  useEffect(() => {
    const load = () => api.active().then(setD).catch(() => {})
    load()
    const t = setInterval(load, 15000)
    return () => clearInterval(t)
  }, [])
  if (!d) return null
  const row = (r) => (
    <tr key={r.id}>
      <td>{r.name}<div className="muted small">{r.group}</div></td>
      <td className="small">{r.ip || '-'}</td>
      <td className="small">{r.replied ? 'Replied' : 'Not yet'}</td>
      <td className="small">{r.visits}</td>
      <td className="small">{ago(r.seconds_ago)}</td>
    </tr>
  )
  const head = <thead><tr><th>Guest</th><th>IP address</th><th>RSVP</th><th>Visits</th><th>Last seen</th></tr></thead>
  return (
    <section>
      <h2 className="display h3">Active now ({d.active.length})</h2>
      {d.active.length === 0 ? <p className="muted small">Nobody has the invitation open right now. Updates every 15 seconds.</p> : (
        <div className="table-wrap"><table>{head}<tbody>{d.active.map(row)}</tbody></table></div>
      )}
      {d.recent.length > 0 && (
        <details>
          <summary className="muted small">Recent visitors</summary>
          <div className="table-wrap"><table>{head}<tbody>{d.recent.map(row)}</tbody></table></div>
        </details>
      )}
    </section>
  )
}

function Overview({ config, goto }) {
  const [s, , error] = useLoad(api.summary)
  if (error) return <p className="error">{error}</p>
  if (!s) return <p className="muted">Loading…</p>
  const pending = s.households - s.responded
  return (
    <div className="stack-lg">
      <section className="stat-row">
        <Stat n={s.households} label="invitations" sub={`${s.seats} seats`} />
        <Stat n={s.invites_sent} label="sent on WhatsApp" sub={`${s.households - s.invites_sent} to send`} />
        <Stat n={s.responded} label="replied" sub={`${pending} waiting${s.rsvp_deadline ? `, due ${fmtDate(s.rsvp_deadline)}` : ''}`} />
        <Stat n={s.dance_acts} label="Sangeet dances" sub={`${s.songs} songs`} />
        <Stat n={s.stay_guests} label="people need a stay" sub={`${s.stay_households} invitations`} />
      </section>

      <ActiveNow />

      <section>
        <h2 className="display h3">Guests and food by event</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Event</th><th>Attending</th><th>Declined</th><th>Waiting</th><th>Seats invited</th>{(s.food_options || []).map((o) => <th key={o}>{o}</th>)}<th>Not said</th>
              </tr>
            </thead>
            <tbody>
              {s.per_event.map((e) => (
                <tr key={e.id}>
                  <td>{e.name}</td>
                  <td><strong>{e.attending_guests}</strong> guests</td>
                  <td>{e.declined_households}</td>
                  <td>{e.pending_households}</td>
                  <td>{e.invited_seats}</td>
                  {(s.food_options || []).map((o) => <td key={o}>{e.food?.[o] || 0}</td>)}
                  <td className="muted">{e.food_unspecified || 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="two-col">
        <div>
          <h2 className="display h3">Vendors</h2>
          <p>
            {s.vendors} booked or shortlisted. {inr(s.vendor_paid)} paid of {inr(s.vendor_total)}
            {s.vendor_total > 0 && <> ({inr(s.vendor_total - s.vendor_paid)} still due)</>}.
          </p>
          <button className="link-btn" onClick={() => goto('vendors')}>Open vendors</button>
        </div>
      </section>
    </div>
  )
}

function Stat({ n, label, sub }) {
  return (
    <div className="stat">
      <div className="stat-n">{n}</div>
      <div className="stat-label">{label}</div>
      <div className="muted small">{sub}</div>
    </div>
  )
}

/* ---------------------------------------------------------------- guests */

const blankGuest = (config) => ({ name: '', phone: '', email: '', group: '', max_party: 1, events: config.events.map((e) => e.id), notes: '', offer_stay: false })

function Guests({ config }) {
  const [guests, reload, error] = useLoad(api.guests)
  const [q, setQ] = useState('')
  const [filter, setFilter] = useState('all')
  const [groupFilter, setGroupFilter] = useState('')
  const [editing, setEditing] = useState(null)
  const [note, setNote] = useState('')

  const shown = useMemo(() => {
    if (!guests) return []
    const s = q.trim().toLowerCase()
    return guests.filter((g) => {
      if (groupFilter && g.group !== groupFilter) return false
      if (filter === 'unsent' && g.invite_sent) return false
      if (['pending', 'attending', 'declined'].includes(filter) && g.status !== filter) return false
      return !s || `${g.name} ${g.group} ${g.phone}`.toLowerCase().includes(s)
    })
  }, [guests, q, filter, groupFilter])

  async function sendWhatsApp(g) {
    window.open(g.whatsapp_url, '_blank', 'noopener')
    if (!g.invite_sent) {
      await api.markSent(g.id, true)
      reload()
    }
  }
  async function copy(g) {
    try {
      await navigator.clipboard.writeText(g.invite_url)
      setNote(`Copied the link for ${g.name}`)
    } catch {
      setNote(g.invite_url)
    }
  }
  async function remove(g) {
    if (!confirm(`Remove ${g.name} and their reply? This can't be undone.`)) return
    await api.deleteGuest(g.id)
    reload()
  }
  async function importCsv(e) {
    const f = e.target.files?.[0]
    if (!f) return
    try {
      const r = await api.importGuests(f)
      setNote(`Added ${r.created} invitations${r.skipped ? `, skipped ${r.skipped} rows without a name` : ''}`)
      reload()
    } catch (err) {
      setNote(err.message)
    }
    e.target.value = ''
  }

  if (error) return <p className="error">{error}</p>
  if (!guests) return <p className="muted">Loading…</p>
  const evName = Object.fromEntries(config.events.map((e) => [e.id, e.name]))

  return (
    <div className="stack">
      <div className="toolbar">
        <input aria-label="Search guests" placeholder="Search name, group or phone" value={q} onChange={(e) => setQ(e.target.value)} />
        <select aria-label="Filter by group" value={groupFilter} onChange={(e) => setGroupFilter(e.target.value)}>
          <option value="">All groups</option>
          {[...new Set([...(config.guest_groups || []), ...(guests || []).map((g) => g.group).filter(Boolean)])].map((x) => (
            <option key={x} value={x}>{x}</option>
          ))}
        </select>
        <select aria-label="Filter guests" value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="all">Everyone ({guests.length})</option>
          <option value="unsent">Not sent yet</option>
          <option value="pending">Waiting for reply</option>
          <option value="attending">Attending</option>
          <option value="declined">Declined</option>
        </select>
        <button className="btn btn-rani" onClick={() => setEditing(blankGuest(config))}>Add guest</button>
        <label className="btn btn-ghost">
          Import CSV
          <input type="file" accept=".csv,text/csv" hidden onChange={importCsv} />
        </label>
        <a className="btn btn-ghost" href={adminUrl('/admin/guests/export.csv')}>Export CSV</a>
      </div>
      {note && <p className="notice" role="status">{note}</p>}
      <p className="muted small">
        CSV columns: name, phone, email, group, max_party, events, offer_stay (yes or blank; use "all" or ids like {config.events.map((e) => e.id).join(';')}).
      </p>

      <div className="table-wrap">
        <table className="cards">
          <thead>
            <tr><th>Guest</th><th>Invited to</th><th>Reply</th><th>Invitation</th><th></th></tr>
          </thead>
          <tbody>
            {shown.length === 0 && (
              <tr><td colSpan="5" className="muted">{guests.length ? 'No guests match.' : 'No guests yet. Add one, or import a CSV.'}</td></tr>
            )}
            {shown.map((g) => (
              <tr key={g.id}>
                <td>
                  <strong>{g.name}</strong>
                  <div className="muted small">{[g.group, `up to ${g.max_party}`, g.phone].filter(Boolean).join(', ')}</div>
                </td>
                <td className="small">{g.events.map((id) => evName[id]).join(', ')}</td>
                <td>
                  <span className={`badge ${g.status}`}>{g.status === 'attending' ? `Attending (${g.headcount})` : g.status === 'declined' ? 'Declined' : 'Waiting'}</span>
                  {g.rsvp?.wants_to_dance && <div className="small">Dancing at Sangeet</div>}
                  {Object.entries(g.rsvp?.events || {}).filter(([, v]) => v.attending && Object.keys(v.food || {}).length).map(([id, v]) => (
                    <div key={id} className="muted small">{evName[id]} food: {Object.entries(v.food).map(([k, n]) => `${k} ×${n}`).join(', ')}</div>
                  ))}
                  {g.rsvp?.dietary && <div className="muted small">Allergies/other: {g.rsvp.dietary}</div>}
                  {g.offer_stay && !g.rsvp?.needs_stay && <div className="muted small">Stay offered</div>}
                  {g.rsvp?.needs_stay && (
                    <div className="small">
                      Needs a stay ({g.rsvp.stay_guests})
                      {g.rsvp.stay_notes && <span className="muted">: {g.rsvp.stay_notes}</span>}
                    </div>
                  )}
                </td>
                <td>
                  <div className="row-actions">
                    <button className="btn btn-small btn-wa" onClick={() => sendWhatsApp(g)} disabled={!g.phone} title={g.phone ? '' : 'Add a phone number first'}>
                      {g.invite_sent ? 'Resend' : 'WhatsApp'}
                    </button>
                    <button className="link-btn" onClick={() => copy(g)}>Copy link</button>
                  </div>
                  {g.invite_sent && <div className="muted small">Sent</div>}
                </td>
                <td>
                  <div className="row-actions">
                    <button className="link-btn" onClick={() => setEditing(g)}>Edit</button>
                    <button className="link-btn danger" onClick={() => remove(g)}>Remove</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {editing && (
        <GuestForm
          config={config}
          initial={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null)
            reload()
          }}
        />
      )}
    </div>
  )
}

function GuestForm({ config, initial, onClose, onSaved }) {
  const [g, setG] = useState(initial)
  const [err, setErr] = useState('')
  const set = (k) => (e) => setG({ ...g, [k]: e.target.value })
  const toggle = (id) => setG({ ...g, events: g.events.includes(id) ? g.events.filter((x) => x !== id) : [...g.events, id] })

  async function save(e) {
    e.preventDefault()
    if (!g.name.trim()) return setErr('Enter a name for the invitation.')
    if (g.events.length === 0) return setErr('Pick at least one event.')
    try {
      await api.saveGuest({ ...g, max_party: Number(g.max_party) || 1 })
      onSaved()
    } catch (e) {
      setErr(e.message)
    }
  }
  return (
    <Modal title={g.id ? 'Edit guest' : 'Add guest'} onClose={onClose}>
      <form onSubmit={save} className="stack" noValidate>
        <label className="field"><span>Name on the invitation</span><input value={g.name} onChange={set('name')} placeholder="Asha Rao, or The Rao family" autoFocus /></label>
        <div className="grid-2">
          <label className="field"><span>WhatsApp number</span><input value={g.phone} onChange={set('phone')} inputMode="tel" placeholder="98450 12345" /></label>
          <label className="field"><span>Seats on this invitation</span><input type="number" min="1" max="20" value={g.max_party} onChange={set('max_party')} /></label>
          <label className="field">
            <span>Group</span>
            <select value={g.group} onChange={set('group')}>
              <option value="">Not set</option>
              {[...(config.guest_groups || []), ...(g.group && !(config.guest_groups || []).includes(g.group) ? [g.group] : [])].map((x) => (
                <option key={x} value={x}>{x}</option>
              ))}
            </select>
          </label>
          <label className="field"><span>Email (optional)</span><input value={g.email} onChange={set('email')} type="email" /></label>
        </div>
        <fieldset className="field-group">
          <legend>Invited to</legend>
          <div className="checks">
            {config.events.map((e) => (
              <label key={e.id} className="check"><input type="checkbox" checked={g.events.includes(e.id)} onChange={() => toggle(e.id)} /> {e.name}</label>
            ))}
          </div>
        </fieldset>
        <label className="check"><input type="checkbox" checked={!!g.offer_stay} onChange={(e) => setG({ ...g, offer_stay: e.target.checked })} /> Offer accommodation (shows the "place to stay" question on this invitation)</label>
        <label className="field"><span>Private notes</span><textarea rows={2} value={g.notes} onChange={set('notes')} /></label>
        {err && <p className="error" role="alert">{err}</p>}
        <div className="form-actions"><button className="btn btn-rani">Save guest</button><button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button></div>
      </form>
    </Modal>
  )
}

/* ---------------------------------------------------------------- sangeet */

function Groups() {
  const [groups, reload, error] = useLoad(api.groups)
  const [note, setNote] = useState('')

  if (error) return <p className="error">{error}</p>
  if (!groups) return <p className="muted">Loading…</p>

  async function mark(group, m, done) {
    await api.markGroup(group.id, m.id, done)
    reload()
  }
  async function send(group, m) {
    window.open(m.whatsapp_url, '_blank', 'noopener')
    if (!m.done) await mark(group, m, true)
  }
  async function copyNumbers(group) {
    const todo = group.members.filter((m) => !m.done && m.number).map((m) => m.number)
    try {
      await navigator.clipboard.writeText(todo.join('\n'))
      setNote(`Copied ${todo.length} number${todo.length === 1 ? '' : 's'} for ${group.name}`)
    } catch {
      setNote(todo.join(', '))
    }
  }

  return (
    <div className="stack-lg">
      <p className="muted small">
        WhatsApp does not let any app add people to a group on its own. Create the group in WhatsApp, paste its invite link into
        config.json, then send each guest the link from here once they have said yes. You can also copy the numbers and add them in
        WhatsApp yourself.
      </p>
      {note && <p className="notice" role="status">{note}</p>}
      {groups.length === 0 && <p className="muted">No groups yet. Add one under "whatsapp_groups" in config.json.</p>}
      {groups.map((grp) => {
        const done = grp.members.filter((m) => m.done).length
        return (
          <section key={grp.id} className="stack" aria-label={grp.name}>
            <div className="toolbar">
              <h2 className="h3">{grp.name}</h2>
              <span className="muted small">{done} of {grp.members.length} done</span>
              <button className="btn btn-ghost btn-small" onClick={() => copyNumbers(grp)} disabled={!grp.members.some((m) => !m.done && m.number)}>
                Copy numbers not yet added
              </button>
            </div>
            {!grp.url && (
              <p className="notice">No invite link yet. In WhatsApp open the group, choose Invite via link, then paste it as "url" for "{grp.id}" in config.json.</p>
            )}
            <div className="table-wrap">
              <table>
                <thead>
                  <tr><th>Guest</th><th>Status</th><th></th></tr>
                </thead>
                <tbody>
                  {grp.members.length === 0 && (
                    <tr><td colSpan="3" className="muted">Nobody yet. Guests appear here after they reply yes.</td></tr>
                  )}
                  {grp.members.map((m) => (
                    <tr key={m.id}>
                      <td>
                        <strong>{m.name}</strong>
                        <div className="muted small">{m.phone || 'No phone number'}</div>
                      </td>
                      <td><span className={`badge ${m.done ? 'attending' : 'pending'}`}>{m.done ? 'Done' : 'To do'}</span></td>
                      <td>
                        <div className="row-actions">
                          <button className="btn btn-small btn-wa" onClick={() => send(grp, m)} disabled={!grp.url || !m.has_phone} title={!grp.url ? 'Add the group link first' : !m.has_phone ? 'Add a phone number first' : ''}>
                            Send group link
                          </button>
                          <button className="link-btn" onClick={() => mark(grp, m, !m.done)}>
                            {m.done ? 'Mark as to do' : 'Mark as added'}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )
      })}
    </div>
  )
}

const DANCE_LABEL = { solo: 'Solo', couple: 'Couple', group: 'Group' }

function Songs() {
  const [acts, reloadActs, error] = useLoad(api.songs)
  const [dg, reloadGroups] = useLoad(api.danceGroups)
  const [name, setName] = useState('')
  const [err, setErr] = useState('')
  if (error) return <p className="error">{error}</p>
  if (!acts || !dg) return <p className="muted">Loading…</p>

  const reload = () => { reloadActs(); reloadGroups() }
  // other acts that picked the same song
  const clashes = (a, s) => acts.filter((o) => o.guest_id !== a.guest_id && o.songs.some((x) => sameSong(s, x))).map((o) => o.guest)
  const clashCount = acts.reduce((n, a) => n + a.songs.filter((s) => clashes(a, s).length).length, 0)
  const groupName = Object.fromEntries(dg.groups.map((g) => [g.id, g.name]))

  async function create(e) {
    e.preventDefault()
    if (!name.trim()) return
    setErr('')
    try { await api.saveDanceGroup({ name }); setName(''); reload() } catch (x) { setErr(x.message) }
  }
  async function rename(g) {
    const n = prompt('Group name', g.name)
    if (n && n.trim() && n !== g.name) { await api.saveDanceGroup({ id: g.id, name: n, notes: g.notes }); reload() }
  }
  async function remove(g) {
    if (!confirm(`Delete the group "${g.name}"? Its members stay on the guest list.`)) return
    await api.deleteDanceGroup(g.id)
    reload()
  }
  async function assign(guestId, value) {
    await api.assignDanceGroup(guestId, value ? Number(value) : null)
    reload()
  }

  return (
    <div className="stack-lg">
      <section className="stack">
        <h2 className="display h3">Dance groups</h2>
        <p className="muted small">Make a group for each dance (for example "Bride's cousins"), then add guests to it. Guests are added from the dropdown on each group, or from the song list below.</p>
        <form className="toolbar" onSubmit={create}>
          <input aria-label="New dance group name" placeholder="New group name" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} />
          <button className="btn btn-rani" disabled={!name.trim()}>Create group</button>
        </form>
        {err && <p className="error">{err}</p>}
        {dg.groups.length === 0 && <p className="muted">No dance groups yet.</p>}
        {dg.groups.map((g) => (
          <article key={g.id} className="act">
            <h3 className="act-name">{g.name} <span className="muted small">({g.members.length} {g.members.length === 1 ? 'guest' : 'guests'})</span></h3>
            {g.members.length === 0 && <p className="muted small">Nobody added yet.</p>}
            <ul className="song-list">
              {g.members.map((m) => (
                <li key={m.guest_id}>
                  {m.name}
                  {m.wants_to_dance && <span className="muted small"> ({DANCE_LABEL[m.dance_type] || 'dancing'}, {m.songs} {m.songs === 1 ? 'song' : 'songs'})</span>}{' '}
                  <button className="link-btn" onClick={() => assign(m.guest_id, '')}>Remove</button>
                </li>
              ))}
            </ul>
            <div className="toolbar">
              <select aria-label={`Add a guest to ${g.name}`} value="" onChange={(e) => e.target.value && assign(e.target.value, g.id)}>
                <option value="">Add a guest…</option>
                {dg.available.map((a) => (
                  <option key={a.guest_id} value={a.guest_id}>{a.name}{a.wants_to_dance ? ' (wants to dance)' : ''}</option>
                ))}
              </select>
              <button className="link-btn" onClick={() => rename(g)}>Rename</button>
              <button className="link-btn" onClick={() => remove(g)}>Delete</button>
            </div>
          </article>
        ))}
      </section>

      <section className="stack">
        <h2 className="display h3">Dance requests</h2>
        {acts.length === 0 ? (
          <p className="muted">No dance requests yet. They'll show up here as guests reply to the Sangeet.</p>
        ) : (
          <>
            <p className="muted">{acts.length} {acts.length === 1 ? 'dance' : 'dances'}, {acts.reduce((n, a) => n + a.songs.length, 0)} songs. Share this list with the DJ or choreographer.</p>
            {clashCount > 0 && <p className="song-warn">⚠ Some songs are picked by more than one dance. They're marked below.</p>}
            {acts.map((a) => (
              <article key={a.guest_id} className="act">
                <h3 className="act-name">
                  {a.guest}{a.group && <span className="muted small"> ({a.group})</span>}
                  {a.dance_type && <span className="badge"> {DANCE_LABEL[a.dance_type]}</span>}
                </h3>
                {a.dance_with && <p>Dancing with: {a.dance_with}</p>}
                <label className="inline-field">
                  <span>Dance group</span>
                  <select value={a.dance_group_id || ''} onChange={(e) => assign(a.guest_id, e.target.value)}>
                    <option value="">None</option>
                    {dg.groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
                  </select>
                </label>
                <ul className="song-list">
                  {a.songs.map((s, i) => (
                    <li key={i}>
                      {s.title || 'Untitled'}{' '}
                      {s.link && <a href={s.link} target="_blank" rel="noreferrer noopener">Listen</a>}
                      {clashes(a, s).length > 0 && <span className="song-dup"> ⚠ also picked by {clashes(a, s).join(', ')}</span>}
                    </li>
                  ))}
                </ul>
                {a.notes && <p className="muted small">Note: {a.notes}</p>}
              </article>
            ))}
          </>
        )}
      </section>
    </div>
  )
}

/* ---------------------------------------------------------------- vendors */

const CATEGORIES = ['Venue', 'Catering', 'Decor', 'Photography', 'Videography', 'Music / DJ', 'Makeup', 'Mehendi', 'Priest', 'Transport', 'Stay', 'Invitations', 'Other']
const VENDOR_STATUS = ['Shortlisted', 'Quoted', 'Booked', 'Advance paid', 'Fully paid']
const blankVendor = () => ({ name: '', category: 'Other', contact_person: '', phone: '', email: '', website: '', total_cost: 0, amount_paid: 0, status: 'Shortlisted', event_ids: [], notes: '' })

function Vendors({ config }) {
  const [vendors, reload, error] = useLoad(api.vendors)
  const [editing, setEditing] = useState(null)
  if (error) return <p className="error">{error}</p>
  if (!vendors) return <p className="muted">Loading…</p>

  async function remove(v) {
    if (!confirm(`Remove ${v.name}?`)) return
    await api.deleteVendor(v.id)
    reload()
  }
  return (
    <div className="stack">
      <div className="toolbar"><button className="btn btn-rani" onClick={() => setEditing(blankVendor())}>Add vendor</button></div>
      <div className="table-wrap">
        <table className="cards">
          <thead><tr><th>Vendor</th><th>Contact</th><th>Status</th><th>Cost</th><th></th></tr></thead>
          <tbody>
            {vendors.length === 0 && <tr><td colSpan="5" className="muted">No vendors yet. Add the venue, caterer, photographer and anyone else you're working with.</td></tr>}
            {vendors.map((v) => (
              <tr key={v.id}>
                <td><strong>{v.name}</strong><div className="muted small">{v.category}</div></td>
                <td className="small">
                  {v.contact_person}
                  {v.phone && <div><a href={`tel:${v.phone}`}>{v.phone}</a></div>}
                  {v.email && <div><a href={`mailto:${v.email}`}>{v.email}</a></div>}
                </td>
                <td>{v.status}</td>
                <td>{inr(v.total_cost)}<div className="muted small">{inr(v.amount_paid)} paid{v.total_cost > v.amount_paid ? `, ${inr(v.total_cost - v.amount_paid)} due` : ''}</div></td>
                <td><div className="row-actions"><button className="link-btn" onClick={() => setEditing(v)}>Edit</button><button className="link-btn danger" onClick={() => remove(v)}>Remove</button></div></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {editing && <VendorForm initial={editing} config={config} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); reload() }} />}
    </div>
  )
}

function VendorForm({ initial, config, onClose, onSaved }) {
  const [v, setV] = useState(initial)
  const [err, setErr] = useState('')
  const set = (k) => (e) => setV({ ...v, [k]: e.target.value })
  const toggle = (id) => setV({ ...v, event_ids: v.event_ids.includes(id) ? v.event_ids.filter((x) => x !== id) : [...v.event_ids, id] })
  async function save(e) {
    e.preventDefault()
    if (!v.name.trim()) return setErr('Enter the vendor name.')
    try {
      await api.saveVendor({ ...v, total_cost: Number(v.total_cost) || 0, amount_paid: Number(v.amount_paid) || 0 })
      onSaved()
    } catch (e) {
      setErr(e.message)
    }
  }
  return (
    <Modal title={v.id ? 'Edit vendor' : 'Add vendor'} onClose={onClose}>
      <form onSubmit={save} className="stack" noValidate>
        <div className="grid-2">
          <label className="field"><span>Vendor name</span><input value={v.name} onChange={set('name')} autoFocus /></label>
          <label className="field"><span>Category</span><select value={v.category} onChange={set('category')}>{CATEGORIES.map((c) => <option key={c}>{c}</option>)}</select></label>
          <label className="field"><span>Contact person</span><input value={v.contact_person} onChange={set('contact_person')} /></label>
          <label className="field"><span>Phone</span><input value={v.phone} onChange={set('phone')} inputMode="tel" /></label>
          <label className="field"><span>Email</span><input value={v.email} onChange={set('email')} type="email" /></label>
          <label className="field"><span>Website or Instagram</span><input value={v.website} onChange={set('website')} /></label>
          <label className="field"><span>Total cost (₹)</span><input type="number" min="0" value={v.total_cost} onChange={set('total_cost')} /></label>
          <label className="field"><span>Paid so far (₹)</span><input type="number" min="0" value={v.amount_paid} onChange={set('amount_paid')} /></label>
          <label className="field"><span>Status</span><select value={v.status} onChange={set('status')}>{VENDOR_STATUS.map((c) => <option key={c}>{c}</option>)}</select></label>
        </div>
        <fieldset className="field-group">
          <legend>Working on</legend>
          <div className="checks">{config.events.map((e) => <label key={e.id} className="check"><input type="checkbox" checked={v.event_ids.includes(e.id)} onChange={() => toggle(e.id)} /> {e.name}</label>)}</div>
        </fieldset>
        <label className="field"><span>Notes</span><textarea rows={3} value={v.notes} onChange={set('notes')} placeholder="Arrival time, package details, payment dates" /></label>
        {err && <p className="error" role="alert">{err}</p>}
        <div className="form-actions"><button className="btn btn-rani">Save vendor</button><button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button></div>
      </form>
    </Modal>
  )
}

