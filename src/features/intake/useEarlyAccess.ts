import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { API_BASE } from "../../shared/api/api";
import { ApiError, parseApiError } from "../../shared/api/apiError";

export function useEarlyAccess() {
  const [isOpen, setIsOpen] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);
  // Client-side validation only; the request's own failure lives on the mutation.
  const [validationError, setValidationError] = useState("");
  const [formData, setFormData] = useState({
    firstName: "",
    lastName: "",
    email: "",
    phone: "",
    preferredContact: "email",
    careerJourney: "",
  });

  const handleChange = (field: keyof typeof formData, value: string) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  const submitRequest = useMutation({
    mutationFn: async (body: Record<string, string>) => {
      const res = await fetch(`${API_BASE}/intake/early-access`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const data = await res.json().catch((e) => {
          console.error("Failed to parse early-access response:", e);
          return {};
        });
        throw parseApiError(res, data, "Could not send request. Please try again.");
      }
    },
    onSuccess: () => {
      setIsOpen(false);
      setIsSuccess(true);
      setFormData({ firstName: "", lastName: "", email: "", phone: "", preferredContact: "email", careerJourney: "" });
    },
  });

  // Async, and awaits the mutation: callers (and tests) that `await
  // handleSubmit()` are done when the submission is, same as before the
  // TanStack conversion. The rejection is swallowed here because the failure
  // already surfaces through the mutation's error state below.
  const handleSubmit = async () => {
    const { firstName, lastName, email, phone, preferredContact, careerJourney } = formData;
    if (!firstName.trim() || !lastName.trim() || !email.trim()) {
      setValidationError("Please fill out all required fields.");
      return;
    }
    setValidationError("");
    await submitRequest
      .mutateAsync({
        firstName: firstName.trim(),
        lastName: lastName.trim(),
        email: email.trim(),
        phone: phone.trim(),
        preferredContact,
        careerJourney,
      })
      .catch(() => {});
  };

  // An ApiError carries the server's own wording; anything else never reached it.
  const error =
    validationError ||
    (submitRequest.isError
      ? submitRequest.error instanceof ApiError
        ? submitRequest.error.message
        : "Could not send request. Please try again."
      : "");

  return {
    isOpen,
    setIsOpen,
    isSuccess,
    setIsSuccess,
    formData,
    handleChange,
    isSubmitting: submitRequest.isPending,
    error,
    handleSubmit,
  };
}
