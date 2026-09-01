import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.tsx';
import { AppErrorBoundary } from './AppErrorBoundary';
import '../styles/index.css';

// AppErrorBoundary wraps App rather than living inside it: everything App
// renders -- QueryClientProvider, AuthProvider, Router -- is then inside the
// net, so a throw in a provider's own render still produces a page instead of
// a blank document. See AppErrorBoundary.tsx.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AppErrorBoundary>
      <App />
    </AppErrorBoundary>
  </StrictMode>
);
