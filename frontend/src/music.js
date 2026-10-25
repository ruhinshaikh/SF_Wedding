// One shared audio element for the background song, used by the music button and the opening screen.
const SRC = '/music/aaj-sajeya.mp3'
const OFF_KEY = 'wedding_music_off'

export const audio = typeof Audio !== 'undefined' ? new Audio(SRC) : null
if (audio) {
  audio.loop = true
  audio.volume = 0.6
  audio.preload = 'auto'
}

export const musicOff = () => {
  try { return localStorage.getItem(OFF_KEY) === '1' } catch { return false }
}
export const setMusicOff = (v) => {
  try { localStorage.setItem(OFF_KEY, v ? '1' : '0') } catch {}
}
// Resolves when sound is playing; rejects when the browser wants a tap first.
export const playMusic = () => (audio ? audio.play() : Promise.reject(new Error('no audio')))
export const pauseMusic = () => audio && audio.pause()
