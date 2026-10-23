/** Shared API base URL. Feature API modules (api/*.ts) import from here.
 *
 * The engine serves the UI itself (desktop window and Linux server alike), so the API lives on
 * the same origin as the page. Only the Vite dev server (npm run dev, port 5173) talks to the
 * engine's own port.
 */
const VITE_DEV_PORT = '5173';

export const API_BASE =
  typeof window === 'undefined' || !window.location.protocol.startsWith('http') || window.location.port === VITE_DEV_PORT
    ? 'http://127.0.0.1:8765/api'
    : `${window.location.origin}/api`;
