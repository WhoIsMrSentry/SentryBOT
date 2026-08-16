from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore
import numpy as np

try:
    from .cascade_loader import load_frontal_face_cascade
except Exception:
    from modules.vlm_bridge.services.cascade_loader import load_frontal_face_cascade  # type: ignore

logger = logging.getLogger("vlm_bridge.face_manager")


class FaceManager:
    """OpenCV ORB + FLANN tabanli hafif yuz tanima yoneticisi.

    Not:
    - Bu sinif dlib/face_recognition gerektirmez.
    - Kayitli her kisi icin ORB descriptor seti JSON dosyasina yazilir.
    """

    def __init__(
        self,
        data_dir: str = "data",
        filename: str = "faces.json",
        ratio_test: float = 0.72,
        min_good_matches: int = 10,
        min_score: float = 0.15,
        social_db: Optional[object] = None,
    ):
        self.data_dir = data_dir
        self.faces_file = os.path.join(data_dir, filename)
        self.ratio_test = float(ratio_test)
        self.min_good_matches = int(min_good_matches)
        self.min_score = float(min_score)

        if social_db is None:
            try:
                from modules.social_db import get_default as _social_default  # type: ignore

                social_db = _social_default()
            except Exception:
                social_db = None
        self._social_db = social_db

        self.known_face_names: List[str] = []
        self._known_descriptors: Dict[str, np.ndarray] = {}

        self._ensure_data_dir()
        self._cascade = load_frontal_face_cascade(logger)
        self._orb = cv2.ORB_create(nfeatures=700)
        self._flann = cv2.FlannBasedMatcher(
            dict(algorithm=6, table_number=6, key_size=12, multi_probe_level=1),
            dict(checks=64),
        )

        self.load_faces()

    def _ensure_data_dir(self) -> None:
        os.makedirs(self.data_dir, exist_ok=True)

    def _to_gray(self, image: np.ndarray) -> Optional[np.ndarray]:
        if image is None or not hasattr(image, "shape"):
            return None
        try:
            if len(image.shape) == 2:
                gray = image
            elif len(image.shape) == 3 and image.shape[2] >= 3:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            else:
                return None
            return cv2.equalizeHist(gray)
        except Exception:
            return None

    def _extract_largest_face_roi(self, image: np.ndarray) -> Optional[np.ndarray]:
        gray = self._to_gray(image)
        if gray is None:
            return None

        faces = []
        if self._cascade is not None and not getattr(self._cascade, "empty", lambda: True)():
            try:
                faces = self._cascade.detectMultiScale(
                    gray,
                    scaleFactor=1.1,
                    minNeighbors=3,
                    minSize=(40, 40),
                )
            except Exception:
                faces = []

        if faces is None or len(faces) == 0:
            return None

        x, y, w, h = max(faces, key=lambda f: int(f[2]) * int(f[3]))
        x1 = max(0, int(x))
        y1 = max(0, int(y))
        x2 = min(gray.shape[1], int(x + w))
        y2 = min(gray.shape[0], int(y + h))
        if x2 <= x1 or y2 <= y1:
            return None
        return image[y1:y2, x1:x2].copy()

    def _extract_descriptor(self, face_roi: np.ndarray) -> Optional[np.ndarray]:
        gray = self._to_gray(face_roi)
        if gray is None:
            return None
        try:
            gray = cv2.resize(gray, (160, 160), interpolation=cv2.INTER_AREA)
        except Exception:
            return None
        _kp, desc = self._orb.detectAndCompute(gray, None)
        if desc is None or len(desc) == 0:
            return None
        return desc.astype(np.uint8)

    def _best_match(self, descriptor: np.ndarray) -> Tuple[str, float, int]:
        best_name = "Unknown"
        best_score = 0.0
        best_good = 0

        for name, known_desc in self._known_descriptors.items():
            if known_desc is None or len(known_desc) == 0:
                continue
            try:
                pairs = self._flann.knnMatch(descriptor, known_desc, k=2)
            except Exception:
                continue

            good = 0
            total = 0
            for pair in pairs:
                if len(pair) < 2:
                    continue
                m, n = pair
                total += 1
                if m.distance < self.ratio_test * n.distance:
                    good += 1

            if total <= 0:
                continue
            score = good / float(total)
            if score > best_score or (abs(score - best_score) < 1e-6 and good > best_good):
                best_name = name
                best_score = score
                best_good = good

        return best_name, best_score, best_good

    def _load_faces_from_social_db(self) -> bool:
        try:
            rows = self._social_db.face_descriptors.list_all_by_kind("orb")
        except Exception as exc:
            logger.warning("face_descriptors load from social_db failed: %s", exc)
            return False
        for _pid, row in rows:
            try:
                rows_n = int(row.get("rows") or 0)
                cols_n = int(row.get("cols") or 32)
                blob = bytes(row.get("blob") or b"")
                if not blob or cols_n <= 0:
                    continue
                arr = np.frombuffer(blob, dtype=np.uint8)
                if rows_n <= 0:
                    rows_n = max(1, arr.size // max(1, cols_n))
                arr = arr.reshape(rows_n, cols_n)
                if arr.ndim != 2 or arr.shape[1] != 32:
                    continue
                name = str(row.get("display_name") or row.get("canonical_name") or "").strip()
                if not name:
                    continue
                self._known_descriptors[name] = arr
            except Exception:
                continue
        self.known_face_names = sorted(self._known_descriptors.keys())
        logger.info("Loaded %d known faces from social_db.", len(self.known_face_names))
        return True

    def _load_faces_from_json(self) -> bool:
        if not os.path.exists(self.faces_file):
            logger.info("No existing faces file found.")
            return False
        try:
            with open(self.faces_file, "r", encoding="utf-8") as f:
                raw = json.load(f) if os.path.getsize(self.faces_file) > 0 else {}
        except Exception as exc:
            logger.warning("Failed to load faces file: %s", exc)
            return False
        if not isinstance(raw, dict):
            logger.warning("Faces file format invalid, expected dict.")
            return False
        for name, item in raw.items():
            desc_list = None
            if isinstance(item, dict):
                desc_list = item.get("descriptors")
            elif isinstance(item, list):
                desc_list = item
            if not isinstance(desc_list, list) or not desc_list:
                continue
            try:
                arr = np.array(desc_list, dtype=np.uint8)
                if arr.ndim != 2 or arr.shape[1] != 32:
                    continue
                self._known_descriptors[str(name)] = arr
                self.known_face_names.append(str(name))
            except Exception:
                continue
        logger.info("Loaded %d known faces.", len(self.known_face_names))
        return True

    def load_faces(self) -> None:
        self.known_face_names = []
        self._known_descriptors = {}
        if self._social_db is not None and self._load_faces_from_social_db():
            return
        self._load_faces_from_json()

    def save_faces(self) -> None:
        if self._social_db is not None:
            try:
                for name, desc in self._known_descriptors.items():
                    arr = desc.astype(np.uint8)
                    rec = self._social_db.persons.upsert(name=name)
                    pid = str(rec.get("id") or "")
                    if not pid:
                        continue
                    self._social_db.face_descriptors.replace_for_person(
                        person_id=pid,
                        kind="orb",
                        blob=arr.tobytes(),
                        rows=int(arr.shape[0]),
                        cols=int(arr.shape[1]),
                        score=1.0,
                    )
                logger.info("Faces persisted to social_db.")
            except Exception as exc:
                logger.error("Failed to persist faces to social_db: %s", exc)
            return

        data: Dict[str, Dict[str, List[List[int]]]] = {}
        for name, desc in self._known_descriptors.items():
            data[name] = {"descriptors": desc.astype(np.uint8).tolist()}

        try:
            with open(self.faces_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info("Faces saved successfully.")
        except Exception as exc:
            logger.error("Failed to save faces: %s", exc)

    def register_face(self, name: str, image: np.ndarray) -> bool:
        if not name or not str(name).strip():
            return False

        roi = self._extract_largest_face_roi(image)
        if roi is None:
            logger.warning("No face found in image.")
            return False

        desc = self._extract_descriptor(roi)
        if desc is None:
            logger.warning("Could not extract ORB descriptor for face.")
            return False

        person = str(name).strip()
        self._known_descriptors[person] = desc
        self.known_face_names = sorted(self._known_descriptors.keys())
        self.save_faces()
        logger.info("Registered/updated face: %s", person)
        return True

    def identify_face_with_score(self, image: np.ndarray) -> Tuple[str, float]:
        if not self._known_descriptors:
            return "Unknown", 0.0

        roi = self._extract_largest_face_roi(image)
        if roi is None:
            roi = image

        desc = self._extract_descriptor(roi)
        if desc is None:
            return "Unknown", 0.0

        best_name, best_score, best_good = self._best_match(desc)
        if best_good < self.min_good_matches or best_score < self.min_score:
            return "Unknown", float(best_score)
        return best_name, float(best_score)

    def identify_face(self, image: np.ndarray) -> str:
        name, _score = self.identify_face_with_score(image)
        return name