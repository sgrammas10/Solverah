from flask import Flask, jsonify, request
from flask_bcrypt import Bcrypt
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required, get_jwt_identity
)
from flask_sqlalchemy import SQLAlchemy
# from sqlalchemy.dialects.sqlite import JSON
import json
from LLM.profile2model import sorted_mlscores
from model import JobRecommendation, User
from datetime import timedelta
import pandas as pd
from LLM.profile2model import jobs_path

app = Flask(__name__)

from flask_cors import CORS
CORS(app)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///users.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

#Configuring secret keys for JWTs
app.config["JWT_SECRET_KEY"] = "super-secret-key"
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=1) #token expires in 1 hours


bcrypt = Bcrypt(app)
jwt = JWTManager(app)

#storing users in dictionary until I have a db setup
#users = {}

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

    # Optional: recruiter-specific default structure
    if role == "recruiter":
        profile.update({
            "company": "",
            "position": "",
            "hiringGoals": "",
            "openRoles": [],
        })

    return profile
  



@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    user = User.query.filter_by(email=email).first()
    if not user or not bcrypt.check_password_hash(user.password, password):
        return jsonify({"error": "Invalid credentials"}), 401

    #for JWT auth stuff
    token = create_access_token(identity=user.email)
    return jsonify({"message": "login successful", "user": {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role
    }, "token": token})


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
    profile_data = data.get("profileData", {})

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




if __name__ == "__main__":
    app.run(debug=True)
