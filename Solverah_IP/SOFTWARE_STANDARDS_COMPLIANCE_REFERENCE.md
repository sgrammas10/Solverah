# Software Standards & Compliance Reference

**Scope:** Generic — every major category of standard, regulation, framework, and certification a software product can face, with the trigger conditions that make each one apply. No single product needs all of these; almost every product needs some from each of the first four sections.

**Date compiled:** 2026-08-20. Regulatory dates verified against current sources where they have recently moved (EU AI Act, Colorado AI Act, NIS2/CRA, US state privacy). This is a planning reference, not legal advice — applicability calls for a lawyer once a product's jurisdictions and data types are fixed.

**How to read this:** every item falls into one of three buckets, and the bucket matters more than the acronym:

- **LAW** — legally mandatory if the trigger condition is met. Non-compliance = fines/liability.
- **CONTRACT/MARKET** — not law, but enterprise customers, payment networks, or app stores demand it. Non-compliance = lost deals, not lawsuits.
- **VOLUNTARY** — quality/maturity standards. Adopted for engineering discipline or marketing signal.

---

## 1. Data privacy & protection (LAW)

Applies based on **whose** data you process and **where those people are** — not where the company is.

### European Union / EEA
| Instrument | Trigger | Core obligations |
|---|---|---|
| **GDPR** (Reg. 2016/679) | Processing personal data of people in the EU/EEA — offering goods/services to them or monitoring their behavior, regardless of company location | Lawful basis for processing, data-subject rights (access/erasure/portability), DPAs with processors, privacy by design, DPIAs for high-risk processing, 72-hour breach notification, EU representative if no EU establishment, restrictions on transfers out of the EU (SCCs / EU-US Data Privacy Framework) |
| **ePrivacy Directive** ("cookie law") | Any website/app reachable from the EU that sets non-essential cookies or does electronic marketing | Prior consent for non-essential cookies/trackers; consent rules for email/SMS marketing |
| **EU Data Act** (applicable Sept 2025) | Connected products and related services; cloud/data-processing services | Data-sharing obligations, cloud switching/egress rules |

### United Kingdom
**UK GDPR + Data Protection Act 2018**, as amended by the **Data (Use and Access) Act 2025**. Same trigger logic as GDPR; UK representative may be needed. **PECR** covers cookies/e-marketing.

### United States — no single federal law; a patchwork
- **State comprehensive privacy laws** — as of 2026 roughly **20 states** have them in effect (California CCPA/CPRA, Virginia, Colorado, Connecticut, Utah, Texas, Oregon, Montana, Florida, Iowa, Delaware, New Hampshire, New Jersey, Nebraska, Kentucky, Minnesota, Tennessee, Maryland, Indiana, Rhode Island — with more phasing in). Triggers are usually revenue and/or number-of-residents thresholds; Texas's applies to almost any non-small business. Obligations: notice, opt-outs (sale/targeted ads/profiling), universal opt-out signal recognition (GPC), consumer rights, data-protection assessments. **Maryland (Oct 2025)** adds strict data-minimization; several states now run active enforcement.
- **State breach-notification laws** — **all 50 states** + DC/territories. Trigger: any breach of residents' personal information. Each state has its own timeline and content rules.
- **FTC Act §5** — federal backstop: "unfair or deceptive" practices. Trigger: saying anything about privacy/security you don't actually do. The de-facto US privacy regulator for uncovered sectors.
- **COPPA** (as amended, 2025 rule) — collecting personal info from children under 13, or a service directed at them. Verifiable parental consent, data-retention limits.
- **Washington My Health My Data / Nevada SB 370** — consumer health data outside HIPAA. Broad definitions; private right of action in WA.
- **Biometric laws** — **Illinois BIPA** (private right of action, per-scan damages), Texas CUBI, Washington HB 1493, plus biometric provisions inside CCPA/Colorado. Trigger: fingerprints, voiceprints, face geometry, and in some readings behavioral biometrics.

### Canada
**PIPEDA** federally; **Quebec Law 25** (materially GDPR-like: consent, DPO-equivalent, privacy impact assessments, data-portability since 2024); **CASL** for email/SMS marketing (consent-based, strict).

### Other major regimes (trigger: users/operations there)
**Brazil LGPD** · **China PIPL + Data Security Law + Cybersecurity Law** (data-localization and cross-border transfer approvals) · **India DPDP Act 2023** (rules operational 2025-26) · **Australia Privacy Act** (amendments phasing in, statutory tort for serious invasions since mid-2025) · **Japan APPI** · **South Korea PIPA** · **Switzerland revFADP** · **Saudi PDPL / UAE PDPL** · **Nigeria NDPA** · **South Africa POPIA**.

---

## 2. Security regulation (LAW) — distinct from voluntary security certs

| Instrument | Trigger | What it demands |
|---|---|---|
| **EU Cyber Resilience Act (CRA)** | Any "product with digital elements" — including plain software — **sold in the EU** | Secure-by-design requirements, vulnerability handling, SBOM, security updates for support period, CE marking. Reporting obligations for actively exploited vulns start **Sept 2026**; main obligations **Dec 2027** |
| **EU NIS2 Directive** | "Essential/important entities" — includes cloud providers, data centers, managed service providers, online marketplaces/search/social above size thresholds | Risk-management measures, supply-chain security, incident reporting (24h early warning), **personal liability for management**. Member-state transposition wave through Oct 2026; registration duties already live in transposed states |
| **EU DORA** | Financial entities in the EU **and their ICT providers** (contractually flows down) | ICT risk management, incident reporting, resilience testing, third-party register. In force since **Jan 2025**; enforcement now active |
| **EU Product Liability Directive (2024 revision)** | Software sold in the EU, standalone or embedded, including AI | Software is now a "product" for strict liability — defects (including cybersecurity defects and failed updates) create no-fault liability for damage. Member-state transposition by **Dec 2026** |
| **NYDFS 23 NYCRR 500** | Financial services licensed in New York, and by contract their vendors | CISO, pen-testing, MFA, incident reporting (72h), annual certification |
| **SEC cybersecurity disclosure rules** | US public companies | Material-incident disclosure (4 business days), annual risk-management disclosure |
| **US state safe-harbor / reasonable-security laws** | Varies (e.g. Ohio, Utah, Connecticut) | Adopting a recognized framework (NIST CSF, ISO 27001) as an affirmative defense |
| **UK Product Security and Telecommunications Infrastructure Act** | Consumer connectable (IoT) products in the UK | No default passwords, vuln disclosure policy, update-period transparency |

---

## 3. Security & trust frameworks (CONTRACT/MARKET — the ones enterprise sales die without)

| Framework | What it is | Who demands it |
|---|---|---|
| **SOC 2 Type II** | AICPA attestation over security/availability/confidentiality/processing-integrity/privacy controls, observed over 3–12 months | The default gate for selling B2B SaaS in North America. Type I (point-in-time) is the starter step |
| **ISO/IEC 27001:2022** | Certifiable information-security management system (ISMS) | The international equivalent of SOC 2; expected in EU/UK/APAC enterprise deals. Extensions: **27017** (cloud), **27018** (cloud PII), **27701** (privacy management, being restructured as certifiable standalone) |
| **PCI DSS v4.0.1** | Payment-card industry standard (contractual via card networks) | **Mandatory** if you store/process/transmit card data. Using Stripe/Adyen-style tokenized checkout reduces scope to SAQ-A but never to zero. All v4.0 future-dated requirements enforceable since **March 31, 2025** |
| **NIST CSF 2.0** | US risk-management framework | Referenced by insurers, regulators, safe-harbor laws; not certifiable |
| **NIST SP 800-53 / FedRAMP** | US federal cloud security | **FedRAMP authorization is legally required** to sell cloud services to US federal agencies; StateRAMP/GovRAMP for states |
| **NIST SP 800-171 / CMMC** | Controlled Unclassified Information in defense supply chain | **CMMC** now appearing in DoD contracts under the phased rollout begun late 2025 — flows down to subcontractors |
| **HITRUST CSF** | Healthcare-oriented certifiable framework | Demanded by US health-sector customers on top of HIPAA |
| **CSA STAR / CAIQ** | Cloud Security Alliance registry & questionnaire | Common in vendor-security review |
| **Common Criteria (ISO 15408) / FIPS 140-3** | Product-level security evaluation; cryptographic-module validation | Government and regulated-industry procurement |
| **OWASP ASVS / SAMM / Top 10** | AppSec verification and maturity models | De-facto engineering baseline; cited in customer security addenda |
| **SBOM (SPDX / CycloneDX) + SSDF (NIST SP 800-218)** | Software bill of materials; secure development framework | Required for US-government software supply (EO 14028 lineage) and by the EU CRA; increasingly a customer ask |

---

## 4. AI-specific regulation (LAW, fast-moving — verify before relying)

| Instrument | Trigger | Status & obligations |
|---|---|---|
| **EU AI Act** | Providing/deploying AI systems in the EU market, regardless of company location | Prohibited-practice and AI-literacy rules live since Feb 2025; GPAI-model rules since Aug 2025. **High-risk (Annex III — includes employment/worker-management, credit, education, biometrics) obligations provisionally delayed to Dec 2, 2027** under the Digital Omnibus agreement (formal adoption pending); transparency/watermarking Dec 2026. High-risk = risk management, data governance, logging, human oversight, conformity assessment, registration |
| **Colorado AI Act (SB 24-205)** | Developers/deployers of "high-risk" AI making consequential decisions (employment, lending, housing, etc.) affecting Colorado residents | **Implementation postponed (now to ~June 30, 2026 and under further legislative rework)** — track before relying on any date. Duty of reasonable care against algorithmic discrimination, impact assessments, notices |
| **Illinois HB 3773 (Human Rights Act amendment)** | AI use in employment decisions affecting Illinois | Effective **Jan 1, 2026**: no discriminatory AI use, notice to employees/applicants required |
| **Illinois AIVIA** | AI analysis of video interviews | Consent, explanation, deletion duties |
| **NYC Local Law 144** | Automated employment decision tools used for NYC roles | Annual independent bias audit, published results, candidate notice |
| **California** — FEHA ADS regulations (Oct 2025) + CCPA ADMT regulations (phasing in 2026-27) | Automated decision systems in employment; automated decisionmaking tech on CA residents' data | Anti-discrimination duties, recordkeeping; ADMT notices, opt-outs, risk assessments |
| **Texas TRAIGA** (Jan 2026), **Utah AI Policy Act**, **Colorado/Connecticut 2026 additions**, and a widening state patchwork | Varies — often government AI use, chatbots, or employment | Disclosure duties mostly; check per-state as of your launch date |
| **ISO/IEC 42001** | Voluntary certifiable AI management system | The emerging "SOC 2 of AI" for enterprise procurement |
| **NIST AI RMF** | Voluntary US framework | Referenced by customers, insurers, and some state laws as the reasonable-care benchmark |
| **EEOC/Title VII, ADA, ADEA (US federal)** | Any tool used in employment selection | Disparate-impact liability applies to algorithmic tools; **Uniform Guidelines on Employee Selection Procedures** (4/5ths rule) is the classic validation framework |

---

## 5. Accessibility (LAW in more places every year)

| Instrument | Trigger | Standard invoked |
|---|---|---|
| **European Accessibility Act** | Consumer-facing e-commerce, banking, ebooks, telecoms, transport software sold in the EU | In force since **June 28, 2025** (legacy-service transition to 2030). Technical standard: **EN 301 549**, which incorporates **WCAG 2.1 AA** (migrating toward 2.2) |
| **ADA (US)** | Places of public accommodation (websites/apps per DOJ and much case law); **Title II rule** sets WCAG 2.1 AA for state/local government sites — compliance dates **April 2026 / April 2027** by population | WCAG 2.1 AA is the de-facto litigation benchmark; private-suit exposure is real and high-volume |
| **Section 508** | Selling to US federal agencies | WCAG-based; procurement gate |
| **AODA (Ontario) / ACA (Canada federal)** | Ontario orgs; federally regulated entities | WCAG 2.0/2.1 AA |
| **WCAG 2.2 (W3C)** | Voluntary standard underlying all of the above | Target AA. WCAG 3.0 in draft |

---

## 6. Industry-specific regimes (LAW — trigger: the sector you sell into)

**Healthcare:** **HIPAA/HITECH** (US — if you touch PHI for covered entities you're a business associate: security rule, BAAs, breach notification) · **FDA software-as-a-medical-device** regime + **IEC 62304** (software lifecycle) + **ISO 14971** (risk management) if the software diagnoses/treats · **EU MDR/IVDR** for the same in Europe · **21 CFR Part 11** (electronic records/signatures in FDA-regulated contexts) · **ONC certification + information-blocking rules** for US EHR-adjacent products.

**Financial services:** **SOX** (public-company financial reporting — ITGC controls on any system feeding financials) · **GLBA Safeguards Rule** (financial institutions broadly defined, incl. many fintechs) · **PCI DSS** (§3) · **DORA** (§2) · **BSA/AML + KYC** rules if moving money · **FINRA/SEC 17a-4** (broker-dealer record immutability) · state **money-transmitter licenses**.

**Education:** **FERPA** (US student records — flows down to vendors via school contracts) · **COPPA** + state student-privacy laws (SOPIPA etc.) · UK/EU age-appropriate design codes.

**Government sales:** FedRAMP/StateRAMP, CMMC, Section 508, **FAR/DFARS** clauses, **ITAR** if defense articles.

**Telecom/communications:** **CPNI** rules, **STIR/SHAKEN**, E911 obligations if you provide voice; **TCPA** (below) for calls/SMS.

**Safety-critical embedded:** **ISO 26262** (automotive) + **UNECE R155/R156** (vehicle cyber/OTA) · **DO-178C** (aviation) · **IEC 61508** (industrial) · **IEC 62443** (industrial control security) · **EN 50128** (rail).

---

## 7. Consumer protection, marketing & commerce (LAW)

- **CAN-SPAM** (US email), **TCPA** (US calls/SMS — per-message statutory damages, consent rules), **CASL** (Canada, strictest), **ePrivacy/PECR** (EU/UK).
- **FTC dark-patterns enforcement + state auto-renewal laws** (California's especially): clear disclosure, one-click cancel. **FTC "click-to-cancel" rule was struck down in 2025** but state laws stand.
- **EU consumer law** (Unfair Commercial Practices, Consumer Rights Directive, Digital Content Directive): withdrawal rights, conformity guarantees for digital content, no dark patterns (also policed under DSA).
- **Sales tax / VAT on digital services** — US economic-nexus rules post-*Wayfair*; EU VAT OSS; digital-services taxes in several countries. Not a "standard" but a compliance regime every SaaS hits.
- **App-store rules** (Apple App Review, Google Play policies) — CONTRACT tier but existential if you distribute mobile: privacy "nutrition labels," data-safety forms, payment rules (in flux under DMA and US litigation).

---

## 8. Platform & content regulation (LAW — trigger: hosting user content or reaching scale)

- **EU Digital Services Act** — all intermediaries serving the EU: notice-and-action, transparency reporting; heavier tiers by size (VLOP at 45M EU users).
- **EU Digital Markets Act** — gatekeepers only, but shapes app-store/interop terms you inherit.
- **UK Online Safety Act** — user-to-user and search services with UK users: illegal-content risk assessments, **age assurance for content harmful to children** (enforced since 2025).
- **US Section 230 / DMCA** — liability shield and copyright safe harbor (register a DMCA agent; run notice-and-takedown).
- **Age-verification laws** — spreading US state patchwork (Texas HB 1181 upheld 2025; app-store age-verification laws in Texas/Utah) and equivalents abroad.
- **GDPR Art. 8 / COPPA / UK & CA Age-Appropriate Design Codes** — children's UX duties if minors plausibly use the product.

---

## 9. IP, licensing & trade compliance (LAW)

- **Open-source license compliance** — every dependency's license (MIT/Apache-2.0/BSD vs GPL/AGPL/SSPL copyleft obligations). AGPL in a SaaS backend is the classic trap. Tooling: SPDX identifiers, license scanners, an OSS policy. **OpenChain (ISO/IEC 5230)** is the certifiable process standard.
- **Export controls — EAR** (US): most software is EAR99, but **encryption** functionality can trigger classification (5D002) and one-time self-classification reporting; publicly available open-source crypto has carve-outs.
- **Sanctions — OFAC**: no provision of services to embargoed countries/SDN-listed persons. Requires geo/entity screening even for a free SaaS.
- **Encryption import rules** — France, China, Russia and others regulate import/use of cryptography.
- **Patent/trademark/copyright hygiene** — freedom-to-operate on your own methods; trademark clearance on the product name in target markets; provenance rules for AI-generated code/content in your IP chain.

---

## 10. Software quality & engineering standards (VOLUNTARY — adopt for discipline, cite in diligence)

- **ISO/IEC 25010** (SQuaRE) — product-quality model (functional suitability, reliability, security, maintainability…): the vocabulary of quality requirements.
- **ISO/IEC/IEEE 12207** — software lifecycle processes; **ISO/IEC/IEEE 29148** — requirements engineering; **ISO/IEC/IEEE 29119** — software testing.
- **ISO 9001** — organizational quality management; sometimes demanded in tenders.
- **CMMI** — process-maturity model; largely displaced outside defense.
- **ISO/IEC 20000-1 / ITIL** — IT service management, if you run managed services.
- **ISO 22301** — business continuity; increasingly asked alongside SOC 2.
- **Semantic Versioning, OpenAPI, RFC-standard protocol conformance** — interoperability expectations rather than compliance, but they appear in enterprise technical due diligence.

---

## 11. Employment & workplace-specific (LAW — trigger: your product makes or informs decisions about workers)

Beyond §4's AI rules: **Title VII / ADA / ADEA disparate-impact doctrine**, the **Uniform Guidelines on Employee Selection Procedures** (validation evidence: content, construct, criterion validity — the framework I-O psychologists audit against), **state fair-chance and salary-history laws** (what a hiring tool may ask/surface), **FCRA** if furnishing background-check-like reports on people (broad definition — "consumer report" can capture algorithmic scores sold to employers), and **GDPR Art. 22** (right not to be subject to solely automated decisions with legal/significant effect — directly implicates automated hiring/matching for EU users).

---

## 12. Quick applicability matrix — what a typical product actually faces

| Product situation | Practically unavoidable set |
|---|---|
| Any public web product | State breach laws, FTC §5, ePrivacy/cookies if EU-reachable, GDPR if EU users, accessibility (litigation risk), OFAC screening, OSS license hygiene, DMCA agent |
| B2B SaaS selling to enterprises | + SOC 2 Type II (or ISO 27001), vendor DPAs, security questionnaires, ISO 42001/AI addenda if AI features |
| Takes payments | + PCI DSS (scope-reduced via tokenization), sales tax/VAT |
| Has EU customers | + GDPR representative & transfers, EAA if consumer-facing, CRA by Dec 2027, DSA basics if user content |
| AI features touching consequential decisions | + §4 in full, EEOC/UGESP if employment, GDPR Art. 22, FCRA analysis |
| Mobile app | + Apple/Google policies, age-rating, privacy labels |
| Sells to US government | + FedRAMP/StateRAMP, Section 508, FAR/DFARS |
| Health / finance / education / children | + the relevant §6/§8 regime |

---

## Sources (regulatory status verified 2026-08-20)

- [Travers Smith — EU agrees to delay key AI Act compliance deadlines](https://www.traverssmith.com/knowledge/knowledge-container/eu-agrees-to-delay-key-ai-act-compliance-deadlines/) (high-risk → Dec 2, 2027, provisional)
- [Holland & Knight — EU AI Act August 2026 deadline analysis](https://www.hklaw.com/en/insights/publications/2026/04/us-companies-face-eu-ai-acts-possible-august-2026-compliance-deadline)
- [Covington Inside Privacy — AI Act timeline relief and simplification](https://www.insideprivacy.com/artificial-intelligence/eu-ai-act-update-timeline-relief-targeted-simplification-and-new-prohibitions/)
- [MultiState — 20 state privacy laws in effect in 2026](https://www.multistate.us/insider/2026/2/4/all-of-the-comprehensive-privacy-laws-that-take-effect-in-2026)
- [Seyfarth — Colorado postpones AI law; California employment AI regs; Illinois disclosure law](https://www.seyfarth.com/news-insights/artificial-intelligence-legal-roundup-colorado-postpones-implementation-of-ai-law-as-california-finalizes-new-employment-discrimination-regulations-and-illinois-disclosure-law-set-to-take-effect.html)
- [Proskauer — Colorado AI law on ice ahead of implementation](https://www.lawandtheworkplace.com/2026/05/major-developments-put-colorados-ai-law-on-ice-ahead-of-implementation/)
- [Schellman — NIS2, CRA, DORA update](https://www.schellman.com/blog/cybersecurity/european-compliance-nis2-cra-dora)
- [Level Access — European Accessibility Act compliance guide](https://www.levelaccess.com/compliance-overview/european-accessibility-act-eaa/)
- [Accessibility.Works — 2026 ADA/WCAG standards & Title II dates](https://www.accessibility.works/blog/wcag-ada-website-compliance-standards-requirements/)
- [K&L Gates — AI employment landscape 2026](https://www.klgates.com/thought-leadership/Navigating-the-AI-Employment-Landscape-in-2026-Considerations-and-Best-Practices-for-Employers-2-2-2026)
