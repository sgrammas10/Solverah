import { useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

// Legacy route - redirect to the code-entry verification page
export default function CheckEmail() {
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    const email =
      (location.state as any)?.email ||
      new URLSearchParams(location.search).get('email') ||
      '';
    navigate('/verify-email', { replace: true, state: { email } });
  }, []);

  return null;
}
