import { Plus, Star } from "lucide-react";
import { ProfileFormData } from "../../types/profile";

type Props = {
  formData: ProfileFormData;
};

export default function PerformanceTab({ formData }: Props) {
  return (
    <div className="space-y-6">
      <div className="bg-white rounded-xl shadow-sm border border-cream-muted p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-ink-primary font-display">Performance Reviews</h2>
          <button
            type="button"
            className="flex items-center px-3 py-2 text-sm font-medium text-forest-light hover:text-forest-mid"
          >
            <Plus className="h-4 w-4 mr-1" />
            Add Review
          </button>
        </div>

        <div className="space-y-6">
          {formData.performanceReviews.map((review) => (
            <div key={review.id} className="p-4 bg-cream-subtle rounded-xl">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <h3 className="font-medium text-ink-primary font-display">{review.company}</h3>
                  <p className="text-sm text-ink-secondary">{review.period}</p>
                </div>
                <div className="flex items-center">
                  <Star className="h-5 w-5 text-amber-300 mr-1" />
                  <span className="text-lg font-semibold text-ink-primary">{review.rating}</span>
                  <span className="text-ink-secondary">/5</span>
                </div>
              </div>

              <p className="text-ink-secondary mb-3">{review.summary}</p>

              <div>
                <h4 className="font-medium text-ink-primary mb-2">Key Achievements:</h4>
                <ul className="list-disc list-inside space-y-1">
                  {(review.keyAchievements as any[])?.map((achievement: any, index: number) => (
                    <li key={index}>{achievement}</li>
                  ))}
                </ul>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
