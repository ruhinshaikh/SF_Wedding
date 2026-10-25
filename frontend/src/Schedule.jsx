import { useEffect, useState } from 'react'
import { api, dayParts, fmtDateLong } from './api.js'

// Public page: every event with its date, time and place. No invitation or login needed.
export default function Schedule() {
  const [config, setConfig] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    api.config().then(setConfig).catch((e) => setError(e.message))
  }, [])

  if (error) return <main className="narrow center-page"><p className="error">{error}</p></main>
  if (!config) return <main className="narrow center-page muted">Loading…</main>

  const events = [...config.events].sort((a, b) => (a.date + (a.sort || '')).localeCompare(b.date + (b.sort || '')))
  return (
    <main className="narrow schedule">
      <header className="schedule-head">
        <p className="muted small">{config.couple.hosted_by}</p>
        <h1 className="display">{config.couple.title}</h1>
        <p className="muted">The celebrations, day by day</p>
      </header>
      <ol className="schedule-list">
        {events.map((e) => {
          const d = dayParts(e.date)
          const place = [e.venue, e.address].filter(Boolean).join(', ')
          return (
            <li key={e.id} className="schedule-item">
              <div className="schedule-date" aria-hidden="true">
                <strong>{d.day}</strong>
                <span>{d.month}</span>
              </div>
              <div>
                <h2 className="display h3">{e.name}</h2>
                <p>{fmtDateLong(e.date)}{e.time ? `, ${e.time}` : ''}</p>
                <p>{place || <span className="muted">Venue to be announced</span>}</p>
                {e.dress_code && <p className="muted small">Dress code: {e.dress_code}</p>}
                {e.map_url && (
                  <a className="link-btn" href={e.map_url} target="_blank" rel="noreferrer">Open in Google Maps</a>
                )}
              </div>
            </li>
          )
        })}
      </ol>
      <p className="muted small center">Have a personal invitation link? Open it to reply.</p>
    </main>
  )
}
