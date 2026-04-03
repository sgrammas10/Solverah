import { FormEvent, useState } from "react";
import { API_BASE } from "../utils/api";

export type SubmissionStatus = "idle" | "submitting" | "success" | "error";
export type AccountStep = "prompt" | "form" | "signin" | "success";
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
  const [submissionStatus, setSubmissionStatus] = useState<SubmissionStatus>("idle");
  const [errorMessage, setErrorMessage] = useState("");
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
  const [isCreatingAccount, setIsCreatingAccount] = useState(false);
  const [isSigningIn, setIsSigningIn] = useState(false);

  const handleInputChange = (field: keyof typeof formData, value: string) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmissionStatus("submitting");
    setErrorMessage("");

    try {
      const firstName = formData.firstName.trim();
      const lastName = formData.lastName.trim();
      const email = formData.email.trim();
      const state = formData.state.trim();
      const linkedinUrl = formData.linkedinUrl.trim();

      if (!firstName || !lastName) throw new Error("Please enter your name.");
      if (!email) throw new Error("Please enter your email.");
      if (!state) throw new Error("Please enter your state / region.");
      if (!privacyConsent) throw new Error("Please agree to the privacy notice to continue.");
      if (!resumeFile) throw new Error("Please attach your resume to continue.");

      if (linkedinUrl.length > 0) {
        try {
          new URL(linkedinUrl);
        } catch {
          throw new Error("Please enter a valid LinkedIn URL.");
        }
      }

      let submission_id: string | null = null;
      let object_key: string | null = null;
      let mime: string | null = null;
      let size: number | null = null;

      const presignRes = await fetch(`${API_BASE}/intake/presign`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mime: resumeFile.type, size: resumeFile.size }),
      });
      const presignData = await presignRes.json().catch((e) => {
        console.error("Failed to parse presign response:", e);
        return {};
      });
      if (!presignRes.ok) throw new Error(presignData?.error || "Unable to start upload.");

      const { submission_id, object_key, upload_url } = presignData as {
        submission_id?: string;
        object_key?: string;
        upload_url?: string;
      };

      if (!submission_id || !object_key || !upload_url) {
        throw new Error("Upload initialization failed. Please try again.");
      }

      setSubmissionId(submission_id);

      const putRes = await fetch(upload_url, {
        method: "PUT",
        headers: { "Content-Type": resumeFile.type },
        body: resumeFile,
      });
      if (!putRes.ok) throw new Error("Upload failed. Please try again.");

      mime = resumeFile.type;
      size = resumeFile.size;

      const finalizeRes = await fetch(`${API_BASE}/intake/finalize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          submission_id,
          object_key,
          mime,
          size,
          first_name: firstName,
          last_name: lastName,
          email,
          state,
          phone: formData.phone.trim() || null,
          linkedin_url: linkedinUrl || null,
          portfolio_url: formData.portfolioUrl.trim() || null,
          privacy_consent: privacyConsent,
          info_opt_in: infoOptIn,
        }),
      });
      const finalizeData = await finalizeRes.json().catch((e) => {
        console.error("Failed to parse finalize response:", e);
        return {};
      });
      if (!finalizeRes.ok) throw new Error(finalizeData?.error || "Unable to submit right now.");

      setSubmissionStatus("success");
      setAccountModalOpen(true);
      setAccountStep("prompt");
      setAccountAction("create");
      setAccountError("");
      setSubmissionEmail(email);
      setSignInEmail(email);
      setSignInPassword("");
      setAccountPassword("");
      setAccountConfirm("");
      setFormData({ firstName: "", lastName: "", email: "", state: "", phone: "", linkedinUrl: "", portfolioUrl: "" });
      setPrivacyConsent(false);
      setInfoOptIn(false);
      setResumeFile(null);
      setSelectedFileName("");
    } catch (error) {
      setSubmissionStatus("error");
      setErrorMessage(error instanceof Error ? error.message : "Unable to submit right now. Please try again.");
    }
  };

  const handleCreateAccount = async () => {
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
    setIsCreatingAccount(true);
    setAccountAction("create");
    setAccountError("");
    try {
      const response = await fetch(`${API_BASE}/intake/create-account`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ submission_id: submissionId, password: accountPassword, role: "job-seeker" }),
      });
      const data = await response.json().catch((e) => {
        console.error("Failed to parse create-account response:", e);
        return {};
      });
      if (!response.ok) throw new Error(data?.error || "Unable to create account right now.");
      setAccountStep("success");
    } catch (error) {
      setAccountError(error instanceof Error ? error.message : "Unable to create account right now.");
    } finally {
      setIsCreatingAccount(false);
    }
  };

  const handleSignInExisting = async () => {
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
    setIsSigningIn(true);
    setAccountAction("signin");
    setAccountError("");
    try {
      const response = await fetch(`${API_BASE}/intake/sign-in`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ submission_id: submissionId, email: signInEmail.trim(), password: signInPassword }),
      });
      const data = await response.json().catch((e) => {
        console.error("Failed to parse sign-in response:", e);
        return {};
      });
      if (!response.ok) throw new Error(data?.error || "Unable to sign in right now.");
      setAccountStep("success");
    } catch (error) {
      setAccountError(error instanceof Error ? error.message : "Unable to sign in right now.");
    } finally {
      setIsSigningIn(false);
    }
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
    isCreatingAccount,
    isSigningIn,
    handleCreateAccount,
    handleSignInExisting,
  };
}
