import { render, screen } from "@testing-library/react";
import PersonalInfoTab from "./PersonalInfoTab";
import { buildDefaultProfile } from "../useProfileForm";
import { ResumeParseUiState } from "../types";

function renderTab(resumeParseStatus: ResumeParseUiState) {
  return render(
    <PersonalInfoTab
      formData={buildDefaultProfile()}
      handleChange={vi.fn()}
      locationLimitMsg=""
      addSecondaryLocation={vi.fn()}
      removeSecondaryLocation={vi.fn()}
      isUploadingResume={false}
      uploadProgress={0}
      uploadedResume={null}
      resumeUploaded={false}
      resumeParseStatus={resumeParseStatus}
      handleResumeUpload={vi.fn()}
      handleViewResume={vi.fn()}
      removeUploadedResume={vi.fn()}
    />
  );
}

describe("PersonalInfoTab - resume parse status", () => {
  it("shows a neutral 'Parsing resume' indicator while running, with no failure banner", () => {
    const { container } = renderTab({ phase: "running" });
    expect(screen.getByText(/parsing resume/i)).toBeInTheDocument();
    expect(container.querySelector(".bg-red-50")).toBeNull();
  });

  it("shows the failure banner with the message while queued/starting are absent", () => {
    const { container } = renderTab({ phase: "failed", message: "boom" });
    expect(screen.getByText("boom")).toBeInTheDocument();
    expect(container.querySelector(".bg-red-50")).not.toBeNull();
    expect(screen.queryByText(/parsing resume/i)).not.toBeInTheDocument();
  });

  it("shows neither indicator when idle", () => {
    const { container } = renderTab({ phase: "idle" });
    expect(screen.queryByText(/parsing resume/i)).not.toBeInTheDocument();
    expect(container.querySelector(".bg-red-50")).toBeNull();
  });

  it("shows neither indicator once succeeded -- the merged fields are the signal", () => {
    const { container } = renderTab({ phase: "succeeded" });
    expect(screen.queryByText(/parsing resume/i)).not.toBeInTheDocument();
    expect(container.querySelector(".bg-red-50")).toBeNull();
  });
});

/**
 * Audit 2026-10-02 item 1: a .doc uploads and then yields no text, so the
 * picker stops offering it, and a file refused before upload says why.
 */
describe("PersonalInfoTab - resume file types", () => {
  it("offers PDF and DOCX, and not .doc", () => {
    const { container } = renderTab({ phase: "idle" });
    const input = container.querySelector("#resume-upload") as HTMLInputElement;
    const accepted = input.accept.split(",");
    expect(accepted).toContain(".pdf");
    expect(accepted).toContain(".docx");
    expect(accepted).not.toContain(".doc");
    expect(accepted).not.toContain("application/msword");
    expect(screen.getByText("PDF or DOCX, up to 10MB")).toBeInTheDocument();
  });

  it("shows a refused file's reason as an alert", () => {
    render(
      <PersonalInfoTab
        formData={buildDefaultProfile()}
        handleChange={vi.fn()}
        locationLimitMsg=""
        addSecondaryLocation={vi.fn()}
        removeSecondaryLocation={vi.fn()}
        isUploadingResume={false}
        uploadProgress={0}
        uploadedResume={null}
        resumeUploaded={false}
        resumeParseStatus={{ phase: "idle" }}
        resumeFileError="We can only read PDF and DOCX files."
        handleResumeUpload={vi.fn()}
        handleViewResume={vi.fn()}
        removeUploadedResume={vi.fn()}
      />
    );
    expect(screen.getByRole("alert")).toHaveTextContent("We can only read PDF and DOCX files.");
  });
});
