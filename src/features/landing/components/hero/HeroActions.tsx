import { useNavigate } from "react-router-dom";

/** The two hero buttons: start the intake, or preview a quiz without signing up. */

const PRIMARY =
  "inline-flex items-center justify-center rounded-[4px] bg-forest-dark px-7 py-3.5 font-headline text-[0.98rem] font-bold text-white transition-colors hover:bg-forest-mid";
const SECONDARY =
  "inline-flex items-center justify-center rounded-[4px] border-2 border-forest-dark px-6 py-3 text-[0.95rem] font-semibold text-forest-dark transition-colors hover:bg-forest-pale";

export function Actions({ onDark = false, center = false }: { onDark?: boolean; center?: boolean }) {
  const navigate = useNavigate();
  return (
    <div className={`ht-actions${center ? " ht-actions--center" : ""}`}>
      <a
        href="#intake"
        className={
          onDark
            ? "inline-flex items-center justify-center rounded-[4px] bg-cream-base px-7 py-3.5 font-headline text-[0.98rem] font-bold text-forest-dark transition-colors hover:bg-forest-pale"
            : PRIMARY
        }
      >
        Get started
      </a>
      <button
        type="button"
        onClick={() => navigate("/quiz-preview")}
        className={
          onDark
            ? "inline-flex items-center justify-center rounded-[4px] border-2 border-cream-base px-6 py-3 text-[0.95rem] font-semibold text-cream-base transition-colors hover:bg-white/10"
            : SECONDARY
        }
      >
        Preview a quiz
      </button>
    </div>
  );
}
