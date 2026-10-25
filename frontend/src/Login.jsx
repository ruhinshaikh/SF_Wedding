import { useState } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { api, guestToken, isLoggedIn } from './api.js'

// Only same-site paths may be used as the "go back to" address.
const safeNext = (n) => (n && n.startsWith('/') && !n.startsWith('//') && !n.startsWith('/login') ? n : '/')

export default function Login() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const next = safeNext(params.get('next'))
  const [phone, setPhone] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  if (isLoggedIn()) return <Navigate to={next} replace />

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const r = await api.guestLogin(phone)
      guestToken.set(r.token, r.invites)
      navigate(next, { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="narrow center-page">
      <h1 className="display">Simran &amp; Farhan</h1>
      <p className="muted lead">Please log in with the mobile number your invitation was sent to.</p>
      <form className="stack" onSubmit={submit}>
        <label className="field">
          <span>Mobile number</span>
          <input type="tel" inputMode="tel" autoComplete="tel" autoFocus placeholder="e.g. 98765 43210" value={phone} onChange={(e) => setPhone(e.target.value)} required />
        </label>
        {error && <p className="error" role="alert">{error}</p>}
        <button className="btn btn-rani" disabled={busy || phone.replace(/\D/g, '').length < 10}>{busy ? 'Checking…' : 'Log in'}</button>
      </form>
    </main>
  )
}
