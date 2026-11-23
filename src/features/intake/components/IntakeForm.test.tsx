/**
 * IntakeForm.test.tsx — G26: the hero form's own validation is the one people see.
 *
 * Found by reading the source (docs/USER_SCENARIOS.md S3.2–S3.3a): the form had
 * no `noValidate`, so the browser's "Please fill out this field." bubble ran
 * before any of useIntakeForm's messages; the resume input was `required` and
 * `display:none`, which Chrome cannot focus to point a bubble at, so a submit
 * with no file did nothing visible; and the two link fields were `type="url"`,
 * which refuses the form's own placeholders ("linkedin.com/in/you",
 * "your-site.com") for lacking a scheme.
 *
 * Rendered through the real hook, so a message asserted here is one the page
 * would show.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";

import IntakeForm from "./IntakeForm";
import { useIntakeForm } from "../useIntakeForm";
import { createQueryClient } from "../../../shared/api/queryClient";
import { mock } from "../../../../tests/msw/contract";
import { server, useApiMocks, recordRequests } from "../../../../tests/msw/server";

useApiMocks();
const { requests } = recordRequests();

const UPLOAD_URL = "https://uploads.example.com/intake-resume-1";

function Harness() {
  const intake = useIntakeForm();
  return (
    <IntakeForm
      formData={intake.formData}
      onInputChange={intake.handleInputChange}
      privacyConsent={intake.privacyConsent}
      setPrivacyConsent={intake.setPrivacyConsent}
      infoOptIn={intake.infoOptIn}
      setInfoOptIn={intake.setInfoOptIn}
      setResumeFile={intake.setResumeFile}
      selectedFileName={intake.selectedFileName}
      setSelectedFileName={intake.setSelectedFileName}
      submissionStatus={intake.submissionStatus}
      errorMessage={intake.errorMessage}
      onSubmit={intake.handleSubmit}
    />
  );
}

function renderForm() {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <Harness />
    </QueryClientProvider>
  );
  return userEvent.setup();
}

function submitButton() {
  return screen.getByRole("button", { name: "Begin setting up my account" });
}

async function fillRequired(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("First name"), "Ada");
  await user.type(screen.getByLabelText("Last name"), "Lovelace");
  await user.type(screen.getByLabelText("Email"), "ada@example.com");
  await user.type(screen.getByLabelText("State / region"), "NY");
  await user.click(screen.getByRole("checkbox", { name: /I consent to Solverah/ }));
}

function attachResume() {
  const input = screen.getByLabelText(/Resume/) as HTMLInputElement;
  fireEvent.change(input, {
    target: { files: [new File(["%PDF-1.4"], "resume.pdf", { type: "application/pdf" })] },
  });
}

describe("IntakeForm validation (G26)", () => {
  it("the form leaves validation to the app, so the browser cannot pre-empt its messages", () => {
    renderForm();

    const form = submitButton().closest("form")!;
    expect(form).toHaveAttribute("novalidate");
    // A required control the browser cannot focus is how a submit went silent.
    expect(screen.getByLabelText(/Resume/)).not.toBeRequired();
  });

  it("an empty submit shows the app's own first message", async () => {
    const user = renderForm();

    await user.click(submitButton());

    expect(await screen.findByRole("alert")).toHaveTextContent("Please enter your name.");
    expect(requests).toEqual([]);
  });

  it("a submit with no resume says so instead of doing nothing", async () => {
    const user = renderForm();
    await fillRequired(user);

    await user.click(submitButton());

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Please attach your resume to continue."
    );
    expect(requests).toEqual([]);
  });

  it("an email without an @ is caught here now that the browser no longer checks it", async () => {
    const user = renderForm();
    await user.type(screen.getByLabelText("First name"), "Ada");
    await user.type(screen.getByLabelText("Last name"), "Lovelace");
    await user.type(screen.getByLabelText("Email"), "ada.example.com");

    await user.click(submitButton());

    expect(await screen.findByRole("alert")).toHaveTextContent("Please enter a valid email address.");
  });

  it("the link fields accept the placeholders' own format and send https URLs", async () => {
    let finalized: Record<string, unknown> = {};
    server.use(
      mock("post", "/api/v1/intake/resume-tickets").resolve(() =>
        HttpResponse.json({
          submission_id: "sub-1",
          object_key: "intake/resume-1.pdf",
          upload_url: UPLOAD_URL,
        })
      ),
      http.put(UPLOAD_URL, () => new HttpResponse(null, { status: 200 })),
      mock("post", "/api/v1/intake/submissions").resolve(async ({ request }) => {
        finalized = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ok: true });
      })
    );
    const user = renderForm();
    await fillRequired(user);
    attachResume();

    const linkedin = screen.getByLabelText(/LinkedIn/);
    const portfolio = screen.getByLabelText(/Portfolio/);
    expect(linkedin).not.toHaveAttribute("type", "url");
    expect(portfolio).not.toHaveAttribute("type", "url");
    await user.type(linkedin, "linkedin.com/in/you");
    await user.type(portfolio, "http://Your-Site.com");

    await user.click(submitButton());

    await waitFor(() => expect(requests).toContain("POST /api/v1/intake/submissions"));
    // The server takes only https, and compares the LinkedIn host exactly.
    expect(finalized.linkedin_url).toBe("https://linkedin.com/in/you");
    expect(finalized.portfolio_url).toBe("https://your-site.com/");
  });

  it("a LinkedIn field holding another site is refused before anything is uploaded", async () => {
    const user = renderForm();
    await fillRequired(user);
    attachResume();
    await user.type(screen.getByLabelText(/LinkedIn/), "twitter.com/you");

    await user.click(submitButton());

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Please enter a LinkedIn link, like linkedin.com/in/you."
    );
    expect(requests).toEqual([]);
  });
});
