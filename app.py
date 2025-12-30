from flask import Flask, jsonify, request
from flask_bcrypt import Bcrypt
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    jwt_required,
    get_jwt_identity,
    set_access_cookies,
    unset_jwt_cookies,
)
from flask_talisman import Talisman

import os
import json


#from LLM.profile2model import sorted_mlscores

from model import JobRecommendation, User, db
from datetime import timedelta
import pandas as pd

#from LLM.profile2model import jobs_path

# from geo_utils import geocode_city, haversine_miles


app = Flask(__name__)
from security import init_rate_limiter
from validators import validate_password, clean_profile_data

from flask_cors import CORS
# CORS(app, resources={
#     r"/api/*": {
#         "origins": ["http://localhost:4173", "https://yourdomain.com"],
#     }
# })

# Security headers with Talisman for CSP 
Talisman(
    app,
    content_security_policy={
        "default-src": ["'self'", "https://fonts.gstatic.com", "https://fonts.googleapis.com"],
    },
    force_https=False,  # Set to True in production with HTTPS
)


# update to the one above when domain is ready
CORS(
    app,
    resources={r"/api/*": {
        "origins": [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "https://solverah.vercel.app"
        ]
    }},
    supports_credentials=True,
    allow_headers=["Content-Type", "X-CSRF-TOKEN"],
)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///users.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


#Configuring secret keys for JWTs
app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY")
if not app.config["JWT_SECRET_KEY"]:
    raise RuntimeError("JWT_SECRET_KEY is not set")
app.config["JWT_ACCESS_TOKEN_EXPIRES"]= timedelta(hours=1) #token expires in 1 hours

# Tell JWTs to live in cookies instead of headers
app.config["JWT_TOKEN_LOCATION"] = ["cookies"]

# In dev (http://localhost), this must be False; in prod over HTTPS set to True
app.config["JWT_COOKIE_SECURE"] = True  # True on real HTTPS

# If frontend and backend are on same origin, "Lax" is fine; if cross-site + HTTPS, use "None"
app.config["JWT_COOKIE_SAMESITE"] = "None" # set to none for deployment

# CSRF protection on state-changing methods
app.config["JWT_COOKIE_CSRF_PROTECT"] = False  # Set to True to enable CSRF protection when done setting up
app.config["JWT_CSRF_METHODS"] = ["POST", "PUT", "PATCH", "DELETE"]
app.config["JWT_CSRF_HEADER_NAME"] = "X-CSRF-TOKEN"


db.init_app(app)
with app.app_context():
    db.create_all()


bcrypt = Bcrypt(app)
jwt = JWTManager(app)

limiter = init_rate_limiter(app)

#Helper function for inital setup of profile on registration
def default_profile(email="", name="", role="job-seeker"):
    first = name.split(" ")[0] if name else ""
    last = " ".join(name.split(" ")[1:]) if name else ""

    # Default job-seeker profile
    profile = {
        "firstName": first,
        "lastName": last,
        "email": email,
        "phone": "",
        "location": "",
        "summary": "",
        "experience": [],
        "education": [],
        "skills": [],
        "performanceReviews": [],
        "psychometricResults": {
            "leadership": {"score": None, "percentile": None, "completed": False},
            "problemSolving": {"score": None, "percentile": None, "completed": False},
            "communication": {"score": None, "percentile": None, "completed": False},
            "creativity": {"score": None, "percentile": None, "completed": False},
            "teamwork": {"score": None, "percentile": None, "completed": False},
        },
    }

    if role == "recruiter":
        profile.update({
            "company": "",
            "position": "",
            "hiringGoals": "",
            "openRoles": [],
        })

    return profile
  
ML_ENABLED = os.getenv("ML_ENABLED", "0") == "1"
DEMO_MODE = os.getenv("DEMO_MODE", "0") == "1"



@limiter.limit("5 per minute")
@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    user = User.query.filter_by(email=email).first()
    if not user or not bcrypt.check_password_hash(user.password, password):
        return jsonify({"error": "Invalid credentials"}), 401

    access_token = create_access_token(identity=user.email)

    # Build JSON response
    resp = jsonify({
        "message": "login successful",
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role,
        }
        # can omit "token" now, since it's in the cookie
    })

    # Attach JWT as HttpOnly cookie
    set_access_cookies(resp, access_token)

    return resp

@app.route("/api/logout", methods=["POST"])
@jwt_required()  # requires valid cookie
def logout():
    resp = jsonify({"message": "logout successful"})
    unset_jwt_cookies(resp)
    return resp


#Registering new user
@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")
    name = data.get("name")
    role = data.get("role", "job-seeker")

    #Check user exsistence off of email
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "User already exists"}), 400

    hashed_pw = bcrypt.generate_password_hash(password).decode("utf-8")
    profile_data = default_profile(email=email, name=name, role=role)


    new_user = User(
        email=email,
        password=hashed_pw,
        name=data.get("name"),
        role=data.get("role"),
        profile_data=profile_data
    )
    #adding user to db
    db.session.add(new_user)
    db.session.commit()

    return jsonify({"message": "registered", "user": {
        "id": new_user.id,
        "email": new_user.email,
        "name": new_user.name,
        "role": new_user.role
    }}), 201





#For viewing profile info, requires JWT auth
@app.route("/api/profile", methods=["GET", "POST"])
@jwt_required()
def profile():
    current_email = get_jwt_identity()
    user = User.query.filter_by(email=current_email).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    if request.method == "GET":
        return jsonify({
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role,
            "profileData": user.profile_data or {}
        })

    # Handle profile update (POST)
    data = request.get_json()
    raw_profile_data = data.get("profileData", {})

    # Clean incoming keys
    profile_data = clean_profile_data(raw_profile_data)

    # Merge incoming profile_data with existing profile_data (preserve other fields)
    existing = user.profile_data or {}
    # shallow merge for top-level; quizzes/results should be a dedicated key
    merged = {**existing, **profile_data}

    # If there are quiz results, merge those specially and compute a lightweight summary
    incoming_quiz = profile_data.get("quizResults")
    existing_quiz = existing.get("quizResults") if isinstance(existing, dict) else None

    if incoming_quiz:
        merged_quiz = {}
        if existing_quiz and isinstance(existing_quiz, dict):
            merged_quiz.update(existing_quiz)
        # overwrite/insert incoming quiz entries
        merged_quiz.update(incoming_quiz if isinstance(incoming_quiz, dict) else {})
        merged["quizResults"] = merged_quiz

        # simple summary computation: counts and average selected option index per quiz
        def compute_stats(ans):
            counts = {}
            total = 0
            n = 0

            def walk(v):
                nonlocal total, n
                if isinstance(v, dict):
                    for item in v.values():
                        walk(item)
                elif isinstance(v, list):
                    for item in v:
                        walk(item)
                elif isinstance(v, int):
                    counts[str(v)] = counts.get(str(v), 0) + 1
                    total += v
                    n += 1

            walk(ans)
            avg = (total / n) if n > 0 else None
            return {"counts": counts, "avgIndex": avg, "n": n}

        summary = {}
        for qkey, qval in merged.get("quizResults", {}).items():
            try:
                summary[qkey] = compute_stats(qval)
            except Exception:
                summary[qkey] = {"counts": {}, "avgIndex": None, "n": 0}

        merged["_quizSummary"] = summary

    user.profile_data = merged
    db.session.commit()

    return jsonify({
        "message": "Profile updated successfully",
        "profileData": user.profile_data
    })



@app.route("/api/recommendations", methods=["POST"])
@jwt_required()
def generate_recommendations():
    if DEMO_MODE:
        return jsonify({"recommendations": []}), 200


    current_email = get_jwt_identity()
    user = User.query.filter_by(email=current_email).first_or_404()

    data = request.get_json() or {}
    profile_pipeline_str = data.get("profilePipeline")
    if not profile_pipeline_str:
        return jsonify({"error": "profilePipeline is required"}), 400

    try:
        # pipeline is an array of {section, content}
        pipeline = json.loads(profile_pipeline_str)
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON in profilePipeline"}), 400

    # Collapse sections into one text blob for the model
    # (You can tweak this format as you like.)
    if isinstance(pipeline, list):
        profile_text = "\n\n".join(
            f"{sec.get('section', '')}:\n{sec.get('content', '')}"
            for sec in pipeline
        )
    else:
        # fallback: treat the whole thing as raw text
        profile_text = str(pipeline)

    # Use your SentenceTransformer pipeline

    #remove lines in between when demo is done
    if not ML_ENABLED:
        return jsonify({"error": "Recommendations disabled for demo"}), 503
    
    from LLM.profile2model import sorted_mlscores
    #till here
    
    scores = sorted_mlscores(profile_text)  # returns list of (job_id, score, job_text)

    # Keep only the top N
    TOP_N = 20
    top_scores = scores[:TOP_N]

    # Optionally clear old recommendations for this user
    JobRecommendation.query.filter_by(user_id=user.id).delete()

    # Insert new ones
    for job_id, score, _job_text in top_scores:
        rec = JobRecommendation(user_id=user.id, job_id=job_id, score=score)
        db.session.add(rec)

    db.session.commit()

    # Also return them for immediate use on the frontend
    return jsonify({
        "recommendations": [
            {"job_id": job_id, "score": score}
            for job_id, score, _ in top_scores
        ]
    })


@app.route("/api/recommendations", methods=["GET"])
@jwt_required()
def get_recommendations():

    if DEMO_MODE:
        return jsonify({"recommendations": []}), 200


    current_email = get_jwt_identity()
    user = User.query.filter_by(email=current_email).first_or_404()

    # Get this user's recommendations ordered by score
    recs = (
        JobRecommendation.query
        .filter_by(user_id=user.id)
        .order_by(JobRecommendation.score.desc())
        .all()
    )

    if not recs:
        return jsonify({"recommendations": []})

    # Load the jobs CSV and index by ID
    
    #removes these lines when demo is done
    from LLM.profile2model import jobs_path
    jobs_df = pd.read_csv(jobs_path)
    #till here

    jobs_df = pd.read_csv(jobs_path)
    jobs_by_id = {
        int(row["ID"]): row
        for _, row in jobs_df.iterrows()
        if "ID" in row
    }

    results = []
    for rec in recs:
        row = jobs_by_id.get(rec.job_id)
        if row is None:
            continue

        # Build a job object matching what Feed.tsx currently uses :contentReference[oaicite:7]{index=7}
        job_obj = {
            "ID": rec.job_id,
            "Title": row.get("Title", ""),
            "Company": row.get("Company", ""),
            "Location": row.get("Location", ""),
            "EmploymentType": row.get("EmploymentType", ""),
            "DatePosted": row.get("DatePosted", ""),
            "Remote": row.get("Remote", ""),
            "RoleDescription": row.get("RoleDescription", ""),
            "Experience": row.get("Experience", ""),
            "Link": row.get("Link", ""),
            "score": rec.score,
        }
        results.append(job_obj)

    return jsonify({"recommendations": results})



@app.route("/api/dashboard-data", methods=["GET"])
@jwt_required()
def get_dashboard_data():
    current_email = get_jwt_identity()
    user = User.query.filter_by(email=current_email).first_or_404()

    profile = user.profile_data or {}

    # Example: compute dynamic stats from their data
    profile_completion = 0
    fields = ["firstName", "lastName", "email", "summary", "skills", "experience", "education"]
    filled = sum(1 for f in fields if profile.get(f))
    profile_completion = int((filled / len(fields)) * 100)

    # Count jobs from recommendations
    job_matches = JobRecommendation.query.filter_by(user_id=user.id).count()

    # You can extend this later with live data (applications, views, etc.)
    applications = len(profile.get("applications", [])) if "applications" in profile else 0

    # Simple example recent activity & recommendations
    recent_activity = [
        {"type": "match", "text": "New job match found", "time": "2 hours ago", "icon": "Briefcase"},
        {"type": "assessment", "text": "Complete your leadership assessment", "time": "1 day ago", "icon": "Brain"}
    ]

    recommendations = [
        {"title": "Complete Psychometric Assessment", "description": "Boost visibility", "action": "Take Assessment", "priority": "high", "href": "/job-seeker/profile#assessments"},
        {"title": "Add Recent Experience", "description": "Update your experience section", "action": "Update Profile", "priority": "medium", "href": "/job-seeker/profile#experience"},
    ]

    return jsonify({
        "profileCompletion": f"{profile_completion}%",
        "jobMatches": job_matches,
        "applications": applications,
        "recentActivity": recent_activity,
        "recommendations": recommendations
    })



if __name__ == "__main__":
    app.run(debug=True)
