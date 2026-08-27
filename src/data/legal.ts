/**
 * legal.ts — Source of truth for legal-document text rendered in the app.
 *
 * DRAFT STATUS: v0.9, pending attorney review. The master drafts (with
 * counsel placeholders and review notes) live in
 * Solverah_IP/compliance/PRIVACY_POLICY_DRAFT.md and TERMS_OF_SERVICE_DRAFT.md.
 * Keep this file and those drafts in sync; bump TERMS_VERSION on any material
 * change (the accepted version is recorded per-user at registration).
 */

export const TERMS_VERSION = "v0.9-draft-2026-08-20";
export const LEGAL_IS_DRAFT = true; // flips the "under review" banner off when counsel signs off

export const PRIVACY_POLICY_MD = `
# Privacy Policy

**Effective date:** pending final legal review

Solverah ("we," "us") is a career platform. This policy explains what personal information we collect, how we use it, who we share it with, and the choices you have. It applies to solverah.com and the Solverah application (the "Service"). The Service is offered to residents of the United States.

## What we collect

**Account information.** Email address, name, and a password (stored only as a salted hash — we cannot read your password).

**Profile and intake information you provide.** Your resume, phone number, state, LinkedIn or portfolio URLs, work experience, education, skills and skill levels, career preferences, and similar information you add to your profile or provide during intake.

**Assessment responses and results.** Your answers to Solverah assessments (such as Work Pulse) and the scores, narratives, and match results derived from them.

**Early-access requests.** If you request early access, the name and email you submit.

**Usage and security information.** IP address, browser/device information, and security events (such as logins and account changes) in our security audit log.

We do **not** collect government identifiers, precise geolocation, biometric data, or payment card details. We do not use advertising trackers or third-party analytics; the only cookies we set are the essential cookies that keep you signed in.

## How we use it

- To provide the Service: generating your assessment results, career insights, company match information, and other features you request.
- To create and secure your account, prevent abuse, and investigate security incidents.
- To send transactional email (verification codes, password resets, service notices). We do not send marketing email unless you separately opt in, and every marketing email would include an unsubscribe link.
- To improve the Service and conduct research using information that has been **de-identified** so it no longer identifies you.

**AI processing.** Parts of the Service are powered by large language models operated by our AI service providers (currently OpenAI and Groq). When you use AI-powered features — career insights, assessment narratives, path suggestions, or the assistant chat — relevant parts of your profile, resume, and assessment context are sent to these providers to generate your results. Under our service terms with these providers, this data is not used to train their models. We do not sell your data to them or anyone else.

## Who can see your information

**Employers cannot see your assessment answers or your individual dimension scores.** This is a design commitment enforced in our software, not just a policy statement. If employers ever participate on the platform, what they would see is a match result — never your answers or scores.

**Service providers**, only as needed to run the Service: cloud hosting (Render, Vercel), file storage (Cloudflare R2) for your resume, AI providers (OpenAI, Groq) as described above, email delivery (Resend), and occupational data services (O*NET Web Services) for career-path features. Each receives only what its function requires.

**Legal and safety.** We may disclose information if required by law, or to protect the rights, safety, or property of users, the public, or Solverah.

**Business transfers.** If Solverah is involved in a merger, acquisition, or sale of assets, information may be transferred as part of that transaction, subject to this policy.

**We do not sell your personal information, and we do not share it for cross-context behavioral advertising.**

## How long we keep it

We keep your information while your account is active. Specific limits: incomplete intake submissions that are never attached to an account are deleted after 90 days; IP addresses and device information in our security log are removed after 12 months; early-access contact information is kept only through the launch period. When you delete your account (below), deletion happens immediately, except where a short backup-retention window or a legal obligation applies.

## Your choices and rights

- **Access and export.** Download a copy of your data from your account settings at any time.
- **Correction.** Edit your profile and account information in the app.
- **Deletion.** Delete your account from account settings. This permanently removes your identity and personal information — account, profile, resume, and intake records. Assessment responses are retained only in **de-identified** form, no longer linked to you, for research and service improvement.
- **Email.** Transactional email is part of the Service; any marketing email would offer unsubscribe.

We honor these rights for everyone, regardless of which state you live in. We will not discriminate against you for exercising them. If you have questions or cannot use the in-app tools, contact us at **info@solverah.com** and we will respond within 45 days.

**California residents:** the categories of personal information we collect are identified above (identifiers; professional and employment-related information; education information; internet activity limited to security logs; inferences in the form of assessment scores). We collect them for the purposes above, and we do not sell or share personal information as those terms are defined in the CCPA. You may exercise your rights to know, delete, and correct through the tools above or by email; authorized agents may submit requests on your behalf with proof of authorization.

## Security

We use HTTPS everywhere, hash passwords with bcrypt, restrict data access to what each system component needs, rate-limit authentication endpoints, and keep a security audit log. No system is perfectly secure; if a breach affects your information, we will notify you as required by applicable law.

## Children

The Service is not directed to children and is only available to people **16 or older**. We do not knowingly collect information from anyone under 16; if we learn we have, we will delete it.

## Changes

If we make material changes to this policy, we will notify you by email or in-app notice before the changes take effect, and update the effective date above.

## Contact

**info@solverah.com**
`;

export const TERMS_OF_SERVICE_MD = `
# Terms of Service

**Effective date:** pending final legal review

These Terms of Service ("Terms") are an agreement between you and Solverah ("we," "us") governing your use of solverah.com and the Solverah application (the "Service"). By creating an account or using the Service, you agree to these Terms and to the [Privacy Policy](/privacy).

## 1. Who can use Solverah

You must be **at least 16 years old** to use the Service. The Service is offered to and intended for **residents of the United States**; we make no representation that it is appropriate or available elsewhere. By registering, you confirm both of the above.

## 2. Your account

Keep your credentials confidential; you are responsible for activity under your account. Provide accurate information and keep it current. We may suspend or terminate accounts that violate these Terms or threaten the security of the Service.

## 3. What the Service is — and is not

Solverah provides career exploration tools: work-preference assessments, AI-generated career insights and narratives, company culture information, and company-person fit signals.

**The Service is informational career guidance only.** It is not:

- a promise or prediction of employment, job performance, or career outcomes;
- an offer of employment or a recruiting decision — Solverah does not make hiring decisions about you, and no employer decision about you is made through the Service;
- professional, legal, financial, or psychological advice.

**About AI-generated content:** portions of the Service are generated by artificial-intelligence systems. AI output can be incomplete, outdated, or wrong, and company information presented in the Service is an interpretation of available sources, not a statement of fact about any employer. Use your own judgment before acting on it.

## 4. Assessments and your results

Your assessment answers and individual dimension scores are yours to see, not employers'. We display results at the level the product provides and do not guarantee any particular interpretation. Assessment instruments and scoring may change over time; when they do, you may be asked to retake an assessment.

## 5. Your content

You retain ownership of what you upload (including your resume and profile information). You grant Solverah a non-exclusive, worldwide, royalty-free license to host, process, analyze, and display that content **solely to operate and improve the Service** — including processing by the AI service providers described in the Privacy Policy. This license ends for identified content when you delete it or your account, except for de-identified data as described in the Privacy Policy and copies in routine backups for a limited period.

## 6. Acceptable use

Don't: break the law; access another person's account or data; probe, scrape, or copy the Service or its data by automated means; upload malicious code or content you don't have rights to; misrepresent your identity to manipulate assessment or match results for fraudulent purposes; reverse engineer the Service except where the law grants that right; resell the Service without our written agreement.

## 7. Solverah's property

The Service — including software, assessments and their items, scoring methods, company profiles, text, and design — is owned by Solverah or its licensors and protected by intellectual-property law. These Terms give you a personal, non-transferable, revocable right to use the Service; they transfer no ownership.

## 8. Feedback

If you send us feedback or suggestions, we may use them without restriction or obligation to you.

## 9. Termination

You may stop using the Service and delete your account at any time in account settings (see the Privacy Policy for what deletion does). We may suspend or terminate your access for violation of these Terms, with notice where practicable. Sections 5 (for the period stated), 7, 8, and 10-13 survive termination.

## 10. Disclaimers

THE SERVICE IS PROVIDED "AS IS" AND "AS AVAILABLE," WITHOUT WARRANTIES OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, ACCURACY, AND NON-INFRINGEMENT. WITHOUT LIMITING THE FOREGOING, WE DO NOT WARRANT THAT ASSESSMENT RESULTS, MATCHES, OR AI-GENERATED CONTENT WILL BE ACCURATE OR RELIABLE, OR THAT USE OF THE SERVICE WILL LEAD TO ANY EMPLOYMENT OUTCOME. SOME JURISDICTIONS DO NOT ALLOW CERTAIN WARRANTY EXCLUSIONS, SO SOME OF THE ABOVE MAY NOT APPLY TO YOU.

## 11. Limitation of liability

TO THE MAXIMUM EXTENT PERMITTED BY LAW, SOLVERAH WILL NOT BE LIABLE FOR INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES, OR FOR LOST PROFITS, DATA, OR OPPORTUNITIES (INCLUDING EMPLOYMENT OPPORTUNITIES), ARISING FROM OR RELATED TO THE SERVICE. OUR TOTAL LIABILITY FOR ALL CLAIMS WILL NOT EXCEED THE GREATER OF $100 OR THE AMOUNTS YOU PAID US IN THE 12 MONTHS BEFORE THE CLAIM.

## 12. Dispute resolution and governing law

Sections addressing dispute resolution and governing law are being finalized with counsel and will be included in the effective version of these Terms.

## 13. Changes to these Terms

We may update these Terms. For material changes we will give notice (email or in-app) before they take effect; continued use after the effective date constitutes acceptance. The current version and its effective date are always available at /terms.

## 14. Contact

**info@solverah.com**
`;
