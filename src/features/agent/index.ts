/**
 * Public surface of the agent slice — the only legal import path for other
 * feature slices (ARCHITECTURE.md 6.4).
 *
 * Deliberately empty: no other slice consumes anything from agent today.
 * AgentChat is reached only through App.tsx's route-level lazy() import, which
 * deep-imports the component module directly so the route chunk stays its own
 * chunk (a barrel in that chain would be a leak path for the entry bundle).
 */
export {};
