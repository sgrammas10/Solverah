from flask import Flask, jsonify, request
from flask_bcrypt import Bcrypt
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required, get_jwt_identity
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.sqlite import JSON



app = Flask(__name__)

from flask_cors import CORS
CORS(app)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///users.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

#Configuring secret keys for JWTs
app.config["JWT_SECRET_KEY"] = "super-secret-key"


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


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    name = db.Column(db.String(120))
    role = db.Column(db.String(50))
    profile_data = db.Column(JSON, default=dict)
    



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


if __name__ == "__main__":
    app.run(debug=True)
