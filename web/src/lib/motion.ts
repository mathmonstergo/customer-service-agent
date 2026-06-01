import type { Transition } from 'framer-motion'

export const ease = {
  out: [0.16, 1, 0.3, 1] as const,
  inOut: [0.65, 0, 0.35, 1] as const,
}

export const dur = {
  fast: 0.12,
  base: 0.2,
  slow: 0.32,
}

export const spring: Transition = {
  type: 'spring',
  damping: 26,
  stiffness: 320,
  mass: 0.7,
}

export const fadeUp = {
  initial: { opacity: 0, y: 4 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -2 },
  transition: { duration: dur.base, ease: ease.out },
}

export const staggerList = {
  animate: {
    transition: { staggerChildren: 0.03 },
  },
}

export const drawerSlide = {
  initial: { x: 20, opacity: 0 },
  animate: { x: 0, opacity: 1 },
  exit: { x: 20, opacity: 0 },
  transition: spring,
}
