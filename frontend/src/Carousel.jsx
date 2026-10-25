import { useCallback, useEffect, useRef, useState } from 'react'
import { api, fmtDateLong } from './api.js'

// Public page, no login: every event's invitation, one after another.
const FILM_SECONDS = 15 // the animated invitations finish their intro in about 14 seconds
const CARD_SECONDS = 10

const filmSrc = (e, couple) =>
  `/films/${e.film}/index.html?` +
  new URLSearchParams({ date: e.date, time: e.time || '', venue: e.venue || '', dress: e.dress_code ? `Dress code: ${e.dress_code}` : '', couple }).toString()

function NikkahCard({ e, couple }) {
  return (
    <div className="slide-card">
      <p className="basmala" lang="ar" dir="rtl">بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ</p>
      <p className="slide-tag">{couple.tagline}</p>
      {couple.hero_photo && (
        <div className="arch slide-arch">
          <img src={couple.hero_photo} alt={`Portrait of ${couple.title}`} />
        </div>
      )}
      <h2 className="slide-names">{couple.title}</h2>
      <p className="slide-occasion">on the occasion of their {e.name}</p>
      <p className="slide-date">{fmtDateLong(e.date)}{e.time ? `, ${e.time}` : ''}</p>
      <p className="slide-place">{[e.venue, e.address].filter(Boolean).join(', ')}</p>
      {e.map_url && (
        <a className="btn btn-gold" href={e.map_url} target="_blank" rel="noreferrer">Get directions</a>
      )}
    </div>
  )
}

export default function Carousel() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [i, setI] = useState(0)
  const [playing, setPlaying] = useState(() => !window.matchMedia?.('(prefers-reduced-motion: reduce)').matches)
  const touch = useRef(null)

  useEffect(() => {
    api.publicInvite().then(setData).catch((e) => setError(e.message))
  }, [])

  const events = data ? [...data.events].sort((a, b) => a.date.localeCompare(b.date)) : []
  const n = events.length
  const go = useCallback((k) => n && setI((x) => (x + k + n) % n), [n])

  // advance automatically; the timer restarts whenever the slide changes
  useEffect(() => {
    if (!playing || !n) return
    const t = setTimeout(() => go(1), (events[i]?.film ? FILM_SECONDS : CARD_SECONDS) * 1000)
    return () => clearTimeout(t)
  }, [i, playing, n]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const k = (ev) => {
      if (ev.key === 'ArrowRight') go(1)
      if (ev.key === 'ArrowLeft') go(-1)
    }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [go])

  if (error) return <main className="narrow center-page"><p className="error">{error}</p></main>
  if (!data) return <main className="narrow center-page muted">Loading…</main>

  const e = events[i]
  const couple = data.couple
  return (
    <main
      className="carousel"
      onTouchStart={(ev) => (touch.current = ev.touches[0].clientX)}
      onTouchEnd={(ev) => {
        if (touch.current == null) return
        const dx = ev.changedTouches[0].clientX - touch.current
        if (Math.abs(dx) > 40) go(dx < 0 ? 1 : -1)
        touch.current = null
      }}
    >
      <header className="carousel-head">
        <p className="carousel-couple">{couple.title}</p>
        <h1 className="carousel-title">{e.name}</h1>
        <p className="carousel-when">{fmtDateLong(e.date)}{e.time ? `, ${e.time}` : ''}</p>
      </header>

      <div className="carousel-stage" aria-live="polite" aria-roledescription="carousel">
        <button className="carousel-arrow prev" onClick={() => go(-1)} aria-label="Previous invitation">‹</button>
        <div className="carousel-slide" role="group" aria-roledescription="slide" aria-label={`${i + 1} of ${n}: ${e.name}`}>
          {e.film ? (
            // key makes the film start from the beginning each time its slide is shown
            <iframe key={`${e.id}-${i}`} className="carousel-frame" src={filmSrc(e, couple.title)} title={`${e.name} invitation`} allow="autoplay" />
          ) : (
            <NikkahCard e={e} couple={couple} />
          )}
        </div>
        <button className="carousel-arrow next" onClick={() => go(1)} aria-label="Next invitation">›</button>
      </div>

      <div className="carousel-controls">
        <div className="carousel-dots">
          {events.map((x, k) => (
            <button key={x.id} className={`dot ${k === i ? 'on' : ''}`} onClick={() => setI(k)} aria-label={`Show ${x.name}`} aria-current={k === i ? 'true' : undefined} />
          ))}
        </div>
        <button className="link-btn carousel-play" onClick={() => setPlaying((p) => !p)}>{playing ? 'Pause slideshow' : 'Play slideshow'}</button>
      </div>
      {e.map_url && e.film && (
        <p className="carousel-map"><a href={e.map_url} target="_blank" rel="noreferrer">Open {e.name} in Maps</a></p>
      )}
      <p className="carousel-foot">Have a personal invitation? <a href="/login">Log in to reply</a></p>
    </main>
  )
}
