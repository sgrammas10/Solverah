import { useState, useEffect } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import { User, Briefcase, GraduationCap, Star, Brain } from "lucide-react";
import { useProfileForm } from "../hooks/useProfileForm";
import PersonalInfoTab from "../components/profile/PersonalInfoTab";
import ExperienceTab from "../components/profile/ExperienceTab";
import EducationTab from "../components/profile/EducationTab";
import PerformanceTab from "../components/profile/PerformanceTab";
import AssessmentsTab from "../components/profile/AssessmentsTab";

const tabs = [
  { id: "personal", label: "Personal Info", icon: User },
  { id: "experience", label: "Experience", icon: Briefcase },
  { id: "education", label: "Education", icon: GraduationCap },
  { id: "performance", label: "Performance", icon: Star },
  { id: "assessments", label: "Assessments", icon: Brain },
];

function JobSeekerProfile() {
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();

  const getTabFromURL = () => {
    const qs = new URLSearchParams(location.search);
    const fromSearch = qs.get("tab");
    if (fromSearch) return fromSearch;
    if (location.hash && location.hash.length > 1) return location.hash.slice(1);
    const st = (location.state as any) || {};
    if (st.initialTab) return st.initialTab;
    return null;
  };

  const [activeTab, setActiveTab] = useState<string>(() => getTabFromURL() || "personal");

  useEffect(() => {
    const incoming = getTabFromURL();
    if (incoming && incoming !== activeTab) setActiveTab(incoming);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.search, location.hash, location.state]);

  const profile = useProfileForm();

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
          />
        )}

        {activeTab === "performance" && <PerformanceTab formData={profile.formData} />}

        {activeTab === "assessments" && <AssessmentsTab formData={profile.formData} />}

        {/* Save Button */}
        <div className="pt-6">
          {profile.isSaving && (
            <div className="mb-4">
              <div className="text-xs uppercase tracking-[0.18em] text-forest-light">Saving profile</div>
              <div className="mt-2 h-2 w-full rounded-full bg-cream-subtle">
                <div
                  className="h-2 rounded-full bg-forest-light transition-all duration-300"
                  style={{ width: `${Math.min(100, Math.max(4, profile.saveProgress))}%` }}
                />
              </div>
            </div>
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
    </div>
  );
}

export default JobSeekerProfile;
