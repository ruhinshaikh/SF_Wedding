import React from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import Invite, { NikkahPublic, Preview } from './Invite.jsx'
import Admin from './Admin.jsx'
import Schedule from './Schedule.jsx'
import './styles.css'

function Landing() {
  return (
    <main className="narrow center-page">
      <h1 className="display">You'll need your personal link</h1>
      <p className="muted">
        Each invitation has its own link. Open the one sent to you on WhatsApp, or ask the family to resend it.
      </p>
      <p><a className="link-btn" href="/events">See all events, dates and places</a></p>
    </main>
  )
}

createRoot(document.getElementById('root')).render(
  <BrowserRouter>
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/i/:token" element={<Invite />} />
      <Route path="/nikkah" element={<NikkahPublic />} />
      <Route path="/events" element={<Schedule />} />
      <Route path="/schedule" element={<Schedule />} />
      <Route path="/preview" element={<Preview />} />
      <Route path="/admin/*" element={<Admin />} />
      <Route path="*" element={<Landing />} />
    </Routes>
  </BrowserRouter>,
)
