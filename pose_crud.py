from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import jwt_required

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///poses.db'  # Separate database for poses
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

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
