from flask import Flask, jsonify, request
from flask_bcrypt import Bcrypt
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required, get_jwt_identity
)
from flask_sqlalchemy import SQLAlchemy





app = Flask(__name__)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///users.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

#Configuring secret keys for JWTs
app.config["JWT_SECRET_KEY"] = "super-secret-key"


bcrypt = Bcrypt(app)
jwt = JWTManager(app)

#storing users in dictionary until I have a db setup
users = {}


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    name = db.Column(db.String(120))
    role = db.Column(db.String(50))
    



@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json();
    email = data.get("email")
    password = data.get("password")


    user=users.get(email)
    
    if not user or not bcrypt.check_password_hash(user["password"], password):
        return jsonify({"error": "Invalid credentials"}), 401

    token = create_access_token(identity=email)
    return jsonify({"message": "login successful", "user": user, "token": token})


@app.route("/api/register", methods=["POST"])
def register():

    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    if email in users:
        return jsonify({"error": "User already exists"}), 400
    
    hashed_pw = bcrypt.generate_password_hash(password).decode("utf-8")


    users[email] = {
        "email": email,
        "name": data.get("name"),
        "role": data.get("role"),
        "password": hashed_pw
    }

    return jsonify({"message": "registered", "user": users[email]}), 201





@app.route("/api/profile", methods=["GET"])
@jwt_required()
def profile():
    current_user = get_jwt_identity()
    return jsonify(users[current_user])


if __name__ == "__main__":
    app.run(debug=True)
