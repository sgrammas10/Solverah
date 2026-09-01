import type { ReactNode } from "react";
import { renderHook, act } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import {
  buildDefaultProfile,
  normalizeProfileData,
  useProfileForm,
} from "../useProfileForm";
import { useAuth } from "../../contexts/useAuth";
import { useProfile, profileKeys } from "../useProfile";
import { useStartResumeParseJob, useResumeParseJobStatus } from "../useResumeParseJob";
import { createQueryClient } from "../../utils/queryClient";

vi.mock("../../contexts/useAuth");
// `profileKeys`/`seedProfileCache` stay real: `useProfileForm` invalidates the
// profile query by the actual key on a succeeded parse job, and a bare
// auto-mock would replace `profileKeys.document` (a function) with a `vi.fn()`
// returning undefined, breaking both the production call and any assertion
// against it.
vi.mock("../useProfile", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../useProfile")>();
  return { ...actual, useProfile: vi.fn() };
});
vi.mock("../useResumeParseJob");

const mockAuth = {
  user: null as any,
  updateProfile: vi.fn(),
  updateProfileData: vi.fn(),
  saveProfileData: vi.fn(),
  fetchWithAuth: vi.fn(),
  login: vi.fn(),
  register: vi.fn(),
  logout: vi.fn(),
  fetchProfile: vi.fn(),
};

/** The profile document the query hands back. Set per test before rendering. */
let mockProfile: Record<string, unknown> | undefined = {};

/** `useStartResumeParseJob()`'s return shape. `mutate` is asserted on directly. */
const mockStartResumeParseJob = {
  mutate: vi.fn(),
  isPending: false,
  isError: false,
  error: null as unknown,
};

/**
 * `useResumeParseJobStatus()`'s return shape, mutable so a test can move a job
 * through statuses across a `rerender()` the way real polling would.
 */
let mockResumeParseJobStatus: { data: any; error: unknown; isLoading: boolean } = {
  data: undefined,
  error: null,
  isLoading: false,
};

const mockUploadFetch = vi.fn();
globalThis.fetch = mockUploadFetch as any;

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useAuth).mockReturnValue(mockAuth as any);
  mockAuth.saveProfileData.mockResolvedValue({});
  mockAuth.fetchWithAuth.mockResolvedValue({});
  // The hook loads the document through useProfile() rather than by calling
  // fetchProfileData() on mount -- one source for the form, not two racing ones.
  mockProfile = {};
  vi.mocked(useProfile).mockImplementation(
    () => ({ data: mockProfile, isSuccess: true }) as any
  );
  mockStartResumeParseJob.isPending = false;
  mockStartResumeParseJob.isError = false;
  mockStartResumeParseJob.error = null;
  vi.mocked(useStartResumeParseJob).mockImplementation(() => mockStartResumeParseJob as any);
  mockResumeParseJobStatus = { data: undefined, error: null, isLoading: false };
  vi.mocked(useResumeParseJobStatus).mockImplementation(() => mockResumeParseJobStatus as any);
  mockUploadFetch.mockResolvedValue({ ok: true });
});

// ─── buildDefaultProfile ──────────────────────────────────────────────────────

describe("buildDefaultProfile", () => {
  it("returns a blank profile when no user is provided", () => {
    const p = buildDefaultProfile();
    expect(p.firstName).toBe("");
    expect(p.email).toBe("");
    expect(p.experience).toEqual([]);
    expect(p.skills).toEqual([]);
    expect(p.uploadedResume).toBeNull();
  });

  it("splits the user name into firstName and lastName", () => {
    const p = buildDefaultProfile({ name: "Ada Lovelace" });
    expect(p.firstName).toBe("Ada");
    expect(p.lastName).toBe("Lovelace");
  });

  it("handles single-word names by leaving lastName empty", () => {
    const p = buildDefaultProfile({ name: "Ada" });
    expect(p.firstName).toBe("Ada");
    expect(p.lastName).toBe("");
  });

  it("preserves a multi-word last name", () => {
    const p = buildDefaultProfile({ name: "Ada Byron Lovelace" });
    expect(p.firstName).toBe("Ada");
    expect(p.lastName).toBe("Byron Lovelace");
  });

  it("seeds email from user", () => {
    const p = buildDefaultProfile({ email: "ada@example.com" });
    expect(p.email).toBe("ada@example.com");
  });

  it("initialises all psychometric scores as null and incomplete", () => {
    const p = buildDefaultProfile();
    Object.values(p.psychometricResults).forEach((metric) => {
      expect(metric.score).toBeNull();
      expect(metric.completed).toBe(false);
    });
  });
});

// ─── normalizeProfileData ─────────────────────────────────────────────────────

describe("normalizeProfileData", () => {
  it("returns an empty object for null input", () => {
    expect(normalizeProfileData(null)).toEqual({});
  });

  it("returns an empty object for non-object input", () => {
    expect(normalizeProfileData("bad" as any)).toEqual({});
  });

  it("preserves known fields", () => {
    const result = normalizeProfileData({ firstName: "Ada", email: "ada@example.com" });
    expect(result.firstName).toBe("Ada");
    expect(result.email).toBe("ada@example.com");
  });

  it("defaults secondaryLocations to [] when missing", () => {
    const result = normalizeProfileData({ firstName: "Ada" });
    expect(result.secondaryLocations).toEqual([]);
  });

  it("migrates legacy location field to primaryLocation", () => {
    const result = normalizeProfileData({ location: "New York" } as any);
    expect(result.primaryLocation).toBe("New York");
  });

  it("prefers explicit primaryLocation over legacy location", () => {
    const result = normalizeProfileData({ location: "Old", primaryLocation: "New York" } as any);
    expect(result.primaryLocation).toBe("New York");
  });
});

// ─── useProfileForm — collection management ───────────────────────────────────

/** Wraps every renderHook in a real QueryClientProvider -- useProfileForm now
 *  calls useQueryClient() directly for the resume-parse-job cache invalidation. */
function createWrapper() {
  const queryClient = createQueryClient();
  const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { Wrapper, invalidateSpy };
}

async function setup() {
  const { Wrapper } = createWrapper();
  const { result } = renderHook(() => useProfileForm(), { wrapper: Wrapper });
  await act(async () => {}); // flush mount effects
  return result;
}

/** Like `setup`, but also exposes `rerender` and the invalidation spy, for
 *  tests that move a mocked resume-parse-job status across renders. */
async function setupWithControls() {
  const { Wrapper, invalidateSpy } = createWrapper();
  const { result, rerender } = renderHook(() => useProfileForm(), { wrapper: Wrapper });
  await act(async () => {});
  return { result, rerender, invalidateSpy };
}

describe("useProfileForm - experience", () => {
  it("adds a new blank experience entry", async () => {
    const result = await setup();
    act(() => { result.current.addExperience(); });
    expect(result.current.formData.experience).toHaveLength(1);
  });

  it("removes an experience entry by id", async () => {
    const result = await setup();
    act(() => { result.current.addExperience(); });
    const id = result.current.formData.experience[0].id;
    act(() => { result.current.removeExperience(id); });
    expect(result.current.formData.experience).toHaveLength(0);
  });

  it("updates a field on an experience entry", async () => {
    const result = await setup();
    act(() => { result.current.addExperience(); });
    const id = result.current.formData.experience[0].id;
    act(() => { result.current.updateExperience(id, "company", "Acme"); });
    expect(result.current.formData.experience[0].company).toBe("Acme");
  });

  it("sets a limit message and blocks adding beyond MAX_EXPERIENCES (20)", async () => {
    const result = await setup();
    act(() => {
      for (let i = 0; i < 20; i++) result.current.addExperience();
    });
    act(() => { result.current.addExperience(); });
    expect(result.current.formData.experience).toHaveLength(20);
    expect(result.current.experienceLimitMsg).toMatch(/maximum/i);
  });
});

describe("useProfileForm - skills", () => {
  it("adds a skill", async () => {
    const result = await setup();
    act(() => { result.current.addSkill("TypeScript"); });
    expect(result.current.formData.skills).toContain("TypeScript");
  });

  it("does not add a duplicate skill", async () => {
    const result = await setup();
    act(() => {
      result.current.addSkill("TypeScript");
      result.current.addSkill("TypeScript");
    });
    expect(result.current.formData.skills).toHaveLength(1);
  });

  it("removes a skill", async () => {
    const result = await setup();
    act(() => { result.current.addSkill("TypeScript"); });
    act(() => { result.current.removeSkill("TypeScript"); });
    expect(result.current.formData.skills).not.toContain("TypeScript");
  });

  it("ignores empty string skill", async () => {
    const result = await setup();
    act(() => { result.current.addSkill(""); });
    expect(result.current.formData.skills).toHaveLength(0);
  });

  it("sets a limit message and blocks adding beyond MAX_SKILLS (50)", async () => {
    const result = await setup();
    act(() => {
      for (let i = 0; i < 50; i++) result.current.addSkill(`Skill${i}`);
    });
    act(() => { result.current.addSkill("OneMore"); });
    expect(result.current.formData.skills).toHaveLength(50);
    expect(result.current.skillLimitMsg).toMatch(/maximum/i);
  });
});

describe("useProfileForm - education", () => {
  it("adds a new blank education entry", async () => {
    const result = await setup();
    act(() => { result.current.addEducation(); });
    expect(result.current.formData.education).toHaveLength(1);
  });

  it("removes an education entry by id", async () => {
    const result = await setup();
    act(() => { result.current.addEducation(); });
    const id = result.current.formData.education[0].id;
    act(() => { result.current.removeEducation(id); });
    expect(result.current.formData.education).toHaveLength(0);
  });

  it("sets a limit message and blocks adding beyond MAX_EDUCATIONS (10)", async () => {
    const result = await setup();
    act(() => {
      for (let i = 0; i < 10; i++) result.current.addEducation();
    });
    act(() => { result.current.addEducation(); });
    expect(result.current.formData.education).toHaveLength(10);
    expect(result.current.educationLimitMsg).toMatch(/maximum/i);
  });
});

describe("useProfileForm - secondary locations", () => {
  it("adds a location", async () => {
    const result = await setup();
    act(() => { result.current.addSecondaryLocation("Austin, TX"); });
    expect(result.current.formData.secondaryLocations).toContain("Austin, TX");
  });

  it("trims whitespace before adding", async () => {
    const result = await setup();
    act(() => { result.current.addSecondaryLocation("  Austin, TX  "); });
    expect(result.current.formData.secondaryLocations).toContain("Austin, TX");
  });

  it("does not add a duplicate location", async () => {
    const result = await setup();
    act(() => {
      result.current.addSecondaryLocation("Austin, TX");
      result.current.addSecondaryLocation("Austin, TX");
    });
    expect(result.current.formData.secondaryLocations).toHaveLength(1);
  });

  it("ignores blank input", async () => {
    const result = await setup();
    act(() => { result.current.addSecondaryLocation("   "); });
    expect(result.current.formData.secondaryLocations).toHaveLength(0);
  });

  it("removes a location", async () => {
    const result = await setup();
    act(() => { result.current.addSecondaryLocation("Austin, TX"); });
    act(() => { result.current.removeSecondaryLocation("Austin, TX"); });
    expect(result.current.formData.secondaryLocations).not.toContain("Austin, TX");
  });

  it("sets a limit message and blocks adding beyond MAX_SECONDARY_LOCATIONS (20)", async () => {
    const result = await setup();
    act(() => {
      for (let i = 0; i < 20; i++) result.current.addSecondaryLocation(`City${i}`);
    });
    act(() => { result.current.addSecondaryLocation("OneMore"); });
    expect(result.current.formData.secondaryLocations).toHaveLength(20);
    expect(result.current.locationLimitMsg).toMatch(/maximum/i);
  });
});

describe("useProfileForm - handleChange", () => {
  it("updates the named field", async () => {
    const result = await setup();
    act(() => { result.current.handleChange("summary", "Hello world"); });
    expect(result.current.formData.summary).toBe("Hello world");
  });

  it("marks isSaved as false after a change", async () => {
    const result = await setup();
    act(() => { result.current.handleChange("summary", "Hello"); });
    expect(result.current.isSaved).toBe(false);
  });

  it("syncs location when primaryLocation changes", async () => {
    const result = await setup();
    act(() => { result.current.handleChange("primaryLocation", "Chicago"); });
    expect(result.current.formData.location).toBe("Chicago");
  });
});

describe("useProfileForm - removeUploadedResume", () => {
  it("clears resume state and marks isSaved false", async () => {
    const result = await setup();
    act(() => {
      result.current.setFormData((prev: any) => ({
        ...prev,
        uploadedResume: { name: "cv.pdf", size: 1000, type: "application/pdf" },
        resumeKey: "some-key",
      }));
    });
    act(() => { result.current.removeUploadedResume(); });
    expect(result.current.formData.uploadedResume).toBeNull();
    expect(result.current.formData.resumeKey).toBeNull();
    expect(result.current.resumeUploaded).toBe(false);
    expect(result.current.pendingResume).toBeNull();
    expect(result.current.isSaved).toBe(false);
  });
});

// ─── useProfileForm — async resume-parse job ──────────────────────────────────

function uploadedFile() {
  return new File(["%PDF-1.4"], "resume.pdf", { type: "application/pdf" });
}

describe("useProfileForm - resume parse job", () => {
  it("starts a parse job with the schema fields after upload, and never calls the old /complete endpoint", async () => {
    mockAuth.fetchWithAuth.mockResolvedValueOnce({
      resume_id: "resume-1",
      upload_url: "https://uploads.example.com/resume-1",
      max_bytes: 10_000_000,
    });
    const result = await setup();
    const file = uploadedFile();

    await act(async () => {
      await result.current.handleResumeUpload({ target: { files: [file] } } as any);
    });

    expect(mockStartResumeParseJob.mutate).toHaveBeenCalledWith(
      { resumeId: "resume-1", mime: "application/pdf", size: file.size, name: "resume.pdf" },
      expect.objectContaining({ onSuccess: expect.any(Function) })
    );
    expect(mockAuth.fetchWithAuth).not.toHaveBeenCalledWith(
      expect.stringContaining("/complete"),
      expect.anything()
    );
  });

  it("merges a succeeded job's profile into formData, leaves isSaved unchanged, and invalidates the profile query", async () => {
    const { result, rerender, invalidateSpy } = await setupWithControls();
    expect(result.current.isSaved).toBe(true);

    mockResumeParseJobStatus = {
      data: {
        job_id: "job-1",
        status: "succeeded",
        profile: { firstName: "Ada", skills: ["Rust"] },
        error: null,
      },
      error: null,
      isLoading: false,
    };
    await act(async () => { rerender(); });

    expect(result.current.formData.firstName).toBe("Ada");
    expect(result.current.formData.skills).toEqual(["Rust"]);
    // The server already persisted this merge (resume_jobs.py's run(), before
    // the job is marked succeeded) -- there is nothing pending to save, so
    // this must NOT flip the unsaved-changes banner on.
    expect(result.current.isSaved).toBe(true);
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: profileKeys.document() });
  });

  it("clears the parse job (and its status) when the resume is removed", async () => {
    mockAuth.fetchWithAuth.mockResolvedValueOnce({
      resume_id: "resume-42",
      upload_url: "https://uploads.example.com/resume-42",
      max_bytes: 10_000_000,
    });
    const { result, rerender } = await setupWithControls();

    await act(async () => {
      await result.current.handleResumeUpload({ target: { files: [uploadedFile()] } } as any);
    });
    const onSuccess = mockStartResumeParseJob.mutate.mock.calls[0][1].onSuccess;
    act(() => onSuccess({ job_id: "job-42", status: "queued", status_url: "" }));

    mockResumeParseJobStatus = {
      data: { job_id: "job-42", status: "queued", profile: null, error: null },
      error: null,
      isLoading: false,
    };
    await act(async () => { rerender(); });
    expect(result.current.resumeParseStatus).toEqual({ phase: "queued" });

    act(() => { result.current.removeUploadedResume(); });
    expect(result.current.resumeParseStatus).toEqual({ phase: "idle" });
  });

  it("handleSubmit no longer touches the old alert/try-catch resume-complete path", async () => {
    const result = await setup();
    const alertSpy = vi.spyOn(window, "alert").mockImplementation(() => {});

    await act(async () => {
      await result.current.handleSubmit({ preventDefault: () => {} } as any);
    });

    expect(alertSpy).not.toHaveBeenCalled();
    expect(mockAuth.fetchWithAuth).not.toHaveBeenCalledWith(
      expect.stringContaining("/complete"),
      expect.anything()
    );
    alertSpy.mockRestore();
  });
});
