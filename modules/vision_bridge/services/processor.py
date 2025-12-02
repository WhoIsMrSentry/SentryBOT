import cv2
import time
import threading
import logging
import requests
import numpy as np
from ultralytics import YOLO
from typing import List, Dict, Any, Optional, Generator

logger = logging.getLogger("vision_bridge")

# Try importing face_recognition, handle failure gracefully
try:
    import face_recognition
    FACE_REC_AVAILABLE = True
except ImportError:
    FACE_REC_AVAILABLE = False
    logger.warning("face_recognition library not found. Face recognition features will be disabled.")

try:
    from .face_manager import FaceManager
except ImportError:
    from services.face_manager import FaceManager
try:
    from .semantic_describer import SemanticDescriber
except ImportError:
    from services.semantic_describer import SemanticDescriber
try:
    from .people_memory import PeopleMemory
except ImportError:
    from services.people_memory import PeopleMemory

class VisionProcessor:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        vision_cfg = config.get("vision", {})
        self.processing_mode = vision_cfg.get("processing_mode", "local")  # local | remote
        self.model_path = vision_cfg.get("model_path", "yolov8n.pt")
        self.camera_source = vision_cfg.get("camera_source", 0)
        self.conf_threshold = vision_cfg.get("confidence_threshold", 0.5)

        self.model = None
        if self.processing_mode == "local":
            logger.info(f"[vision_bridge] Local mode: loading YOLO model from {self.model_path}")
            try:
                self.model = YOLO(self.model_path)
            except Exception as e:
                logger.error(f"Failed to load YOLO model: {e}")
        else:
            logger.info("[vision_bridge] Remote mode: skipping local model load")

        self.face_manager = None
        if FACE_REC_AVAILABLE and self.processing_mode == "local":
            self.face_manager = FaceManager()
        
        self._stop_event = threading.Event()
        self._capture_thread: Optional[threading.Thread] = None
        self._inference_thread: Optional[threading.Thread] = None
        
        self.latest_results: List[Dict[str, Any]] = []
        self.blind_mode_enabled = False
        self.last_blind_announcement = 0.0
        self.last_alert_announcement = 0.0
        self._last_person_greet: Dict[str, float] = {}
        
        # Shared state
        self._frame_lock = threading.Lock()
        self._latest_raw_frame: Optional[Any] = None
        self._latest_annotated_frame: Optional[bytes] = None

        # Semantic describer (even in remote mode, works on ingested results)
        self.semantic = SemanticDescriber(config)
        self.memory = PeopleMemory()

    def start_stream_processing(self):
        if self.processing_mode != "local":
            # In remote mode we rely on external processor feeding results
            logger.debug("start_stream_processing() called in remote mode; no-op")
            return
        if self._capture_thread and self._capture_thread.is_alive():
            return
        self._stop_event.clear()
        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._capture_thread.start()
        self._inference_thread = threading.Thread(target=self._inference_loop, daemon=True)
        self._inference_thread.start()
        logger.info("Vision processing started (Multi-threaded, local mode)")

    def stop_stream_processing(self):
        if self.processing_mode != "local":
            return
        self._stop_event.set()
        if self._capture_thread:
            self._capture_thread.join(timeout=2.0)
        if self._inference_thread:
            self._inference_thread.join(timeout=2.0)
        logger.info("Vision processing stopped")

    def _capture_loop(self):
        """Continuously grabs frames from the camera."""
        cap = cv2.VideoCapture(self.camera_source)
        if not cap.isOpened():
            logger.error(f"Could not open camera source: {self.camera_source}")
            return

        while not self._stop_event.is_set():
            ret, frame = cap.read()
            if not ret:
                logger.warning("Failed to read frame, retrying...")
                time.sleep(1.0)
                cap.release()
                cap = cv2.VideoCapture(self.camera_source)
                continue
            
            with self._frame_lock:
                self._latest_raw_frame = frame
            
            # Capture as fast as possible
            time.sleep(0.001)

        cap.release()

    def _inference_loop(self):
        """Runs inference on the latest available frame."""
        while not self._stop_event.is_set():
            frame = None
            with self._frame_lock:
                if self._latest_raw_frame is not None:
                    frame = self._latest_raw_frame.copy()
            
            if frame is None:
                time.sleep(0.1)
                continue

            if self.model is None:
                time.sleep(0.5)
                continue
            # Run YOLO inference
            results = self.model(frame, verbose=False, conf=self.conf_threshold)
            
            parsed_results = []
            annotated_frame = frame.copy()
            
            person_boxes = []
            
            for r in results:
                for box in r.boxes:
                    cls_id = int(box.cls[0])
                    label = self.model.names[cls_id]
                    conf = float(box.conf[0])
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    
                    # Distance estimation
                    distance = -1.0
                    if label == "person":
                        h = y2 - y1
                        if h > 0:
                            distance = (1.7 * 600) / h 
                        
                        # Store for face recognition
                        # YOLO: x1, y1, x2, y2
                        # Face_rec: top, right, bottom, left -> y1, x2, y2, x1
                        person_boxes.append((int(y1), int(x2), int(y2), int(x1)))
                    
                    parsed_results.append({
                        "label": label,
                        "confidence": conf,
                        "bbox": [x1, y1, x2, y2],
                        "distance_m": round(distance, 2) if distance > 0 else None,
                        "name": "Unknown" # Default
                    })

            # Face Recognition
            if self.face_manager and person_boxes:
                # Convert BGR to RGB
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                try:
                    # Compute encodings for detected people
                    encodings = face_recognition.face_encodings(rgb_frame, person_boxes)
                    
                    # Match encodings to names
                    for i, encoding in enumerate(encodings):
                        name = self.face_manager.identify_face(encoding)
                        
                        # Find the corresponding result in parsed_results and update it
                        # The order of person_boxes matches the order we added them
                        # We need to map back.
                        # Since we iterated results linearly, let's just find the person result
                        # This is a bit tricky if there are non-person objects interspersed.
                        # Let's re-iterate parsed_results to find the i-th person.
                        person_idx = 0
                        for res in parsed_results:
                            if res["label"] == "person":
                                if person_idx == i:
                                    res["name"] = name
                                    res["label"] = name # Update label for display
                                    break
                                person_idx += 1
                except Exception as e:
                    logger.error(f"Face recognition error: {e}")

            # Draw annotations
            for res in parsed_results:
                x1, y1, x2, y2 = res["bbox"]
                label = res["label"] # Might be name now
                conf = res["confidence"]
                distance = res["distance_m"]
                
                color = (0, 255, 0)
                if res.get("name") and res["name"] != "Unknown":
                    color = (255, 0, 0) # Blue for known people
                
                cv2.rectangle(annotated_frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
                text = f"{label} {conf:.2f}"
                if distance:
                    text += f" {distance:.1f}m"
                cv2.putText(annotated_frame, text, (int(x1), int(y1) - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

            self.latest_results = parsed_results
            # Alerts & liveliness
            self._evaluate_alerts(parsed_results)
            # Person greet/interaction (local mode)
            self._handle_person_interactions(parsed_results)
            
            # Encode frame for streaming
            ret, buffer = cv2.imencode('.jpg', annotated_frame)
            if ret:
                with self._frame_lock:
                    self._latest_annotated_frame = buffer.tobytes()
            
            if self.blind_mode_enabled:
                self._handle_blind_mode(parsed_results)

            time.sleep(0.05)

    def generate_frames(self) -> Generator[bytes, None, None]:
        """Generator for MJPEG streaming."""
        while True:
            with self._frame_lock:
                frame = self._latest_annotated_frame
            
            if frame:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            else:
                pass
            
            time.sleep(0.05)

    def _handle_blind_mode(self, results: List[Dict[str, Any]]):
        now = time.time()
        interval = self.config.get("vision", {}).get("blind_mode", {}).get("interval_seconds", 5.0)
        
        if now - self.last_blind_announcement < interval:
            return

        if not results:
            return

        # Construct a simple description
        counts = {}
        distances = {}
        for r in results:
            lbl = r["label"] # Uses name if identified
            counts[lbl] = counts.get(lbl, 0) + 1
            if r["distance_m"]:
                if lbl not in distances:
                    distances[lbl] = []
                distances[lbl].append(r["distance_m"])

        text = self.semantic.describe(results)
        # Hafıza: tanınan kişilere özet kaydı
        for r in results:
            name = r.get("name")
            if name and name != "Unknown":
                self.memory.set_summary(name, text)
        self._send_tts(text)
        self.last_blind_announcement = now

    def _send_tts(self, text: str):
        url = self.config.get("speak", {}).get("endpoint") or "http://localhost:8083/speak/say"
        try:
            requests.post(url, json={"text": text}, timeout=1.0)
        except Exception as e:
            logger.error(f"Failed to send TTS: {e}")

    def analyze_snapshot(self) -> List[Dict[str, Any]]:
        """Capture a single frame and analyze it (local mode only)."""
        if self.processing_mode != "local" or self.model is None:
            return [{"error": "Local inference disabled (remote mode)"}]
        cap = cv2.VideoCapture(self.camera_source)
        if not cap.isOpened():
            return [{"error": "Could not open camera"}]
        ret, frame = cap.read()
        cap.release()
        if not ret:
            return [{"error": "Failed to capture frame"}]
        results = self.model(frame, verbose=False, conf=self.conf_threshold)
        parsed_results = []
        
        # ... (Same logic as loop, but simplified) ...
        # For snapshot, we might skip face rec or include it.
        # Let's include it if available.
        
        person_boxes = []
        for r in results:
            for box in r.boxes:
                cls_id = int(box.cls[0])
                label = self.model.names[cls_id]
                conf = float(box.conf[0])
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                
                distance = -1.0
                if label == "person":
                    h = y2 - y1
                    if h > 0:
                        distance = (1.7 * 600) / h
                    person_boxes.append((int(y1), int(x2), int(y2), int(x1)))
                
                parsed_results.append({
                    "label": label,
                    "confidence": conf,
                    "bbox": [x1, y1, x2, y2],
                    "distance_m": round(distance, 2) if distance > 0 else None,
                    "name": "Unknown"
                })

        if self.face_manager and person_boxes:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            try:
                encodings = face_recognition.face_encodings(rgb_frame, person_boxes)
                person_idx = 0
                for i, encoding in enumerate(encodings):
                    name = self.face_manager.identify_face(encoding)
                    for res in parsed_results:
                        if res["label"] == "person":
                            if person_idx == i:
                                res["name"] = name
                                res["label"] = name
                                break
                            person_idx += 1
            except Exception:
                pass

        return parsed_results

    def register_face_from_current_frame(self, name: str) -> bool:
        """Register the largest face in the current frame (local mode only)."""
        if not self.face_manager or self.processing_mode != "local":
            return False
        frame = None
        with self._frame_lock:
            if self._latest_raw_frame is not None:
                frame = self._latest_raw_frame.copy()
        if frame is None:
            return False
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return self.face_manager.register_face(name, rgb_frame)

    # Remote ingestion -------------------------------------------------
    def ingest_remote_results(self, objects: List[Dict[str, Any]]):
        """Accept externally processed detection results (remote mode)."""
        if self.processing_mode != "remote":
            logger.debug("ingest_remote_results called while not in remote mode; updating anyway")
        # Basic validation & normalization
        normalized: List[Dict[str, Any]] = []
        for o in objects:
            if not isinstance(o, dict):
                continue
            label = o.get("label") or o.get("name") or "unknown"
            conf = float(o.get("confidence", o.get("conf", 0)))
            bbox = o.get("bbox") or o.get("box") or []
            distance = o.get("distance_m") or o.get("distance")
            entry = {
                "label": label,
                "confidence": conf,
                "bbox": bbox,
                "distance_m": distance,
                "name": o.get("name", o.get("id", "Unknown")),
            }
            normalized.append(entry)
        self.latest_results = normalized
        self._evaluate_alerts(normalized)
        self._handle_person_interactions(normalized)
        if self.blind_mode_enabled and normalized:
            self._handle_blind_mode(normalized)
        return {"count": len(normalized)}

    # Basit yardımcı: sohbet kaydı
    def record_chat(self, person: str, text: str, role: str = "assistant"):
        self.memory.append_chat(person, role, text)


    # ------------------------------------------------------------------
    def _evaluate_alerts(self, results: List[Dict[str, Any]]):
        vision_cfg = self.config.get("vision", {})
        alerts_cfg = vision_cfg.get("alerts", {})
        if not alerts_cfg or not vision_cfg.get("modes", {}).get("hazards", True):
            return
        classes = set(alerts_cfg.get("classes", []))
        dist_thr = float(alerts_cfg.get("distance_threshold_m", 1.0))
        announce_interval = float(alerts_cfg.get("announce_interval_s", 10.0))
        now = time.time()
        if now - self.last_alert_announcement < announce_interval:
            return
        hazards = []
        for r in results:
            lbl = r.get("label")
            dist = r.get("distance_m")
            if lbl in classes and dist is not None and dist <= dist_thr:
                hazards.append((lbl, dist))
        if not hazards:
            return
        # Build alert text
        parts = [f"{lbl} {dist:.1f}m" for lbl, dist in hazards]
        text = "Dikkat yakın tehlike: " + ", ".join(parts)
        self._send_tts(text)
        self._emit_emotion("alert")
        self.last_alert_announcement = now

    def _emit_emotion(self, emotion: str):
        # Hook to interactions module using its event API
        try:
            requests.post(
                "http://localhost:8080/interactions/event",
                json={"type": f"autonomy.{emotion}"},
                timeout=0.5,
            )
        except Exception:
            pass

    # Person-centric interactions -------------------------------------
    def _handle_person_interactions(self, results: List[Dict[str, Any]]):
        vision_cfg = self.config.get("vision", {})
        if not vision_cfg.get("modes", {}).get("people", True):
            return
        greet_cooldown = float(vision_cfg.get("personalization", {}).get("greet_cooldown_s", 30))
        now = time.time()
        for r in results:
            name = r.get("name")
            if not name or name == "Unknown":
                continue
            last = self._last_person_greet.get(name, 0.0)
            if now - last < greet_cooldown:
                continue
            # Build greeting
            greeting = self._build_greeting(name)
            if greeting:
                self._send_tts(greeting)
            # Emotion and memory
            self._emit_emotion("excited")
            self.memory.append_chat(name, role="system", text=f"Greeted: {greeting}")
            # Optional: ask LLM for a friendly follow-up line
            follow = self._ollama_followup(name)
            if follow:
                self._send_tts(follow)
                self.memory.append_chat(name, role="assistant", text=follow)
            self._last_person_greet[name] = now

    def _build_greeting(self, name: str) -> Optional[str]:
        p_cfg = self.config.get("vision", {}).get("personalization", {})
        known = p_cfg.get("known_people", {})
        if name in known:
            return known[name].get("greeting")
        return f"Merhaba {name}, seni gördüğüme sevindim."

    def _ollama_followup(self, name: str) -> Optional[str]:
        # Query Ollama for a short warm line referencing last summary
        try:
            import httpx  # type: ignore
        except Exception:
            return None
        rec = self.memory.get_person(name) or {}
        last_sum = (rec.get("last_summary") or {}).get("text")
        prompt = f"{name} ile karşılaştın. {('Özet: '+last_sum) if last_sum else ''} Türkçe kısacık ve sıcak bir cümle söyle."
        url = self.config.get("ollama", {}).get("endpoint", "http://localhost:11434/api/generate")
        model = self.config.get("ollama", {}).get("model", "llama3")
        try:
            with httpx.Client(timeout=4.0) as client:
                resp = client.post(url, json={"model": model, "prompt": prompt, "stream": False})
            if resp.status_code == 200:
                data = resp.json()
                return data.get("response")
        except Exception:
            return None
        return None
