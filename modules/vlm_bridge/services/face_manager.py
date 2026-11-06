from __future__ import annotations

import json
import logging
import os
from typing import Dict, List, Optional, Tuple

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore
import numpy as np

try:
    from .cascade_loader import load_frontal_face_cascade
except Exception:
    from modules.vlm_bridge.services.cascade_loader import load_frontal_face_cascade  # type: ignore

try:
    from .yunet_detector import get_sface_recognizer, get_yunet_detector
except Exception:
    get_yunet_detector = lambda: None  # type: ignore
    get_sface_recognizer = lambda: None  # type: ignore

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
        if not os.path.isabs(data_dir):
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            self.data_dir = os.path.join(base_dir, data_dir)
        else:
            self.data_dir = data_dir
        self.faces_file = os.path.join(self.data_dir, filename)
        self.ratio_test = float(ratio_test)
        self.min_good_matches = int(min_good_matches)
        self.min_score = float(min_score)

        if social_db is None:
            try:
                from modules.cognitive_memory import get_default as _social_default  # type: ignore

                social_db = _social_default()
            except Exception:
                social_db = None
        if social_db is None:
            try:
                from modules.cognitive_memory.services.repositories import SocialDb
                db_path = os.path.join(self.data_dir, "social.sqlite3")
                social_db = SocialDb(path=db_path)
            except Exception:
                social_db = None
        self._social_db = social_db

        self.known_face_names: List[str] = []
        self._known_descriptors: Dict[str, np.ndarray] = {}
        self._known_embeddings: Dict[str, np.ndarray] = {}
        self._last_detected_raw_face: Optional[np.ndarray] = None

        self._ensure_data_dir()
        self._yunet = get_yunet_detector()
        self._sface = get_sface_recognizer()
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
        if image is None or not hasattr(image, "shape"):
            return None

        # 1. Try YuNet (Deep Learning, robust against angles/lighting)
        if self._yunet is not None and getattr(self._yunet, "is_available", False):
            try:
                yfaces = self._yunet.detect(image)
                if yfaces:
                    best_yface = max(yfaces, key=lambda f: (f["bbox"][2] - f["bbox"][0]) * (f["bbox"][3] - f["bbox"][1]))
                    x1, y1, x2, y2 = best_yface["bbox"]
                    self._last_detected_raw_face = best_yface.get("raw_face")
                    if x2 > x1 and y2 > y1:
                        return image[y1:y2, x1:x2].copy()
            except Exception as exc:
                logger.debug("YuNet face extraction failed, falling back to Haar: %s", exc)

        # 2. Fallback to Haar Cascade
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
            # ORB yields a small fraction of good matches for 3D faces due to lighting/angle.
            # Normalizing by 40 good matches gives a much more functional and intuitive 0-100% score
            # than dividing by total keypoints (~500), which artificially suppresses the score.
            score = min(1.0, good / 40.0)
            
            if score > best_score or (abs(score - best_score) < 1e-6 and good > best_good):
                best_name = name
                best_score = score
                best_good = good

        return best_name, best_score, best_good

    def _load_faces_from_social_db(self) -> bool:
        loaded = False
        try:
            sface_rows = self._social_db.face_descriptors.list_all_by_kind("sface")
            for _pid, row in sface_rows:
                try:
                    blob = bytes(row.get("blob") or b"")
                    if not blob or len(blob) < 128 * 4:
                        continue
                    arr = np.frombuffer(blob, dtype=np.float32)
                    if arr.size == 128:
                        name = str(row.get("display_name") or row.get("canonical_name") or "").strip()
                        if name:
                            self._known_embeddings[name] = arr / max(1e-9, float(np.linalg.norm(arr)))
                            loaded = True
                except Exception:
                    continue
        except Exception as exc:
            logger.debug("sface descriptors load from social_db skipped: %s", exc)

        try:
            rows = self._social_db.face_descriptors.list_all_by_kind("orb")
        except Exception as exc:
            logger.warning("face_descriptors load from social_db failed: %s", exc)
            return loaded

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
                loaded = True
            except Exception:
                continue

        all_names = sorted(set(self._known_descriptors.keys()) | set(self._known_embeddings.keys()))
        self.known_face_names = all_names
        logger.info("Loaded %d known faces (%d sface, %d orb) from social_db.", len(all_names), len(self._known_embeddings), len(self._known_descriptors))
        return loaded

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
            name_str = str(name).strip()
            if not name_str:
                continue
            desc_list = None
            emb_list = None
            if isinstance(item, dict):
                desc_list = item.get("descriptors")
                emb_list = item.get("embedding")
            elif isinstance(item, list):
                desc_list = item

            if isinstance(emb_list, list):
                try:
                    arr_emb = np.array(emb_list, dtype=np.float32).flatten()
                    if arr_emb.size == 128:
                        self._known_embeddings[name_str] = arr_emb / max(1e-9, float(np.linalg.norm(arr_emb)))
                except Exception:
                    pass

            if isinstance(desc_list, list) and desc_list:
                try:
                    arr = np.array(desc_list, dtype=np.uint8)
                    if arr.ndim == 2 and arr.shape[1] == 32:
                        self._known_descriptors[name_str] = arr
                except Exception:
                    pass

        self.known_face_names = sorted(set(self._known_descriptors.keys()) | set(self._known_embeddings.keys()))
        logger.info("Loaded %d known faces from json.", len(self.known_face_names))
        return True

    def load_faces(self) -> None:
        self.known_face_names = []
        self._known_descriptors = {}
        self._known_embeddings = {}
        if self._social_db is not None:
            try:
                self._load_faces_from_social_db()
            except Exception:
                pass
        if not self._known_descriptors and not self._known_embeddings:
            self._load_faces_from_json()
        self.known_face_names = sorted(set(self._known_descriptors.keys()) | set(self._known_embeddings.keys()))
        logger.info("Total %d known faces registered in FaceManager.", len(self.known_face_names))

    def save_faces(self) -> None:
        persisted = False
        if self._social_db is not None:
            try:
                for name, emb in self._known_embeddings.items():
                    arr = emb.astype(np.float32)
                    rec = self._social_db.persons.upsert(name=name)
                    pid = str(rec.get("id") or "")
                    if not pid:
                        continue
                    self._social_db.face_descriptors.replace_for_person(
                        person_id=pid,
                        kind="sface",
                        blob=arr.tobytes(),
                        rows=1,
                        cols=128,
                        score=1.0,
                    )
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
                persisted = True
            except Exception as exc:
                logger.error("Failed to persist faces to social_db: %s", exc)
        if persisted:
            return

        data: Dict[str, Dict[str, Any]] = {}
        all_names = set(self._known_descriptors.keys()) | set(self._known_embeddings.keys())
        for name in all_names:
            entry: Dict[str, Any] = {}
            if name in self._known_descriptors:
                entry["descriptors"] = self._known_descriptors[name].astype(np.uint8).tolist()
            if name in self._known_embeddings:
                entry["embedding"] = self._known_embeddings[name].astype(np.float32).flatten().tolist()
            data[name] = entry

        try:
            with open(self.faces_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info("Faces saved successfully to %s", self.faces_file)
        except Exception as exc:
            logger.error("Failed to save faces to %s: %s", self.faces_file, exc)

    def register_face(self, name: str, image: np.ndarray) -> bool:
        if not name or not str(name).strip():
            return False

        person = str(name).strip()
        roi = self._extract_largest_face_roi(image)
        if roi is None and (self._yunet is None or not self._yunet.is_available):
            logger.warning("No face found in image.")
            return False

        registered = False

        # 1. SFace embedding (YuNet + SFace)
        if self._sface is not None and getattr(self._sface, "is_available", False):
            raw_face = getattr(self, "_last_detected_raw_face", None)
            if raw_face is None and self._yunet is not None and getattr(self._yunet, "is_available", False):
                yfaces = self._yunet.detect(image)
                if yfaces:
                    raw_face = yfaces[0].get("raw_face")
            if raw_face is not None:
                feat = self._sface.extract_feature(image, raw_face)
                if feat is not None:
                    self._known_embeddings[person] = feat
                    registered = True

        # 2. ORB descriptor (classical fallback)
        if roi is not None:
            desc = self._extract_descriptor(roi)
            if desc is not None:
                self._known_descriptors[person] = desc
                registered = True

        if not registered:
            logger.warning("Could not extract any face descriptor or embedding for %s", person)
            return False

        self.known_face_names = sorted(set(self._known_descriptors.keys()) | set(self._known_embeddings.keys()))
        self.save_faces()
        logger.info("Registered/updated face: %s (sface=%s, orb=%s)", person, person in self._known_embeddings, person in self._known_descriptors)
        return True

    def identify_face_with_score(self, image: np.ndarray) -> Tuple[str, float]:
        if not self._known_descriptors and not self._known_embeddings:
            return "Unknown", 0.0

        # 1. High-accuracy YuNet + SFace recognition
        if self._known_embeddings and self._sface is not None and getattr(self._sface, "is_available", False) and self._yunet is not None and getattr(self._yunet, "is_available", False):
            try:
                yfaces = self._yunet.detect(image)
                if yfaces:
                    best_yface = max(yfaces, key=lambda f: (f["bbox"][2] - f["bbox"][0]) * (f["bbox"][3] - f["bbox"][1]))
                    raw_face = best_yface.get("raw_face")
                    if raw_face is not None:
                        feat = self._sface.extract_feature(image, raw_face)
                        if feat is not None:
                            best_name = "Unknown"
                            best_score = -1.0
                            for name, known_feat in self._known_embeddings.items():
                                score = float(self._sface.match(feat, known_feat))
                                if score > best_score:
                                    best_score = score
                                    best_name = name
                            if best_score >= self._sface.COSINE_MATCH_THRESHOLD:
                                calibrated = min(1.0, 0.5 + 0.5 * ((best_score - self._sface.COSINE_MATCH_THRESHOLD) / (1.0 - self._sface.COSINE_MATCH_THRESHOLD)))
                                return best_name, float(round(calibrated, 3))
                            return "Unknown", float(round(max(0.0, best_score), 3))
            except Exception as exc:
                logger.debug("YuNet+SFace identification failed, trying ORB: %s", exc)

        # 2. Classical ORB + FLANN fallback
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

    def close(self) -> None:
        """Close any open database connections."""
        if self._social_db is not None and hasattr(self._social_db, "close"):
            try:
                self._social_db.close()
            except Exception:
                pass