import React from 'react';
import { FileText, ClipboardList, Lock } from 'lucide-react';

function PrelaunchLandingPage() {
  return (
    <div className="bg-white">
      {/* Hero Section */}
      <div className="relative overflow-hidden">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 pt-20 pb-16 text-center">
          <h1 className="text-4xl sm:text-5xl font-bold text-gray-900 mb-6">
            Solverah is Building the Future of
            <span className="text-blue-600 block">Career Matching</span>
          </h1>

          <p className="text-xl text-gray-600 max-w-3xl mx-auto mb-8">
            We’re currently in private development. Solverah goes beyond resumes by
            combining skills, work style, and archetype-driven insights to match people
            with roles where they actually thrive.
          </p>

          <div className="inline-flex items-center px-4 py-2 rounded-md bg-yellow-50 border border-yellow-200 text-yellow-800 text-sm">
            <Lock className="h-4 w-4 mr-2" />
            Private Development · Early Access Intake
          </div>
        </div>

        {/* Background decoration */}
        <div className="absolute inset-0 -z-10">
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-96 h-96 bg-gradient-to-r from-blue-400 to-purple-500 rounded-full opacity-10 blur-3xl" />
        </div>
      </div>

      {/* Intake Form Section */}
      <div className="py-16 bg-gray-50">
        <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="bg-white rounded-lg shadow-sm p-8">
            <h2 className="text-2xl font-bold text-gray-900 mb-2 text-center">
              Submit Your Information
            </h2>
            <p className="text-gray-600 text-center mb-8">
              Share your resume and a few details to be considered for early access.
            </p>

            <form className="space-y-6">
              {/* Name Fields */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700">
                    First Name
                  </label>
                  <input
                    type="text"
                    placeholder="First name"
                    className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700">
                    Last Name
                  </label>
                  <input
                    type="text"
                    placeholder="Last name"
                    className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
                  />
                </div>
              </div>

              {/* Resume Upload */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Resume
                </label>
                <div className="flex items-center justify-center w-full">
                  <label className="flex flex-col items-center justify-center w-full h-32 border-2 border-dashed border-gray-300 rounded-md cursor-pointer hover:bg-gray-50">
                    <FileText className="h-6 w-6 text-gray-400 mb-2" />
                    <span className="text-sm text-gray-600">
                      Upload PDF or DOCX
                    </span>
                    <input type="file" className="hidden" />
                  </label>
                </div>
              </div>

              {/* Archetype Placeholder 1 */}
              <div className="border border-dashed border-blue-300 rounded-md p-4 bg-blue-50">
                <div className="flex items-center mb-2">
                  <ClipboardList className="h-5 w-5 text-blue-600 mr-2" />
                  <h3 className="font-semibold text-blue-900">
                    Archetype Assessment (Placeholder)
                  </h3>
                </div>
                <p className="text-sm text-blue-800">
                  This section will contain a short archetype quiz focused on work style,
                  motivation, and problem-solving preferences.
                </p>
              </div>

              {/* Archetype Placeholder 2 */}
              <div className="border border-dashed border-purple-300 rounded-md p-4 bg-purple-50">
                <div className="flex items-center mb-2">
                  <ClipboardList className="h-5 w-5 text-purple-600 mr-2" />
                  <h3 className="font-semibold text-purple-900">
                    Culture & Team Fit Quiz (Placeholder)
                  </h3>
                </div>
                <p className="text-sm text-purple-800">
                  This section will later capture how candidates prefer to collaborate,
                  receive feedback, and operate within teams.
                </p>
              </div>

              {/* Submit */}
              <div className="pt-4">
                <button
                  type="submit"
                  disabled
                  className="w-full inline-flex justify-center items-center px-6 py-3 rounded-md bg-blue-600 text-white font-medium opacity-70 cursor-not-allowed"
                >
                  Submit (Backend Not Wired Yet)
                </button>
              </div>
            </form>
          </div>

          {/* Footer Note */}
          <p className="text-center text-sm text-gray-500 mt-6">
            We’ll only use your information to evaluate early access and product fit.
          </p>
        </div>
      </div>
    </div>
  );
}

export default PrelaunchLandingPage;
