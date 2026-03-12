import { useEffect, useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { useAuth } from '../contexts/useAuth';
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
        <Search className="animate-spin w-6 h-6 text-slate-400" />
      </div>
    );

  if (!filtered.length)
    return (
      <div className="text-center py-20 text-slate-100">
        <Search className="mx-auto h-12 w-12 text-slate-500 mb-4" />
        <h2 className="text-lg font-semibold text-white">
          No results found for “{query}”
        </h2>
        <p className="text-slate-300">Try adjusting your search terms.</p>
        <Link to="/feed" className="text-emerald-200 mt-4 hover:underline">
          ← Back to Feed
        </Link>
      </div>
    );

  return (
    <div className="max-w-5xl mx-auto px-6 py-10 text-slate-100">
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-white">
            Search results for “{query}”
          </h1>
          <p className="text-slate-300">
            Showing {startIdx + 1}–{Math.min(endIdx, filtered.length)} of {filtered.length} results
          </p>
        </div>
        <Link to="/feed" className="text-emerald-200 hover:underline">
          ← Back to Feed
        </Link>
      </div>

      <div className="space-y-4">
        {currentPageJobs.map((job, idx) => {
          const idKey = job.ID ?? `${page}-${idx}`;
          const isExpanded = !!expanded[idKey];

          return (
            <div key={idKey} className="border border-white/10 rounded-lg bg-slate-900/60 p-4 shadow-lg shadow-black/20">
              <a
                href={job.Link || "#"}
                className="text-emerald-200 font-semibold text-lg hover:underline"
                target="_blank"
                rel="noreferrer"
              >
                {job.Title}
              </a>
              <div className="text-sm text-slate-200/80">
                {job.Company} • {job.Location} • {job.EmploymentType}
              </div>

              <div className="text-slate-200/80 mt-3 whitespace-pre-line">
                {isExpanded
                  ? job.RoleDescription
                  : job.RoleDescription?.slice(0, 250) + (job.RoleDescription?.length > 250 ? "..." : "")}
              </div>

              {job.RoleDescription?.length > 250 && (
                <button
                  onClick={() => toggleExpanded(idKey)}
                  className="mt-2 text-sm text-emerald-200 hover:underline"
                >
                  {isExpanded ? "View less" : "View more"}
                </button>
              )}

              <div className="text-xs text-slate-400 mt-2">
                Match score: {(job.score * 100).toFixed(0)}%
              </div>
            </div>
          );
        })}
      </div>

      {/* Pagination controls */}
      {totalPages > 1 && (
        <div className="flex flex-wrap justify-center items-center gap-2 mt-8">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className={`px-3 py-1 border rounded-full text-sm ${
              page === 1
                ? "text-slate-500 border-white/10"
                : "text-emerald-200 border-emerald-300/40 hover:bg-white/5"
            }`}
          >
            Previous
          </button>

          {[...Array(totalPages)].map((_, i) => (
            <button
              key={i}
              onClick={() => setPage(i + 1)}
              className={`px-3 py-1 rounded-full border text-sm ${
                page === i + 1
                  ? "bg-emerald-400/20 text-emerald-100 border-emerald-300/40"
                  : "border-white/10 text-slate-200 hover:bg-white/5"
              }`}
            >
              {i + 1}
            </button>
          ))}

          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className={`px-3 py-1 border rounded-full text-sm ${
              page === totalPages
                ? "text-slate-500 border-white/10"
                : "text-emerald-200 border-emerald-300/40 hover:bg-white/5"
            }`}
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
