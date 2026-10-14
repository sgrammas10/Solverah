/**
 * useCompanyRead -- one company's six-trait read, and the two things a user can do
 * with it.
 *
 *   GET    /companies/{id}/read[?posting_id=]   the read (and a pasted posting's, beside it)
 *   GET    /companies/{id}                      the legacy research profile, if any
 *   POST   /me/job-postings {company_id, text, title?}   paste a posting (202)
 *   GET    /me/job-postings/{id}                that posting, polled until it has a read
 *   GET    /me/company-links                    "I took this job" links
 *   POST   /me/company-links {company_id, started_on}
 *   PATCH  /me/company-links/{id} {ended_on}   "I left this job"
 *   DELETE /me/company-links/{id}
 *
 * A user has at most one open link: a new POST closes the previous one server-side,
 * so every link mutation refetches the list.
 *
 * Every query key sits under matching's `companyLensKeys.all`, so a research run
 * finishing anywhere refreshes this page too. Types are the generated contract's.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "../auth";
import { companyLensKeys, usePoll, DEFAULT_POLL_TIMING, type PollTiming } from "../matching";
import type { components } from "../../shared/api/schema";

type Schemas = components["schemas"];
export type CompanyReadResponse = Schemas["CompanyReadResponse"];
export type TraitRead = Schemas["TraitRead"];
export type PostingRead = Schemas["PostingRead"];
export type PostingTraitRead = Schemas["PostingTraitRead"];
export type EvidenceItem = Schemas["EvidenceItem"];
export type MixedEnd = Schemas["MixedEnd"];
export type CompanyDetailResponse = Schemas["CompanyDetailResponse"];
export type JobPostingResponse = Schemas["JobPostingResponse"];
export type JobPostingStatus = Schemas["JobPostingStatus"];
export type CompanyLinkEntry = Schemas["CompanyLinkEntry"];
export type CompanyLinkListResponse = Schemas["CompanyLinkListResponse"];
export type CompanyLinkResponse = Schemas["CompanyLinkResponse"];
type OkResponse = Schemas["OkResponse"];

/** `GET /companies/{id}/read`, with the posting's read beside it once it has one. */
export function useCompanyRead(companyId: string, postingId: number | null) {
  const { fetchWithAuth } = useAuth();
  return useQuery({
    queryKey: companyLensKeys.read(companyId, postingId),
    // Both spellings written out with the "?" literal: tests/test_frontend_contract.py
    // reads the path up to the first "?", so a `${query}` suffix would be scanned
    // as part of the path and fail the "every path is served" check.
    queryFn: () =>
      postingId === null
        ? fetchWithAuth<CompanyReadResponse>(`/companies/${companyId}/read`)
        : fetchWithAuth<CompanyReadResponse>(`/companies/${companyId}/read?posting_id=${postingId}`),
    // Keep the company read on screen while the posting's version loads.
    placeholderData: (previous) => previous,
  });
}

/**
 * `GET /companies/{id}`: the legacy research profile. Secondary content, so its
 * failure never takes the page down.
 */
export function useCompanyProfile(companyId: string) {
  const { fetchWithAuth } = useAuth();
  return useQuery({
    queryKey: companyLensKeys.profile(companyId),
    queryFn: () => fetchWithAuth<CompanyDetailResponse>(`/companies/${companyId}`),
    throwOnError: false,
    retry: false,
  });
}

export function useSubmitPosting() {
  const { fetchWithAuth } = useAuth();
  return useMutation({
    mutationFn: (body: { company_id: number; text: string; title: string | null }) =>
      fetchWithAuth<JobPostingResponse>("/me/job-postings", {
        method: "POST",
        body: JSON.stringify(body),
      }),
  });
}

/** A posting is finished once it has a read, or scoring stopped either way. */
export function isPostingSettled(posting: JobPostingStatus): boolean {
  return posting.has_read || posting.status !== "pending";
}

/** `GET /me/job-postings/{id}`, polled (3 s, backing off) until settled. */
export function usePostingStatus(postingId: number | null, timing: PollTiming = DEFAULT_POLL_TIMING) {
  const { fetchWithAuth } = useAuth();
  return usePoll<JobPostingResponse>(
    postingId === null ? null : String(postingId),
    (id) => fetchWithAuth<JobPostingResponse>(`/me/job-postings/${id}`),
    (response) => isPostingSettled(response.posting),
    timing,
  );
}

export function useCompanyLinks() {
  const { fetchWithAuth } = useAuth();
  return useQuery({
    queryKey: companyLensKeys.links,
    queryFn: () => fetchWithAuth<CompanyLinkListResponse>("/me/company-links"),
    throwOnError: false,
  });
}

export function useCreateCompanyLink() {
  const { fetchWithAuth } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { company_id: number; started_on: string }) =>
      fetchWithAuth<CompanyLinkResponse>("/me/company-links", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: companyLensKeys.links }),
  });
}

/** "I left this job": `PATCH /me/company-links/{id}` with an end date. 422 when the
 *  date is before the start date. */
export function useEndCompanyLink() {
  const { fetchWithAuth } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ linkId, endedOn }: { linkId: number; endedOn: string }) =>
      fetchWithAuth<CompanyLinkResponse>(`/me/company-links/${linkId}`, {
        method: "PATCH",
        body: JSON.stringify({ ended_on: endedOn }),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: companyLensKeys.links }),
  });
}

export function useDeleteCompanyLink() {
  const { fetchWithAuth } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (linkId: number) =>
      fetchWithAuth<OkResponse>(`/me/company-links/${linkId}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: companyLensKeys.links }),
  });
}
