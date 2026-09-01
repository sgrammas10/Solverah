/// <reference types="vite/client" />

/**
 * Resolved base URL for all API requests.
 *
 * In development: reads VITE_API_URL from .env.local, defaulting to
 * http://localhost:5000 when the variable is absent.
 *
 * In production (Vercel): VITE_API_URL must be set to the Flask API
 * origin (e.g. https://api.solverah.com or the Render URL).
 *
 * Normalization rules applied:
 *  - Trailing slashes are stripped from the raw value.
 *  - A trailing "/api" or "/api/v1" is stripped before "/api/v1" is appended,
 *    so a deployment whose variable is already configured either way resolves
 *    to the same base. That is what makes this change deployable without
 *    editing an environment variable in lockstep with the release.
 *
 * Phase 1b moved this from "/api" to "/api/v1". The unversioned paths were
 * aliases kept alive only for the cutover and have been removed, so the version
 * now lives in exactly one constant rather than at every call site -- which is
 * what makes a future "/api/v2" a one-line change here.
 */
const rawApiUrl = (import.meta.env.VITE_API_URL as string) || "http://localhost:5000";
const normalizedApiUrl = rawApiUrl.replace(/\/+$/, "").replace(/\/api(\/v1)?$/, "");

// API_BASE is used by every fetch call in the app via fetchWithAuth() in AuthContext.tsx.
export const API_BASE = `${normalizedApiUrl}/api/v1`;
