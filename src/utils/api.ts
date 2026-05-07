/// <reference types="vite/client" />

/**
 * Resolved base URL for all API requests.
 *
 * In development: reads VITE_API_URL from .env.local, defaulting to
 * http://localhost:5000/api when the variable is absent.
 *
 * In production (Vercel): VITE_API_URL must be set to the Flask API
 * origin (e.g. https://api.solverah.com/api or the Heroku/Render URL).
 *
 * Normalization rules applied:
 *  - Trailing slashes are stripped from the raw value.
 *  - The "/api" suffix is appended exactly once, preventing double-slashes
 *    if the variable already ends with "/api".
 */
const rawApiUrl = (import.meta.env.VITE_API_URL as string) || "http://localhost:5000/api";
const normalizedApiUrl = rawApiUrl.replace(/\/+$/, "");

// API_BASE is used by every fetch call in the app via fetchWithAuth() in AuthContext.tsx.
export const API_BASE =
  normalizedApiUrl.endsWith("/api") ? normalizedApiUrl : `${normalizedApiUrl}/api`;
