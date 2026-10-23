import type React from 'react';

/** Props that make a clickable card/row keyboard accessible (focusable, Enter/Space activates). */
export const clickableProps = (onActivate: () => void) => ({
  role: 'button' as const,
  tabIndex: 0,
  onClick: onActivate,
  onKeyDown: (e: React.KeyboardEvent) => {
    // Keys pressed on a nested button/link belong to that control
    if (e.target !== e.currentTarget) return;
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onActivate();
    }
  },
});

/** Visible keyboard focus ring for such elements. */
export const FOCUS_RING = 'focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/60';
