# main.py
from flask import Flask, Response, redirect, request, jsonify
from flask_socketio import SocketIO, emit
import cv2
import mediapipe as mp
import numpy as np
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import timedelta

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = 'super-secret'
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(minutes=30)

db = SQLAlchemy(app)
jwt = JWTManager(app)
socketio = SocketIO(app)

# User Model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)

    def __repr__(self):
        return f'<User {self.username}>'

# Pose Model
class Pose(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    skill_level = db.Column(db.String(50))
    images = db.Column(db.String(255))  # URL to image
    ytlink = db.Column(db.String(255))
    tips = db.Column(db.Text)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'skill_level': self.skill_level,
            'images': self.images,
            'ytlink': self.ytlink,
            'tips': self.tips,
        }

with app.app_context():
    db.create_all()

mpDraw = mp.solutions.drawing_utils
mPose = mp.solutions.pose
pose = mPose.Pose()

VIDEO_SOURCE = "./test/tree3.mp4" # Replace with your video source.
reference_landmarks_by_pose = np.load("reference_landmarks_20241209_222448.npy", allow_pickle=True).item()
camera = None
active_connections = 0

def release_camera():
    global camera
    if camera is not None:
        camera.release()
        camera = None
        print("Camera released")

def get_landmarks(landmarks):
    return np.array([[lmk.x, lmk.y, lmk.z] for lmk in landmarks.landmark])

def normalize_landmarks(landmarks):
    torso_center = (landmarks[11] + landmarks[12]) / 2
    normalized = landmarks - torso_center
    max_distance = np.linalg.norm(landmarks[11] - landmarks[12])
    return normalized / max_distance

def compare_poses(current_landmarks, reference_landmarks):
    current_landmarks = normalize_landmarks(current_landmarks)
    reference_landmarks = normalize_landmarks(reference_landmarks)
    distances = np.linalg.norm(current_landmarks - reference_landmarks, axis=1)
    score = 100 - (np.mean(distances) * 100)
    score = max(min(score, 100), 0)
    score *= 1.5
    if score > 100:
        score -= (0.5 * score)
    return score

@socketio.on('connect')
def handle_connect():
    global active_connections
    active_connections += 1
    print("Client connected. Active:", active_connections)
    emit('message', {'data': 'Connected to WebSocket'})

@socketio.on('disconnect')
def handle_disconnect():
    global active_connections
    active_connections -= 1
    print("Client disconnected. Active:", active_connections)
    if active_connections <= 0:
        release_camera()

@socketio.on('stop_camera')
def stop_camera():
    print("Stop camera requested from frontend.")
    release_camera()

def generate_video():
    global camera
    while camera is not None and camera.isOpened():
        success, img = camera.read()
        if not success:
            break

        imgRGB = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        results = pose.process(imgRGB)

        if results.pose_landmarks:
            mpDraw.draw_landmarks(img, results.pose_landmarks, mPose.POSE_CONNECTIONS)
            current_landmarks = get_landmarks(results.pose_landmarks)

            best_score = 0
            best_pose_name = "Unknown"
            feedback = ""
            for pose_name, ref_landmarks_list in reference_landmarks_by_pose.items():
                for ref_landmarks in ref_landmarks_list:
                    score = compare_poses(current_landmarks, ref_landmarks)
                    if score > best_score:
                        best_score = score
                        best_pose_name = pose_name

                    if best_pose_name == "Unknown" or best_pose_name == "no_pose":
                        best_score = 0

                    if best_score > 90:
                        feedback = "Nice!! You are doing good!!"

                    elif best_score > 85:
                        feedback = "Good!! But, You can do better!!"
                    else:
                        feedback = "Needs Improvement!!"

            socketio.emit('pose_feedback', {
                'feedback': feedback,
                'score': int(best_score),
                'pose': best_pose_name
            })

            cv2.putText(img, f'Pose Accuracy: {int(best_score)}%', (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2)
            cv2.putText(img, feedback, (10, 70),
                        cv2.FONT_HERSHEY_SIMPLEX, 1,
                        (0, 255, 0) if best_score > 85 else (0, 0, 255), 2)
            cv2.putText(img, best_pose_name, (10, 110),
                        cv2.FONT_HERSHEY_SIMPLEX, 1,
                        (0, 255, 0) if best_score > 85 else (0, 0, 255), 2)

        _, buffer = cv2.imencode('.jpg', img)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

    release_camera()

@app.route('/')
def home():
    release_camera()
    return redirect('http://localhost:5173')

@app.route('/video_feed')
@jwt_required()
def video_feed():
    global camera
    release_camera()
    camera = cv2.VideoCapture(VIDEO_SOURCE)
    return Response(generate_video(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/stop_camera')
@jwt_required()
def stop_camera_route():
    release_camera()
    return "Camera stopped"

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'message': 'Username and password are required'}), 400

    existing_user = User.query.filter_by(username=username).first()
    if existing_user:
        return jsonify({'message': 'Username already exists'}), 400

    hashed_password = generate_password_hash(password)
    new_user = User(username=username, password=hashed_password)
    db.session.add(new_user)
    db.session.commit()

    return jsonify({'message': 'User created successfully'}), 201

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'message': 'Username and password are required'}), 400

    user = User.query.filter_by(username=username).first()
    if user and check_password_hash(user.password, password):
        access_token = create_access_token(identity=username)
        return jsonify({'access_token': access_token}), 200
    else:
        return jsonify({'message': 'Invalid credentials'}), 401

@app.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    return jsonify({'message': 'Logout successful'}), 200

# Pose CRUD Routes
@app.route('/poses', methods=['POST'])
@jwt_required()
def create_pose():
    data = request.get_json()
    new_pose = Pose(
        name=data.get('name'),
        skill_level=data.get('skill_level'),
        images=data.get('images'),
        ytlink=data.get('ytlink'),
        tips=data.get('tips'),
    )
    db.session.add(new_pose)
    db.session.commit()
    return jsonify(new_pose.to_dict()), 201

@app.route('/poses', methods=['GET'])
def get_poses():
    poses = Pose.query.all()
    return jsonify([pose.to_dict() for pose in poses]), 200

@app.route('/poses/<int:pose_id>', methods=['GET'])
def get_pose(pose_id):
    pose = Pose.query.get(pose_id)
    if pose:
        return jsonify(pose.to_dict()), 200
    return jsonify({'message': 'Pose not found'}), 404

@app.route('/poses/<int:pose_id>', methods=['PUT'])
@jwt_required()
def update_pose(pose_id):
    pose = Pose.query.get(pose_id)
    if pose:
        data = request.get_json()
        pose.name = data.get('name', pose.name)
        pose.skill_level = data.get('skill_level', pose.skill_level)
        pose.images = data.get('images', pose.images)
        pose.ytlink = data.get('ytlink', pose.ytlink)
        pose.tips = data.get('tips', pose.tips)
        db.session.commit()
        return jsonify(pose.to_dict()), 200
    return jsonify({'message': 'Pose not found'}), 404

@app.route('/poses/<int:pose_id>', methods=['DELETE'])
@jwt_required()
def delete_pose(pose_id):
    pose = Pose.query.get(pose_id)
    if pose:
        db.session.delete(pose)
        db.session.commit()
        return jsonify({'message': 'Pose deleted'}), 200
    return jsonify({'message': 'Pose not found'}), 404

if __name__ == '__main__':
    socketio.run(app, debug=True)
