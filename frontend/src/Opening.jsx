import { useEffect, useState } from 'react'
import { audio, musicOff, playMusic } from './music.js'

// Opening screen for /invite and /nikkah so the song starts with the invitation.
// Browsers block sound until the visitor taps, so: if the song can start on its own we skip straight in,
// otherwise one tap on "Open the invitation" starts the music and shows the page.
export default function Opening({ children }) {
  const [state, setState] = useState(() => (musicOff() || !audio || !audio.paused ? 'open' : 'checking'))

  useEffect(() => {
    if (state !== 'checking') return
    playMusic().then(() => setState('open')).catch(() => setState('closed'))
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  if (state === 'open') return children
  if (state === 'checking') return <main className="opening" aria-busy="true" />

  function open() {
    playMusic().catch(() => {})
    setState('open')
  }

  return (
    <main className="opening">
      <button type="button" className="opening-card" onClick={open}>
        <span className="opening-kicker">You are invited</span>
        <span className="opening-names">Simran &amp; Farhan</span>
        <span className="opening-cta">Tap to open the invitation</span>
        <span className="opening-note">with music ♪</span>
      </button>
    </main>
  )
}
