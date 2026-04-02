import { Plus, X } from "lucide-react";
import { ProfileFormData } from "../../types/profile";

const fieldCls =
  "w-full border border-cream-muted bg-cream-base px-3 py-2.5 text-sm text-ink-primary placeholder:text-ink-tertiary focus:border-forest-light focus:outline-none focus:ring-2 focus:ring-forest-pale transition-colors rounded-md";

type Props = {
  formData: ProfileFormData;
  addExperience: () => void;
  removeExperience: (id: number) => void;
  updateExperience: (id: number, field: string, value: string) => void;
  experienceLimitMsg: string;
  addSkill: (skill: string) => void;
  removeSkill: (skill: string) => void;
  skillLimitMsg: string;
};

export default function ExperienceTab({
  formData,
  addExperience,
  removeExperience,
  updateExperience,
  experienceLimitMsg,
  addSkill,
  removeSkill,
  skillLimitMsg,
}: Props) {
  return (
    <div className="space-y-6">
      <div className="bg-white rounded-xl shadow-sm border border-cream-muted p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-ink-primary font-display">Work Experience</h2>
          <button
            type="button"
            onClick={addExperience}
            className="flex items-center px-3 py-2 text-sm font-medium text-forest-light hover:text-forest-mid"
          >
            <Plus className="h-4 w-4 mr-1" />
            Add Experience
          </button>
        </div>

        {experienceLimitMsg && (
          <div className="p-2 mb-3 text-red-700 bg-red-50 border border-red-200 rounded">
            {experienceLimitMsg}
          </div>
        )}

        <div className="space-y-6">
          {formData.experience.map((exp, index) => {
            const isCurrent =
              (exp.endDate || "").toLowerCase() === "present" ||
              (exp.endDate || "").toLowerCase() === "current";
            const endDateValue = isCurrent ? "" : exp.endDate;

            return (
              <div key={exp.id} className="p-4 border border-cream-muted rounded-xl">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="font-medium text-ink-primary font-display">Experience #{index + 1}</h3>
                  <button
                    type="button"
                    onClick={() => removeExperience(exp.id)}
                    className="text-red-400 hover:text-red-600"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-ink-secondary mb-1">Company</label>
                    <input
                      type="text"
                      maxLength={50}
                      value={exp.company}
                      onChange={(e) => updateExperience(exp.id, "company", e.target.value)}
                      className={fieldCls}
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-ink-secondary mb-1">Position</label>
                    <input
                      type="text"
                      maxLength={50}
                      value={exp.position}
                      onChange={(e) => updateExperience(exp.id, "position", e.target.value)}
                      className={fieldCls}
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-ink-secondary mb-1">Start Date</label>
                    <input
                      type="month"
                      value={exp.startDate}
                      onChange={(e) => updateExperience(exp.id, "startDate", e.target.value)}
                      className={fieldCls}
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-ink-secondary mb-1">End Date</label>
                    <input
                      type="month"
                      value={endDateValue}
                      onChange={(e) => updateExperience(exp.id, "endDate", e.target.value)}
                      disabled={isCurrent}
                      className={fieldCls}
                      placeholder="Present"
                    />
                    <label className="mt-2 inline-flex items-center gap-2 text-sm text-ink-secondary">
                      <input
                        type="checkbox"
                        checked={isCurrent}
                        onChange={(e) =>
                          updateExperience(exp.id, "endDate", e.target.checked ? "Present" : "")
                        }
                        className="h-4 w-4 rounded border-cream-muted bg-transparent text-forest-light focus:ring-forest-pale"
                      />
                      I currently work here
                    </label>
                  </div>

                  <div className="md:col-span-2">
                    <label className="block text-sm font-medium text-ink-secondary mb-1">Description</label>
                    <textarea
                      rows={3}
                      maxLength={4000}
                      value={exp.description}
                      onChange={(e) => updateExperience(exp.id, "description", e.target.value)}
                      className={fieldCls}
                      placeholder="Describe your role, responsibilities, and achievements..."
                    />
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Skills Section */}
        <div className="mt-8 pt-6 border-t border-cream-muted">
          <h3 className="text-lg font-medium text-ink-primary font-display mb-4">Skills</h3>
          <div className="flex flex-wrap gap-2 mb-4">
            {formData.skills.map((skill) => (
              <span
                key={skill}
                className="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-forest-pale text-forest-dark"
              >
                {skill}
                <button
                  type="button"
                  onClick={() => removeSkill(skill)}
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
              placeholder="Add a skill (press Enter)"
              className="flex-1 border border-cream-muted bg-cream-base px-3 py-2.5 text-sm text-ink-primary placeholder:text-ink-tertiary focus:border-forest-light focus:outline-none focus:ring-2 focus:ring-forest-pale transition-colors rounded-l-md"
              onKeyPress={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  const target = e.target as HTMLInputElement;
                  addSkill(target.value);
                  target.value = "";
                }
              }}
            />
            <button
              type="button"
              className="px-4 py-2 bg-forest-dark text-white rounded-r-md hover:bg-forest-mid"
              onClick={(e) => {
                const input = (e.target as HTMLButtonElement).previousElementSibling as HTMLInputElement;
                addSkill(input.value);
                input.value = "";
              }}
            >
              Add
            </button>
          </div>
          {skillLimitMsg && (
            <div className="p-2 mt-3 text-red-700 bg-red-50 border border-red-200 rounded">
              {skillLimitMsg}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
