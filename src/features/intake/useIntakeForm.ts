/**
 * useIntakeForm — State and submission logic for the landing-page intake form.
 *
 * Two-step submission flow:
 *   1. presign  — POST /api/intake/presign to get a presigned S3 PUT URL.
 *   2. upload   — PUT the resume file directly to S3/R2 from the browser.
 *   3. finalize — POST /api/intake/finalize with personal details + S3 metadata.
 *
 * After a successful submission, a post-submission account modal guides the
 * user through either creating a new account or signing into an existing one,
 * tying the intake submission to their profile.
 *
 * State groups exposed:
 *   formData / setters       — Personal info fields.
 *   privacyConsent           — Required consent checkbox.
 *   resumeFile               — Selected File object to be uploaded.
 *   submissionStatus         — "idle" | "submitting" | "success" | "error".
 *   submissionId             — UUID returned by the finalize endpoint.
 *   accountModal*            — State for the post-submission account creation/sign-in modal.
 */
import { FormEvent, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { API_BASE } from "../../shared/api/api";
import { ApiError, parseApiError } from "../../shared/api/apiError";
import type { SessionResponse, User } from "../auth";

/** Overall submission lifecycle state, derived from the submit mutation. */
export type SubmissionStatus = "idle" | "submitting" | "success" | "error";
/** Step within the post-submission account modal. */
export type AccountStep = "prompt" | "form" | "signin" | "success";
/** Whether the user is creating a new account or signing into an existing one. */
export type AccountAction = "create" | "signin";

/**
 * The first rule `password` breaks, or "" when it passes.
 *
 * A copy of `validate_password` in validators.py, the rule `/intake/claims`
 * (register mode) enforces -- same order, same wording. The modal said "at
 * least 8 characters" until G30, so an 8-to-11 character password passed here
 * and bounced off the server.
 */
export function passwordProblem(password: string): string {
  if (password.length < 12) return "Password must be at least 12 characters.";
  if (!/[A-Z]/.test(password)) return "Password must contain an uppercase letter.";
  if (!/[a-z]/.test(password)) return "Password must contain a lowercase letter.";
  if (!/[0-9]/.test(password)) return "Password must contain a number.";
  if (!/[^A-Za-z0-9]/.test(password)) return "Password must contain a symbol.";
  return "";
}

/** The hosts `is_valid_linkedin_url` (solverah/domain/validation.py) accepts. */
const LINKEDIN_HOSTS = new Set(["linkedin.com", "www.linkedin.com"]);

/**
 * Turn what someone typed into an optional link field into the https URL the
 * server accepts, or null when it cannot be one.
 *
 * The form's own placeholders are "linkedin.com/in/you" and "your-site.com",
 * and the server only takes `https://` (G26): a bare address gets the scheme,
 * and `http://` is upgraded rather than refused. The result is the parsed
 * URL's `href`, so the host reaches the server lowercased -- the server
 * compares it to its allowed set case-sensitively.
 */
export function toHttpsUrl(raw: string): URL | null {
  let value = raw.trim();
  if (!value) return null;
  if (/^http:\/\//i.test(value)) value = `https://${value.slice("http://".length)}`;
  else if (!/^[a-z][a-z0-9+.-]*:\/\//i.test(value)) value = `https://${value}`;
  try {
    const url = new URL(value);
    if (url.protocol !== "https:" || !url.host || url.username || url.password) return null;
    return url;
  } catch {
    return null;
  }
}

/** Loose shape check; the server's `is_valid_email` has the final word. */
const EMAIL_SHAPE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** What the account modal's sign-in hands the app's auth state (G29). */
export interface IntakeFormOptions {
  /**
   * Called once a `sign_in` claim has opened a session, with the arguments
   * `AuthContext.loginWithData` takes. The claim sets the session cookies
   * server-side; until this existed the app never heard about it, and the page
   * looked signed out until a reload.
   */
  onSignedIn?: (user: User, csrfToken: string) => void;
}

/**
 * The `User` the app holds, from the session probe.
 *
 * The claim's own body carries only the summary user (id, email, name, role),
 * so handing that to `loginWithData` would leave the completion flags
 * undefined and the dashboard prompting for instruments already done. The
 * probe answers them; this mirrors AuthContext's `toUser`.
 */
function userFromSession(session: SessionResponse): User {
  return {
    ...(session.user as unknown as User),
    wpl_completed: session.flags.wpl_completed,
    wpll_completed: session.flags.wpll_completed,
    wp_v2_completed: session.flags.wp_v2_completed,
  } as User;
}

export function useIntakeForm({ onSignedIn }: IntakeFormOptions = {}) {
  const [formData, setFormData] = useState({
    firstName: "",
    lastName: "",
    email: "",
    state: "",
    phone: "",
    linkedinUrl: "",
    portfolioUrl: "",
  });
  const [privacyConsent, setPrivacyConsent] = useState(false);
  const [infoOptIn, setInfoOptIn] = useState(false);
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [selectedFileName, setSelectedFileName] = useState("");
  // Client-side validation only; the submission's own failure lives on the mutation.
  const [validationError, setValidationError] = useState("");
  const [submissionId, setSubmissionId] = useState<string | null>(null);
  const [submissionEmail, setSubmissionEmail] = useState("");

  // Account modal state
  const [accountModalOpen, setAccountModalOpen] = useState(false);
  const [accountStep, setAccountStep] = useState<AccountStep>("prompt");
  const [accountAction, setAccountAction] = useState<AccountAction>("create");
  const [signInEmail, setSignInEmail] = useState("");
  const [signInPassword, setSignInPassword] = useState("");
  const [accountPassword, setAccountPassword] = useState("");
  const [accountConfirm, setAccountConfirm] = useState("");
  const [accountError, setAccountError] = useState("");
  // The last sign-in failed on an unconfirmed email (403), so the modal offers
  // a fresh code rather than a dead end.
  const [signInNeedsVerification, setSignInNeedsVerification] = useState(false);

  const handleInputChange = (field: keyof typeof formData, value: string) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  // One mutation for the whole chain: presign, S3 PUT, finalize succeed or
  // fail as a unit, exactly as the hand-rolled try block treated them (same
  // shape as IntakePromptModal's submit). Mutations never retry, and the S3
  // PUT in particular must not be — the presigned URL is single-use.
  const submitIntake = useMutation({
    mutationFn: async (input: {
      firstName: string;
      lastName: string;
      email: string;
      state: string;
      linkedinUrl: string;
      portfolioUrl: string;
      resumeFile: File;
    }) => {
      // Step 1: get presigned upload URL
      const presignRes = await fetch(`${API_BASE}/intake/resume-tickets`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mime: input.resumeFile.type, size: input.resumeFile.size }),
      });
      const presignData = await presignRes.json().catch((e) => {
        console.error("Failed to parse presign response:", e);
        return {};
      });
      if (!presignRes.ok) throw parseApiError(presignRes, presignData, "Unable to start upload.");

      const { submission_id, object_key, upload_url } = presignData as {
        submission_id?: string;
        object_key?: string;
        upload_url?: string;
      };

      if (!submission_id || !object_key || !upload_url) {
        throw new Error("Upload initialization failed. Please try again.");
      }

      // Recorded as soon as the ticket exists, as before — the account modal's
      // claims need it after success, and it names the submission either way.
      setSubmissionId(submission_id);

      // Step 2: upload resume directly to S3
      const putRes = await fetch(upload_url, {
        method: "PUT",
        headers: { "Content-Type": input.resumeFile.type },
        body: input.resumeFile,
      });
      if (!putRes.ok) throw new Error("Upload failed. Please try again.");

      // Step 3: finalize the submission
      const finalizeRes = await fetch(`${API_BASE}/intake/submissions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          submission_id,
          object_key,
          mime: input.resumeFile.type,
          size: input.resumeFile.size,
          first_name: input.firstName,
          last_name: input.lastName,
          email: input.email,
          state: input.state,
          phone: formData.phone.trim() || null,
          linkedin_url: input.linkedinUrl || null,
          portfolio_url: input.portfolioUrl || null,
          privacy_consent: privacyConsent,
          info_opt_in: infoOptIn,
        }),
      });
      const finalizeData = await finalizeRes.json().catch((e) => {
        console.error("Failed to parse finalize response:", e);
        return {};
      });
      if (!finalizeRes.ok) throw parseApiError(finalizeRes, finalizeData, "Unable to submit right now.");
    },
    onSuccess: (_data, input) => {
      setAccountModalOpen(true);
      setAccountStep("prompt");
      setAccountAction("create");
      setAccountError("");
      setSubmissionEmail(input.email);
      setSignInEmail(input.email);
      setSignInPassword("");
      setAccountPassword("");
      setAccountConfirm("");
      setFormData({ firstName: "", lastName: "", email: "", state: "", phone: "", linkedinUrl: "", portfolioUrl: "" });
      setPrivacyConsent(false);
      setInfoOptIn(false);
      setResumeFile(null);
      setSelectedFileName("");
    },
  });

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const firstName = formData.firstName.trim();
    const lastName = formData.lastName.trim();
    const email = formData.email.trim();
    const state = formData.state.trim();
    const linkedinRaw = formData.linkedinUrl.trim();
    const portfolioRaw = formData.portfolioUrl.trim();

    // The form is noValidate (G26): these messages are the ones people see, so
    // every rule the browser used to apply first has to be here instead.
    if (!firstName || !lastName) { setValidationError("Please enter your name."); return; }
    if (!email) { setValidationError("Please enter your email."); return; }
    if (!EMAIL_SHAPE.test(email)) { setValidationError("Please enter a valid email address."); return; }
    if (!state) { setValidationError("Please enter your state / region."); return; }
    if (!privacyConsent) { setValidationError("Please agree to the privacy notice to continue."); return; }
    if (!resumeFile) { setValidationError("Please attach your resume to continue."); return; }

    let linkedinUrl = "";
    if (linkedinRaw) {
      const url = toHttpsUrl(linkedinRaw);
      if (!url || !LINKEDIN_HOSTS.has(url.host)) {
        setValidationError("Please enter a LinkedIn link, like linkedin.com/in/you.");
        return;
      }
      linkedinUrl = url.href;
    }

    let portfolioUrl = "";
    if (portfolioRaw) {
      const url = toHttpsUrl(portfolioRaw);
      if (!url) {
        setValidationError("Please enter your portfolio's web address, like your-site.com.");
        return;
      }
      portfolioUrl = url.href;
    }

    setValidationError("");
    submitIntake.mutate({ firstName, lastName, email, state, linkedinUrl, portfolioUrl, resumeFile });
  };

  // The lifecycle the components render is the mutation's, with client-side
  // validation failures folded in as the "error" they always were.
  const submissionStatus: SubmissionStatus = validationError
    ? "error"
    : submitIntake.isPending
    ? "submitting"
    : submitIntake.isSuccess
    ? "success"
    : submitIntake.isError
    ? "error"
    : "idle";
  const errorMessage =
    validationError ||
    (submitIntake.isError
      ? submitIntake.error instanceof Error
        ? submitIntake.error.message
        : "Unable to submit right now. Please try again."
      : "");

  const createAccountMutation = useMutation({
    mutationFn: async (password: string) => {
      // `/intake/claims` replaces the four account-attachment endpoints; `mode`
      // selects which one this is. Registering a new account from a finished
      // submission -- the email comes from the submission, never from here.
      const response = await fetch(`${API_BASE}/intake/claims`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mode: "register",
          submission_id: submissionId,
          password,
          role: "job-seeker",
        }),
      });
      const data = await response.json().catch((e) => {
        console.error("Failed to parse create-account response:", e);
        return {};
      });
      if (!response.ok) throw parseApiError(response, data, "Unable to create account right now.");
    },
    onSuccess: () => setAccountStep("success"),
    onError: (error) =>
      setAccountError(error instanceof Error ? error.message : "Unable to create account right now."),
  });

  const signInExistingMutation = useMutation({
    mutationFn: async (credentials: { email: string; password: string }) => {
      // Same endpoint, different mode: attaching the submission to an account
      // that already exists.
      const response = await fetch(`${API_BASE}/intake/claims`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          mode: "sign_in",
          submission_id: submissionId,
          email: credentials.email,
          password: credentials.password,
        }),
      });
      const data = await response.json().catch((e) => {
        console.error("Failed to parse sign-in response:", e);
        return {};
      });
      if (!response.ok) throw parseApiError(response, data, "Unable to sign in right now.");

      // The claim opened a session (both cookies are set); ask it who we are
      // so the app gets the full user, flags included. Should the probe fail,
      // the claim's summary user still beats leaving the app signed out.
      const claim = data as { user?: User; csrfToken?: string };
      let user = claim.user as User;
      let csrfToken = claim.csrfToken ?? "";
      try {
        const sessionRes = await fetch(`${API_BASE}/auth/session`, { credentials: "include" });
        if (sessionRes.ok) {
          const session = (await sessionRes.json()) as SessionResponse;
          user = userFromSession(session);
          csrfToken = session.csrf_token ?? csrfToken;
        }
      } catch (e) {
        console.error("Session probe after intake sign-in failed:", e);
      }
      return { user, csrfToken };
    },
    onSuccess: ({ user, csrfToken }) => {
      if (user) onSignedIn?.(user, csrfToken);
      setAccountStep("success");
    },
    onError: (error) => {
      // sign_in answers 403 for one reason only: the email is not confirmed.
      setSignInNeedsVerification(error instanceof ApiError && error.status === 403);
      setAccountError(error instanceof Error ? error.message : "Unable to sign in right now.");
    },
  });

  // Same call Login.tsx's "Resend verification code" makes; the modal moves on
  // to /verify-email once it lands.
  const resendVerificationMutation = useMutation({
    mutationFn: async (email: string) => {
      const response = await fetch(`${API_BASE}/auth/email/verify/resend`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const data = await response.json().catch(() => null);
      if (!response.ok) throw parseApiError(response, data, "Failed to resend code.");
    },
    onError: (error) =>
      setAccountError(error instanceof Error ? error.message : "Failed to resend code."),
  });

  /** Send a fresh verification code; resolves to whether it was sent. */
  const resendVerification = async (): Promise<boolean> => {
    try {
      await resendVerificationMutation.mutateAsync(signInEmail.trim());
      return true;
    } catch {
      return false;
    }
  };

  const handleCreateAccount = () => {
    if (!submissionId) {
      setAccountError("We couldn't find your submission ID. Please resubmit the form.");
      return;
    }
    const passwordError = passwordProblem(accountPassword);
    if (passwordError) {
      setAccountError(passwordError);
      return;
    }
    if (accountPassword !== accountConfirm) {
      setAccountError("Passwords do not match.");
      return;
    }
    setAccountAction("create");
    setAccountError("");
    createAccountMutation.mutate(accountPassword);
  };

  const handleSignInExisting = () => {
    if (!submissionId) {
      setAccountError("We couldn't find your submission ID. Please resubmit the form.");
      return;
    }
    if (!signInEmail.trim()) {
      setAccountError("Please enter the email used on your submission.");
      return;
    }
    if (!signInPassword) {
      setAccountError("Please enter your password.");
      return;
    }
    setAccountAction("signin");
    setAccountError("");
    setSignInNeedsVerification(false);
    signInExistingMutation.mutate({ email: signInEmail.trim(), password: signInPassword });
  };

  return {
    formData,
    handleInputChange,
    privacyConsent,
    setPrivacyConsent,
    infoOptIn,
    setInfoOptIn,
    resumeFile,
    setResumeFile,
    selectedFileName,
    setSelectedFileName,
    submissionStatus,
    errorMessage,
    handleSubmit,
    submissionId,
    submissionEmail,
    accountModalOpen,
    setAccountModalOpen,
    accountStep,
    setAccountStep,
    accountAction,
    setAccountAction,
    signInEmail,
    setSignInEmail,
    signInPassword,
    setSignInPassword,
    accountPassword,
    setAccountPassword,
    accountConfirm,
    setAccountConfirm,
    accountError,
    setAccountError,
    isCreatingAccount: createAccountMutation.isPending,
    isSigningIn: signInExistingMutation.isPending,
    signInNeedsVerification,
    resendVerification,
    isResendingVerification: resendVerificationMutation.isPending,
    handleCreateAccount,
    handleSignInExisting,
  };
}
