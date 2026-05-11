#!/usr/bin/env python3
"""
Virtual Mouse Controller using Hand Gesture Recognition
Supports: Movement, Clicking, Double-click, Scrolling, Drag & Drop
Works on: Windows & Linux
"""

import cv2
import numpy as np
import mediapipe as mp
from collections import deque
import platform
import time

# Platform-specific mouse control
if platform.system() == "Windows":
    import pyautogui
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0
else:  # Linux
    import subprocess


class HandGestureMouseController:
    def __init__(self, screen_width=None, screen_height=None):
        """Initialize hand gesture mouse controller"""
        
        # Get screen dimensions
        if screen_width is None or screen_height is None:
            if platform.system() == "Windows":
                import pyautogui
                self.screen_width, self.screen_height = pyautogui.size()
            else:  # Linux
                result = subprocess.run(
                    ['xrandr'], capture_output=True, text=True
                )
                for line in result.stdout.split('\n'):
                    if ' connected primary' in line:
                        parts = line.split()
                        res = parts[3].split('+')[0]
                        self.screen_width, self.screen_height = map(
                            int, res.split('x')
                        )
                        break
        else:
            self.screen_width = screen_width
            self.screen_height = screen_height

        # MediaPipe Hand Detection
        self.mp_hands = mp.solutions.hands
        self.mp_drawing = mp.solutions.drawing_utils
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            model_complexity=0,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.5
        )

        # Gesture tracking
        self.click_threshold = 30  # pixels
        self.scroll_threshold = 10  # pixels
        self.smoothing_history = deque(maxlen=8)  # For cursor smoothing
        
        # State tracking
        self.is_clicking = False
        self.last_click_time = 0
        self.click_cooldown = 0.3  # seconds
        self.last_position = None
        self.pinch_start = None
        self.scroll_start = None
        self.scroll_direction = None
        
        # FPS tracking
        self.frame_count = 0
        self.start_time = time.time()
        
        print(f"Virtual Mouse Initialized")
        print(f"Screen: {self.screen_width}x{self.screen_height}")
        print(f"Platform: {platform.system()}")

    def move_mouse(self, x, y):
        """Move mouse to screen coordinates with smoothing"""
        # Clamp to screen bounds
        x = max(0, min(int(x), self.screen_width - 1))
        y = max(0, min(int(y), self.screen_height - 1))
        
        if platform.system() == "Windows":
            pyautogui.moveTo(x, y, duration=0)
        else:  # Linux
            subprocess.run(
                ['xdotool', 'mousemove', str(x), str(y)],
                capture_output=True
            )

    def click_mouse(self, button='left'):
        """Simulate mouse click"""
        if platform.system() == "Windows":
            if button == 'left':
                pyautogui.click(button='left')
            elif button == 'right':
                pyautogui.click(button='right')
        else:  # Linux
            button_map = {'left': '1', 'right': '3', 'middle': '2'}
            subprocess.run(
                ['xdotool', 'click', button_map.get(button, '1')],
                capture_output=True
            )

    def double_click_mouse(self):
        """Simulate double click"""
        if platform.system() == "Windows":
            pyautogui.click(clicks=2, interval=0.1)
        else:  # Linux
            subprocess.run(['xdotool', 'click', '1'], capture_output=True)
            time.sleep(0.1)
            subprocess.run(['xdotool', 'click', '1'], capture_output=True)

    def scroll_mouse(self, direction, amount=5):
        """Simulate mouse scroll"""
        if platform.system() == "Windows":
            win_amount = int(amount * 120)
            if direction == 'up':
                pyautogui.scroll(win_amount)
            else:  # down
                pyautogui.scroll(-win_amount)
        else:  # Linux
            button = '4' if direction == 'up' else '5'
            for _ in range(int(amount)):
                subprocess.run(
                    ['xdotool', 'click', button],
                    capture_output=True
                )

    def calculate_distance(self, point1, point2):
        """Calculate Euclidean distance between two points"""
        return np.sqrt((point1[0] - point2[0])**2 + 
                      (point1[1] - point2[1])**2)

    def is_pinch_gesture(self, landmarks, frame_width, frame_height):
        """Detect pinch gesture (thumb and index finger close together)"""
        thumb_tip = landmarks[4]
        index_tip = landmarks[8]
        
        thumb_pos = np.array([
            thumb_tip.x * frame_width,
            thumb_tip.y * frame_height
        ])
        index_pos = np.array([
            index_tip.x * frame_width,
            index_tip.y * frame_height
        ])
        
        distance = self.calculate_distance(thumb_pos, index_pos)
        return distance < 50  # Pixels

    def is_victory_gesture(self, landmarks, frame_width, frame_height):
        """Detect victory/peace gesture (index and middle fingers raised)"""
        # Check if index and middle fingers are extended upward
        index_tip = landmarks[8]
        middle_tip = landmarks[12]
        index_pip = landmarks[6]
        middle_pip = landmarks[10]
        
        # Index and middle should be above their PIP joints (extended)
        index_extended = index_tip.y < index_pip.y
        middle_extended = middle_tip.y < middle_pip.y
        
        return index_extended and middle_extended

    def is_peace_sign_scroll(self, landmarks, frame_width, frame_height):
        """Detect peace sign for scrolling control"""
        # Check if only index and middle fingers are up
        fingers_up = [
            landmarks[i].y < landmarks[i-2].y  # Tip above PIP
            for i in [8, 12, 16, 20]  # Index, Middle, Ring, Pinky
        ]
        
        # Peace sign: Index and Middle up, Ring and Pinky down
        return fingers_up[0] and fingers_up[1] and not fingers_up[2]

    def process_frame(self, frame):
        """Process a single frame and update mouse"""
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.hands.process(rgb_frame)
        
        frame_height, frame_width, _ = frame.shape
        
        if results.multi_hand_landmarks:
            hand_landmarks = results.multi_hand_landmarks[0]
            landmarks = hand_landmarks.landmark
            
            # Get index finger tip (cursor position)
            index_tip = landmarks[8]
            cursor_x = index_tip.x * self.screen_width
            cursor_y = index_tip.y * self.screen_height
            
            # Apply smoothing
            self.smoothing_history.append((cursor_x, cursor_y))
            if len(self.smoothing_history) > 1:
                cursor_x = np.mean([p[0] for p in self.smoothing_history])
                cursor_y = np.mean([p[1] for p in self.smoothing_history])
            
            # Move cursor
            self.move_mouse(cursor_x, cursor_y)
            self.last_position = (cursor_x, cursor_y)
            
            # Detect gestures
            current_time = time.time()
            
            # Pinch gesture = Left Click
            if self.is_pinch_gesture(landmarks, frame_width, frame_height):
                if not self.is_clicking and \
                   current_time - self.last_click_time > self.click_cooldown:
                    self.click_mouse('left')
                    self.is_clicking = True
                    self.last_click_time = current_time
            else:
                self.is_clicking = False
            
            # Peace sign for scrolling
            if self.is_peace_sign_scroll(landmarks, frame_width, frame_height):
                middle_tip = landmarks[12]
                middle_y = middle_tip.y * frame_height
                
                if self.scroll_start is None:
                    self.scroll_start = middle_y
                else:
                    delta = middle_y - self.scroll_start
                    if abs(delta) > self.scroll_threshold:
                        direction = 'down' if delta > 0 else 'up'
                        amount = max(1, int(abs(delta) / 10))
                        self.scroll_mouse(direction, amount=amount)
                        self.scroll_start = middle_y
            else:
                self.scroll_start = None
            
            # Draw hand skeleton
            self.mp_drawing.draw_landmarks(
                frame, hand_landmarks, self.mp_hands.HAND_CONNECTIONS
            )
            
            return frame, True
        
        return frame, False

    def draw_ui(self, frame, hand_detected):
        """Draw UI elements on frame"""
        # Draw instructions
        instructions = [
            "INDEX FINGER: Control cursor",
            "PINCH (Thumb+Index): LEFT CLICK",
            "PEACE SIGN + MOVE: SCROLL",
            "Press 'Q' to quit",
        ]
        
        for i, text in enumerate(instructions):
            cv2.putText(
                frame, text, (10, 30 + i * 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1
            )
        
        # Status indicator
        status = "HAND DETECTED" if hand_detected else "NO HAND"
        color = (0, 255, 0) if hand_detected else (0, 0, 255)
        cv2.putText(
            frame, status, (10, frame.shape[0] - 20),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2
        )
        
        # FPS
        self.frame_count += 1
        fps = self.frame_count / (time.time() - self.start_time)
        cv2.putText(
            frame, f"FPS: {fps:.1f}",
            (frame.shape[1] - 150, 30),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2
        )

    def run(self, camera_index=0, flip_horizontal=True):
        """Run the virtual mouse controller"""
        cap = cv2.VideoCapture(camera_index)
        
        if not cap.isOpened():
            print(f"Error: Could not open camera {camera_index}")
            return
        
        # Set camera properties for better performance
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 30)
        
        print("Virtual Mouse Controller Running")
        print("=" * 50)
        print("Gestures:")
        print("  • Move cursor with INDEX FINGER")
        print("  • PINCH (thumb + index) to LEFT CLICK")
        print("  • PEACE SIGN + MOVE UP/DOWN to SCROLL")
        print("\nPress 'Q' to quit\n")
        
        try:
            while True:
                ret, frame = cap.read()
                
                if not ret:
                    print("Error: Failed to read frame")
                    break
                
                if flip_horizontal:
                    frame = cv2.flip(frame, 1)
                
                # Process frame
                frame, hand_detected = self.process_frame(frame)
                
                # Draw UI
                self.draw_ui(frame, hand_detected)
                
                # Display
                cv2.imshow('Virtual Mouse Controller', frame)
                
                # Check for exit
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q') or key == ord('Q'):
                    print("\nShutting down...")
                    break
        
        except KeyboardInterrupt:
            print("\nInterrupted by user")
        
        finally:
            cap.release()
            cv2.destroyAllWindows()
            print("Virtual Mouse Controller stopped")


def main():
    """Main entry point"""
    controller = HandGestureMouseController()
    controller.run(camera_index=0, flip_horizontal=True)


if __name__ == "__main__":
    main()
