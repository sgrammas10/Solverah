import { useState, useEffect } from "react";
import { useLocation, useSearchParams, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { User, Briefcase, GraduationCap, Star, X } from "lucide-react";
import { useProfileForm } from "../useProfileForm";
import { readCareerStatusReturnTo } from "../../../shared/lib/careerStatusReturn";
import CareerStatusReturnDialog from "./CareerStatusReturnDialog";
import { invalidateProfileDependents, useSetCareerStatus } from "./useSetCareerStatus";
import PersonalInfoTab from "./PersonalInfoTab";
import ExperienceTab from "./ExperienceTab";
import EducationTab from "./EducationTab";
import PerformanceTab from "./PerformanceTab";

const tabs = [
  { id: "personal", label: "Personal Info", icon: User },
  { id: "experience", label: "Experience", icon: Briefcase },
  { id: "education", label: "Education", icon: GraduationCap },
  { id: "performance", label: "Performance", icon: Star },
];

const DEFAULT_TAB = "personal";

/** A tab id this page can render, or null. An unknown `?tab=` (or hash, or
 *  router state) used to become the active tab and render an empty page with
 *  no tab highlighted (G12). */
function knownTab(value: unknown): string | null {
  return typeof value === "string" && tabs.some((tab) => tab.id === value) ? value : null;
}

// ---------------------------------------------------------------------------
// Career Status Modal
// ---------------------------------------------------------------------------

interface CareerStatusModalProps {
  onDismiss: () => void;
  /** Runs after the status is saved. */
  onSaved: () => void;
}

function CareerStatusModal({ onDismiss, onSaved }: CareerStatusModalProps) {
  // The same write as the Experience tab's control: it puts the status in the
  // cached profile document (the page the user goes back to reads it there,
  // and a stale copy would put the same prompt straight back in front of
  // them), then drops the dashboard and Situation Report. A failure shows the
  // alert below and re-enables the buttons.
  const selectStatus = useSetCareerStatus({ onSaved });

  const loading = selectStatus.isPending;
  const handleSelect = (status: "between_jobs" | "first_job") => selectStatus.mutate(status);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center px-4">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-ink-primary/50" onClick={onDismiss} />

      {/* Modal card */}
      <div className="relative z-10 w-full max-w-md bg-white rounded-2xl shadow-2xl overflow-hidden">
        <div className="px-6 py-5 border-b border-cream-muted flex items-start justify-between gap-4">
          <div>
            <p className="font-semibold text-ink-primary font-display">
              Where are you in your career?
            </p>
            <p className="text-sm text-ink-secondary mt-0.5">
              We need this to generate your path suggestions.
            </p>
          </div>
          <button
            type="button"
            onClick={onDismiss}
            aria-label="Close"
            className="shrink-0 p-1 text-ink-tertiary hover:text-ink-primary transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="px-6 py-5 space-y-4">
          <p className="text-sm text-ink-secondary leading-relaxed">
            If you're currently employed, check{" "}
            <span className="font-medium text-ink-primary">I currently work here</span> on your
            most recent role below and save your profile.
          </p>
          <p className="text-sm text-ink-secondary">Or select your status now:</p>

          <div className="space-y-2">
            <button
              type="button"
              disabled={loading}
              onClick={() => handleSelect("between_jobs")}
              className="w-full text-left rounded-lg border border-cream-muted bg-cream-base hover:bg-cream-subtle px-4 py-3 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <p className="font-medium text-sm text-ink-primary">Currently unemployed</p>
              <p className="text-xs text-ink-secondary mt-0.5">
                You're between roles and actively looking
              </p>
            </button>

            <button
              type="button"
              disabled={loading}
              onClick={() => handleSelect("first_job")}
              className="w-full text-left rounded-lg border border-cream-muted bg-cream-base hover:bg-cream-subtle px-4 py-3 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <p className="font-medium text-sm text-ink-primary">Looking for my first job</p>
              <p className="text-xs text-ink-secondary mt-0.5">
                You're early in your career and seeking an entry-level role
              </p>
            </button>
          </div>

          {selectStatus.isError && (
            <p role="alert" className="text-sm text-red-700 pt-2">
              We couldn't save that just now. Try again.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

function JobSeekerProfile() {
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();

  const getTabFromURL = () => {
    const qs = new URLSearchParams(location.search);
    const fromSearch = knownTab(qs.get("tab"));
    if (fromSearch) return fromSearch;
    const fromHash = location.hash && location.hash.length > 1 ? knownTab(location.hash.slice(1)) : null;
    if (fromHash) return fromHash;
    const st = (location.state as any) || {};
    return knownTab(st.initialTab);
  };

  const [activeTab, setActiveTab] = useState<string>(() => getTabFromURL() || DEFAULT_TAB);
  const [showCareerStatusModal, setShowCareerStatusModal] = useState<boolean>(
    () => !!(location.state as any)?.showCareerStatusModal
  );
  // Where the user was sent from to set a career status, if anywhere. Cleared
  // once they have answered the "go back?" dialog, so later saves don't ask.
  const [returnTo, setReturnTo] = useState(() => readCareerStatusReturnTo(location.state));
  const [showReturnDialog, setShowReturnDialog] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    const incoming = getTabFromURL();
    if (incoming && incoming !== activeTab) setActiveTab(incoming);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.search, location.hash, location.state]);

  const queryClient = useQueryClient();
  const profile = useProfileForm({
    // The employed path: saving a profile with a current role, when no status
    // is stored yet, sets career_status "employed" (useProfileForm.handleSubmit).
    onSaved: (saved) => {
      // A save can change career_status and everything the dashboard's next
      // steps read; neither cached read was ever dropped (audit items 6, 7).
      void invalidateProfileDependents(queryClient);
      if (returnTo && saved.career_status === "employed") {
        setShowCareerStatusModal(false);
        setShowReturnDialog(true);
      }
    },
  });

  const handleCareerStatusSaved = () => {
    setShowCareerStatusModal(false);
    if (returnTo) {
      setShowReturnDialog(true);
    } else {
      navigate("/intelligence/paths");
    }
  };

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8 text-ink-primary font-sans bg-cream-base">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-ink-primary font-display">Job Seeker Profile</h1>
        <p className="text-ink-secondary mt-2">
          Complete your profile to get better job matches and increase visibility to recruiters.
        </p>
      </div>

      {/* Tab Navigation */}
      <div className="border-b border-cream-muted mb-8">
        <nav className="-mb-px flex space-x-8">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                type="button"
                key={tab.id}
                onClick={() => {
                  setActiveTab(tab.id);
                  const next = new URLSearchParams(searchParams);
                  next.set("tab", tab.id);
                  setSearchParams(next, { replace: true });
                }}
                className={`flex items-center py-4 px-1 border-b-2 font-medium text-sm ${
                  activeTab === tab.id
                    ? "border-forest-light text-forest-mid"
                    : "border-transparent text-ink-secondary hover:text-forest-mid hover:border-forest-pale"
                }`}
              >
                <Icon className="h-5 w-5 mr-2" />
                {tab.label}
              </button>
            );
          })}
        </nav>
      </div>

      {!profile.isSaved && (
        <div className="mb-4 p-3 bg-amber-50 border border-amber-200 text-amber-900 rounded-md text-sm">
          You have unsaved changes — don't forget to click <b>Save Profile</b>.
        </div>
      )}

      <form onSubmit={profile.handleSubmit}>
        {activeTab === "personal" && (
          <PersonalInfoTab
            formData={profile.formData}
            handleChange={profile.handleChange}
            locationLimitMsg={profile.locationLimitMsg}
            addSecondaryLocation={profile.addSecondaryLocation}
            removeSecondaryLocation={profile.removeSecondaryLocation}
            isUploadingResume={profile.isUploadingResume}
            uploadProgress={profile.uploadProgress}
            uploadedResume={profile.uploadedResume}
            resumeUploaded={profile.resumeUploaded}
            resumeParseStatus={profile.resumeParseStatus}
            resumeFileError={profile.resumeFileError}
            handleResumeUpload={profile.handleResumeUpload}
            handleViewResume={profile.handleViewResume}
            removeUploadedResume={profile.removeUploadedResume}
          />
        )}

        {activeTab === "experience" && (
          <ExperienceTab
            formData={profile.formData}
            addExperience={profile.addExperience}
            removeExperience={profile.removeExperience}
            updateExperience={profile.updateExperience}
            experienceLimitMsg={profile.experienceLimitMsg}
            addSkill={profile.addSkill}
            removeSkill={profile.removeSkill}
            updateSkillLevel={profile.updateSkillLevel}
            skillLimitMsg={profile.skillLimitMsg}
          />
        )}

        {activeTab === "education" && (
          <EducationTab
            formData={profile.formData}
            addEducation={profile.addEducation}
            removeEducation={profile.removeEducation}
            updateEducation={profile.updateEducation}
            educationLimitMsg={profile.educationLimitMsg}
            addCertification={profile.addCertification}
            removeCertification={profile.removeCertification}
            updateCertification={profile.updateCertification}
            certificationLimitMsg={profile.certificationLimitMsg}
          />
        )}

        {activeTab === "performance" && <PerformanceTab formData={profile.formData} />}

        {/* Save Button */}
        <div className="pt-6">
          {profile.saveBarVisible && (
            <div className="mb-4">
              <div className="text-sm text-ink-secondary">
                {profile.isSaving ? "Saving profile" : "Saved"}
              </div>
              <div className="mt-2 h-2 w-full rounded-full bg-cream-subtle">
                <div
                  className="h-2 rounded-full bg-forest-light transition-all duration-300"
                  style={{ width: `${Math.min(100, Math.max(4, profile.saveProgress))}%` }}
                />
              </div>
            </div>
          )}
          {profile.saveError && (
            <p role="alert" className="mb-4 p-3 text-sm text-red-700 bg-red-50 border border-red-200 rounded-md">
              {profile.saveError}
            </p>
          )}
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={profile.isSaving}
              className="px-6 py-3 bg-forest-dark text-white rounded-md hover:bg-forest-mid disabled:opacity-50 disabled:cursor-not-allowed font-medium"
            >
              {profile.isSaving ? "Saving..." : "Save Profile"}
            </button>
          </div>
        </div>
      </form>

      {/* Career Status Modal — shown when navigated here from Path Intelligence */}
      {showCareerStatusModal && (
        <CareerStatusModal
          onDismiss={() => setShowCareerStatusModal(false)}
          onSaved={handleCareerStatusSaved}
        />
      )}

      {showReturnDialog && returnTo && (
        <CareerStatusReturnDialog
          label={returnTo.label}
          onGoBack={() => navigate(returnTo.path)}
          onStay={() => {
            setShowReturnDialog(false);
            setReturnTo(null);
          }}
        />
      )}
    </div>
  );
}

export default JobSeekerProfile;
