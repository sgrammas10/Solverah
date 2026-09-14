/**
 * AccountSettingsPage — "Account settings": export your data, delete your account.
 *
 * The screen three legal documents already promised. The Privacy Policy
 * ("Download a copy of your data from your account settings at any time",
 * "Delete your account from account settings"), the Terms, and /trust all point
 * at "account settings"; none of them names a path, so a page with this title
 * satisfies them verbatim. Both endpoints existed and were tested before this
 * page did — nothing in the SPA had ever called them.
 *
 * Two things here are the first of their kind in this codebase, and both fail
 * silently rather than loudly:
 *
 * 1. The first client-side file download. jsdom has no `URL.createObjectURL`,
 *    which is why the test stubs it; a browser that revokes too early hands the
 *    user an empty file. The payload is NEVER rendered — it is every identified
 *    row we hold, including free-text pulse notes, and a screen is a far easier
 *    place to leak it from than a file the user chose to save.
 *
 * 2. The first DELETE, and the only place the app tears down a session that the
 *    server has already torn down. Order is load-bearing: navigate first, THEN
 *    clear. Clearing first drops `user` to null while this page is still
 *    mounted under `RequireAuth`, which bounces to /login and eats the
 *    confirmation the user just earned. `logout()` is not used — see
 *    `clearSessionLocally` in authContext.ts for why.
 */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";

import { useAuth } from "../../auth";
import { ApiError } from "../../../shared/api/apiError";

/** The confirmation the server compares with a strict `!=` — no trimming, no casefold. */
const DELETE_CONFIRMATION = "DELETE";

/**
 * How long the object URL outlives the click. `anchor.click()` returns once the
 * download is *requested*, not once the blob has been *read*; revoking on the
 * same tick is the documented way to hand Firefox an empty file. A minute is
 * long enough for any browser to have opened the blob and costs nothing — the
 * payload is kilobytes and lives in this tab's memory either way.
 */
export const EXPORT_URL_REVOKE_DELAY_MS = 60_000;

interface DeleteAccountResponse {
  message?: string;
  /** Object keys the backend could not remove from storage. Deliberately surfaced (D-07). */
  r2_delete_failures?: unknown[];
}

/** `solverah-data-2026-09-14.json`, in the user's own timezone rather than UTC. */
function downloadFilename(now: Date): string {
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `solverah-data-${now.getFullYear()}-${month}-${day}.json`;
}

/**
 * A 404 on DELETE means the JWT resolved to no row — the account is already
 * gone. That is the outcome the user asked for, so it takes the success path;
 * showing them an error would be telling them a true thing in a false way.
 */
function isAlreadyDeleted(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}

function AccountSettingsPage() {
  const { user, fetchWithAuth, clearSessionLocally } = useAuth();
  const navigate = useNavigate();

  const [confirming, setConfirming] = useState(false);
  const [confirmText, setConfirmText] = useState("");

  // ── Export ───────────────────────────────────────────────────────────────
  //
  // A mutation, not a query: neither endpoint is separately rate-limited, and
  // the query client retries twice on 429/5xx. A download the user asked for
  // once should be requested once.
  const exportData = useMutation({
    mutationFn: () => fetchWithAuth<unknown>("/me/export"),
    onSuccess: (data) => {
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const href = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = href;
      anchor.download = downloadFilename(new Date());
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      window.setTimeout(() => URL.revokeObjectURL(href), EXPORT_URL_REVOKE_DELAY_MS);
    },
  });

  // ── Delete ───────────────────────────────────────────────────────────────

  const finishDeletion = (filesLeftBehind: boolean) => {
    navigate("/", { replace: true, state: { accountDeleted: true, filesLeftBehind } });
    clearSessionLocally();
  };

  const deleteAccount = useMutation({
    mutationFn: () =>
      fetchWithAuth<DeleteAccountResponse>("/me", {
        method: "DELETE",
        // The literal, never the raw input: " DELETE " is a fine thing to type
        // and a 400 to send.
        body: JSON.stringify({ confirm: DELETE_CONFIRMATION }),
      }),
    onSuccess: (data) => finishDeletion((data?.r2_delete_failures?.length ?? 0) > 0),
    onError: (error) => {
      if (isAlreadyDeleted(error)) finishDeletion(false);
    },
  });

  const canConfirm = confirmText.trim() === DELETE_CONFIRMATION;
  // An already-deleted account navigated away; only a real failure is an error.
  const deleteFailed = deleteAccount.isError && !isAlreadyDeleted(deleteAccount.error);

  const cancelDeletion = () => {
    setConfirming(false);
    setConfirmText("");
    deleteAccount.reset();
  };

  return (
    <div className="min-h-screen bg-cream-base font-sans">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <h1 className="font-display text-3xl font-bold text-ink-primary">Account settings</h1>

        {user && (
          <div className="mt-4 text-sm text-ink-secondary">
            <p className="font-medium text-ink-primary">{user.name}</p>
            <p>{user.email}</p>
          </div>
        )}

        {/* ── Your data ────────────────────────────────────────────────── */}
        <section className="mt-10 rounded-xl border border-cream-muted bg-white p-6">
          <h2 className="font-display text-xl font-semibold text-ink-primary">Your data</h2>
          <p className="mt-2 text-sm text-ink-secondary leading-relaxed">
            Download everything Solverah holds about you as a JSON file — your account and
            profile, your assessment answers and scores, your check-ins, and the records behind
            your recommendations.
          </p>

          {exportData.isError && (
            <div className="mt-4 rounded bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
              <p>We couldn't prepare your download just now.</p>
              <p className="mt-1">Please try again in a moment.</p>
              <button
                type="button"
                onClick={() => exportData.mutate()}
                className="mt-2 font-medium underline"
              >
                Try again
              </button>
            </div>
          )}

          <button
            type="button"
            disabled={exportData.isPending}
            onClick={() => exportData.mutate()}
            className="mt-5 px-6 py-3 bg-forest-dark text-white rounded-md hover:bg-forest-mid disabled:opacity-50 disabled:cursor-not-allowed font-medium"
          >
            {exportData.isPending ? "Preparing your download…" : "Download a copy of your data"}
          </button>
        </section>

        {/* ── Delete your account ──────────────────────────────────────── */}
        <section className="mt-8 rounded-xl border border-cream-muted bg-white p-6">
          <h2 className="font-display text-xl font-semibold text-ink-primary">
            Delete your account
          </h2>
          <p className="mt-2 text-sm text-ink-secondary leading-relaxed">
            This permanently removes your account, profile, resume and intake records. Your
            assessment responses are kept only in de-identified form, no longer linked to you.
            This cannot be undone.
          </p>

          {deleteFailed && (
            <div className="mt-4 rounded bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
              <p>We couldn't delete your account just now.</p>
              <p className="mt-1">Please try again in a moment. Nothing has been changed.</p>
            </div>
          )}

          {!confirming ? (
            <button
              type="button"
              onClick={() => setConfirming(true)}
              className="mt-5 font-medium text-red-400 hover:text-red-600"
            >
              Delete my account
            </button>
          ) : (
            <div className="mt-5 rounded-lg border border-cream-muted bg-cream-base p-4">
              <label
                htmlFor="delete-confirm"
                className="text-sm font-medium text-ink-primary"
              >
                Type DELETE to confirm
              </label>
              <input
                id="delete-confirm"
                type="text"
                value={confirmText}
                autoComplete="off"
                onChange={(e) => setConfirmText(e.target.value)}
                className="mt-2 w-full rounded-md border border-cream-muted px-3 py-2 text-sm text-ink-primary"
              />
              <div className="mt-4 flex items-center gap-4">
                <button
                  type="button"
                  disabled={!canConfirm || deleteAccount.isPending}
                  onClick={() => deleteAccount.mutate()}
                  className="px-6 py-3 bg-forest-dark text-white rounded-md hover:bg-forest-mid disabled:opacity-50 disabled:cursor-not-allowed font-medium"
                >
                  {deleteAccount.isPending ? "Deleting…" : "Permanently delete"}
                </button>
                <button
                  type="button"
                  disabled={deleteAccount.isPending}
                  onClick={cancelDeletion}
                  className="text-sm font-medium text-ink-secondary hover:text-forest-mid disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

export default AccountSettingsPage;
