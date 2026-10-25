import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { adminToken, guestToken, isLoggedIn } from './api.js'

// Back button and menu for the guest pages (bottom-left; the music button is bottom-right).
export default function SiteNav() {
  const { pathname } = useLocation()
  const [open, setOpen] = useState(false)
  const box = useRef(null)

  useEffect(() => setOpen(false), [pathname])
  useEffect(() => {
    if (!open) return
    const away = (e) => box.current && !box.current.contains(e.target) && setOpen(false)
    const esc = (e) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('pointerdown', away)
    document.addEventListener('keydown', esc)
    return () => {
      document.removeEventListener('pointerdown', away)
      document.removeEventListener('keydown', esc)
    }
  }, [open])

  if (pathname.startsWith('/admin')) return null

  const loggedIn = isLoggedIn()
  const home = loggedIn ? '/' : '/invite'
  const invites = loggedIn ? guestToken.invites() : []
  const links = loggedIn
    ? [
        ['/', 'Home'],
        ...invites.map((i) => [`/i/${i.token}`, invites.length > 1 ? `Invitation: ${i.name}` : 'My invitation and reply']),
        ['/events', 'All events, dates and places'],
        ['/invite', 'All invitations (slideshow)'],
        ['/nikkah', 'The Nikkah invitation'],
      ]
    : [
        ['/invite', 'All invitations (slideshow)'],
        ['/nikkah', 'The Nikkah invitation'],
        ['/login', 'Log in to reply'],
      ]

  function back() {
    // go back within the site when we came from it, otherwise to the main page
    let sameSite = false
    try { sameSite = !!document.referrer && new URL(document.referrer).origin === window.location.origin } catch {}
    if (sameSite && window.history.length > 1) window.history.back()
    else window.location.assign(home)
  }

  function logOut() {
    guestToken.clear()
    adminToken.clear()
    window.location.assign('/login')
  }

  return (
    <nav className="site-nav" ref={box} aria-label="Site">
      {pathname !== home && (
        <button type="button" className="nav-btn" onClick={back} aria-label="Go back">
          <span aria-hidden="true">‹</span> <span className="nav-text">Back</span>
        </button>
      )}
      <button type="button" className="nav-btn" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-controls="site-menu">
        <span aria-hidden="true">☰</span> <span className="nav-text">Menu</span>
      </button>
      {open && (
        <ul id="site-menu" className="nav-menu">
          {links.map(([href, label]) => (
            <li key={href}>
              <a href={href} aria-current={pathname === href ? 'page' : undefined}>{label}</a>
            </li>
          ))}
          {loggedIn && (
            <li><button type="button" onClick={logOut}>Log out</button></li>
          )}
        </ul>
      )}
    </nav>
  )
}
