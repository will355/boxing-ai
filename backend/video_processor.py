import cv2
from pose import process_frame
import mediapipe as mp

mp_drawing = mp.solutions.drawing_utils
mp_pose = mp.solutions.pose

def analyze_video(video_path, show_preview=False):
    cap = cv2.VideoCapture(video_path)

    frame_count = 0
    punch_attempts = 0
    prev_right_wrist_y = None

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_count += 1
        results = process_frame(frame)

        if results.pose_landmarks:
            landmarks = results.pose_landmarks.landmark

            right_wrist = landmarks[mp_pose.PoseLandmark.RIGHT_WRIST]
            right_elbow = landmarks[mp_pose.PoseLandmark.RIGHT_ELBOW]


            if prev_right_wrist_y is not None:
                if prev_right_wrist_y - right_wrist.y > 0.03:
                    punch_attempts += 1

            prev_right_wrist_y = right_wrist.y

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

    return {
        "frames": frame_count,
        "punch_attempts": punch_attempts
    }
