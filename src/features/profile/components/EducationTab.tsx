import { Plus, X } from "lucide-react";
import { ProfileFormData, Certification } from "../types";

const fieldCls =
  "w-full border border-cream-muted bg-cream-base px-3 py-2.5 text-sm text-ink-primary placeholder:text-ink-tertiary focus:border-forest-light focus:outline-none focus:ring-2 focus:ring-forest-pale transition-colors rounded-md";

type Props = {
  formData: ProfileFormData;
  addEducation: () => void;
  removeEducation: (id: number) => void;
  updateEducation: (id: number, field: string, value: string) => void;
  educationLimitMsg: string;
  addCertification: () => void;
  removeCertification: (id: number) => void;
  updateCertification: (id: number, field: keyof Omit<Certification, "id">, value: string) => void;
  certificationLimitMsg: string;
};

export default function EducationTab({
  formData,
  addEducation,
  removeEducation,
  updateEducation,
  educationLimitMsg,
  addCertification,
  removeCertification,
  updateCertification,
  certificationLimitMsg,
}: Props) {
  return (
    <div className="space-y-6">
      <div className="bg-white rounded-xl shadow-sm border border-cream-muted p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-ink-primary font-display">Education</h2>
          <button
            type="button"
            onClick={addEducation}
            className="flex items-center px-3 py-2 text-sm font-medium text-forest-light hover:text-forest-mid"
          >
            <Plus className="h-4 w-4 mr-1" />
            Add Education
          </button>
        </div>

        {educationLimitMsg && (
          <div className="p-2 mb-3 text-red-700 bg-red-50 border border-red-200 rounded">
            {educationLimitMsg}
          </div>
        )}

        <div className="space-y-6">
          {formData.education.map((edu, index) => (
            <div key={edu.id} className="p-4 border border-cream-muted rounded-xl">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-medium text-ink-primary font-display">Education #{index + 1}</h3>
                <button
                  type="button"
                  onClick={() => removeEducation(edu.id)}
                  className="text-red-400 hover:text-red-600"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="md:col-span-2">
                  <label className="block text-sm font-medium text-ink-secondary mb-1">Institution</label>
                  <input
                    type="text"
                    maxLength={50}
                    value={edu.institution}
                    onChange={(e) => updateEducation(edu.id, "institution", e.target.value)}
                    className={fieldCls}
                  />
                </div>

                <div className="md:col-span-2">
                  <label className="block text-sm font-medium text-ink-secondary mb-1">Degree</label>
                  <input
                    type="text"
                    maxLength={50}
                    value={edu.degree}
                    onChange={(e) => updateEducation(edu.id, "degree", e.target.value)}
                    className={fieldCls}
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-ink-secondary mb-1">Start Date</label>
                  <input
                    type="month"
                    value={edu.startDate}
                    onChange={(e) => updateEducation(edu.id, "startDate", e.target.value)}
                    className={fieldCls}
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-ink-secondary mb-1">End Date</label>
                  <input
                    type="month"
                    value={edu.endDate}
                    onChange={(e) => updateEducation(edu.id, "endDate", e.target.value)}
                    className={fieldCls}
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-ink-secondary mb-1">GPA (Optional)</label>
                  <input
                    type="text"
                    maxLength={50}
                    value={edu.gpa}
                    onChange={(e) => updateEducation(edu.id, "gpa", e.target.value)}
                    className={fieldCls}
                    placeholder="3.8"
                  />
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Certifications */}
      <div className="bg-white rounded-xl shadow-sm border border-cream-muted p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-ink-primary font-display">Certifications</h2>
          <button
            type="button"
            onClick={addCertification}
            className="flex items-center px-3 py-2 text-sm font-medium text-forest-light hover:text-forest-mid"
          >
            <Plus className="h-4 w-4 mr-1" />
            Add Certification
          </button>
        </div>

        {certificationLimitMsg && (
          <div className="p-2 mb-3 text-red-700 bg-red-50 border border-red-200 rounded">
            {certificationLimitMsg}
          </div>
        )}

        <div className="space-y-6">
          {(formData.certifications ?? []).map((cert, index) => (
            <div key={cert.id} className="p-4 border border-cream-muted rounded-xl">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-medium text-ink-primary font-display">Certification #{index + 1}</h3>
                <button
                  type="button"
                  onClick={() => removeCertification(cert.id)}
                  className="text-red-400 hover:text-red-600"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="md:col-span-2">
                  <label className="block text-sm font-medium text-ink-secondary mb-1">Certification Name</label>
                  <input
                    type="text"
                    maxLength={100}
                    value={cert.name}
                    onChange={(e) => updateCertification(cert.id, "name", e.target.value)}
                    className={fieldCls}
                    placeholder="e.g. AWS Certified Solutions Architect"
                  />
                </div>

                <div className="md:col-span-2">
                  <label className="block text-sm font-medium text-ink-secondary mb-1">Issuing Organization</label>
                  <input
                    type="text"
                    maxLength={100}
                    value={cert.issuer}
                    onChange={(e) => updateCertification(cert.id, "issuer", e.target.value)}
                    className={fieldCls}
                    placeholder="e.g. Amazon Web Services"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-ink-secondary mb-1">Issue Date</label>
                  <input
                    type="month"
                    value={cert.issueDate}
                    onChange={(e) => updateCertification(cert.id, "issueDate", e.target.value)}
                    className={fieldCls}
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-ink-secondary mb-1">Expiry Date (Optional)</label>
                  <input
                    type="month"
                    value={cert.expiryDate}
                    onChange={(e) => updateCertification(cert.id, "expiryDate", e.target.value)}
                    className={fieldCls}
                  />
                </div>
              </div>
            </div>
          ))}

          {(formData.certifications ?? []).length === 0 && (
            <p className="text-sm text-ink-tertiary text-center py-4">
              No certifications added yet. Click "Add Certification" to get started.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
