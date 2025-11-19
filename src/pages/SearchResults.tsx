import { useEffect, useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { Search } from "lucide-react";

const RESULTS_PER_PAGE = 5; // adjust as you like

export default function SearchResults() {
  const { fetchWithAuth } = useAuth();
  const [searchParams] = useSearchParams();
  const query = (searchParams.get("q") || "").toLowerCase();
  const [jobs, setJobs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [page, setPage] = useState(1);

  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetchWithAuth<{ recommendations: any[] }>("/recommendations", {
          method: "GET",
        });
        setJobs(res.recommendations ?? []);
      } catch (err) {
        console.error("Failed to load recommendations", err);
        setJobs([]);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [fetchWithAuth]);

  const filtered = jobs.filter((job) => {
    if (!query) return true;
    return (
      job.Title?.toLowerCase().includes(query) ||
      job.Company?.toLowerCase().includes(query) ||
      job.RoleDescription?.toLowerCase().includes(query)
    );
  });

  const totalPages = Math.ceil(filtered.length / RESULTS_PER_PAGE);
  const startIdx = (page - 1) * RESULTS_PER_PAGE;
  const endIdx = startIdx + RESULTS_PER_PAGE;
  const currentPageJobs = filtered.slice(startIdx, endIdx);

  const toggleExpanded = (id: string | number) => {
    const key = String(id);
    setExpanded((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  if (loading)
    return (
      <div className="flex justify-center items-center h-64">
        <Search className="animate-spin w-6 h-6 text-gray-500" />
      </div>
    );

  if (!filtered.length)
    return (
      <div className="text-center py-20">
        <Search className="mx-auto h-12 w-12 text-gray-400 mb-4" />
        <h2 className="text-lg font-semibold text-gray-700">
          No results found for “{query}”
        </h2>
        <p className="text-gray-500">Try adjusting your search terms.</p>
        <Link to="/feed" className="text-blue-600 mt-4 hover:underline">
          ← Back to Feed
        </Link>
      </div>
    );

  return (
    <div className="max-w-5xl mx-auto px-6 py-10">
      <div className="mb-6 flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold">
            Search results for “{query}”
          </h1>
          <p className="text-gray-500">
            Showing {startIdx + 1}–{Math.min(endIdx, filtered.length)} of {filtered.length} results
          </p>
        </div>
        <Link to="/feed" className="text-blue-600 hover:underline">
          ← Back to Feed
        </Link>
      </div>

      <div className="space-y-4">
        {currentPageJobs.map((job, idx) => {
          const idKey = job.ID ?? `${page}-${idx}`;
          const isExpanded = !!expanded[idKey];

          return (
            <div key={idKey} className="border border-gray-200 rounded-lg p-4 hover:shadow-sm">
              <a
                href={job.Link || "#"}
                className="text-blue-600 font-semibold text-lg hover:underline"
                target="_blank"
                rel="noreferrer"
              >
                {job.Title}
              </a>
              <div className="text-sm text-gray-600">
                {job.Company} • {job.Location} • {job.EmploymentType}
              </div>

              <div className="text-gray-700 mt-3 whitespace-pre-line">
                {isExpanded
                  ? job.RoleDescription
                  : job.RoleDescription?.slice(0, 250) + (job.RoleDescription?.length > 250 ? "..." : "")}
              </div>

              {job.RoleDescription?.length > 250 && (
                <button
                  onClick={() => toggleExpanded(idKey)}
                  className="mt-2 text-sm text-blue-600 hover:underline"
                >
                  {isExpanded ? "View less" : "View more"}
                </button>
              )}

              <div className="text-xs text-gray-400 mt-2">
                Match score: {(job.score * 100).toFixed(0)}%
              </div>
            </div>
          );
        })}
      </div>

      {/* Pagination controls */}
      {totalPages > 1 && (
        <div className="flex justify-center items-center space-x-2 mt-8">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className={`px-3 py-1 border rounded-md ${
              page === 1 ? "text-gray-400 border-gray-200" : "text-blue-600 border-blue-300 hover:bg-blue-50"
            }`}
          >
            Previous
          </button>

          {[...Array(totalPages)].map((_, i) => (
            <button
              key={i}
              onClick={() => setPage(i + 1)}
              className={`px-3 py-1 rounded-md border ${
                page === i + 1
                  ? "bg-blue-600 text-white border-blue-600"
                  : "border-gray-300 hover:bg-gray-100"
              }`}
            >
              {i + 1}
            </button>
          ))}

          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className={`px-3 py-1 border rounded-md ${
              page === totalPages
                ? "text-gray-400 border-gray-200"
                : "text-blue-600 border-blue-300 hover:bg-blue-50"
            }`}
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
