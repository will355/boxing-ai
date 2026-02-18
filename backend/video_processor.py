import cv2
import math
from pose import process_frame
import mediapipe as mp

mp_drawing = mp.solutions.drawing_utils
mp_pose = mp.solutions.pose

DEFAULT_SETTINGS = {
    "preset": "balanced",
    "min_visibility": 0.5,
    "speed_threshold": 0.022,
    "extension_threshold": 0.006,
    "elbow_angle_threshold": 120.0,
    "cooldown_sec": 0.15,
    "combo_gap_sec": 0.8,
    "timeline_bucket_sec": 10,
    "min_confidence": 0.0,
}

PRESET_OVERRIDES = {
    "conservative": {
        "speed_threshold": 0.028,
        "extension_threshold": 0.008,
        "elbow_angle_threshold": 130.0,
        "cooldown_sec": 0.18,
        "min_confidence": 0.55,
    },
    "balanced": {},
    "aggressive": {
        "speed_threshold": 0.018,
        "extension_threshold": 0.004,
        "elbow_angle_threshold": 112.0,
        "cooldown_sec": 0.12,
        "min_confidence": 0.35,
    },
}


def _distance(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)


def _joint_angle(a, b, c):
    ab = (a.x - b.x, a.y - b.y)
    cb = (c.x - b.x, c.y - b.y)

    ab_mag = math.hypot(ab[0], ab[1])
    cb_mag = math.hypot(cb[0], cb[1])
    if ab_mag == 0 or cb_mag == 0:
        return 0.0

    cosine = (ab[0] * cb[0] + ab[1] * cb[1]) / (ab_mag * cb_mag)
    cosine = max(-1.0, min(1.0, cosine))
    return math.degrees(math.acos(cosine))


def _classify_punch(dx, dy):
    # Simple 2D heuristic: lateral-heavy movement resembles a hook.
    if abs(dx) > abs(dy) * 1.2:
        return "hook"
    return "straight"


def _clamp(value, low, high):
    return max(low, min(high, value))


def _score_punch(speed, distance_growth, elbow_angle):
    # Normalize each signal to 0..1 and blend into a simple confidence score.
    speed_score = _clamp((speed - 0.022) / 0.03, 0.0, 1.0)
    extension_score = _clamp((distance_growth - 0.006) / 0.02, 0.0, 1.0)
    angle_score = _clamp((elbow_angle - 120.0) / 40.0, 0.0, 1.0)
    return round((0.4 * speed_score) + (0.35 * extension_score) + (0.25 * angle_score), 3)


def _build_fight_analytics(punch_events, duration_sec, combo_gap_sec=0.8, bucket_sec=10):
    if duration_sec <= 0:
        duration_sec = 1e-6

    punches_per_minute = round((len(punch_events) / duration_sec) * 60.0, 2)

    combo_count = 0
    max_combo = 0
    current_combo = 0
    prev_time = None

    for event in punch_events:
        event_time = event["time_sec"]
        if prev_time is None or (event_time - prev_time) <= combo_gap_sec:
            current_combo += 1
        else:
            if current_combo >= 2:
                combo_count += 1
            max_combo = max(max_combo, current_combo)
            current_combo = 1
        prev_time = event_time

    if current_combo >= 2:
        combo_count += 1
    max_combo = max(max_combo, current_combo)

    timeline_counts = {}
    for event in punch_events:
        bucket = int(event["time_sec"] // bucket_sec) * bucket_sec
        label = f"{bucket}-{bucket + bucket_sec}s"
        timeline_counts[label] = timeline_counts.get(label, 0) + 1

    return {
        "duration_sec": round(duration_sec, 3),
        "punches_per_minute": punches_per_minute,
        "total_counted_punches": len(punch_events),
        "combo_count": combo_count,
        "max_combo": max_combo,
        f"timeline_counts_{bucket_sec}s": timeline_counts,
    }


def _resolve_settings(settings):
    merged = dict(DEFAULT_SETTINGS)
    preset = merged["preset"]
    if isinstance(settings, dict):
        if settings.get("preset"):
            preset = str(settings["preset"]).lower()
        merged.update({k: v for k, v in settings.items() if v is not None and k != "preset"})

    if preset not in PRESET_OVERRIDES:
        preset = "balanced"
    merged["preset"] = preset
    merged.update(PRESET_OVERRIDES[preset])

    merged["min_visibility"] = _clamp(float(merged["min_visibility"]), 0.0, 1.0)
    merged["speed_threshold"] = max(0.0, float(merged["speed_threshold"]))
    merged["extension_threshold"] = max(0.0, float(merged["extension_threshold"]))
    merged["elbow_angle_threshold"] = _clamp(float(merged["elbow_angle_threshold"]), 60.0, 180.0)
    merged["cooldown_sec"] = max(0.0, float(merged["cooldown_sec"]))
    merged["combo_gap_sec"] = max(0.0, float(merged["combo_gap_sec"]))
    merged["timeline_bucket_sec"] = max(1, int(merged["timeline_bucket_sec"]))
    merged["min_confidence"] = _clamp(float(merged["min_confidence"]), 0.0, 1.0)
    return merged


def analyze_video(video_path, show_preview=False, settings=None):
    cap = cv2.VideoCapture(video_path)
    cfg = _resolve_settings(settings)

    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 1:
        fps = 30.0

    frame_count = 0
    detected_punches = 0
    counted_punches = 0
    punch_events = []
    counted_events = []
    punches_by_hand = {"left": 0, "right": 0}
    punches_by_type = {"straight": 0, "hook": 0}
    frames_with_pose = 0

    cooldown_frames = max(2, int(fps * cfg["cooldown_sec"]))
    side_state = {
        "left": {"prev_wrist": None, "prev_shoulder_distance": None, "last_punch_frame": -cooldown_frames},
        "right": {"prev_wrist": None, "prev_shoulder_distance": None, "last_punch_frame": -cooldown_frames},
    }

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_count += 1
        results = process_frame(frame)

        if results.pose_landmarks:
            frames_with_pose += 1
            landmarks = results.pose_landmarks.landmark

            side_landmarks = {
                "left": (
                    landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER],
                    landmarks[mp_pose.PoseLandmark.LEFT_ELBOW],
                    landmarks[mp_pose.PoseLandmark.LEFT_WRIST],
                ),
                "right": (
                    landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER],
                    landmarks[mp_pose.PoseLandmark.RIGHT_ELBOW],
                    landmarks[mp_pose.PoseLandmark.RIGHT_WRIST],
                ),
            }

            for side, (shoulder, elbow, wrist) in side_landmarks.items():
                if (
                    shoulder.visibility < cfg["min_visibility"]
                    or elbow.visibility < cfg["min_visibility"]
                    or wrist.visibility < cfg["min_visibility"]
                ):
                    continue

                prev_wrist = side_state[side]["prev_wrist"]
                shoulder_distance = _distance(wrist, shoulder)
                prev_shoulder_distance = side_state[side]["prev_shoulder_distance"]
                elbow_angle = _joint_angle(shoulder, elbow, wrist)

                if prev_wrist is not None and prev_shoulder_distance is not None:
                    dx = wrist.x - prev_wrist.x
                    dy = wrist.y - prev_wrist.y
                    speed = math.hypot(dx, dy)
                    distance_growth = shoulder_distance - prev_shoulder_distance
                    enough_cooldown = frame_count - side_state[side]["last_punch_frame"] >= cooldown_frames

                    # Trigger on fast extension with a mostly opened arm.
                    if (
                        enough_cooldown
                        and speed > cfg["speed_threshold"]
                        and distance_growth > cfg["extension_threshold"]
                        and elbow_angle > cfg["elbow_angle_threshold"]
                    ):
                        punch_type = _classify_punch(dx, dy)
                        timestamp_sec = round(frame_count / fps, 3)
                        confidence = _score_punch(speed, distance_growth, elbow_angle)

                        detected_punches += 1
                        side_state[side]["last_punch_frame"] = frame_count

                        event = {
                            "frame": frame_count,
                            "time_sec": timestamp_sec,
                            "hand": side,
                            "type": punch_type,
                            "confidence": confidence,
                            "counted": confidence >= cfg["min_confidence"],
                            "debug": {
                                "speed": round(speed, 4),
                                "distance_growth": round(distance_growth, 4),
                                "elbow_angle": round(elbow_angle, 2),
                            },
                        }
                        punch_events.append(event)
                        if event["counted"]:
                            counted_punches += 1
                            punches_by_hand[side] += 1
                            punches_by_type[punch_type] += 1
                            counted_events.append(event)

                side_state[side]["prev_wrist"] = wrist
                side_state[side]["prev_shoulder_distance"] = shoulder_distance

            mp_drawing.draw_landmarks(
                frame,
                results.pose_landmarks,
                mp_pose.POSE_CONNECTIONS
            )

        if show_preview:
            cv2.imshow("Pose Detection", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    cap.release()
    if show_preview:
        cv2.destroyAllWindows()

    duration_sec = frame_count / fps if fps > 0 else 0
    analytics = _build_fight_analytics(
        counted_events,
        duration_sec,
        combo_gap_sec=cfg["combo_gap_sec"],
        bucket_sec=cfg["timeline_bucket_sec"],
    )
    pose_coverage = round((frames_with_pose / frame_count), 3) if frame_count > 0 else 0.0

    return {
        "frames": frame_count,
        "fps": round(fps, 2),
        "frames_with_pose": frames_with_pose,
        "pose_coverage": pose_coverage,
        "punch_attempts": counted_punches,
        "detected_punches_raw": detected_punches,
        "counted_punches": counted_punches,
        "punches_by_hand": punches_by_hand,
        "punches_by_type": punches_by_type,
        "punch_events": punch_events,
        "counted_events": counted_events,
        "analytics": analytics,
        "settings_used": cfg,
    }
