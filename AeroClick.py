import cv2
import mediapipe as mp
import time
import math
import threading
import ctypes  # PyAutoGUI yerine Windows API (Sıfır Gecikme)
from pynput.mouse import Controller as MouseController, Button
from pynput.keyboard import Controller as KeyboardController, Key

# Sistem tepsisi (System Tray) ve Görsel İşlemler
import pystray
from PIL import Image, ImageDraw

# Sesli geri bildirim (Sadece Windows)
try:
    import winsound
    HAS_SOUND = True
except ImportError:
    HAS_SOUND = False

class AeroClickUltra:
    def __init__(self):
        # MediaPipe Kurulumu (Yüksek Hassasiyet)
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=1, 
            min_detection_confidence=0.8,
            min_tracking_confidence=0.8
        )

        # Windows API ile Ekran Çözünürlüğü Alma (Ultra Hızlı)
        user32 = ctypes.windll.user32
        self.screen_w = user32.GetSystemMetrics(0)
        self.screen_h = user32.GetSystemMetrics(1)
        
        self.cam_w, self.cam_h = 640, 480
        self.frame_r = 100 

        # Pynput Kontrolcüleri
        self.mouse = MouseController()
        self.keyboard = KeyboardController()

        # Konum ve Durum Değişkenleri
        self.curr_x, self.curr_y = self.mouse.position
        self.last_click_time = 0
        self.click_delay = 0.3
        self.is_dragging = False
        self.scroll_start_y = None
        self.vol_start_y = None

        # Uyku Modu ve Yumruk Jesti Değişkenleri
        self.is_running = True
        self.is_paused = False
        self.fist_start_time = 0
        self.last_pause_toggle = 0
        self.tray_icon = None  # İkon rengini değiştirmek için

    def play_sound(self, sound_type="click"):
        """Asenkron ses bildirimleri"""
        if not HAS_SOUND: return
        if sound_type == "click":
            winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)
        elif sound_type == "pause":
            winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS | winsound.SND_ASYNC)

    def update_tray_image(self):
        """Uygulama durumuna göre ikon rengini (Yeşil/Kırmızı) değiştirir"""
        if not self.tray_icon: return
        color = (255, 50, 50) if self.is_paused else (0, 255, 100)
        image = Image.new('RGB', (64, 64), color=(0, 0, 0))
        dc = ImageDraw.Draw(image)
        dc.rectangle((16, 16, 48, 48), fill=color)
        self.tray_icon.icon = image

    def toggle_pause(self):
        """Uyku modunu açar/kapatır ve sistemi uyarır"""
        self.is_paused = not self.is_paused
        self.play_sound("pause")
        self.update_tray_image()
        durum = "UYKU MODUNDA" if self.is_paused else "AKTİF"
        print(f"🔄 Durum Değişti: {durum}")

    def get_distance(self, p1, p2):
        return math.hypot(p2[0] - p1[0], p2[1] - p1[1])

    def apply_ema_filter(self, target_x, target_y):
        """Dinamik EMA Filtresi (Pro Düzey Pürüzsüzleştirme)"""
        distance = self.get_distance((self.curr_x, self.curr_y), (target_x, target_y))
        
        if distance < 2: return self.curr_x, self.curr_y # Deadzone
        alpha = 0.6 if distance > 100 else 0.3 if distance > 30 else 0.15
        
        self.curr_x += alpha * (target_x - self.curr_x)
        self.curr_y += alpha * (target_y - self.curr_y)
        return self.curr_x, self.curr_y

    def vision_loop(self):
        cap = cv2.VideoCapture(0)
        cap.set(3, self.cam_w)
        cap.set(4, self.cam_h)

        print("🚀 AeroClick Ultra v5.0 Başladı!")
        print("🖐️  Hareketi Durdurmak/Başlatmak için: Elini 1.5 saniye YUMRUK yap.")

        while self.is_running:
            success, img = cap.read()
            if not success: continue

            img = cv2.flip(img, 1)
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            results = self.hands.process(img_rgb)
            
            if not results.multi_hand_landmarks:
                time.sleep(0.01) # El yoksa CPU'yu dinlendir
                continue

            hand_landmarks = results.multi_hand_landmarks[0]
            landmarks = hand_landmarks.landmark
            
            # --- YUMRUK JESTİ İLE UYKU MODU KONTROLÜ ---
            # 4 parmağın ucu (tip), eklemlerin (pip) altındaysa el kapalıdır.
            open_fingers = 0
            for tip, pip in [(8, 6), (12, 10), (16, 14), (20, 18)]:
                if landmarks[tip].y < landmarks[pip].y:
                    open_fingers += 1

            if open_fingers == 0: # El tamamen yumruk
                if self.fist_start_time == 0:
                    self.fist_start_time = time.time()
                # 1.5 saniye boyunca yumruk tutulursa ve son geçişin üzerinden 2 sn geçtiyse
                elif time.time() - self.fist_start_time > 1.5 and time.time() - self.last_pause_toggle > 2.0:
                    self.toggle_pause()
                    self.last_pause_toggle = time.time()
                    self.fist_start_time = 0
            else:
                self.fist_start_time = 0 # Yumruk bozulduysa sayacı sıfırla

            # Eğer uygulama uyku modundaysa diğer hareketleri yoksay
            if self.is_paused:
                continue

            # --- DİNAMİK ORANLAMA VE HAREKET ---
            wx, wy = int(landmarks[0].x * self.cam_w), int(landmarks[0].y * self.cam_h)
            bx, by = int(landmarks[5].x * self.cam_w), int(landmarks[5].y * self.cam_h)
            hand_size = self.get_distance((wx, wy), (bx, by))
            if hand_size < 15: continue

            # Parmak Koordinatları
            tx, ty = int(landmarks[4].x * self.cam_w), int(landmarks[4].y * self.cam_h)   # Baş
            ix, iy = int(landmarks[8].x * self.cam_w), int(landmarks[8].y * self.cam_h)   # İşaret
            mx, my = int(landmarks[12].x * self.cam_w), int(landmarks[12].y * self.cam_h) # Orta
            rx, ry = int(landmarks[16].x * self.cam_w), int(landmarks[16].y * self.cam_h) # Yüzük
            px, py = int(landmarks[20].x * self.cam_w), int(landmarks[20].y * self.cam_h) # Serçe

            # Oransal Mesafeler
            click_ratio = self.get_distance((ix, iy), (tx, ty)) / hand_size
            mclick_ratio = self.get_distance((mx, my), (tx, ty)) / hand_size
            scroll_ratio = self.get_distance((rx, ry), (tx, ty)) / hand_size
            rclick_ratio = self.get_distance((px, py), (tx, ty)) / hand_size

            # Hedef ve Pürüzsüzleştirme
            # map_coordinates metodunu inline (satır içi) yazarak hızı artırdık
            target_x = max(min(ix, self.cam_w - self.frame_r), self.frame_r)
            target_x = (target_x - self.frame_r) * self.screen_w / (self.cam_w - 2 * self.frame_r)
            
            target_y = max(min(iy, self.cam_h - self.frame_r), self.frame_r)
            target_y = (target_y - self.frame_r) * self.screen_h / (self.cam_h - 2 * self.frame_r)
            
            smooth_x, smooth_y = self.apply_ema_filter(target_x, target_y)

            # 1. SOL TIK VE SÜRÜKLE (İşaret + Başparmak)
            if click_ratio < 0.25:
                if not self.is_dragging:
                    self.mouse.press(Button.left)
                    self.is_dragging = True
                else:
                    self.mouse.position = (smooth_x, smooth_y)
            else:
                if self.is_dragging:
                    self.mouse.release(Button.left)
                    self.play_sound("click")
                    self.is_dragging = False
                
                # Diğer işlemler yapılmıyorsa fareyi hareket ettir
                if scroll_ratio > 0.3 and rclick_ratio > 0.3 and mclick_ratio > 0.3:
                    self.mouse.position = (smooth_x, smooth_y)

            # 2. SAĞ TIK (Serçe + Başparmak)
            if rclick_ratio < 0.25 and not self.is_dragging:
                if time.time() - self.last_click_time > self.click_delay:
                    self.mouse.click(Button.right)
                    self.play_sound("click")
                    self.last_click_time = time.time()

            # 3. BAĞIL SCROLL (Yüzük + Başparmak)
            if scroll_ratio < 0.25 and not self.is_dragging:
                if self.scroll_start_y is None: self.scroll_start_y = ry
                else:
                    delta = self.scroll_start_y - ry
                    if abs(delta) > 10:
                        self.mouse.scroll(0, 1 if delta > 0 else -1)
                        self.scroll_start_y = ry
            else:
                self.scroll_start_y = None

            # 4. SES KONTROLÜ (Orta Parmak + Başparmak)
            if mclick_ratio < 0.25 and not self.is_dragging:
                if self.vol_start_y is None: self.vol_start_y = my
                else:
                    delta = self.vol_start_y - my
                    if abs(delta) > 15: # Ses değişimi için deadzone
                        if delta > 0: self.keyboard.press(Key.media_volume_up)
                        else: self.keyboard.press(Key.media_volume_down)
                        self.keyboard.release(Key.media_volume_up) # Tuşu bırak
                        self.keyboard.release(Key.media_volume_down)
                        self.vol_start_y = my
            else:
                self.vol_start_y = None

        cap.release()

# ==========================================
# SİSTEM TEPSİSİ VE BAŞLATICI
# ==========================================

def setup_tray_and_run():
    app = AeroClickUltra()
    
    vision_thread = threading.Thread(target=app.vision_loop)
    vision_thread.start()

    def on_pause(icon, item):
        app.toggle_pause()

    def on_exit(icon, item):
        app.is_running = False
        icon.stop()
        vision_thread.join()

    menu = pystray.Menu(
        pystray.MenuItem("Uyku Modu Aç/Kapat (Yumruk Jesti)", on_pause),
        pystray.MenuItem("Çıkış", on_exit)
    )

    # Başlangıçta yeşil ikon oluştur
    image = Image.new('RGB', (64, 64), color=(0, 0, 0))
    dc = ImageDraw.Draw(image)
    dc.rectangle((16, 16, 48, 48), fill=(0, 255, 100))
    
    icon = pystray.Icon("AeroClickUltra", image, "AeroClick Ultra v5.0", menu)
    app.tray_icon = icon # İkon referansını uygulamaya gönder ki rengini değiştirebilsin
    
    icon.run() 

if __name__ == "__main__":
    setup_tray_and_run()