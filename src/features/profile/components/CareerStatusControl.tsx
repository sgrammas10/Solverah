/**
 * CareerStatusControl — "Where are you in your career?" on the Experience tab.
 *
 * Always on screen, so a status can be changed after it is set (audit
 * 2026-10-02 item 6: the onboarding modal was the only way in, and only while
 * the status was unset). Each choice saves at once through
 * `PATCH /me/career-status`; it is not part of the Save Profile form, which is
 * why its buttons are `type="button"` radios rather than form fields.
 *
 * Reads the stored status off the profile document, not the form, so the
 * control shows what the server holds rather than an unsaved draft.
 */
import { useProfile } from "../useProfile";
import { CAREER_STATUS_OPTIONS, isCareerStatus, useSetCareerStatus } from "./useSetCareerStatus";

export default function CareerStatusControl() {
  const { data: profile } = useProfile();
  const setStatus = useSetCareerStatus();

  const stored = profile?.career_status;
  // While a choice is in flight, show it as chosen so the click registers.
  const selected = setStatus.isPending ? setStatus.variables : isCareerStatus(stored) ? stored : undefined;

  return (
    <section className="bg-white rounded-xl shadow-sm border border-cream-muted p-6">
      <h2 id="career-status-heading" className="text-lg font-semibold text-ink-primary font-display">
        Where are you in your career?
      </h2>
      <p className="text-sm text-ink-secondary mt-1 mb-4">
        This changes what we ask and suggest. You can change it any time.
      </p>
      <div role="radiogroup" aria-labelledby="career-status-heading" className="grid gap-2 md:grid-cols-3">
        {CAREER_STATUS_OPTIONS.map((option) => {
          const checked = selected === option.value;
          return (
            <button
              key={option.value}
              type="button"
              role="radio"
              aria-checked={checked}
              disabled={setStatus.isPending}
              onClick={() => {
                if (!checked) setStatus.mutate(option.value);
              }}
              className={`text-left rounded-lg border px-4 py-3 transition-colors disabled:cursor-not-allowed ${
                checked
                  ? "border-forest-light bg-forest-pale"
                  : "border-cream-muted bg-cream-base hover:bg-cream-subtle"
              }`}
            >
              <span className="block font-medium text-sm text-ink-primary">{option.label}</span>
              <span className="block text-xs text-ink-secondary mt-0.5">{option.hint}</span>
            </button>
          );
        })}
      </div>
      {setStatus.isError && (
        <p role="alert" className="text-sm text-red-700 mt-3">
          We couldn't save that just now. Try again.
        </p>
      )}
      {setStatus.isSuccess && !setStatus.isPending && (
        <p role="status" className="text-sm text-forest-mid mt-3">
          Status saved.
        </p>
      )}
    </section>
  );
}
