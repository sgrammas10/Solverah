import React from 'react';
import { Link, Navigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { Users, Target, BarChart3, Shield, ArrowRight } from 'lucide-react';

function LandingPage() {
  const { user } = useAuth();

  // If user is logged in, redirect to feed
  if (user) {
    return <Navigate to="/feed" replace />;
  }

  return (
    <div className="bg-white">
      {/* Hero Section */}
      <div className="relative overflow-hidden">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-20 pb-16">
          <div className="text-center">
            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-gray-900 mb-6">
              Perfect Job Matches with
              <span className="text-blue-600 block">Solverah Intelligence</span>
            </h1>
            <p className="text-xl text-gray-600 mb-8 max-w-3xl mx-auto">
              Connect job seekers and employers through comprehensive profiles powered by 
              resumes, performance reviews, and our proprietary psychometric assessments.
            </p>
            <div className="flex flex-col sm:flex-row gap-4 justify-center">
              <Link
                to="/register"
                className="inline-flex items-center justify-center px-8 py-3 border border-transparent text-base font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 transition-colors"
              >
                Get Started
                <ArrowRight className="ml-2 h-4 w-4" />
              </Link>
              <Link
                to="/login"
                className="inline-flex items-center justify-center px-8 py-3 border border-gray-300 text-base font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 transition-colors"
              >
                Sign In
              </Link>
            </div>
          </div>
        </div>

        {/* Background decoration */}
        <div className="absolute inset-0 -z-10">
          <div className="absolute top-0 left-1/2 transform -translate-x-1/2 w-96 h-96 bg-gradient-to-r from-blue-400 to-purple-500 rounded-full opacity-10 blur-3xl"></div>
          <div className="absolute bottom-0 right-0 w-96 h-96 bg-gradient-to-r from-purple-400 to-pink-500 rounded-full opacity-10 blur-3xl"></div>
        </div>
      </div>

      {/* Features Section */}
      <div className="py-16 bg-gray-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-12">
            <h2 className="text-3xl font-bold text-gray-900 mb-4">
              Why Choose Solverah?
            </h2>
            <p className="text-lg text-gray-600">
              Our comprehensive approach to job matching goes beyond traditional methods
            </p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-8">
            <div className="text-center p-6 bg-white rounded-lg shadow-sm hover:shadow-md transition-shadow">
              <div className="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center mx-auto mb-4">
                <Users className="h-6 w-6 text-blue-600" />
              </div>
              <h3 className="text-lg font-semibold text-gray-900 mb-2">
                Comprehensive Profiles
              </h3>
              <p className="text-gray-600">
                Combine resumes, performance reviews, and psychometric assessments for complete candidate insights
              </p>
            </div>

            <div className="text-center p-6 bg-white rounded-lg shadow-sm hover:shadow-md transition-shadow">
              <div className="w-12 h-12 bg-green-100 rounded-lg flex items-center justify-center mx-auto mb-4">
                <Target className="h-6 w-6 text-green-600" />
              </div>
              <h3 className="text-lg font-semibold text-gray-900 mb-2">
                Smart Matching
              </h3>
              <p className="text-gray-600">
                AI-powered algorithms match candidates with roles based on skills, personality, and culture fit
              </p>
            </div>

            <div className="text-center p-6 bg-white rounded-lg shadow-sm hover:shadow-md transition-shadow">
              <div className="w-12 h-12 bg-purple-100 rounded-lg flex items-center justify-center mx-auto mb-4">
                <BarChart3 className="h-6 w-6 text-purple-600" />
              </div>
              <h3 className="text-lg font-semibold text-gray-900 mb-2">
                Performance Insights
              </h3>
              <p className="text-gray-600">
                Track and analyze performance data to predict job success and career growth potential
              </p>
            </div>

            <div className="text-center p-6 bg-white rounded-lg shadow-sm hover:shadow-md transition-shadow">
              <div className="w-12 h-12 bg-orange-100 rounded-lg flex items-center justify-center mx-auto mb-4">
                <Shield className="h-6 w-6 text-orange-600" />
              </div>
              <h3 className="text-lg font-semibold text-gray-900 mb-2">
                Proprietary Assessments
              </h3>
              <p className="text-gray-600">
                Our trademarked psychometric tests provide unique insights into candidate potential
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* User Types Section */}
      <div className="py-16 bg-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-12">
            <h2 className="text-3xl font-bold text-gray-900 mb-4">
              Built for Both Sides of Hiring
            </h2>
          </div>

          <div className="grid md:grid-cols-2 gap-12">
            <div className="text-center">
              <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-6">
                <Users className="h-8 w-8 text-blue-600" />
              </div>
              <h3 className="text-2xl font-bold text-gray-900 mb-4">For Job Seekers</h3>
              <ul className="text-left space-y-3 text-gray-600">
                <li className="flex items-center">
                  <div className="w-2 h-2 bg-blue-600 rounded-full mr-3"></div>
                  Create comprehensive profiles with resume, performance history, and assessments
                </li>
                <li className="flex items-center">
                  <div className="w-2 h-2 bg-blue-600 rounded-full mr-3"></div>
                  Get matched with roles that fit your skills and personality
                </li>
                <li className="flex items-center">
                  <div className="w-2 h-2 bg-blue-600 rounded-full mr-3"></div>
                  Showcase your true potential beyond traditional resumes
                </li>
                <li className="flex items-center">
                  <div className="w-2 h-2 bg-blue-600 rounded-full mr-3"></div>
                  Receive personalized career development insights
                </li>
              </ul>
            </div>

            <div className="text-center">
              <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-6">
                <Target className="h-8 w-8 text-green-600" />
              </div>
              <h3 className="text-2xl font-bold text-gray-900 mb-4">For Recruiters</h3>
              <ul className="text-left space-y-3 text-gray-600">
                <li className="flex items-center">
                  <div className="w-2 h-2 bg-green-600 rounded-full mr-3"></div>
                  Access detailed candidate profiles with performance data
                </li>
                <li className="flex items-center">
                  <div className="w-2 h-2 bg-green-600 rounded-full mr-3"></div>
                  Use AI-powered matching to find ideal candidates
                </li>
                <li className="flex items-center">
                  <div className="w-2 h-2 bg-green-600 rounded-full mr-3"></div>
                  Evaluate culture fit through psychometric assessments
                </li>
                <li className="flex items-center">
                  <div className="w-2 h-2 bg-green-600 rounded-full mr-3"></div>
                  Reduce hiring time and improve success rates
                </li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default LandingPage;