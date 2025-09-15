import pandas as pd
import random

#  Load your resume dataset 
df = pd.read_csv("UpdatedResumeDataSet.csv")
#  Job descriptions for each category 
job_desc = {
    "Data Science": [
        "Looking for a Data Scientist with strong skills in Python, machine learning, and SQL to analyze large datasets and build predictive models."
    ],
    "HR": [
        "Hiring an HR Specialist to manage recruitment, onboarding, and employee relations for a growing tech company."
    ],
    "Advocate": [
        "Seeking a Legal Advocate with experience in corporate law, contract drafting, and dispute resolution."
    ],
    "Arts": [
        "Hiring a Creative Designer skilled in Adobe Photoshop, Illustrator, and digital media to create visual content for marketing campaigns."
    ],
    "Web Designing": [
        "Looking for a Web Designer with experience in HTML, CSS, JavaScript, and responsive design frameworks."
    ],
    "Mechanical Engineer": [
        "Seeking a Mechanical Engineer to design and test manufacturing equipment, with proficiency in AutoCAD and SolidWorks."
    ],
    "Sales": [
        "Hiring a Sales Executive to build client relationships, generate leads, and achieve monthly revenue targets."
    ],
    "Health and fitness": [
        "Looking for a Fitness Trainer with certification in personal training and knowledge of nutrition planning."
    ],
    "Civil Engineer": [
        "Seeking a Civil Engineer with expertise in construction project management, AutoCAD, and structural analysis."
    ],
    "Java Developer": [
        "Hiring a Java Developer experienced in Spring Boot, Hibernate, and REST API development."
    ],
    "Business Analyst": [
        "Looking for a Business Analyst to gather requirements, analyze workflows, and deliver data-driven insights."
    ],
    "SAP Developer": [
        "Seeking an SAP Developer with expertise in ABAP, FICO, and integration of SAP modules."
    ],
    "Automation Testing": [
        "Hiring a QA Engineer with hands-on experience in Selenium, TestNG, and automation frameworks."
    ],
    "Electrical Engineering": [
        "Looking for an Electrical Engineer to design, maintain, and troubleshoot power distribution systems."
    ],
    "Operations Manager": [
        "Seeking an Operations Manager to oversee daily workflows, optimize efficiency, and manage cross-functional teams."
    ],
    "Python Developer": [
        "Hiring a Python Developer skilled in Django, Flask, and data processing libraries such as Pandas and NumPy."
    ],
    "DevOps Engineer": [
        "Looking for a DevOps Engineer with experience in CI/CD pipelines, Docker, Kubernetes, and cloud infrastructure."
    ],
    "Network Security Engineer": [
        "Hiring a Network Security Engineer to configure firewalls, monitor threats, and ensure cybersecurity compliance."
    ],
    "PMO": [
        "Seeking a Project Management Officer (PMO) to support project governance, track KPIs, and manage documentation."
    ],
    "Database": [
        "Looking for a Database Administrator (DBA) with expertise in SQL Server, MySQL, and database performance tuning."
    ],
    "Hadoop": [
        "Hiring a Big Data Engineer with hands-on experience in Hadoop ecosystem tools such as Hive, Pig, and Spark."
    ],
    "ETL Developer": [
        "Seeking an ETL Developer skilled in Informatica and SQL for building and optimizing data pipelines."
    ],
    "DotNet Developer": [
        "Hiring a .NET Developer experienced in ASP.NET Core, C#, and MVC framework for enterprise applications."
    ],
    "Blockchain": [
        "Looking for a Blockchain Developer with knowledge of Ethereum, smart contracts, and distributed ledger technologies."
    ],
    "Testing": [
        "Hiring a Software Tester with experience in manual testing, writing test cases, and using bug tracking tools like JIRA."
    ],
}

#  Build positive & negative training pairs 
pairs = []

for _, row in df.iterrows():
    resume = row["Resume"]
    category = row["Category"]

    # Positive example: same category
    job_pos = random.choice(job_desc[category])
    pairs.append({"resume_text": resume, "job_text": job_pos, "label": 1})

    # Negative example: different category
    neg_cat = random.choice([c for c in job_desc.keys() if c != category])
    job_neg = random.choice(job_desc[neg_cat])
    pairs.append({"resume_text": resume, "job_text": job_neg, "label": 0})

#save data set
pairs_df = pd.DataFrame(pairs)
pairs_df.to_csv("../Filtered_data/resume_job_pairs.csv", index=False)

print("Training pairs generated and saved to resume_job_pairs.csv")
