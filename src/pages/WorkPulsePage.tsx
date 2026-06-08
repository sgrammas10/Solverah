import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useWP } from "../hooks/useWP";
import { useAuth } from "../contexts/useAuth";
import WPStepper from "../components/wp/WPStepper";

export default function WorkPulsePage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { state, isComplete, setAnswer } = useWP();

  useEffect(() => {
    if (user?.wpl_completed || isComplete) {
      navigate("/work-pulse/results", { replace: true });
    }
  }, [user?.wpl_completed, isComplete, navigate]);

  function handleComplete() {
    navigate("/work-pulse/results");
  }

  return (
    <div className="min-h-screen bg-cream-base">
      <div className="mx-auto max-w-2xl px-6 pt-12 pb-16">
        <div className="mb-8 space-y-2">
          <h1 className="font-display text-2xl sm:text-3xl font-semibold text-ink-primary">
            Work Pulse
          </h1>
          <p className="text-sm text-ink-secondary">
            12 questions about how you work — takes about 4 minutes.
          </p>
        </div>

        <WPStepper
          answers={state.answers}
          onAnswer={setAnswer}
          onComplete={handleComplete}
        />
      </div>
    </div>
  );
}
