import React, { Suspense, lazy, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { adminToken, guestToken, isLoggedIn } from './api.js'
import Login from './Login.jsx'
import Invite, { NikkahPublic, Preview } from './Invite.jsx'
// loaded only when needed, so guests don't download the admin screens
const Admin = lazy(() => import('./Admin.jsx'))
const Schedule = lazy(() => import('./Schedule.jsx'))
const Carousel = lazy(() => import('./Carousel.jsx'))
import Music from './Music.jsx'
import SiteNav from './SiteNav.jsx'
import Opening from './Opening.jsx'
import './styles.css'

function Landing() {
  const invites = guestToken.invites()
  return (
    <main className="narrow center-page">
      <h1 className="display">Simran &amp; Farhan</h1>
      <p className="muted lead">Welcome. Here is everything for the celebrations.</p>
      <ul className="stack landing-links">
        {invites.map((i) => (
          <li key={i.token}>
            <a className="btn btn-rani" href={`/i/${i.token}`}>Open the invitation{invites.length > 1 ? ` for ${i.name}` : ''}</a>
          </li>
        ))}
        {adminToken.get() && <li><a className="btn btn-ghost" href="/admin">Open the dashboard</a></li>}
        <li><a className="link-btn" href="/events">All events, dates and places</a></li>
        <li><a className="link-btn" href="/nikkah">The Nikkah invitation</a></li>
        <li>
          <button className="link-btn" onClick={() => { guestToken.clear(); adminToken.clear(); window.location.assign('/login') }}>Log out</button>
        </li>
      </ul>
    </main>
  )
}

// The home page shows the login (guest or admin) until someone is logged in.
function Home() {
  const [, bump] = useState(0)
  useEffect(() => {
    const f = () => bump((n) => n + 1)
    window.addEventListener('guest-logout', f)
    return () => window.removeEventListener('guest-logout', f)
  }, [])
  return guestToken.get() ? <Landing /> : <Login />
}

// Every guest-facing page sits behind the mobile-number login (the admin's own login also works).
function RequireLogin({ children }) {
  const location = useLocation()
  const [, bump] = useState(0)
  useEffect(() => {
    const f = () => bump((n) => n + 1)
    window.addEventListener('guest-logout', f)
    return () => window.removeEventListener('guest-logout', f)
  }, [])
  if (!isLoggedIn()) return <Navigate to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`} replace />
  return children
}

createRoot(document.getElementById('root')).render(
  <BrowserRouter>
    <Music />
    <SiteNav />
    <Suspense fallback={<main className="narrow center-page muted">Loading…</main>}>
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<Home />} />
      <Route path="/i/:token" element={<RequireLogin><Invite /></RequireLogin>} />
      <Route path="/nikkah" element={<Opening><NikkahPublic /></Opening>} />
      <Route path="/invite" element={<Opening><Carousel /></Opening>} />
      <Route path="/events" element={<RequireLogin><Schedule /></RequireLogin>} />
      <Route path="/schedule" element={<RequireLogin><Schedule /></RequireLogin>} />
      <Route path="/preview" element={<RequireLogin><Preview /></RequireLogin>} />
      <Route path="/admin/*" element={<Admin />} />
      <Route path="*" element={<RequireLogin><Landing /></RequireLogin>} />
    </Routes>
    </Suspense>
  </BrowserRouter>,
)
