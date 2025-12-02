import face_recognition
import json
import os
import logging
import numpy as np
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("vision_bridge.face_manager")

class FaceManager:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.faces_file = os.path.join(data_dir, "faces.json")
        self.known_face_encodings: List[np.ndarray] = []
        self.known_face_names: List[str] = []
        
        self._ensure_data_dir()
        self.load_faces()

    def _ensure_data_dir(self):
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)

    def load_faces(self):
        """Load known faces from JSON file."""
        if not os.path.exists(self.faces_file):
            logger.info("No existing faces file found.")
            return

        try:
            with open(self.faces_file, 'r') as f:
                data = json.load(f)
            
            self.known_face_names = []
            self.known_face_encodings = []
            
            for name, encoding_list in data.items():
                self.known_face_names.append(name)
                self.known_face_encodings.append(np.array(encoding_list))
            
            logger.info(f"Loaded {len(self.known_face_names)} known faces.")
        except Exception as e:
            logger.error(f"Failed to load faces: {e}")

    def save_faces(self):
        """Save known faces to JSON file."""
        data = {}
        for name, encoding in zip(self.known_face_names, self.known_face_encodings):
            data[name] = encoding.tolist()
        
        try:
            with open(self.faces_file, 'w') as f:
                json.dump(data, f)
            logger.info("Faces saved successfully.")
        except Exception as e:
            logger.error(f"Failed to save faces: {e}")

    def register_face(self, name: str, image_rgb: np.ndarray) -> bool:
        """Detect and register a face from an image."""
        # Find all faces in the image
        face_locations = face_recognition.face_locations(image_rgb)
        if not face_locations:
            logger.warning("No face found in image.")
            return False
        
        # Assume the largest face is the target if multiple
        # Or just take the first one
        face_encodings = face_recognition.face_encodings(image_rgb, face_locations)
        
        if not face_encodings:
            return False
            
        new_encoding = face_encodings[0]
        
        # Check if already exists (optional, maybe update?)
        # For now, just append
        self.known_face_names.append(name)
        self.known_face_encodings.append(new_encoding)
        self.save_faces()
        logger.info(f"Registered new face: {name}")
        return True

    def identify_face(self, face_encoding: np.ndarray, tolerance: float = 0.6) -> str:
        """Identify a face encoding against known faces."""
        if not self.known_face_encodings:
            return "Unknown"

        matches = face_recognition.compare_faces(self.known_face_encodings, face_encoding, tolerance=tolerance)
        name = "Unknown"

        # If a match was found in known_face_encodings, just use the first one.
        if True in matches:
            first_match_index = matches.index(True)
            name = self.known_face_names[first_match_index]
            
            # Or use the one with the smallest distance
            face_distances = face_recognition.face_distance(self.known_face_encodings, face_encoding)
            best_match_index = np.argmin(face_distances)
            if matches[best_match_index]:
                name = self.known_face_names[best_match_index]

        return name
