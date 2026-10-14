import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import JobSeekerProfile from "./JobSeekerProfile";
import { createQueryClient } from "../../../shared/api/queryClient";
import { ApiError } from "../../../shared/api/apiError";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  /** The options JobSeekerProfile passed to useProfileForm (its onSaved). */
  formOptions: undefined as undefined | { onSaved?: (saved: any) => void },
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
    saveBarVisible: false,
    saveError: null as string | null,
    resumeFileError: null as string | null,
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
  useProfileForm: (options?: { onSaved?: (saved: any) => void }) => {
    mocks.formOptions = options;
    return mocks.profileForm;
  },
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

beforeEach(() => {
  vi.clearAllMocks();
  mocks.profileForm.isSaved = true;
  mocks.profileForm.isSaving = false;
  mocks.profileForm.saveBarVisible = false;
  mocks.profileForm.saveProgress = 0;
  mocks.profileForm.saveError = null;
});

/** The page calls useQueryClient() itself now (it drops the dashboard and the
 *  Situation Report after a save), so every render needs a client. */
function renderJobSeekerProfile(search = "", client = createQueryClient()) {
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[{ pathname: "/job-seeker/profile", search }]}>
        <JobSeekerProfile />
      </MemoryRouter>
    </QueryClientProvider>
  );
  return client;
}

/** Navigated here with the modal already open, as `EnvironmentReportPage`'s
 *  "Set your career status" button does. Needs a real query client -- the
 *  modal's save is a `useMutation`. */
function renderWithCareerStatusModal(
  state: Record<string, unknown> = { showCareerStatusModal: true },
  client = createQueryClient(),
) {
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={[
          { pathname: "/job-seeker/profile", state },
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

  it("renders all three tab buttons", () => {
    renderJobSeekerProfile();
    expect(screen.getByRole("button", { name: /personal info/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /experience/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /education/i })).toBeInTheDocument();
  });

  it("no longer renders a Performance tab (dead UI removal)", () => {
    renderJobSeekerProfile();
    expect(screen.queryByRole("button", { name: /performance/i })).toBeNull();
    expect(screen.queryByTestId("performance-tab")).toBeNull();
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

  it("falls back to Personal Info for an unknown ?tab= (G12)", () => {
    // Used to become the active tab: no tab highlighted and an empty page.
    renderJobSeekerProfile("?tab=nonsense");
    expect(screen.getByTestId("personal-info-tab")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /personal info/i }).className).toContain(
      "border-forest-light",
    );
  });

  it("falls back to Personal Info for the removed ?tab=performance (G12)", () => {
    renderJobSeekerProfile("?tab=performance");
    expect(screen.getByTestId("personal-info-tab")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /personal info/i }).className).toContain(
      "border-forest-light",
    );
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

  it("shows a failed save as an alert by the button (audit item 5)", () => {
    mocks.profileForm.saveError = "We couldn't save your profile. Your changes are still here, so try again.";
    renderJobSeekerProfile();
    expect(screen.getByRole("alert")).toHaveTextContent("We couldn't save your profile.");
    expect(screen.queryByText("Saved")).toBeNull();
  });

  it("drops the dashboard and the Situation Report after a save (audit items 6, 7)", () => {
    const client = renderJobSeekerProfile();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    act(() => {
      mocks.formOptions?.onSaved?.({ ...mocks.profileForm.formData });
    });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["dashboard"] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["situationReport"] });
  });

  it("keeps the save bar on screen at 100% after the save finishes", () => {
    mocks.profileForm.isSaving = false;
    mocks.profileForm.saveBarVisible = true;
    mocks.profileForm.saveProgress = 100;
    renderJobSeekerProfile();
    expect(screen.getByText("Saved")).toBeInTheDocument();
    expect(document.querySelector('[style*="width: 100%"]')).not.toBeNull();
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

  it("drops the dashboard and Situation Report once a status is saved", async () => {
    mocks.fetchWithAuth.mockResolvedValueOnce({});
    const client = createQueryClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    renderWithCareerStatusModal({ showCareerStatusModal: true }, client);

    fireEvent.click(screen.getByRole("button", { name: /currently unemployed/i }));

    await waitFor(() => expect(mocks.navigate).toHaveBeenCalledWith("/intelligence/paths"));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["dashboard"] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["situationReport"] });
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

// ─── career status: offer the way back ────────────────────────────────────────

const RETURN_STATE = {
  showCareerStatusModal: true,
  returnTo: { path: "/intelligence/paths", label: "Path Intelligence" },
};

describe("JobSeekerProfile - return after setting career status", () => {
  it.each([
    [/currently unemployed/i, "between_jobs"],
    [/looking for my first job/i, "first_job"],
  ])("offers to go back after %s is saved", async (button, status) => {
    mocks.fetchWithAuth.mockResolvedValueOnce({});
    renderWithCareerStatusModal(RETURN_STATE);

    fireEvent.click(screen.getByRole("button", { name: button }));

    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("Status saved.");
    expect(dialog).toHaveTextContent("Go back to Path Intelligence?");
    expect(mocks.fetchWithAuth).toHaveBeenCalledWith("/me/career-status", {
      method: "PATCH",
      body: JSON.stringify({ status }),
    });
    // The modal is gone and nothing has navigated on the user's behalf.
    expect(screen.queryByText("Where are you in your career?")).toBeNull();
    expect(mocks.navigate).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /go back/i }));
    expect(mocks.navigate).toHaveBeenCalledWith("/intelligence/paths");
  });

  it("Stay here closes the dialog and goes nowhere", async () => {
    mocks.fetchWithAuth.mockResolvedValueOnce({});
    renderWithCareerStatusModal(RETURN_STATE);
    fireEvent.click(screen.getByRole("button", { name: /currently unemployed/i }));
    await screen.findByRole("dialog");

    fireEvent.click(screen.getByRole("button", { name: /stay here/i }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(mocks.navigate).not.toHaveBeenCalled();
  });

  it("offers to go back after an employed save (a current role)", async () => {
    renderWithCareerStatusModal(RETURN_STATE);
    // The user closes the modal to tick "I currently work here" and saves.
    fireEvent.click(screen.getByRole("button", { name: /close/i }));
    act(() => {
      mocks.formOptions?.onSaved?.({ ...mocks.profileForm.formData, career_status: "employed" });
    });

    expect(screen.getByRole("dialog")).toHaveTextContent("Go back to Path Intelligence?");
    fireEvent.click(screen.getByRole("button", { name: /go back/i }));
    expect(mocks.navigate).toHaveBeenCalledWith("/intelligence/paths");
  });

  it("does not ask after an ordinary save that set no career status", () => {
    renderWithCareerStatusModal(RETURN_STATE);
    act(() => {
      mocks.formOptions?.onSaved?.({ ...mocks.profileForm.formData });
    });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("does not ask after an employed save when nobody sent the user here", () => {
    renderJobSeekerProfile();
    act(() => {
      mocks.formOptions?.onSaved?.({ ...mocks.profileForm.formData, career_status: "employed" });
    });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("ignores a returnTo that points off-site", async () => {
    mocks.fetchWithAuth.mockResolvedValueOnce({});
    renderWithCareerStatusModal({
      showCareerStatusModal: true,
      returnTo: { path: "//evil.example", label: "Evil" },
    });
    fireEvent.click(screen.getByRole("button", { name: /currently unemployed/i }));
    // Falls back to the old behaviour.
    await waitFor(() => expect(mocks.navigate).toHaveBeenCalledWith("/intelligence/paths"));
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
