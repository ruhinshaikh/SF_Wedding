import { useState } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { adminToken, api, guestToken, isLoggedIn } from './api.js'

// Only same-site paths may be used as the "go back to" address.
const safeNext = (n) => (n && n.startsWith('/') && !n.startsWith('//') && !n.startsWith('/login') ? n : '/')

// Home page and /login: guests sign in with their mobile number, the family signs in to the dashboard.
export default function Login() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const next = safeNext(params.get('next'))
  const [mode, setMode] = useState(params.get('as') === 'admin' ? 'admin' : 'guest')
  const [phone, setPhone] = useState('')
  const [password, setPassword] = useState('')
  const [usePassword, setUsePassword] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  if (mode === 'guest' && isLoggedIn() && next !== '/') return <Navigate to={next} replace />

  function switchTo(m) {
    setMode(m)
    setError('')
  }

  async function guestSubmit(e) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const r = await api.guestLogin(phone)
      guestToken.set(r.token, r.invites)
      if (r.admin_token) adminToken.set(r.admin_token)
      // straight to their invitation when there is just one
      const dest = next !== '/' ? next : r.invites.length === 1 ? `/i/${r.invites[0].token}` : '/'
      window.location.assign(dest)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function adminSubmit(e) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      if (usePassword) {
        const { token } = await api.login(password, phone)
        adminToken.set(token)
      } else {
        // admins are guests too: their mobile number logs them in to both
        const r = await api.guestLogin(phone)
        if (!r.admin_token) throw new Error("This number isn't set up as an admin. Ask an admin to tick \"Admin\" on your guest entry, or use the admin password.")
        guestToken.set(r.token, r.invites)
        adminToken.set(r.admin_token)
      }
      navigate('/admin', { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="narrow center-page login-page">
      <p className="login-kicker">Welcome to the wedding of</p>
      <h1 className="display">Simran &amp; Farhan</h1>

      <div className="login-switch" role="tablist" aria-label="Log in as">
        <button type="button" role="tab" aria-selected={mode === 'guest'} className={mode === 'guest' ? 'on' : ''} onClick={() => switchTo('guest')}>
          Guest
        </button>
        <button type="button" role="tab" aria-selected={mode === 'admin'} className={mode === 'admin' ? 'on' : ''} onClick={() => switchTo('admin')}>
          Admin
        </button>
      </div>

      {mode === 'guest' ? (
        <form className="stack" onSubmit={guestSubmit} key="guest">
          <p className="muted">Log in with the mobile number your invitation was sent to.</p>
          <label className="field">
            <span>Mobile number</span>
            <input type="tel" inputMode="tel" autoComplete="tel" placeholder="e.g. 98765 43210" value={phone} onChange={(e) => setPhone(e.target.value)} required />
          </label>
          {error && <p className="error" role="alert">{error}</p>}
          <button className="btn btn-rani" disabled={busy || phone.replace(/\D/g, '').length < 10}>{busy ? 'Checking…' : 'Log in'}</button>
        </form>
      ) : (
        <form className="stack" onSubmit={adminSubmit} key="admin">
          <p className="muted">For the family: manage guests, replies, dances and vendors.</p>
          <label className="field">
            <span>Your mobile number</span>
            <input type="tel" inputMode="tel" autoComplete="tel" placeholder="e.g. 98765 43210" value={phone} onChange={(e) => setPhone(e.target.value)} required />
          </label>
          {usePassword && (
            <label className="field">
              <span>Admin password</span>
              <input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
            </label>
          )}
          {error && <p className="error" role="alert">{error}</p>}
          <button className="btn btn-rani" disabled={busy || phone.replace(/\D/g, '').length < 10 || (usePassword && !password)}>{busy ? 'Checking…' : 'Open the dashboard'}</button>
          <button type="button" className="link-btn" onClick={() => { setUsePassword((u) => !u); setError('') }}>
            {usePassword ? 'Log in with just your mobile number instead' : 'Use the admin password instead'}
          </button>
        </form>
      )}

      <p className="muted small login-public">
        Just want to see the invitations? <a href="/invite">Watch them here</a>
      </p>
    </main>
  )
}
