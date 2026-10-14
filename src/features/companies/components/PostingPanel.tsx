/**
 * Paste a job posting: the role-level read beside the company's.
 *
 * The text is the user's own paste; nothing is fetched (PRODUCT_DECISIONS §2). It is
 * scored against the same rubric as the company evidence and its read is private to
 * the user. The page owns the posting id (it lives in the URL, so a reload keeps it)
 * and the polling; this panel is the form and the status around it.
 *
 * A posting that is only a requirements list has nothing to say about how the work
 * runs: every trait abstains, and the panel says so instead of showing an empty read.
 */
import { useId, useState, type FormEvent } from "react";

import {
  BODY_MUTED,
  INPUT,
  LABEL,
  PANEL,
  PRIMARY_BUTTON,
  QUIET_BUTTON,
  REPORT_H2,
  joinNames,
  traitName,
} from "../../matching";
import { ApiError } from "../../../shared/api/apiError";
import { useSubmitPosting, type JobPostingStatus, type PostingRead } from "../useCompanyRead";

export interface PostingProgress {
  /** The posting as last polled, or null before the first poll lands. */
  status: JobPostingStatus | null;
  /** Polling stopped on an error (a stale or someone else's id is a 404). */
  error: unknown;
}

interface PostingPanelProps {
  companyId: number;
  companyName: string;
  postingId: number | null;
  progress: PostingProgress;
  /** The posting's read, once the company read has been fetched with it. */
  read: PostingRead | null;
  onPostingChange: (postingId: number | null) => void;
}

function submitProblem(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 429) return "That's a lot of postings in a short time. Wait a little, then try again.";
    if (error.status === 503) return "Reading postings isn't available right now. Please try again a little later.";
    if (error.status === 400 || error.status === 422) return error.message || "Paste the posting's text, then try again.";
  }
  return "Something went wrong sending that posting. Please try again.";
}

function statusMessage(progress: PostingProgress, read: PostingRead | null): {
  text: string;
  problem: boolean;
} {
  if (progress.error) {
    return {
      text: "We couldn't find that posting any more. You can paste it again.",
      problem: true,
    };
  }
  const status = progress.status;
  if (status === null || (status.status === "pending" && !status.has_read)) {
    return {
      text: "Reading the posting. This usually takes under a minute, and it keeps going if you leave.",
      problem: false,
    };
  }
  if (status.status === "failed" && !status.has_read) {
    return { text: "We couldn't read that posting. You can try pasting it again.", problem: true };
  }
  if (!status.has_read) {
    return {
      text: "This posting lists what the role needs but says nothing clear about how the work runs, so there's nothing to set beside the company's read.",
      problem: false,
    };
  }
  const disagreements = (read?.disagreements ?? []).map(traitName);
  if (disagreements.length > 0) {
    return {
      text: `This posting's read is beside the company's below. They disagree on ${joinNames(disagreements)}: the role may not work the way the company evidence suggests. It's worth asking about.`,
      problem: false,
    };
  }
  return {
    text: "This posting's read is beside the company's below, trait by trait. They don't disagree anywhere.",
    problem: false,
  };
}

export default function PostingPanel({
  companyId,
  companyName,
  postingId,
  progress,
  read,
  onPostingChange,
}: PostingPanelProps) {
  const submit = useSubmitPosting();
  const [text, setText] = useState("");
  const [title, setTitle] = useState("");
  const [emptyError, setEmptyError] = useState(false);
  const titleId = useId();
  const textId = useId();
  const hintId = useId();

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!text.trim()) {
      setEmptyError(true);
      return;
    }
    setEmptyError(false);
    submit.mutate(
      { company_id: companyId, text: text.trim(), title: title.trim() || null },
      { onSuccess: (response) => onPostingChange(response.posting.id) },
    );
  };

  const message = postingId === null ? null : statusMessage(progress, read);
  const postingTitle = progress.status?.title ?? read?.title ?? null;

  return (
    <section className={`${PANEL} space-y-4 px-5 py-5`} aria-labelledby="posting-heading">
      <div className="space-y-1">
        <h2 id="posting-heading" className={REPORT_H2}>
          Paste a job posting
        </h2>
        <p className={BODY_MUTED}>
          A posting describes one role, which can differ from {companyName} as a whole. Paste
          one and we'll read it on the same six traits and show where it and the company
          evidence disagree. Only you see it.
        </p>
      </div>

      {postingId === null ? (
        <form onSubmit={onSubmit} className="space-y-3" noValidate>
          <div className="space-y-1.5">
            <label htmlFor={titleId} className={LABEL}>
              Role title (optional)
            </label>
            <input
              id={titleId}
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className={INPUT}
              maxLength={200}
            />
          </div>
          <div className="space-y-1.5">
            <label htmlFor={textId} className={LABEL}>
              The posting's text
            </label>
            <p id={hintId} className="text-[0.85rem] text-ink-secondary">
              Copy the whole posting from the job page and paste it here.
            </p>
            <textarea
              id={textId}
              value={text}
              onChange={(e) => setText(e.target.value)}
              aria-describedby={hintId}
              aria-invalid={emptyError || undefined}
              rows={8}
              className={INPUT}
            />
          </div>
          <button type="submit" className={PRIMARY_BUTTON} disabled={submit.isPending}>
            {submit.isPending ? "Sending..." : "Read this posting"}
          </button>
          <div role="status" aria-live="polite">
            {emptyError && (
              <p className="text-[0.93rem] text-red-800">Paste the posting's text first.</p>
            )}
            {submit.isError && (
              <p className="text-[0.93rem] text-red-800">{submitProblem(submit.error)}</p>
            )}
          </div>
        </form>
      ) : (
        <div className="space-y-3">
          {postingTitle && (
            <p className="font-semibold text-ink-primary">{postingTitle}</p>
          )}
          <div role="status" aria-live="polite">
            {message && (
              <p
                className={
                  message.problem ? "text-[0.93rem] leading-[1.55] text-red-800" : BODY_MUTED
                }
              >
                {message.text}
              </p>
            )}
          </div>
          <button type="button" className={QUIET_BUTTON} onClick={() => onPostingChange(null)}>
            Paste a different posting
          </button>
        </div>
      )}
    </section>
  );
}
