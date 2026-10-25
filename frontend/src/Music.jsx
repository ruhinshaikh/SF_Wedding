import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { audio, musicOff, pauseMusic, playMusic, setMusicOff } from './music.js'

// Music button for the guest pages. Browsers only allow sound after the visitor taps or presses a key,
// so besides trying straight away it also starts on the first interaction (unless they turned it off).
export default function Music() {
  const { pathname } = useLocation()
  const [playing, setPlaying] = useState(() => !!audio && !audio.paused)
  const hidden = pathname.startsWith('/admin')

  useEffect(() => {
    if (!audio) return
    const on = () => setPlaying(true)
    const off = () => setPlaying(false)
    audio.addEventListener('play', on)
    audio.addEventListener('pause', off)
    return () => {
      audio.removeEventListener('play', on)
      audio.removeEventListener('pause', off)
    }
  }, [])

  useEffect(() => {
    if (hidden) {
      pauseMusic()
      return
    }
    const start = () => {
      if (!musicOff() && audio && audio.paused) playMusic().catch(() => {})
    }
    const events = ['pointerdown', 'keydown', 'touchstart']
    events.forEach((e) => window.addEventListener(e, start, { once: true, passive: true }))
    start()
    return () => events.forEach((e) => window.removeEventListener(e, start))
  }, [hidden])

  if (hidden || !audio) return null

  function toggle(e) {
    e.stopPropagation()
    if (audio.paused) {
      setMusicOff(false)
      playMusic().catch(() => {})
    } else {
      setMusicOff(true)
      pauseMusic()
    }
  }

  return (
    <button
      type="button"
      className={`music-btn ${playing ? 'on' : ''}`}
      onPointerDown={(e) => e.stopPropagation()}
      onClick={toggle}
      aria-pressed={playing}
      aria-label={playing ? 'Pause music' : 'Play music'}
      title={playing ? 'Pause music' : 'Play music'}
    >
      <span className="music-icon" aria-hidden="true">{playing ? '❚❚' : '♪'}</span>
      <span className="music-label">{playing ? 'Pause music' : 'Play music'}</span>
    </button>
  )
}
