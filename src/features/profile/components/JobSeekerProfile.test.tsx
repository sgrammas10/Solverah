import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import JobSeekerProfile from "./JobSeekerProfile";
import { createQueryClient } from "../../../shared/api/queryClient";
import { ApiError } from "../../../shared/api/apiError";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  fetchWithAuth: vi.fn(),
  profileForm: {
    formData: {
      firstName: "Ada",
      lastName: "Lovelace",
      email: "ada@example.com",
      phone: "",
      location: "",
      primaryLocation: "",
      secondaryLocations: [],
      linkedinUrl: "",
      summary: "",
      experience: [],
      education: [],
      certifications: [],
      skills: [],
      skill_levels: {},
      performanceReviews: [],
      psychometricResults: {},
      uploadedResume: null,
      resumeKey: null,
    },
    isSaving: false,
    isSaved: true,
    saveProgress: 0,
    isUploadingResume: false,
    uploadProgress: 0,
    uploadedResume: null,
    resumeUploaded: false,
    locationLimitMsg: "",
    experienceLimitMsg: "",
    skillLimitMsg: "",
    educationLimitMsg: "",
    certificationLimitMsg: "",
    handleSubmit: vi.fn((e: any) => e?.preventDefault?.()),
    handleChange: vi.fn(),
    addExperience: vi.fn(),
    removeExperience: vi.fn(),
    updateExperience: vi.fn(),
    addSkill: vi.fn(),
    removeSkill: vi.fn(),
    updateSkillLevel: vi.fn(),
    addEducation: vi.fn(),
    removeEducation: vi.fn(),
    updateEducation: vi.fn(),
    addCertification: vi.fn(),
    removeCertification: vi.fn(),
    updateCertification: vi.fn(),
    addSecondaryLocation: vi.fn(),
    removeSecondaryLocation: vi.fn(),
    handleResumeUpload: vi.fn(),
    handleViewResume: vi.fn(),
    removeUploadedResume: vi.fn(),
  } as any,
}));

vi.mock("../useProfileForm", () => ({
  useProfileForm: () => mocks.profileForm,
}));

vi.mock("../../auth/useAuth", () => ({
  useAuth: () => ({ fetchWithAuth: mocks.fetchWithAuth }),
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mocks.navigate };
});

vi.mock("./PersonalInfoTab", () => ({
  default: () => <div data-testid="personal-info-tab">Personal Info Tab</div>,
}));
vi.mock("./ExperienceTab", () => ({
  default: () => <div data-testid="experience-tab">Experience Tab</div>,
}));
vi.mock("./EducationTab", () => ({
  default: () => <div data-testid="education-tab">Education Tab</div>,
}));
vi.mock("./PerformanceTab", () => ({
  default: () => <div data-testid="performance-tab">Performance Tab</div>,
}));

beforeEach(() => {
  vi.clearAllMocks();
  mocks.profileForm.isSaved = true;
  mocks.profileForm.isSaving = false;
});

function renderJobSeekerProfile(search = "") {
  render(
    <MemoryRouter initialEntries={[{ pathname: "/job-seeker/profile", search }]}>
      <JobSeekerProfile />
    </MemoryRouter>
  );
}

/** Navigated here with the modal already open, as `EnvironmentReportPage`'s
 *  "Set your career status" button does. Needs a real query client -- the
 *  modal's save is a `useMutation`. */
function renderWithCareerStatusModal() {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter
        initialEntries={[
          { pathname: "/job-seeker/profile", state: { showCareerStatusModal: true } },
        ]}
      >
        <JobSeekerProfile />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

// ─── happy path ────────────────────────────────────────────────────────────────

describe("JobSeekerProfile - happy path", () => {
  it("renders the page heading", () => {
    renderJobSeekerProfile();
    expect(screen.getByText("Job Seeker Profile")).toBeInTheDocument();
  });

  it("shows Personal Info tab by default", () => {
    renderJobSeekerProfile();
    expect(screen.getByTestId("personal-info-tab")).toBeInTheDocument();
  });

  it("renders all four tab buttons", () => {
    renderJobSeekerProfile();
    expect(screen.getByRole("button", { name: /personal info/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /experience/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /education/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /performance/i })).toBeInTheDocument();
  });
});

// ─── tab switching ─────────────────────────────────────────────────────────────

describe("JobSeekerProfile - tab switching", () => {
  it("shows Experience tab when clicked", () => {
    renderJobSeekerProfile();
    fireEvent.click(screen.getByRole("button", { name: /experience/i }));
    expect(screen.getByTestId("experience-tab")).toBeInTheDocument();
  });

  it("shows Education tab when clicked", () => {
    renderJobSeekerProfile();
    fireEvent.click(screen.getByRole("button", { name: /education/i }));
    expect(screen.getByTestId("education-tab")).toBeInTheDocument();
  });

  it("shows Performance tab when clicked", () => {
    renderJobSeekerProfile();
    fireEvent.click(screen.getByRole("button", { name: /performance/i }));
    expect(screen.getByTestId("performance-tab")).toBeInTheDocument();
  });
});

// ─── URL param tab activation ──────────────────────────────────────────────────

describe("JobSeekerProfile - URL param", () => {
  it("activates experience tab from ?tab=experience query param", () => {
    renderJobSeekerProfile("?tab=experience");
    expect(screen.getByTestId("experience-tab")).toBeInTheDocument();
  });

  it("activates education tab from ?tab=education query param", () => {
    renderJobSeekerProfile("?tab=education");
    expect(screen.getByTestId("education-tab")).toBeInTheDocument();
  });
});

// ─── unsaved changes warning ───────────────────────────────────────────────────

describe("JobSeekerProfile - unsaved changes", () => {
  it("shows unsaved changes banner when isSaved is false", () => {
    mocks.profileForm.isSaved = false;
    renderJobSeekerProfile();
    expect(screen.getByText(/unsaved changes/i)).toBeInTheDocument();
  });

  it("does not show unsaved changes banner when isSaved is true", () => {
    mocks.profileForm.isSaved = true;
    renderJobSeekerProfile();
    expect(screen.queryByText(/unsaved changes/i)).toBeNull();
  });
});

// ─── save button ──────────────────────────────────────────────────────────────

describe("JobSeekerProfile - save button", () => {
  it("renders Save Profile button", () => {
    renderJobSeekerProfile();
    expect(screen.getByRole("button", { name: /save profile/i })).toBeInTheDocument();
  });

  it("shows 'Saving…' and disables button when isSaving is true", () => {
    mocks.profileForm.isSaving = true;
    renderJobSeekerProfile();
    expect(screen.getByRole("button", { name: /saving/i })).toBeDisabled();
  });
});

// ─── career status modal (G13) ────────────────────────────────────────────────

/**
 * Regression: a failed `PATCH /me/career-status` used to just re-enable the
 * buttons with no other feedback -- indistinguishable from the click not
 * having registered at all.
 */
describe("JobSeekerProfile - career status modal (G13)", () => {
  it("shows an inline alert and re-enables the buttons when the save fails", async () => {
    mocks.fetchWithAuth.mockRejectedValue(new ApiError("boom", { status: 403 }));
    renderWithCareerStatusModal();

    fireEvent.click(screen.getByRole("button", { name: /currently unemployed/i }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("We couldn't save that just now. Try again.");
    expect(screen.getByRole("button", { name: /currently unemployed/i })).not.toBeDisabled();
    expect(screen.getByRole("button", { name: /looking for my first job/i })).not.toBeDisabled();
    // The modal stays open -- there is nowhere else for this user to go.
    expect(screen.getByText("Where are you in your career?")).toBeInTheDocument();
    expect(mocks.navigate).not.toHaveBeenCalled();
  });

  it("navigates once a retried save succeeds", async () => {
    mocks.fetchWithAuth
      .mockRejectedValueOnce(new ApiError("boom", { status: 403 }))
      .mockResolvedValueOnce({});
    renderWithCareerStatusModal();

    fireEvent.click(screen.getByRole("button", { name: /currently unemployed/i }));
    await screen.findByRole("alert");

    fireEvent.click(screen.getByRole("button", { name: /currently unemployed/i }));
    await waitFor(() => expect(mocks.navigate).toHaveBeenCalledWith("/intelligence/paths"));
  });
});
