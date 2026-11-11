import { useSyncExternalStore } from 'react'

/** True while the CSS media query matches; updates on resize. */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const media = window.matchMedia(query)
      media.addEventListener('change', onChange)
      return () => media.removeEventListener('change', onChange)
    },
    () => window.matchMedia(query).matches,
  )
}

/** Matches Tailwind's `lg` breakpoint (64rem = 1024px). */
export const DESKTOP_QUERY = '(min-width: 64rem)'
