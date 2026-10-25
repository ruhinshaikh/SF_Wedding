import { useEffect, useMemo, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api, dayParts, fmtDateLong } from './api.js'

const emptySong = () => ({ title: '', link: '' })

export default function Invite() {
  const { token } = useParams()
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.invite(token).then(setData).catch((e) => setError(e.message))
  }, [token])

  if (error)
    return (
      <main className="narrow center-page">
        <h1 className="display">We can't find this invitation</h1>
        <p className="muted">Check that the whole link was copied, or ask the family to send it again.</p>
      </main>
    )
  if (!data) return <main className="narrow center-page muted">Loading your invitation…</main>

  return <InviteBody token={token} data={data} />
}

/* Shows the invitation with a sample guest so it can be seen without adding anyone. Saves nothing. */
export function Preview() {
  const [config, setConfig] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    api.config().then(setConfig).catch((e) => setError(e.message))
  }, [])

  if (error)
    return (
      <main className="narrow center-page">
        <h1 className="display">The preview can't load</h1>
        <p className="muted">Start the backend (uvicorn on port 8000), then refresh this page. Details: {error}</p>
      </main>
    )
  if (!config) return <main className="narrow center-page muted">Loading the preview…</main>

  const data = {
    guest: { name: 'Asha Rao', max_party: 3, events: config.events.map((e) => e.id), offer_stay: true },
    config,
    rsvp: null,
  }
  return <InviteBody token="preview" data={data} preview />
}

/* Open invitation for the Nikkah: no personal link, no reply form. Anyone with the address can see it. */
export function NikkahPublic() {
  const [config, setConfig] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    api.config().then(setConfig).catch((e) => setError(e.message))
  }, [])
  if (error) return <main className="narrow center-page"><p className="error">{error}</p></main>
  if (!config) return <main className="narrow center-page muted">Loading…</main>

  const { couple } = config
  const e = config.events.find((x) => x.id === 'nikkah') || config.events.find((x) => x.id === couple.featured_event)
  if (!e) return <main className="narrow center-page muted">The Nikkah details are not ready yet.</main>
  const d = dayParts(e.date)
  return (
    <>
      <Hero couple={couple} featured={e} publicPage />
      <main>
        <section className="narrow section" aria-labelledby="nk-h">
          <h2 id="nk-h" className="display h2">Where we'll be</h2>
          <p className="muted lead">{couple.hosted_by} invite you to join the celebration.</p>
          <ol className="events">
            <li className="event">
              <div className="event-date" aria-hidden="true">
                <span className="event-day">{d.day}</span>
                <span className="event-month">{d.month}</span>
              </div>
              <div>
                <h3 className="event-name">{e.name}</h3>
                <p className="event-when">{d.weekday}{e.time ? `, ${e.time}` : ''}</p>
                <p>
                  {e.venue}{e.address ? `, ${e.address}` : ''}
                  {e.map_url && (<>{' '}<a href={e.map_url} target="_blank" rel="noreferrer">Open in Maps</a></>)}
                </p>
                {e.dress_code && <p className="muted small">Dress: {e.dress_code}</p>}
                {e.map_url && (
                  <div className="qr-card">
                    <img src="/nikkah-qr.png" alt={`QR code for the ${e.name} location`} width="160" height="160" />
                    <div>
                      <a className="btn btn-gold" href={e.map_url} target="_blank" rel="noreferrer">Get directions</a>
                      <p className="muted small">Or scan the code to open the location in Maps.</p>
                    </div>
                  </div>
                )}
              </div>
            </li>
          </ol>
          <p className="muted small">Looking for the other celebrations? <a href="/events">See the full schedule</a>.</p>
        </section>
      </main>
      <footer className="footer">With love, {couple.title}</footer>
    </>
  )
}

export function InviteBody({ token, data, preview = false }) {
  const { guest, config, rsvp: existing } = data
  const { couple, events } = config
  const firstName = guest.name.split(' ')[0]
  // tell the couple this guest is looking at the invitation (only while the tab is visible)
  useEffect(() => {
    if (preview) return
    const t = setInterval(() => document.visibilityState === 'visible' && api.ping(token), 60000)
    return () => clearInterval(t)
  }, [token, preview])
  const [answers, setAnswers] = useState(() =>
    Object.fromEntries(
      events.map((e) => {
        const prev = existing?.events?.[e.id]
        return [e.id, { attending: prev ? prev.attending : null, headcount: prev?.headcount || 1, food: prev?.food || {} }]
      }),
    ),
  )
  const setAnswer = (id, patch) => setAnswers((a) => ({ ...a, [id]: { ...a[id], ...patch } }))

  return (
    <>
      {preview && (
        <div className="preview-bar" role="note">
          Preview with a sample guest. Nothing you enter here is saved.
        </div>
      )}
      <Hero couple={couple} featured={events.find((e) => e.id === couple.featured_event)} guestName={guest.name} />

      <main>
        <section className="narrow section" aria-labelledby="events-h">
          <h2 id="events-h" className="display h2">Where we'll be</h2>
          <p className="muted lead">{couple.welcome_note}</p>
          <ol className="events">
            {events.map((e, i) => (
              <EventRow key={e.id} e={e} index={i} couple={couple.title} answer={answers[e.id]} setAnswer={setAnswer} maxParty={guest.max_party} foodOptions={config.food_options || []} />
            ))}
          </ol>
        </section>

        <section id="rsvp" className="band">
          <div className="narrow section">
            <h2 className="display h2">Will you join us, {firstName}?</h2>
            <RsvpForm token={token} guest={guest} config={config} existing={existing} preview={preview} answers={answers} />
          </div>
        </section>

      </main>
      <footer className="footer">With love, {couple.title}</footer>
    </>
  )
}

/* ---------- hero: arch photo, sparkles, countdown ---------- */

// Fixed positions so the sparkles look scattered but render the same every time.
const SPARKS = Array.from({ length: 16 }, (_, i) => ({
  x: (i * 37) % 100,
  delay: ((i * 0.9) % 7).toFixed(1),
  dur: 8 + ((i * 1.3) % 6),
  size: 3 + (i % 4),
}))

function Sparkles() {
  return (
    <div className="sparks" aria-hidden="true">
      {SPARKS.map((s, i) => (
        <span key={i} style={{ '--x': `${s.x}%`, '--d': `${s.delay}s`, '--t': `${s.dur}s`, '--s': `${s.size}px` }} />
      ))}
    </div>
  )
}

function Hero({ couple, featured, guestName, publicPage = false }) {
  return (
    <header className="hero">
      <Sparkles />
      <p className="basmala" lang="ar" dir="rtl">
        بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ
      </p>
      <p className="hero-tagline">{couple.tagline}</p>
      {couple.hero_photo && (
        <div className="arch">
          <img src={couple.hero_photo} alt={`Portrait of ${couple.title}`} />
        </div>
      )}
      <h1 className="hero-names">{couple.title}</h1>
      {featured && (
        <>
          <p className="hero-occasion">on the occasion of their {featured.name}</p>
          <p className="hero-date">{fmtDateLong(featured.date)}</p>
          <p className="hero-place">{featured.venue}</p>
          <Countdown target={featured.date} label={`until the ${featured.name}`} />
        </>
      )}
      {!publicPage && <p className="hero-greeting">Dear {guestName},</p>}
      {!publicPage && (
        <a className="btn btn-gold hero-cta" href="#rsvp">
          Reply to this invitation
        </a>
      )}
    </header>
  )
}

function Countdown({ target, label }) {
  const end = useMemo(() => new Date(`${target}T00:00:00`).getTime(), [target])
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])

  const secs = Math.floor((end - now) / 1000)
  if (secs <= 0) return null
  const parts = [
    ['days', Math.floor(secs / 86400)],
    ['hours', Math.floor((secs % 86400) / 3600)],
    ['minutes', Math.floor((secs % 3600) / 60)],
    ['seconds', secs % 60],
  ]
  return (
    <div className="countdown" role="timer" aria-label={`${parts[0][1]} days ${label}`}>
      {parts.map(([name, n]) => (
        <div className="cd-unit" key={name}>
          {/* key={n} remounts the number each time it changes, which replays the small tick animation */}
          <span className="cd-num" key={n} aria-hidden="true">
            {String(n).padStart(2, '0')}
          </span>
          <span className="cd-label">{name}</span>
        </div>
      ))}
      <p className="cd-caption">{label}</p>
    </div>
  )
}

function useReveal() {
  const ref = useRef(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          el.classList.add('in')
          io.disconnect()
        }
      },
      { threshold: 0.15 },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [])
  return ref
}

function EventReply({ e, a, setAnswer, maxParty, foodOptions = [] }) {
  const food = a.food || {}
  const head = a.headcount || 1
  const toggle = (o) => {
    const n = { ...food }
    if (n[o]) delete n[o]
    else n[o] = Object.keys(food).length ? 1 : head
    setAnswer(e.id, { food: n })
  }
  return (
    <div className="reply-side" role="group" aria-label={`Your reply for the ${e.name}`}>
      <p className="reply-title">Will you be there?</p>
      <div className="choice-col" role="radiogroup" aria-label={`Attending ${e.name}`}>
        <Choice checked={a.attending === true} onClick={() => setAnswer(e.id, { attending: true })}>
          Yes, I'll be there
        </Choice>
        <Choice checked={a.attending === false} onClick={() => setAnswer(e.id, { attending: false })}>
          Can't make it
        </Choice>
      </div>
      {a.attending && maxParty > 1 && (
        <label className="inline-field">
          <span>How many will attend?</span>
          <select value={a.headcount} onChange={(ev) => setAnswer(e.id, { headcount: Number(ev.target.value) })}>
            {Array.from({ length: maxParty }, (_, i) => i + 1).map((n) => (
              <option key={n} value={n}>
                {n} {n === 1 ? 'guest' : 'guests'}
              </option>
            ))}
          </select>
        </label>
      )}
      {a.attending && foodOptions.length > 0 && (
        <div className="food-opts">
          <p className="reply-title">Food for this one</p>
          {foodOptions.map((o) => (
            <div key={o} className="food-opt">
              <label className="check">
                <input type="checkbox" checked={!!food[o]} onChange={() => toggle(o)} /> {o}
              </label>
              {food[o] && head > 1 && (
                <label className="food-n">
                  <input type="number" min="1" max={head} value={Math.min(food[o], head)} onChange={(ev) => setAnswer(e.id, { food: { ...food, [o]: Math.max(1, Math.min(head, Number(ev.target.value) || 1)) } })} />
                  <span>{food[o] === 1 ? 'person' : 'people'}</span>
                </label>
              )}
            </div>
          ))}
        </div>
      )}
      <p className="muted small">Then send your reply at the bottom of the page.</p>
    </div>
  )
}

function EventRow({ e, index, couple, answer, setAnswer, maxParty, foodOptions }) {
  const ref = useReveal()
  const d = dayParts(e.date)

  // Events with an animated invitation show only that, with a link to the map underneath.
  if (e.film) {
    const src =
      `/films/${e.film}/index.html?` +
      new URLSearchParams({ date: e.date, time: e.time || '', venue: e.venue || '', dress: e.dress_code ? `Dress code: ${e.dress_code}` : '', couple }).toString()
    return (
      <li ref={ref} className="event-film reveal" style={{ '--i': index % 4 }}>
        <h3 className="film-title">{e.name}</h3>
        <p className="film-sub">
          {d.weekday}, {d.day} {d.month}
          {e.time ? ` \u00b7 ${e.time}` : ''}
        </p>
        <div className="film-row">
          <iframe className="film-frame" src={src} title={`${e.name} invitation`} loading="lazy" allow="autoplay" />
          <EventReply e={e} a={answer} setAnswer={setAnswer} maxParty={maxParty} foodOptions={foodOptions} />
        </div>
        {(e.map_url || e.address) && (
          <p className="small">
            {e.address}
            {e.map_url && (
              <>
                {e.address ? ' ' : ''}
                <a href={e.map_url} target="_blank" rel="noreferrer">Open {e.name} in Maps</a>
              </>
            )}
          </p>
        )}
      </li>
    )
  }

  return (
    <li ref={ref} className="event reveal" style={{ '--i': index % 4 }}>
      <div className="event-date" aria-hidden="true">
        <span className="event-day">{d.day}</span>
        <span className="event-month">{d.month}</span>
      </div>
      <div>
        <h3 className="event-name">{e.name}</h3>
        <p className="event-when">
          {d.weekday}
          {e.time ? `, ${e.time}` : ''}
        </p>
        <p>
          {e.venue}
          {e.address ? `, ${e.address}` : ''}
          {e.map_url && (
            <>
              {' '}
              <a href={e.map_url} target="_blank" rel="noreferrer">
                Open in Maps
              </a>
            </>
          )}
        </p>
        {e.dress_code && <p className="muted small">Dress: {e.dress_code}</p>}
        <EventReply e={e} a={answer} setAnswer={setAnswer} maxParty={maxParty} foodOptions={foodOptions} />
      </div>
    </li>
  )
}

function RsvpForm({ token, guest, config, existing, preview, answers }) {
  const events = config.events
  const sangeet = events.find((e) => e.is_sangeet)

  const [dietary, setDietary] = useState(existing?.dietary || '')
  const [needsStay, setNeedsStay] = useState(existing ? !!existing.needs_stay : null)
  const [stayGuests, setStayGuests] = useState(existing?.stay_guests || guest.max_party)
  const [stayNotes, setStayNotes] = useState(existing?.stay_notes || '')
  const [message, setMessage] = useState(existing?.message || '')
  const [wantsDance, setWantsDance] = useState(existing ? (sangeet ? existing.wants_to_dance : null) : null)
  const [danceType, setDanceType] = useState(existing?.dance_type || '')
  const [danceWith, setDanceWith] = useState(existing?.dance_with || '')
  const [danceNotes, setDanceNotes] = useState(existing?.dance_notes || '')
  const [songs, setSongs] = useState(existing?.songs?.length ? existing.songs : [emptySong()])
  const [status, setStatus] = useState(existing ? 'saved' : 'idle') // idle | sending | saved
  const [error, setError] = useState('')
  const errRef = useRef(null)

  const sangeetAttending = !!sangeet && answers[sangeet.id]?.attending === true
  const anyAttending = Object.values(answers).some((a) => a.attending)

  // Changing an answer up in the invitations reopens the form so it can be sent again.
  const firstRender = useRef(true)
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false
      return
    }
    setStatus((st) => (st === 'saved' ? 'idle' : st))
  }, [answers])
  const setSong = (i, patch) => setSongs((s) => s.map((x, idx) => (idx === i ? { ...x, ...patch } : x)))

  async function submit(ev) {
    ev.preventDefault()
    setError('')
    const unanswered = events.find((e) => answers[e.id].attending === null)
    if (unanswered) return fail(`Please tell us if you can make the ${unanswered.name}.`)
    if (sangeetAttending && wantsDance === null) return fail('Please tell us if you want to dance at the Sangeet.')
    if (anyAttending && guest.offer_stay && needsStay === null) return fail('Please tell us if you will need a place to stay.')
    const filled = songs.filter((s) => s.title.trim() || s.link.trim())
    if (sangeetAttending && wantsDance && filled.length === 0)
      return fail('Add at least one song, either a link or a title.')
    if (sangeetAttending && wantsDance && filled.some((s) => s.link.trim() && !/^https?:\/\//i.test(s.link.trim())))
      return fail('Song links need to start with http:// or https://')

    if (preview) {
      setStatus('saved')
      return
    }
    setStatus('sending')
    try {
      await api.rsvp(token, {
        events: Object.fromEntries(
          events.map((e) => [e.id, { attending: answers[e.id].attending, headcount: answers[e.id].attending ? answers[e.id].headcount : 0, food: answers[e.id].attending ? answers[e.id].food || {} : {} }]),
        ),
        dietary: anyAttending ? dietary : '',
        needs_stay: anyAttending && needsStay === true,
        stay_guests: anyAttending && needsStay === true ? stayGuests : 0,
        stay_notes: anyAttending && needsStay === true ? stayNotes : '',
        message,
        wants_to_dance: sangeetAttending && wantsDance === true,
        dance_type: danceType,
        dance_with: danceType === 'solo' ? '' : danceWith,
        dance_notes: danceNotes,
        songs: filled,
      })
      setStatus('saved')
    } catch (e) {
      fail(e.message)
    }
  }
  function fail(msg) {
    setError(msg)
    setStatus('idle')
    setTimeout(() => errRef.current?.focus(), 0)
  }

  return (
    <form onSubmit={submit} className="form" noValidate>
      {existing && status !== 'saved' && (
        <p className="notice">You've already replied. Change anything below and send it again.</p>
      )}

      <ul className="reply-summary" aria-label="Your answers so far">
        {events.map((e) => {
          const a = answers[e.id]
          return (
            <li key={e.id}>
              <strong>{e.name}</strong>
              <span className={a.attending === null ? 'muted' : ''}>
                {a.attending === null
                  ? 'Choose Yes or No next to the invitation above'
                  : a.attending
                    ? `Yes, ${a.headcount} ${a.headcount === 1 ? 'guest' : 'guests'}`
                    : "Can't make it"}
              </span>
            </li>
          )
        })}
      </ul>

      {sangeetAttending && (
        <fieldset className="field-group sangeet">
          <legend>Sangeet dance floor</legend>
          <p className="muted">Want to perform, or have a dance planned with family or friends?</p>
          <div className="choice-row" role="radiogroup" aria-label="Dance at the Sangeet">
            <Choice checked={wantsDance === true} onClick={() => setWantsDance(true)}>
              Yes, I'd like to dance
            </Choice>
            <Choice checked={wantsDance === false} onClick={() => setWantsDance(false)}>
              Just here to cheer
            </Choice>
          </div>

          {wantsDance === true && (
            <div className="stack">
              <div>
                <p className="label">What kind of dance is it? <span className="muted small">(optional)</span></p>
                <div className="choice-row" role="radiogroup" aria-label="Kind of dance">
                  <Choice checked={danceType === 'solo'} onClick={() => setDanceType('solo')}>Solo</Choice>
                  <Choice checked={danceType === 'couple'} onClick={() => setDanceType('couple')}>Couple</Choice>
                  <Choice checked={danceType === 'group'} onClick={() => setDanceType('group')}>Group</Choice>
                </div>
              </div>
              {(danceType === 'couple' || danceType === 'group') && (
                <label className="field">
                  <span>{danceType === 'couple' ? "Who's your partner?" : "Who's in your group?"}</span>
                  <input value={danceWith} onChange={(e) => setDanceWith(e.target.value)} placeholder={danceType === 'couple' ? 'Their name' : 'Names of everyone dancing'} maxLength={300} />
                </label>
              )}

              <div>
                <p className="label">Songs for your dance</p>
                <p className="muted small">Paste a YouTube, Spotify or any music link. Add a title if you like.</p>
                {songs.map((s, i) => (
                  <div className="song-row" key={i}>
                    <input aria-label={`Song ${i + 1} title`} value={s.title} onChange={(e) => setSong(i, { title: e.target.value })} placeholder="Song title" maxLength={200} />
                    <input aria-label={`Song ${i + 1} link`} value={s.link} onChange={(e) => setSong(i, { link: e.target.value })} placeholder="https://…" inputMode="url" maxLength={500} />
                    {songs.length > 1 && (
                      <button type="button" className="icon-btn" onClick={() => setSongs(songs.filter((_, idx) => idx !== i))} aria-label={`Remove song ${i + 1}`}>
                        ×
                      </button>
                    )}
                  </div>
                ))}
                {songs.length < 5 && (
                  <button type="button" className="link-btn" onClick={() => setSongs([...songs, emptySong()])}>
                    Add another song
                  </button>
                )}
              </div>

              <label className="field">
                <span>Anything the DJ should know?</span>
                <textarea value={danceNotes} onChange={(e) => setDanceNotes(e.target.value)} rows={2} placeholder="Which part of the song to play, how long you need" maxLength={1000} />
              </label>
            </div>
          )}
        </fieldset>
      )}

      {anyAttending && (
        <fieldset className="field-group">
          <legend>Allergies</legend>
          <label className="field">
            <span>Allergies or anything else</span>
            <textarea value={dietary} onChange={(e) => setDietary(e.target.value)} rows={2} placeholder="Nut allergy, no onion or garlic…" maxLength={1000} />
          </label>
        </fieldset>
      )}

      {anyAttending && guest.offer_stay && (
        <fieldset className="field-group">
          <legend>A place to stay</legend>
          <p className="muted">Will you need accommodation during the celebrations?</p>
          <div className="choice-row" role="radiogroup" aria-label="Need a place to stay">
            <Choice checked={needsStay === true} onClick={() => setNeedsStay(true)}>
              Yes, please arrange a stay
            </Choice>
            <Choice checked={needsStay === false} onClick={() => setNeedsStay(false)}>
              No, I have it covered
            </Choice>
          </div>
          {needsStay === true && (
            <div className="stack">
              {guest.max_party > 1 && (
                <label className="inline-field">
                  <span>How many people need a room?</span>
                  <select value={stayGuests} onChange={(e) => setStayGuests(Number(e.target.value))}>
                    {Array.from({ length: guest.max_party }, (_, i) => i + 1).map((n) => (
                      <option key={n} value={n}>
                        {n} {n === 1 ? 'person' : 'people'}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <label className="field">
                <span>Arrival and departure dates, and anything we should know</span>
                <textarea value={stayNotes} onChange={(e) => setStayNotes(e.target.value)} rows={2} placeholder="Arriving 21 Dec evening, leaving 26 Dec. Ground floor please." maxLength={1000} />
              </label>
            </div>
          )}
        </fieldset>
      )}

      <label className="field">
        <span>A note for the couple (optional)</span>
        <textarea value={message} onChange={(e) => setMessage(e.target.value)} rows={3} maxLength={2000} />
      </label>

      {error && (
        <p className="error" role="alert" tabIndex={-1} ref={errRef}>
          {error}
        </p>
      )}

      <div className="form-actions">
        <button className="btn btn-rani" disabled={status === 'sending'}>
          {status === 'sending' ? 'Sending…' : existing ? 'Update reply' : 'Send reply'}
        </button>
        {status === 'saved' && anyAttending && <GroupJoin token={token} preview={preview} answers={answers} />}
        {status === 'saved' && (
          <p className="success" role="status">
            {anyAttending ? "Thank you, we've got your reply and can't wait to see you." : "Thank you for letting us know. We'll miss you."}
            {preview && ' (Preview only, nothing was saved.)'}
          </p>
        )}
      </div>
    </form>
  )
}

function GroupJoin({ token, preview, answers }) {
  const [groups, setGroups] = useState(null)
  const going = Object.keys(answers).filter((id) => answers[id].attending).join(',')

  useEffect(() => {
    if (preview) {
      setGroups([{ id: 'sample', name: "Simran & Farhan's wedding", url: '#' }])
      return
    }
    let live = true
    api.inviteGroups(token).then((r) => live && setGroups(r.groups)).catch(() => live && setGroups([]))
    return () => {
      live = false
    }
  }, [token, preview, going])

  if (!groups || groups.length === 0) return null
  return (
    <div className="group-join">
      <p className="group-join-title">Join our WhatsApp {groups.length > 1 ? 'groups' : 'group'}</p>
      <p className="muted small">That's where we'll share updates, timings and photos.</p>
      <div className="row-actions">
        {groups.map((g) => (
          <a key={g.id} className="btn btn-wa" href={g.url} target="_blank" rel="noopener noreferrer" onClick={preview ? (e) => e.preventDefault() : undefined}>
            Join {g.name}
          </a>
        ))}
      </div>
    </div>
  )
}

function Choice({ checked, onClick, children }) {
  return (
    <button type="button" role="radio" aria-checked={checked} className={`choice ${checked ? 'on' : ''}`} onClick={onClick}>
      {children}
    </button>
  )
}

