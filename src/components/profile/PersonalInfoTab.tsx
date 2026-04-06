import React from "react";
import { Upload, X } from "lucide-react";
import { ProfileFormData, PendingResumeUpload } from "../../types/profile";

const fieldCls =
  "w-full border border-cream-muted bg-cream-base px-3 py-2.5 text-sm text-ink-primary placeholder:text-ink-tertiary focus:border-forest-light focus:outline-none focus:ring-2 focus:ring-forest-pale transition-colors rounded-md";

type Props = {
  formData: ProfileFormData;
  handleChange: (field: string, value: any) => void;
  locationLimitMsg: string;
  addSecondaryLocation: (loc: string) => void;
  removeSecondaryLocation: (loc: string) => void;
  isUploadingResume: boolean;
  uploadProgress: number;
  uploadedResume: File | null;
  resumeUploaded: boolean;
  handleResumeUpload: (e: React.ChangeEvent<HTMLInputElement>) => void;
  handleViewResume: () => void;
  removeUploadedResume: () => void;
};

export default function PersonalInfoTab({
  formData,
  handleChange,
  locationLimitMsg,
  addSecondaryLocation,
  removeSecondaryLocation,
  isUploadingResume,
  uploadProgress,
  uploadedResume,
  resumeUploaded,
  handleResumeUpload,
  handleViewResume,
  removeUploadedResume,
}: Props) {
  return (
    <div className="space-y-6">
      <div className="bg-white rounded-xl shadow-sm border border-cream-muted p-6">
        <h2 className="text-lg font-semibold text-ink-primary font-display mb-4">Personal Information</h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <label className="block text-sm font-medium text-ink-secondary mb-2">First Name</label>
            <input
              type="text"
              maxLength={25}
              value={formData.firstName}
              onChange={(e) => handleChange("firstName", e.target.value)}
              className={fieldCls}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-ink-secondary mb-2">Last Name</label>
            <input
              type="text"
              maxLength={25}
              value={formData.lastName}
              onChange={(e) => handleChange("lastName", e.target.value)}
              className={fieldCls}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-ink-secondary mb-2">Email</label>
            <input
              type="email"
              maxLength={50}
              value={formData.email}
              onChange={(e) => handleChange("email", e.target.value)}
              className={fieldCls}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-ink-secondary mb-2">Phone</label>
            <input
              type="tel"
              maxLength={25}
              value={formData.phone}
              onChange={(e) => handleChange("phone", e.target.value)}
              className={fieldCls}
            />
          </div>

          <div className="md:col-span-2">
            <label className="block text-sm font-medium text-ink-secondary mb-2">LinkedIn Profile URL</label>
            <input
              type="url"
              maxLength={400}
              value={formData.linkedinUrl}
              onChange={(e) => handleChange("linkedinUrl", e.target.value)}
              className={fieldCls}
              placeholder="https://www.linkedin.com/in/your-profile"
            />
          </div>

          <div className="md:col-span-2">
            <label className="block text-sm font-medium text-ink-secondary mb-2">
              Primary Location (where you live)
            </label>
            <input
              type="text"
              maxLength={50}
              value={formData.primaryLocation}
              onChange={(e) => handleChange("primaryLocation", e.target.value)}
              className={fieldCls}
              placeholder="e.g., Annapolis, MD"
            />
          </div>

          <div className="md:col-span-2">
            <label className="block text-sm font-medium text-ink-secondary mb-2">Open to work locations</label>
            <div className="flex flex-wrap gap-2 mb-2">
              {formData.secondaryLocations.map((loc) => (
                <span
                  key={loc}
                  className="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-forest-pale text-forest-dark"
                >
                  {loc}
                  <button
                    type="button"
                    onClick={() => removeSecondaryLocation(loc)}
                    className="ml-2 text-forest-light hover:text-forest-mid"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </span>
              ))}
            </div>
            <div className="flex">
              <input
                type="text"
                maxLength={50}
                placeholder="Add a location (press Enter)"
                className="flex-1 border border-cream-muted bg-cream-base px-3 py-2.5 text-sm text-ink-primary placeholder:text-ink-tertiary focus:border-forest-light focus:outline-none focus:ring-2 focus:ring-forest-pale transition-colors rounded-l-md"
                onKeyPress={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    const target = e.target as HTMLInputElement;
                    addSecondaryLocation(target.value);
                    target.value = "";
                  }
                }}
              />
              <button
                type="button"
                className="px-4 py-2 bg-forest-dark text-white rounded-r-md hover:bg-forest-mid"
                onClick={(e) => {
                  const input = e.currentTarget.previousElementSibling as HTMLInputElement;
                  addSecondaryLocation(input.value);
                  input.value = "";
                }}
              >
                Add
              </button>
            </div>
            {locationLimitMsg && (
              <div className="mt-2 p-2 text-red-700 bg-red-50 border border-red-200 rounded text-sm">
                {locationLimitMsg}
              </div>
            )}
          </div>

          <div className="md:col-span-2">
            <label className="block text-sm font-medium text-ink-secondary mb-2">Professional Summary</label>
            <textarea
              rows={4}
              maxLength={4000}
              value={formData.summary}
              onChange={(e) => handleChange("summary", e.target.value)}
              className={fieldCls}
              placeholder="Brief summary of your professional background and career goals..."
            />
          </div>
        </div>

        {/* Resume Upload */}
        <div className="mt-6 pt-6 border-t border-cream-muted">
          <label className="block text-sm font-medium text-ink-secondary mb-2">Resume</label>

          {isUploadingResume && (
            <div className="mb-4">
              <div className="text-xs uppercase tracking-[0.18em] text-forest-light">Uploading resume</div>
              <div className="mt-2 h-2 w-full rounded-full bg-cream-subtle">
                <div
                  className="h-2 rounded-full bg-forest-light transition-all duration-300"
                  style={{ width: `${Math.min(100, Math.max(4, uploadProgress))}%` }}
                />
              </div>
            </div>
          )}

          {(uploadedResume || formData.uploadedResume) && (
            <div className="mb-4 p-3 bg-forest-pale border border-forest-light rounded-md">
              <div className="flex items-center justify-between">
                <div className="flex items-center">
                  <div className="flex-shrink-0">
                    <div className="w-8 h-8 bg-forest-pale rounded-full flex items-center justify-center">
                      <svg className="w-4 h-4 text-forest-light" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                      </svg>
                    </div>
                  </div>
                  <div className="ml-3">
                    <p className="text-sm font-medium text-forest-dark">
                      {uploadedResume?.name || formData.uploadedResume?.name || "Resume uploaded successfully"}
                    </p>
                    <p className="text-xs text-forest-light">
                      {uploadedResume
                        ? `${(uploadedResume.size / 1024 / 1024).toFixed(2)} MB`
                        : formData.uploadedResume
                        ? `${(formData.uploadedResume.size / 1024 / 1024).toFixed(2)} MB`
                        : "File processed"}
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={removeUploadedResume}
                  className="text-forest-light hover:text-forest-mid"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
              {formData.resumeKey && (
                <div className="mt-3 flex justify-end">
                  <button
                    type="button"
                    onClick={handleViewResume}
                    className="rounded-full border border-forest-light px-3 py-1 text-xs font-semibold text-forest-dark hover:border-forest-mid"
                  >
                    View Resume
                  </button>
                </div>
              )}
            </div>
          )}

          <div className="mt-1 flex justify-center px-6 pt-5 pb-6 border-2 border-cream-muted border-dashed rounded-md">
            <div className="space-y-1 text-center">
              <Upload className="mx-auto h-12 w-12 text-ink-tertiary" />
              <div className="flex text-sm text-ink-secondary">
                <label
                  htmlFor="resume-upload"
                  className="relative cursor-pointer bg-white rounded-md font-medium text-forest-light hover:text-forest-mid"
                >
                  <span>{uploadedResume || resumeUploaded ? "Replace resume" : "Upload your resume"}</span>
                  <input
                    id="resume-upload"
                    name="resume-upload"
                    type="file"
                    className="sr-only"
                    accept=".pdf,.doc,.docx"
                    onChange={handleResumeUpload}
                  />
                </label>
                <p className="pl-1">or drag and drop</p>
              </div>
              <p className="text-xs text-ink-secondary">PDF, DOC, DOCX up to 10MB</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
