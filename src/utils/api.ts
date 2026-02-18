/// <reference types="vite/client" />

const rawApiUrl = (import.meta.env.VITE_API_URL as string) || "http://localhost:5000/api";
const normalizedApiUrl = rawApiUrl.replace(/\/+$/, "");

export const API_BASE =
  normalizedApiUrl.endsWith("/api") ? normalizedApiUrl : `${normalizedApiUrl}/api`;
