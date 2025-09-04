from resume_parser import parse_resume
from embedding import embed_and_compare

resume_text = parse_resume("Sebastian Grammas Resume S25.pdf")
job_text = "Looking for a backend engineer with strong Python and AWS cloud background."
embed_and_compare(resume_text, job_text)