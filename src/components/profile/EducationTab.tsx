import { Plus, X } from "lucide-react";
import { ProfileFormData } from "../../types/profile";

const fieldCls =
  "w-full border border-cream-muted bg-cream-base px-3 py-2.5 text-sm text-ink-primary placeholder:text-ink-tertiary focus:border-forest-light focus:outline-none focus:ring-2 focus:ring-forest-pale transition-colors rounded-md";

type Props = {
  formData: ProfileFormData;
  addEducation: () => void;
  removeEducation: (id: number) => void;
  updateEducation: (id: number, field: string, value: string) => void;
  educationLimitMsg: string;
};

export default function EducationTab({
  formData,
  addEducation,
  removeEducation,
  updateEducation,
  educationLimitMsg,
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
    </div>
  );
}
