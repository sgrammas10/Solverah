/**
 * useIntakeForm — State and submission logic for the pre-launch intake form.
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
import { parseApiError } from "../../shared/api/apiError";

/** Overall submission lifecycle state, derived from the submit mutation. */
export type SubmissionStatus = "idle" | "submitting" | "success" | "error";
/** Step within the post-submission account modal. */
export type AccountStep = "prompt" | "form" | "signin" | "success";
/** Whether the user is creating a new account or signing into an existing one. */
export type AccountAction = "create" | "signin";

export function useIntakeForm() {
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
          portfolio_url: formData.portfolioUrl.trim() || null,
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
    const linkedinUrl = formData.linkedinUrl.trim();

    if (!firstName || !lastName) { setValidationError("Please enter your name."); return; }
    if (!email) { setValidationError("Please enter your email."); return; }
    if (!state) { setValidationError("Please enter your state / region."); return; }
    if (!privacyConsent) { setValidationError("Please agree to the privacy notice to continue."); return; }
    if (!resumeFile) { setValidationError("Please attach your resume to continue."); return; }

    if (linkedinUrl.length > 0) {
      try {
        new URL(linkedinUrl);
      } catch {
        setValidationError("Please enter a valid LinkedIn URL.");
        return;
      }
    }

    setValidationError("");
    submitIntake.mutate({ firstName, lastName, email, state, linkedinUrl, resumeFile });
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
    },
    onSuccess: () => setAccountStep("success"),
    onError: (error) =>
      setAccountError(error instanceof Error ? error.message : "Unable to sign in right now."),
  });

  const handleCreateAccount = () => {
    if (!submissionId) {
      setAccountError("We couldn't find your submission ID. Please resubmit the form.");
      return;
    }
    if (!accountPassword || accountPassword.length < 8) {
      setAccountError("Please choose a password with at least 8 characters.");
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
    handleCreateAccount,
    handleSignInExisting,
  };
}
