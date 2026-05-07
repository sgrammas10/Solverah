import { renderHook, act, waitFor } from "@testing-library/react";
import {
  buildDefaultProfile,
  normalizeProfileData,
  useProfileForm,
} from "../useProfileForm";
import { useAuth } from "../../contexts/useAuth";

vi.mock("../../contexts/useAuth");

const mockAuth = {
  user: null as any,
  updateProfile: vi.fn(),
  updateProfileData: vi.fn(),
  fetchProfileData: vi.fn(),
  saveProfileData: vi.fn(),
  fetchWithAuth: vi.fn(),
  login: vi.fn(),
  register: vi.fn(),
  logout: vi.fn(),
  fetchProfile: vi.fn(),
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useAuth).mockReturnValue(mockAuth as any);
  mockAuth.fetchProfileData.mockResolvedValue({ profileData: null });
  mockAuth.saveProfileData.mockResolvedValue({});
  mockAuth.fetchWithAuth.mockResolvedValue({});
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

async function setup() {
  const { result } = renderHook(() => useProfileForm());
  await act(async () => {}); // flush mount effects
  return result;
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
