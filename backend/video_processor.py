import cv2
import math
from pose import process_frame
import mediapipe as mp

mp_drawing = mp.solutions.drawing_utils
mp_pose = mp.solutions.pose


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


def _build_fight_analytics(punch_events, duration_sec, bucket_sec=10):
    if duration_sec <= 0:
        duration_sec = 1e-6

    punches_per_minute = round((len(punch_events) / duration_sec) * 60.0, 2)

    combo_count = 0
    max_combo = 0
    current_combo = 0
    prev_time = None
    combo_gap_sec = 0.8

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
        "combo_count": combo_count,
        "max_combo": max_combo,
        "timeline_counts_10s": timeline_counts,
    }


def analyze_video(video_path, show_preview=False):
    cap = cv2.VideoCapture(video_path)

    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 1:
        fps = 30.0

    frame_count = 0
    punch_attempts = 0
    punch_events = []
    punches_by_hand = {"left": 0, "right": 0}
    punches_by_type = {"straight": 0, "hook": 0}

    cooldown_frames = max(2, int(fps * 0.15))
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
                if shoulder.visibility < 0.5 or elbow.visibility < 0.5 or wrist.visibility < 0.5:
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
                    if enough_cooldown and speed > 0.022 and distance_growth > 0.006 and elbow_angle > 120:
                        punch_type = _classify_punch(dx, dy)
                        timestamp_sec = round(frame_count / fps, 3)

                        punch_attempts += 1
                        punches_by_hand[side] += 1
                        punches_by_type[punch_type] += 1
                        side_state[side]["last_punch_frame"] = frame_count

                        punch_events.append(
                            {
                                "frame": frame_count,
                                "time_sec": timestamp_sec,
                                "hand": side,
                                "type": punch_type,
                            }
                        )

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
    analytics = _build_fight_analytics(punch_events, duration_sec)

    return {
        "frames": frame_count,
        "fps": round(fps, 2),
        "punch_attempts": punch_attempts,
        "punches_by_hand": punches_by_hand,
        "punches_by_type": punches_by_type,
        "punch_events": punch_events,
        "analytics": analytics,
    }
