/**
 * ManagerPlaybookPage -- the Manager Decoder's payoff surface (BUILD_PLAN C-4).
 *
 * One query (`useManagerPlaybook`), four renderable outcomes:
 *
 *   1. Loading.
 *   2. `409 no_manager_match`  -- this user has never taken ManagerMatch, so
 *      the Decoder has nothing to diff a manager profile against. Bridges to
 *      `/manager-match` rather than showing an error.
 *   3. `409 no_manager_profile` -- ManagerMatch is done but this user has
 *      never profiled their actual manager. Bridges to `/manager-profile`.
 *   4. Any other failure -- a real error, with retry.
 *   5. Success -- the playbook.
 *
 * States 2 and 3 are distinguished by `error.errorFor(...)?.code`
 * (`"no_manager_match"` / `"no_manager_profile"`), never by the prose in
 * `error.message` -- see `useManagerPlaybook`'s header. Copy on both avoids
 * the words "unlock"/"locked": the real_stack feature-tour E2E classifies
 * that language as a hard gate, which this is not -- a user can reach either
 * instrument from here in one click.
 *
 * Print/copy-friendly by construction: `<article>`/`<section>`/<ul> markup
 * throughout rather than flex tricks that would reorder or clip on print, so
 * the browser's own Print (or a text selection + copy) reproduces the
 * reading order as-is. No third-party PDF machinery -- `window.print()` is
 * the one affordance this page adds over that baseline.
 */
import { useNavigate } from "react-router-dom";
import { useManagerPlaybook } from "../useManagerPlaybook";
import type { ManagerPlaybookDimensionEntry } from "../useManagerPlaybook";
import { ApiError } from "../../../shared/api/apiError";

const DIMENSION_LABELS: Record<string, string> = {
  autonomy: "Autonomy",
  feedback_style: "Feedback Style",
  relationship: "Relationship",
  growth_focus: "Growth Focus",
};

const DIRECTION_LABELS: Record<string, string> = {
  over_supplied: "More than you need",
  under_supplied: "Less than you need",
};

const SEVERITY_LABELS: Record<string, string> = {
  notable: "Notable",
  acute: "Acute",
};

function GrindCard({ entry }: { entry: ManagerPlaybookDimensionEntry }) {
  return (
    <article className="rounded-xl border border-amber-200 bg-amber-50/60 px-6 py-6 space-y-4">
      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="font-display text-lg font-semibold text-ink-primary">
            {DIMENSION_LABELS[entry.dimension] ?? entry.dimension}
          </h3>
          <span className="rounded-full border border-amber-300 bg-white px-2.5 py-0.5 text-xs font-semibold text-amber-700">
            {entry.severity ? SEVERITY_LABELS[entry.severity] : "Grind"}
          </span>
          {entry.direction && (
            <span className="text-xs text-ink-tertiary">{DIRECTION_LABELS[entry.direction]}</span>
          )}
        </div>
        {entry.headline && (
          <p className="font-display text-base font-semibold text-ink-primary">{entry.headline}</p>
        )}
      </header>

      {entry.why && (
        <section className="space-y-1">
          <h4 className="text-xs font-semibold uppercase tracking-widest text-forest-light">Why</h4>
          <p className="text-sm text-ink-primary leading-relaxed">{entry.why}</p>
        </section>
      )}

      {entry.ask && (
        <section className="space-y-1">
          <h4 className="text-xs font-semibold uppercase tracking-widest text-forest-light">The ask</h4>
          <p className="text-sm text-ink-primary leading-relaxed">{entry.ask}</p>
        </section>
      )}

      {entry.agenda && entry.agenda.length > 0 && (
        <section className="space-y-1">
          <h4 className="text-xs font-semibold uppercase tracking-widest text-forest-light">
            Bring to your 1:1
          </h4>
          <ul className="space-y-1.5">
            {entry.agenda.map((item, i) => (
              <li key={i} className="flex gap-2 text-sm text-ink-primary leading-relaxed">
                <span className="text-forest-mid shrink-0 font-bold">›</span>
                {item}
              </li>
            ))}
          </ul>
        </section>
      )}

      {entry.scripts && entry.scripts.length > 0 && (
        <section className="space-y-1">
          <h4 className="text-xs font-semibold uppercase tracking-widest text-forest-light">
            What to say
          </h4>
          <ul className="space-y-1.5">
            {entry.scripts.map((item, i) => (
              <li
                key={i}
                className="text-sm text-ink-primary leading-relaxed italic border-l-2 border-forest-light/40 pl-3"
              >
                “{item}”
              </li>
            ))}
          </ul>
        </section>
      )}

      {entry.constraint_note && (
        <p className="text-xs text-ink-tertiary leading-relaxed border-t border-amber-200 pt-3">
          {entry.constraint_note}
        </p>
      )}
    </article>
  );
}

function MeshCard({ entry }: { entry: ManagerPlaybookDimensionEntry }) {
  return (
    <article className="rounded-xl border border-forest-light bg-forest-pale/60 px-6 py-5 space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="font-display text-base font-semibold text-ink-primary">
          {DIMENSION_LABELS[entry.dimension] ?? entry.dimension}
        </h3>
        <span className="rounded-full border border-forest-light bg-white px-2.5 py-0.5 text-xs font-semibold text-forest-mid">
          Mesh
        </span>
      </div>
      {entry.note && <p className="text-sm text-ink-primary leading-relaxed">{entry.note}</p>}
    </article>
  );
}

export default function ManagerPlaybookPage() {
  const navigate = useNavigate();
  const query = useManagerPlaybook();

  const err = query.error;
  const noManagerMatch =
    err instanceof ApiError && err.errorFor("manager_match")?.code === "no_manager_match";
  const noManagerProfile =
    err instanceof ApiError && err.errorFor("manager_profile")?.code === "no_manager_profile";

  if (query.isLoading) {
    return (
      <div className="min-h-screen bg-cream-base flex flex-col items-center justify-center gap-4">
        <div className="w-8 h-8 rounded-full border-2 border-forest-light border-t-transparent animate-spin" />
        <p className="text-sm text-ink-secondary">Loading your playbook…</p>
      </div>
    );
  }

  if (noManagerMatch) {
    return (
      <div className="min-h-screen bg-cream-base flex items-center justify-center px-6">
        <div className="max-w-sm w-full rounded-xl border border-cream-muted bg-white px-6 py-8 text-center space-y-4">
          <h1 className="font-display text-xl font-semibold text-ink-primary">
            Take ManagerMatch first
          </h1>
          <p className="text-sm text-ink-secondary leading-relaxed">
            Your playbook diffs what you need from a manager against how your manager
            actually works. Take ManagerMatch so there's something to compare your
            manager profile against.
          </p>
          <button
            type="button"
            onClick={() => navigate("/manager-match")}
            className="w-full bg-forest-dark text-white font-semibold py-3 rounded hover:bg-forest-mid transition-colors"
          >
            Take ManagerMatch →
          </button>
        </div>
      </div>
    );
  }

  if (noManagerProfile) {
    return (
      <div className="min-h-screen bg-cream-base flex items-center justify-center px-6">
        <div className="max-w-sm w-full rounded-xl border border-cream-muted bg-white px-6 py-8 text-center space-y-4">
          <h1 className="font-display text-xl font-semibold text-ink-primary">
            Profile your manager
          </h1>
          <p className="text-sm text-ink-secondary leading-relaxed">
            You've completed ManagerMatch. Now tell us how your actual manager works,
            so we can build your playbook.
          </p>
          <button
            type="button"
            onClick={() => navigate("/manager-profile")}
            className="w-full bg-forest-dark text-white font-semibold py-3 rounded hover:bg-forest-mid transition-colors"
          >
            Profile your manager →
          </button>
        </div>
      </div>
    );
  }

  if (query.isError) {
    return (
      <div className="min-h-screen bg-cream-base flex items-center justify-center px-6">
        <div className="max-w-sm w-full rounded-lg border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-700">
          <p className="font-medium mb-1">We couldn't load your playbook right now.</p>
          <p className="text-xs">Please try again in a moment.</p>
          <button
            type="button"
            onClick={() => query.refetch()}
            className="mt-3 text-xs font-semibold text-red-700 underline"
          >
            Try again
          </button>
        </div>
      </div>
    );
  }

  const data = query.data;
  if (!data) return null;
  const { playbook } = data;

  return (
    <div className="min-h-screen bg-cream-base print:bg-white">
      <div className="mx-auto max-w-2xl px-6 pt-12 pb-20 space-y-8">

        {/* Back nav + print (hidden on print) */}
        <div className="flex items-center justify-between print:hidden">
          <button
            type="button"
            onClick={() => navigate("/intelligence")}
            className="flex items-center gap-1.5 text-sm font-semibold text-forest-dark hover:underline"
          >
            <span aria-hidden>←</span> Intelligence Hub
          </button>
          <button
            type="button"
            onClick={() => window.print()}
            className="text-xs font-semibold text-ink-tertiary hover:underline"
          >
            Print this playbook
          </button>
        </div>

        <article className="space-y-8">
          <header className="space-y-2">
            <p className="text-xs font-semibold uppercase tracking-widest text-forest-light">
              Manager Decoder
            </p>
            <h1 className="font-display text-2xl sm:text-3xl font-semibold text-ink-primary">
              Your managing-up playbook
            </h1>
          </header>

          {/* Privacy notice -- must render verbatim and stay visible. */}
          <section className="rounded-lg border border-cream-muted bg-white px-5 py-4">
            <p className="text-sm text-ink-secondary leading-relaxed">{playbook.privacy_notice}</p>
          </section>

          {/* Priority -- where to focus first */}
          {playbook.priority.length > 0 ? (
            <section className="space-y-2">
              <h2 className="text-xs font-semibold uppercase tracking-widest text-forest-light">
                Where to focus first
              </h2>
              <ol className="flex flex-wrap gap-2">
                {playbook.priority.map((dim, i) => (
                  <li
                    key={dim}
                    className="rounded-full border border-amber-300 bg-amber-50 px-3 py-1 text-sm font-semibold text-amber-800"
                  >
                    {i + 1}. {DIMENSION_LABELS[dim] ?? dim}
                  </li>
                ))}
              </ol>
            </section>
          ) : (
            <section className="rounded-lg border border-forest-light bg-forest-pale px-5 py-4">
              <p className="text-sm text-forest-dark font-medium">
                No grinds — your manager profile meshes with what you need across all
                four dimensions.
              </p>
            </section>
          )}

          {/* The full map, in the server's fixed dimension order */}
          <section className="space-y-4">
            <h2 className="text-xs font-semibold uppercase tracking-widest text-forest-light">
              The full map
            </h2>
            <div className="space-y-4">
              {playbook.dimensions.map((entry) =>
                entry.classification === "grind" ? (
                  <GrindCard key={entry.dimension} entry={entry} />
                ) : (
                  <MeshCard key={entry.dimension} entry={entry} />
                )
              )}
            </div>
          </section>
        </article>

        <button
          type="button"
          onClick={() => navigate("/intelligence")}
          className="w-full bg-forest-dark text-white font-semibold py-3.5 rounded hover:bg-forest-mid transition-colors print:hidden"
        >
          Back to Intelligence Hub
        </button>

      </div>
    </div>
  );
}
