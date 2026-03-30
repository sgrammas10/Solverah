from company import (
    CompanyProfile, CompanyOverview, Executive, CultureValues,
    Compensation, InterviewProcess, RemotePolicy, GlassdoorRatings,
    NewsControversies, RecruitingContacts, TechStack, InternshipProgram,
    WorkforceSignals,
)

google = CompanyProfile(
    overview=CompanyOverview(
        name="Google",
        founded=1998,
        website="https://abc.xyz",
        industry="Big Tech / AI",
        size="enterprise",
        headquarters="Mountain View, USA",
        ownership="Public (NASDAQ: GOOGL)",
        revenue_est="$307B (FY2023)",
        headcount_est="~182,000",
    ),
    executives=[
        Executive(name="Sundar Pichai", title="CEO, Alphabet & Google", linkedin_url="https://www.linkedin.com/in/sundarpichai/"),
        Executive(name="Ruth Porat", title="SVP & CFO, Alphabet", linkedin_url="https://www.linkedin.com/in/ruth-porat-8799452/"),
        Executive(name="Prabhakar Raghavan", title="SVP, Google", linkedin_url="https://www.linkedin.com/in/prabhakar-raghavan-5b93bb/"),
        Executive(name="Jeff Dean", title="Chief Scientist, Google DeepMind", linkedin_url="https://www.linkedin.com/in/jeff-dean-8b212555/"),
        Executive(name="Thomas Kurian", title="CEO, Google Cloud", linkedin_url="https://www.linkedin.com/in/thomas-kurian-469b6b3/"),
    ],
    culture=CultureValues(
        culture_narrative=(
            "Google fosters a culture of intellectual curiosity and data-driven decision-making, "
            "where engineers are given significant autonomy to pursue moonshot ideas alongside core "
            "product work. Teams operate with a relatively flat hierarchy and OKRs provide shared "
            "alignment across functions. The pace is fast but offset by genuine investment in employee "
            "wellbeing. Cross-functional collaboration is deeply embedded — alignment is expected "
            "before major decisions ship."
        ),
        core_values=["curiosity", "data-driven", "moonshot thinking", "openness", "impact at scale"],
        work_environment="collaborative, high-autonomy",
        pace="fast",
        empathy=0.65,
        creative_drive=0.85,
        adaptability=0.75,
        futuristic=0.9,
        harmony=0.7,
        data_orientation=0.95,
    ),
    compensation=Compensation(
        new_grad_swe_total="$220K–$280K",
        mid_level_total="$300K–$450K",
        senior_total="$400K–$600K+",
        base_range="$140K–$200K (L3–L5)",
        equity_notes="4-year RSU vest; refreshes common at L5+",
        bonus="15–25% target annual",
        levels="L3 (New Grad) → L4 → L5 (Senior) → L6 (Staff) → L7 (Principal)",
        notes="levels.fyi verified. Total comp includes base + RSU + bonus. Equity refreshes make senior L5+ comp significantly higher.",
    ),
    interview=InterviewProcess(
        difficulty="Very High",
        process_overview="1 recruiter screen → 1 phone tech screen → 4-5 onsite rounds (coding, system design, behavioral, Googleyness)",
        coding_focus="LeetCode hard, data structures, algorithms, graph problems",
        system_design=True,
        behavioral="Googleyness & Leadership round; STAR format expected",
        avg_rounds=6,
        timeline="4–8 weeks",
        notes="HC (Hiring Committee) review adds time. Strong emphasis on problem-solving approach over just correctness. Notoriously competitive for new grads.",
    ),
    remote_policy=RemotePolicy(
        policy="Hybrid (3 days in office)",
        remote_friendly="Limited",
        details="Google requires most employees to be in office Tue–Thu. Remote exceptions exist but are limited and require approval. Major hubs: MTV, NYC, Seattle, London, Zurich.",
    ),
    glassdoor=GlassdoorRatings(
        overall_rating=4.3,
        ceo_approval="87%",
        recommend_to_friend="84%",
        work_life_balance=4.1,
        compensation_score=4.5,
        culture_score=4.3,
        key_positives="Smart colleagues, great perks, strong compensation, career growth",
        key_negatives="Bureaucracy, slow promotions, political internal dynamics, 'not the old Google'",
        source="Glassdoor aggregate, 2024",
    ),
    news=NewsControversies(
        controversy_level="High",
        key_topics="Antitrust, AI ethics, layoffs, defense contracts",
        recent_news=(
            "2023–2024 layoffs (12,000+); Gemini AI launch and controversies around image generation; "
            "DOJ antitrust trial (search monopoly); Pixel hardware restructuring; tension with employees "
            "over Israel contracts (Project Nimbus)."
        ),
    ),
    recruiting=RecruitingContacts(
        key_programs="STEP (freshman/soph), SWE Intern, APM Intern, UX Intern",
        university_recruiting_url="https://careers.google.com/students/",
        general_jobs_url="https://careers.google.com",
        linkedin_search_tip='Search "Google University Recruiter" on LinkedIn',
        recruiter_tip="Google recruiters are active on LinkedIn. Connecting with a university recruiter at your target campus increases visibility. Referrals are highly effective.",
    ),
    tech_stack=TechStack(
        frontend="Angular, React (internal), Polymer",
        backend="Go, C++, Java, Python, Kotlin",
        infrastructure="GCP, Kubernetes (originated here), Borg",
        data_ml="TensorFlow, JAX, BigQuery, Vertex AI",
        devtools_cicd="Bazel, Critique (internal CR), Piper (mono-VCS)",
        notable_oss="Kubernetes, TensorFlow, gRPC, Abseil",
        primary_languages="Go, C++, Python, Java",
        notes="Mono-repo (Piper) with Bazel build system. Enormous internal tooling surface.",
    ),
    internship=InternshipProgram(
        program_exists=True,
        program_name="Google STEP / SWE Intern / APM Intern",
        duration_weeks="12–14",
        roles_available="SWE, PM (APM), UX, Data, Hardware, Business",
        weekly_comp_usd="$8,000–$10,000",
        return_offer_rate="~85%",
        pipeline_to_fulltime="Strong — majority of new grad SWE class is ex-intern",
        application_timeline="Aug–Jan (for following summer)",
        intern_headcount_est="4,000–6,000 / year",
        notes="STEP is for freshman/sophomore; SWE Intern for juniors+. APM is highly competitive. Housing stipend included.",
    ),
    workforce_signals=WorkforceSignals(
        warn_activity="Multiple WARN filings 2023–2024 tied to the Jan 2023 12,000-person layoff and subsequent restructuring rounds.",
        warn_risk_level="Medium",
        warn_analyst_note="WARN activity is real but largely reflects the post-2022 correction. Ongoing restructuring in hardware and some moonshot divisions. Core Search and Cloud teams appear stable.",
        reddit_glassdoor_themes="Glassdoor themes: bureaucracy increasing, slower promotions, 'not the old Google.' Reddit r/cscareerquestions: Google seen as safer than Meta/Amazon but less exciting than pre-2022.",
        linkedin_signals="LinkedIn hiring velocity is recovering; heavy headcount growth in AI/Cloud. Some senior departures to OpenAI/Anthropic noted.",
        news_press_signals="2023 layoffs widely covered. 2024: restructuring of Pixel hardware team, Assistant group realigned to Gemini. Generally stable externally.",
        overall_workforce_risk="Medium",
        signal_confidence="Pattern-based",
        analyst_summary="Post-correction stabilization. AI pivot is real. Workforce risk is moderate and driven by structural realignment, not financial distress. WARN data reflects a one-time correction, not ongoing instability.",
    ),
)
