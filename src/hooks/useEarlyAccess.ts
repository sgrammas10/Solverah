import { useState } from "react";
import { API_BASE } from "../utils/api";

export function useEarlyAccess() {
  const [isOpen, setIsOpen] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");
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

  const handleSubmit = async () => {
    const { firstName, lastName, email, phone, preferredContact, careerJourney } = formData;
    if (!firstName.trim() || !lastName.trim() || !email.trim()) {
      setError("Please fill out all required fields.");
      return;
    }
    setIsSubmitting(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/early-access-request`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          firstName: firstName.trim(),
          lastName: lastName.trim(),
          email: email.trim(),
          phone: phone.trim(),
          preferredContact,
          careerJourney,
        }),
      });
      if (!res.ok) {
        const data = await res.json().catch((e) => {
          console.error("Failed to parse early-access response:", e);
          return {};
        });
        setError(data?.error || "Could not send request. Please try again.");
        return;
      }
      setIsOpen(false);
      setIsSuccess(true);
      setFormData({ firstName: "", lastName: "", email: "", phone: "", preferredContact: "email", careerJourney: "" });
    } catch {
      setError("Could not send request. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return {
    isOpen,
    setIsOpen,
    isSuccess,
    setIsSuccess,
    formData,
    handleChange,
    isSubmitting,
    error,
    handleSubmit,
  };
}
