"""
Πthon Arena - FINAL WORKING CLIENT (Fixed Sound Mute Button with Emoji)
Run: python client.py
"""

import pygame
import socket
import threading
import json
import sys
import math
import array
import random

CELL = 20
GRID_W = 30
GRID_H = 30
SIDEBAR_W = 280
WIN_W = GRID_W * CELL + SIDEBAR_W
WIN_H = GRID_H * CELL
FPS = 30

# Colors (simplified but same as before)
BLACK = (0,0,0)
WHITE = (255,255,255)
GREY = (128,128,128)
DGREY = (30,30,40)
GREEN = (0,255,100)
DGREEN = (0,180,50)
BLUE = (0,150,255)
DBLUE = (0,80,200)
RED = (255,50,80)
YELLOW = (255,220,0)
GOLD = (255,200,50)
PURPLE = (180,50,255)
ORANGE = (255,100,0)
TEAL = (0,200,200)
CYAN = (0,255,255)
NEON_PURPLE = (160,0,200)
NEON_GREEN = (80,220,80)
NEON_BLUE = (0,180,220)
PINK = (255,80,150)
SILVER = (192,192,192)
MINT = (100,220,150)
CORAL = (255,100,80)
LAVENDER = (180,150,255)

SNAKE_COLOR_OPTIONS = {
    "neon_green": (NEON_GREEN, (0,150,20)),
    "electric_blue": (NEON_BLUE, (0,100,180)),
    "lava_red": (RED, (150,0,0)),
    "sunset_orange": (ORANGE, (180,60,0)),
    "royal_purple": (NEON_PURPLE, (100,0,150)),
    "cyan": (CYAN, (0,150,150)),
    "pink": (PINK, (180,40,100)),
    "silver": (SILVER, (120,120,120)),
    "mint": (MINT, (60,160,100)),
    "coral": (CORAL, (180,60,40)),
    "lavender": (LAVENDER, (120,90,200)),
    "gold": (GOLD, (180,140,20))
}

PIE_COLOR = {"standard": YELLOW, "golden": GOLD, "poison": PURPLE}
POWERUP_COLOR = {"speed": CYAN, "shield": BLUE, "growth": ORANGE}

def draw_gradient_rect(screen, rect, top_color, bottom_color):
    for y in range(rect.height):
        ratio = y / rect.height
        color = tuple(int(top_color[i] * (1-ratio) + bottom_color[i] * ratio) for i in range(3))
        pygame.draw.line(screen, color, (rect.x, rect.y+y), (rect.x+rect.width, rect.y+y))

def draw_rounded_rect(screen, color, rect, radius, border=0, border_color=None):
    pygame.draw.rect(screen, color, rect, border_radius=radius)
    if border and border_color:
        pygame.draw.rect(screen, border_color, rect, border, border_radius=radius)

def draw_shadow(screen, rect, offset=4, alpha=80):
    shadow = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
    shadow.fill((0,0,0,alpha))
    screen.blit(shadow, (rect.x+offset, rect.y+offset))

def draw_glow(screen, pos, color, radius):
    for i in range(radius, 0, -5):
        alpha = int(100 * (i/radius))
        glow_color = (*color, alpha)
        surf = pygame.Surface((i*2, i*2), pygame.SRCALPHA)
        pygame.draw.circle(surf, glow_color, (i, i), i)
        screen.blit(surf, (pos[0]-i, pos[1]-i))

class Particle:
    def __init__(self, x, y, color, velocity, lifetime):
        self.x, self.y = x, y
        self.color = color
        self.vx, self.vy = velocity
        self.lifetime = lifetime
        self.max_lifetime = lifetime
    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.lifetime -= 1
        return self.lifetime > 0
    def draw(self, screen):
        alpha = int(255 * (self.lifetime / self.max_lifetime))
        size = max(1, int(3 * (self.lifetime / self.max_lifetime)))
        pygame.draw.circle(screen, (*self.color, alpha), (int(self.x), int(self.y)), size)

class FloatingText:
    def __init__(self, text, x, y, color, lifetime=30):
        self.text = text
        self.x, self.y = x, y
        self.color = color
        self.lifetime = lifetime
        self.max_lifetime = lifetime
    def update(self):
        self.y -= 1
        self.lifetime -= 1
        return self.lifetime > 0
    def draw(self, screen, font):
        alpha = int(255 * (self.lifetime / self.max_lifetime))
        surf = font.render(self.text, True, self.color)
        surf.set_alpha(alpha)
        screen.blit(surf, (self.x - surf.get_width()//2, self.y))

class LineReader:
    def __init__(self, sock):
        self._sock = sock
        self._buf = b""
    def readline(self):
        while b'\n' not in self._buf:
            chunk = self._sock.recv(4096)
            if not chunk:
                return None
            self._buf += chunk
        line, self._buf = self._buf.split(b'\n', 1)
        return line
    def read_json(self):
        line = self.readline()
        if not line:
            return None
        try:
            return json.loads(line.decode('utf-8'))
        except:
            return None

class IthonArenaClient:
    def __init__(self):
        # Networking
        self.sock = None
        self.reader = None
        self.username = ""
        self.snake_color = "neon_green"
        self.role = "player"
        self.game_state = {}
        self.prev_game_state = {}
        self.online = []
        self.msg_lock = threading.Lock()
        self.messages = []
        self.countdown = None
        self.game_over = None
        self.connected = False
        self.server_port = 0
        self.p2p_listener = None
        self.p2p_port = 0
        self.peer_ip = None
        self.peer_p2p_port = None
        self.chat_input = ""
        self.chat_scroll = 0
        self.pending_challenge = None
        self.rematch_request = False
        self.phase = "connect"
        self.rematch_timer = None
        self.chat_auto_scroll = True
        self.last_time_left = None

        # Leaderboard
        self.leaderboard_data = {}
        self.show_leaderboard = False

        # Controls
        self.key_map = {
            "UP": [pygame.K_UP, pygame.K_w],
            "DOWN": [pygame.K_DOWN, pygame.K_s],
            "LEFT": [pygame.K_LEFT, pygame.K_a],
            "RIGHT": [pygame.K_RIGHT, pygame.K_d]
        }
        self.remap_action = None
        self.remap_waiting = False

        # Design
        self.pattern = "solid"
        self.eyes = True
        self.rules_shown = False

        # Sound system (fixed version from fancy client)
        self.sound_enabled = True
        self.music_playing = False
        self.sounds = {}
        self._init_sounds()

        # Visual effects
        self.particles = []
        self.floating_texts = []
        self.screen_shake = 0

        # UI button rects
        self.mute_button_rect = None
        self.fan_emoji_buttons = []

        # Fan popup suppression
        self.fan_skip_popup = False

        # Emoji font for mute button
        self.emoji_font = None

    def _make_sound(self, frequency, duration, volume=0.5):
        sample_rate = 22050
        n_samples = int(sample_rate * duration)
        max_amp = 2**15 - 1
        samples = []
        for i in range(n_samples):
            t = float(i) / sample_rate
            value = int(max_amp * volume * math.sin(2 * math.pi * frequency * t))
            samples.append(value)
        sound_array = array.array('h', samples)
        return pygame.mixer.Sound(buffer=sound_array)

    def _init_sounds(self):
        try:
            pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
        except:
            print("Warning: Could not initialize mixer. Sound disabled.")
            self.sound_enabled = False
            return
        try:
            self.sounds['countdown_tick'] = self._make_sound(880, 0.08, 0.3)
            self.sounds['countdown_beep'] = self._make_sound(440, 0.2, 0.4)
            self.sounds['game_start'] = self._make_sound(880, 0.5, 0.5)
            self.sounds['powerup'] = self._make_sound(1200, 0.12, 0.4)
            self.sounds['pie_eat'] = self._make_sound(660, 0.1, 0.3)
            self.sounds['poison'] = self._make_sound(300, 0.15, 0.4)
            self.sounds['damage'] = self._make_sound(200, 0.2, 0.5)
        except:
            pass

    def _play_sound(self, sound_name):
        if self.sound_enabled and sound_name in self.sounds:
            self.sounds[sound_name].play()

    def _start_bg_music(self):
        if not self.sound_enabled:
            return
        if self.music_playing:
            return
        music_file = "yellowbirdbeats-moombahton-whistle-x-banger-x-bad-bunny-black-mamba-292100 (1).mp3"
        try:
            pygame.mixer.music.load(music_file)
            pygame.mixer.music.set_volume(0.3)
            pygame.mixer.music.play(-1)
            self.music_playing = True
            print("Background music started")
        except Exception as e:
            print(f"Could not load background music: {e}")

    def _stop_bg_music(self):
        if self.music_playing:
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()
            self.music_playing = False
            print("Background music stopped")

    def toggle_sound(self):
        """Toggle all sound (music + SFX) on/off."""
        self.sound_enabled = not self.sound_enabled
        if not self.sound_enabled:
            self._stop_bg_music()
        else:
            # Restart music only if game is active
            status = self.game_state.get("status")
            if status in ("running", "countdown") and self.phase == "game":
                self._start_bg_music()
        print(f"Sound toggled, enabled={self.sound_enabled}")

    def _get_free_port(self):
        sock = socket.socket()
        sock.bind(('', 0))
        port = sock.getsockname()[1]
        sock.close()
        return port

    # ---------- NETWORKING ----------
    def connect(self, ip, port, username, color):
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
            self.sock = None
        self.connected = False
        self.online = []
        self.game_state = {}
        self.prev_game_state = {}
        self.game_over = None
        self.countdown = None
        self.peer_ip = None
        self.peer_p2p_port = None
        self.messages.clear()
        self.role = "fan"
        self.pending_challenge = None
        self.rematch_request = False
        self.fan_skip_popup = False
        if self.rematch_timer:
            self.rematch_timer.cancel()
            self.rematch_timer = None

        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.sock.settimeout(5)
            self.sock.connect((ip, port))
            self.sock.settimeout(None)
            self.reader = LineReader(self.sock)
            self.server_port = port
            self.username = username
            self.snake_color = color
            self.p2p_port = self._get_free_port()
            self.sock.sendall(f"{username}|{self.p2p_port}|{color}\n".encode('utf-8'))
            resp = self.reader.read_json()
            if not resp or resp.get("type") != "auth":
                return False, "No response"
            if resp["status"] == "fail":
                return False, resp.get("reason")
            self.role = resp.get("role", "fan")
            self.online = resp.get("online", [])
            self.connected = True
            threading.Thread(target=self._p2p_listen, daemon=True).start()
            threading.Thread(target=self._receive_loop, daemon=True).start()
            self._send({"type": "get_lobby"})
            return True, "ok"
        except Exception as e:
            return False, str(e)

    def _receive_loop(self):
        while self.connected:
            try:
                msg = self.reader.read_json()
                if not msg:
                    break
                self._handle_server_msg(msg)
            except:
                break
        self.connected = False

    def _handle_server_msg(self, msg):
        mtype = msg.get("type")
        if mtype == "state":
            self.prev_game_state = self.game_state.copy()
            self.game_state = msg["data"]
            if self.username in self.game_state.get("snakes", {}):
                self.role = "player"
            else:
                self.role = "fan"
            status = self.game_state.get("status")
            if status == "running":
                self.countdown = None
                self.fan_skip_popup = False
            elif status == "waiting":
                self.countdown = None
                self.game_over = None
                if self.phase in ("game", "rematch_popup", "fan_rematch_popup"):
                    self.phase = "lobby"
                    self._stop_bg_music()
                    if self.rematch_timer:
                        self.rematch_timer.cancel()
                        self.rematch_timer = None
                    self.rematch_request = False
                self.fan_skip_popup = False
            elif status == "finished" and not self.game_over:
                snakes = self.game_state.get("snakes", {})
                winner = self.game_state.get("winner")
                loser = next((u for u in snakes if u != winner), None) if winner else None
                self.game_over = {"winner": winner, "loser": loser, "scores": {u: s.get("health", 0) for u, s in snakes.items()}, "reason": "Health reached 0 or time ended"}
                if self.username not in snakes:
                    if not self.fan_skip_popup:
                        self.phase = "fan_rematch_popup"
                elif self.phase == "game":
                    self._start_rematch_timer()
                self._stop_bg_music()
            elif status == "countdown":
                self.rematch_request = False
                if self.rematch_timer:
                    self.rematch_timer.cancel()
                    self.rematch_timer = None
                if self.phase in ("lobby", "rematch_popup", "fan_rematch_popup"):
                    self.phase = "game"
                    if self.sound_enabled:
                        self._start_bg_music()
                self.fan_skip_popup = False
        elif mtype == "lobby":
            self.online = msg.get("online", [])
        elif mtype == "leaderboard":
            self.leaderboard_data = msg.get("data", {})
        elif mtype == "countdown":
            new_countdown = msg.get("value")
            if self.sound_enabled and new_countdown is not None and self.game_state.get("status") == "countdown":
                if new_countdown <= 3 and new_countdown > 0:
                    self._play_sound('countdown_tick')
            self.countdown = new_countdown
        elif mtype == "game_over":
            winner = msg.get("winner")
            scores = msg.get("scores", {})
            loser = next((u for u in scores if u != winner), None) if winner else None
            self.countdown = None
            self.game_over = {"winner": winner, "loser": loser, "scores": scores, "reason": msg.get("reason")}
            if self.username not in self.game_state.get("snakes", {}):
                if not self.fan_skip_popup:
                    self.phase = "fan_rematch_popup"
            elif self.phase == "game":
                self._start_rematch_timer()
            self._stop_bg_music()
        elif mtype == "chat":
            with self.msg_lock:
                self.messages.append((f"{msg.get('from')}: {msg.get('text')}", pygame.time.get_ticks()))
                if len(self.messages) > 100:
                    self.messages.pop(0)
                if self.chat_auto_scroll:
                    self.chat_scroll = 0
        elif mtype == "peer_info":
            self.peer_ip = msg.get("peer_ip")
            self.peer_p2p_port = msg.get("peer_port")
            with self.msg_lock:
                self.messages.append((f"[System] P2P ready with {self.peer_ip}:{self.peer_p2p_port}", pygame.time.get_ticks()))
        elif mtype == "challenge":
            self.pending_challenge = msg.get("from")
            if self.phase == "lobby":
                self.phase = "challenge_popup"
        elif mtype == "rematch_request":
            self.rematch_request = True
            if self.phase == "game":
                if self.rematch_timer:
                    self.rematch_timer.cancel()
                    self.rematch_timer = None
                self.phase = "rematch_popup"
        elif mtype == "error":
            with self.msg_lock:
                self.messages.append((f"[Error] {msg.get('text')}", pygame.time.get_ticks()))

    def _start_rematch_timer(self):
        if self.rematch_timer:
            self.rematch_timer.cancel()
        self.rematch_timer = threading.Timer(3.0, self._show_rematch_popup)
        self.rematch_timer.daemon = True
        self.rematch_timer.start()

    def _show_rematch_popup(self):
        if self.phase == "game" and self.game_over and not self.rematch_request:
            self.rematch_request = True
            self.phase = "rematch_popup"
        self.rematch_timer = None

    def send_move(self, direction):
        if self.connected and self.username in self.game_state.get("snakes", {}):
            self._send({"type": "move", "dir": direction})

    def send_chat(self, text):
        if text.strip():
            self._send({"type": "chat", "text": text.strip()})

    def p2p_send(self, text):
        if self.peer_ip and self.peer_p2p_port:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(2)
                s.connect((self.peer_ip, self.peer_p2p_port))
                payload = json.dumps({"from": self.username, "text": text}).encode('utf-8') + b'\n'
                s.sendall(payload)
                s.close()
                with self.msg_lock:
                    self.messages.append((f"[P2P→{self.peer_ip}] You: {text}", pygame.time.get_ticks()))
            except Exception as e:
                with self.msg_lock:
                    self.messages.append((f"[P2P] Failed: {e}", pygame.time.get_ticks()))
        else:
            with self.msg_lock:
                self.messages.append(("[P2P] No peer info yet", pygame.time.get_ticks()))

    def _send(self, obj):
        try:
            self.sock.sendall(json.dumps(obj).encode('utf-8') + b'\n')
        except:
            self.connected = False

    def _p2p_listen(self):
        try:
            ls = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            ls.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            ls.bind(('0.0.0.0', self.p2p_port))
            ls.listen(5)
            while self.connected:
                try:
                    conn, addr = ls.accept()
                    threading.Thread(target=self._p2p_handle, args=(conn,), daemon=True).start()
                except:
                    break
        except Exception as e:
            print(f"P2P listen error: {e}")

    def _p2p_handle(self, conn):
        try:
            reader = LineReader(conn)
            while True:
                msg = reader.read_json()
                if not msg:
                    break
                sender = msg.get("from", "Peer")
                text = msg.get("text", "")
                with self.msg_lock:
                    self.messages.append((f"[P2P] {sender}: {text}", pygame.time.get_ticks()))
        except:
            pass
        finally:
            conn.close()

    def _check_for_sound_triggers(self):
        status = self.game_state.get("status")
        if status not in ("running", "countdown"):
            return
        if not self.sound_enabled:
            return
        prev_powerups = {tuple(p["pos"]): p["type"] for p in self.prev_game_state.get("powerups", [])}
        curr_powerups = {tuple(p["pos"]): p["type"] for p in self.game_state.get("powerups", [])}
        for pos, ptype in prev_powerups.items():
            if pos not in curr_powerups:
                self._play_sound('powerup')
                self._add_particle_burst(pos[0]*CELL+CELL//2, pos[1]*CELL+CELL//2, POWERUP_COLOR.get(ptype, CYAN), 12)
        prev_pies = {tuple(p["pos"]): p["type"] for p in self.prev_game_state.get("pies", [])}
        curr_pies = {tuple(p["pos"]): p["type"] for p in self.game_state.get("pies", [])}
        for pos, ptype in prev_pies.items():
            if pos not in curr_pies:
                if ptype == "poison":
                    self._play_sound('poison')
                    self._add_floating_text("-15", pos[0]*CELL+CELL//2, pos[1]*CELL+CELL//2, PURPLE)
                else:
                    self._play_sound('pie_eat')
                    self._add_floating_text("+10", pos[0]*CELL+CELL//2, pos[1]*CELL+CELL//2, GREEN)
                self._add_particle_burst(pos[0]*CELL+CELL//2, pos[1]*CELL+CELL//2, PIE_COLOR.get(ptype, YELLOW), 8)
        for uname, snake in self.game_state.get("snakes", {}).items():
            if uname == self.username:
                old_health = self.prev_game_state.get("snakes", {}).get(uname, {}).get("health", 100)
                new_health = snake.get("health", 100)
                if new_health < old_health:
                    self._play_sound('damage')
                    self._screen_shake(3)
                    self._add_floating_text(f"-{old_health - new_health}", snake["body"][0][0]*CELL+CELL//2, snake["body"][0][1]*CELL+CELL//2, RED)
        tl = self.game_state.get("time_left", 0)
        if tl != self.last_time_left and status == "running":
            if 0 < tl <= 10:
                self._play_sound('countdown_beep')
            self.last_time_left = tl

    def _add_particle_burst(self, x, y, color, count=10):
        for _ in range(count):
            angle = random.uniform(0, math.pi*2)
            speed = random.uniform(1, 3)
            vx = math.cos(angle) * speed
            vy = math.sin(angle) * speed
            lifetime = random.randint(15, 30)
            self.particles.append(Particle(x, y, color, (vx, vy), lifetime))

    def _add_floating_text(self, text, x, y, color):
        self.floating_texts.append(FloatingText(text, x, y, color))

    def _screen_shake(self, intensity=5):
        self.screen_shake = intensity

    # ---------- TEXT WRAPPING HELPER FOR CHAT ----------
    def _wrap_text(self, text, font, max_width):
        """Wrap text to fit within max_width, including very long words with no spaces."""
        if not text:
            return [""]

        lines = []
        current_line = ""

        def split_long_chunk(chunk):
            parts = []
            current = ""
            for ch in chunk:
                test = current + ch
                if current and font.render(test, True, WHITE).get_width() > max_width:
                    parts.append(current)
                    current = ch
                else:
                    current = test
            if current:
                parts.append(current)
            return parts or [chunk]

        words = text.split(" ")
        for i, word in enumerate(words):
            separator = "" if current_line == "" else " "
            test_line = current_line + separator + word

            if font.render(test_line, True, WHITE).get_width() <= max_width:
                current_line = test_line
                continue

            if current_line:
                lines.append(current_line)
                current_line = ""

            if font.render(word, True, WHITE).get_width() <= max_width:
                current_line = word
            else:
                broken_word_parts = split_long_chunk(word)
                lines.extend(broken_word_parts[:-1])
                current_line = broken_word_parts[-1]

        if current_line:
            lines.append(current_line)

        return lines if lines else [text]

    # ---------- DRAWING METHODS ----------
    def _draw_connect(self, screen, fsm, fmd, flg, ip_t, port_t, user_t, active, err, ip_r, port_r, user_r, btn_r, color_btn_r, current_color):
        draw_gradient_rect(screen, pygame.Rect(0,0,WIN_W,WIN_H), (15,15,35), (5,5,15))
        title = flg.render("Πthon Arena", True, NEON_PURPLE)
        screen.blit(title, (WIN_W//2 - title.get_width()//2, 80))
        fields = [("Server IP", ip_t, ip_r, "ip"), ("Port", port_t, port_r, "port"), ("Username", user_t, user_r, "user")]
        for label, val, rect, key in fields:
            draw_shadow(screen, rect)
            color = NEON_PURPLE if active==key else DGREY
            draw_rounded_rect(screen, DGREY if active!=key else (40,40,60), rect, 8)
            pygame.draw.rect(screen, color, rect, 2, 8)
            lbl = fsm.render(label, True, GREY)
            screen.blit(lbl, (rect.x, rect.y-18))
            txt = fmd.render(val + ("_" if active==key else ""), True, WHITE)
            screen.blit(txt, (rect.x+8, rect.y+8))
        hover = btn_r.collidepoint(*pygame.mouse.get_pos())
        draw_shadow(screen, btn_r)
        draw_rounded_rect(screen, NEON_GREEN if hover else (30,90,30), btn_r, 10)
        bt = fmd.render("Next: Choose Color", True, WHITE)
        screen.blit(bt, (btn_r.centerx - bt.get_width()//2, btn_r.centery - bt.get_height()//2))
        if err:
            et = fsm.render(f"Error: {err}", True, RED)
            screen.blit(et, (200,420))

    def _draw_color(self, screen, fmd, flg, color_names, color_index, err):
        draw_gradient_rect(screen, pygame.Rect(0,0,WIN_W,WIN_H), (15,15,35), (5,5,15))
        title = flg.render("Choose Your Snake Color", True, NEON_PURPLE)
        screen.blit(title, (WIN_W//2 - title.get_width()//2, 100))
        color_name = color_names[color_index]
        preview_color = SNAKE_COLOR_OPTIONS[color_name][0]
        circle_x = WIN_W//2
        circle_y = 220
        pygame.draw.circle(screen, preview_color, (circle_x, circle_y), 50)
        pygame.draw.circle(screen, WHITE, (circle_x, circle_y), 50, 3)
        name_text = fmd.render(color_name.upper(), True, WHITE)
        screen.blit(name_text, (WIN_W//2 - name_text.get_width()//2, 290))

        change_btn_rect = pygame.Rect(WIN_W//2 - 150, 340, 300, 40)
        hover_color = change_btn_rect.collidepoint(*pygame.mouse.get_pos())
        draw_shadow(screen, change_btn_rect)
        draw_rounded_rect(screen, TEAL if hover_color else DGREY, change_btn_rect, 8)
        ct = fmd.render("Change Color (← →)", True, WHITE)
        screen.blit(ct, (change_btn_rect.centerx - ct.get_width()//2, change_btn_rect.centery - ct.get_height()//2))

        next_btn_rect = pygame.Rect(WIN_W//2 - 100, 410, 200, 50)
        hover_connect = next_btn_rect.collidepoint(*pygame.mouse.get_pos())
        draw_shadow(screen, next_btn_rect)
        draw_rounded_rect(screen, NEON_GREEN if hover_connect else (30,90,30), next_btn_rect, 10)
        bt = fmd.render("Next: Customize", True, WHITE)
        screen.blit(bt, (next_btn_rect.centerx - bt.get_width()//2, next_btn_rect.centery - bt.get_height()//2))

        if err:
            et = fmd.render(f"Error: {err}", True, RED)
            screen.blit(et, (200, 500))
        return change_btn_rect, next_btn_rect

    def _draw_controls(self, screen, fmd, flg, btn_rect):
        draw_gradient_rect(screen, pygame.Rect(0,0,WIN_W,WIN_H), (15,15,35), (5,5,15))
        title = flg.render("Customize Controls & Snake Design", True, NEON_PURPLE)
        screen.blit(title, (WIN_W//2 - title.get_width()//2, 40))

        left_x = 50
        right_x = WIN_W//2 + 30
        y = 100
        key_header = fmd.render("CONTROLS (click to remap):", True, WHITE)
        screen.blit(key_header, (left_x, y))
        y += 35
        directions = ["UP", "DOWN", "LEFT", "RIGHT"]
        self.control_buttons = {}
        for d in directions:
            rect = pygame.Rect(left_x, y, 200, 35)
            self.control_buttons[d] = rect
            color = YELLOW if self.remap_waiting and self.remap_action == d else NEON_GREEN
            draw_shadow(screen, rect)
            draw_rounded_rect(screen, color, rect, 8)
            keys = self.key_map[d]
            key_names = []
            for k in keys:
                if k == pygame.K_UP: name = "↑"
                elif k == pygame.K_DOWN: name = "↓"
                elif k == pygame.K_LEFT: name = "←"
                elif k == pygame.K_RIGHT: name = "→"
                else: name = pygame.key.name(k).upper()
                key_names.append(name)
            label = fmd.render(f"{d}: {', '.join(key_names)}", True, WHITE)
            screen.blit(label, (rect.x + 10, rect.y + 8))
            y += 45

        y = 100
        design_header = fmd.render("SNAKE DESIGN:", True, WHITE)
        screen.blit(design_header, (right_x, y))
        y += 35
        pattern_rects = {}
        patterns = ["solid", "striped", "dotted"]
        for i, pat in enumerate(patterns):
            rect = pygame.Rect(right_x, y + i*40, 120, 35)
            pattern_rects[pat] = rect
            color = TEAL if self.pattern == pat else DGREY
            draw_shadow(screen, rect)
            draw_rounded_rect(screen, color, rect, 8)
            pat_text = fmd.render(pat.upper(), True, WHITE)
            screen.blit(pat_text, (rect.x + 10, rect.y + 8))
        y += 40 * 3 + 10
        eyes_rect = pygame.Rect(right_x, y, 180, 40)
        draw_shadow(screen, eyes_rect)
        draw_rounded_rect(screen, NEON_GREEN if self.eyes else DGREY, eyes_rect, 8)
        eyes_text = fmd.render("Eyes: " + ("ON" if self.eyes else "OFF"), True, WHITE)
        screen.blit(eyes_text, (eyes_rect.x + 20, eyes_rect.y + 10))
        self.eyes_rect = eyes_rect
        self.pattern_rects = pattern_rects

        next_rect = pygame.Rect(WIN_W//2 - 100, WIN_H - 70, 200, 45)
        self.controls_next_rect = next_rect
        hover = next_rect.collidepoint(*pygame.mouse.get_pos())
        draw_shadow(screen, next_rect)
        draw_rounded_rect(screen, NEON_GREEN if hover else (30,90,30), next_rect, 10)
        next_text = fmd.render("Next: View Rules", True, WHITE)
        screen.blit(next_text, (next_rect.centerx - next_text.get_width()//2, next_rect.centery - next_text.get_height()//2))

    def _draw_rules(self, screen, fmd, flg):
        draw_gradient_rect(screen, pygame.Rect(0,0,WIN_W,WIN_H), (15,15,35), (5,5,15))
        title = flg.render("Game Rules", True, GOLD)
        screen.blit(title, (WIN_W//2 - title.get_width()//2, 30))

        font_small = pygame.font.SysFont("monospace", 16)
        y = 90
        line_height = 26

        line1a = "1. HEALTH: Start with 100 HP. Lose HP when hitting walls,"
        line1b = "   obstacles, or the other snake."
        txt1a = fmd.render(line1a, True, WHITE)
        screen.blit(txt1a, (30, y))
        y += line_height
        txt1b = fmd.render(line1b, True, WHITE)
        screen.blit(txt1b, (30, y))
        y += line_height

        txt = fmd.render("2. PIES:", True, WHITE)
        screen.blit(txt, (30, y))
        y += line_height
        pie_items = [
            ("Standard pie: +10 HP", YELLOW, "circle"),
            ("Golden pie: +25 HP", GOLD, "circle"),
            ("Poison pie: -15 HP", PURPLE, "circle")
        ]
        for text, color, shape in pie_items:
            if shape == "circle":
                pygame.draw.circle(screen, color, (50, y+10), 8)
                pygame.draw.circle(screen, WHITE, (50, y+10), 3)
            txt = font_small.render(text, True, WHITE)
            screen.blit(txt, (70, y))
            y += line_height

        txt = fmd.render("3. POWER-UPS (appear randomly):", True, WHITE)
        screen.blit(txt, (30, y))
        y += line_height
        powerup_items = [
            ("Speed (cyan): Moves twice as fast for 5 seconds", CYAN, "rect"),
            ("Shield (blue): Protects from one collision (no HP loss)", BLUE, "rect"),
            ("Growth (orange): Instantly adds 3 segments to your snake", ORANGE, "rect")
        ]
        for text, color, shape in powerup_items:
            if shape == "rect":
                pygame.draw.rect(screen, color, (40, y+5, 16, 16))
            txt = font_small.render(text, True, WHITE)
            screen.blit(txt, (70, y))
            y += line_height

        txt = fmd.render("4. COLLISIONS:", True, WHITE)
        screen.blit(txt, (30, y))
        y += line_height
        collisions = [
            "   - Wall/obstacle: -20 HP (unless shielded)",
            "   - Self collision: -10 HP",
            "   - Other snake: -30 HP"
        ]
        for line in collisions:
            txt = font_small.render(line, True, WHITE)
            screen.blit(txt, (50, y))
            y += line_height

        txt = fmd.render("5. GAME DURATION: 120 seconds. Winner is the player with higher HP.", True, WHITE)
        screen.blit(txt, (30, y))
        y += line_height

        txt = fmd.render("6. If HP reaches 0, the player loses immediately.", True, WHITE)
        screen.blit(txt, (30, y))
        y += line_height + 20

        btn_rect = pygame.Rect(WIN_W//2 - 100, WIN_H - 60, 200, 45)
        hover = btn_rect.collidepoint(*pygame.mouse.get_pos())
        draw_shadow(screen, btn_rect)
        draw_rounded_rect(screen, NEON_GREEN if hover else (30,90,30), btn_rect, 10)
        btn_text = fmd.render("I Understand", True, WHITE)
        screen.blit(btn_text, (btn_rect.centerx - btn_text.get_width()//2, btn_rect.centery - btn_text.get_height()//2))
        return btn_rect

    def _draw_lobby(self, screen, fmd, flg):
        draw_gradient_rect(screen, pygame.Rect(0,0,WIN_W,WIN_H), (15,15,35), (5,5,15))
        title = flg.render("Πthon Arena - Lobby", True, NEON_PURPLE)
        screen.blit(title, (WIN_W//2 - title.get_width()//2, 100))
        y = 180
        head = fmd.render("Online Players (click to challenge):", True, WHITE)
        screen.blit(head, (WIN_W//2 - head.get_width()//2, y))
        y += 40
        for p in self.online:
            color = GOLD if p == self.username else WHITE
            txt = fmd.render(f"{'★ ' if p == self.username else '  '}{p}", True, color)
            screen.blit(txt, (WIN_W//2 - txt.get_width()//2, y))
            y += 30
        if len(self.online) <= 1:
            wait = fmd.render("Waiting for other players...", True, GREY)
            screen.blit(wait, (WIN_W//2 - wait.get_width()//2, y+20))

        exit_rect = pygame.Rect(WIN_W - 120, 20, 100, 40)
        hover = exit_rect.collidepoint(*pygame.mouse.get_pos())
        draw_shadow(screen, exit_rect)
        draw_rounded_rect(screen, RED if hover else (140,40,40), exit_rect, 8)
        exit_text = fmd.render("Exit Game", True, WHITE)
        screen.blit(exit_text, (exit_rect.centerx - exit_text.get_width()//2, exit_rect.centery - exit_text.get_height()//2))
        self.exit_rect = exit_rect

        lb_rect = pygame.Rect(WIN_W - 200, 80, 180, 40)
        hover_lb = lb_rect.collidepoint(*pygame.mouse.get_pos())
        draw_shadow(screen, lb_rect)
        draw_rounded_rect(screen, TEAL if hover_lb else DGREY, lb_rect, 8)
        lb_text = fmd.render("Leaderboard", True, WHITE)
        screen.blit(lb_text, (lb_rect.centerx - lb_text.get_width()//2, lb_rect.centery - lb_text.get_height()//2))
        self.lb_rect = lb_rect

    def _draw_leaderboard_popup(self, screen, font):
        s = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        s.fill((0,0,0,200))
        screen.blit(s, (0,0))
        box = pygame.Rect(WIN_W//2 - 300, WIN_H//2 - 200, 600, 400)
        draw_shadow(screen, box)
        draw_rounded_rect(screen, (20,20,40), box, 15)
        pygame.draw.rect(screen, GOLD, box, 3, 15)
        title = font.render("Leaderboard (by wins)", True, GOLD)
        screen.blit(title, (box.centerx - title.get_width()//2, box.y + 20))
        y = box.y + 70
        sorted_stats = sorted(self.leaderboard_data.items(), key=lambda x: x[1].get("wins",0), reverse=True)
        for i, (name, stat) in enumerate(sorted_stats[:10]):
            display_name = name[:20] + "..." if len(name) > 20 else name
            line = font.render(f"{i+1}. {display_name}: {stat.get('wins',0)} wins | Longest: {stat.get('longest',0)} | Pies: {stat.get('pies',0)}", True, WHITE)
            if line.get_width() > box.width - 40:
                line = font.render(f"{i+1}. {display_name}: {stat.get('wins',0)} wins | Longest: {stat.get('longest',0)}", True, WHITE)
            screen.blit(line, (box.x + 20, y))
            y += 30
        close_rect = pygame.Rect(box.right - 80, box.y + 10, 70, 30)
        draw_rounded_rect(screen, RED, close_rect, 8)
        close_text = font.render("Close", True, WHITE)
        screen.blit(close_text, (close_rect.centerx - close_text.get_width()//2, close_rect.centery - close_text.get_height()//2))
        return close_rect

    def _draw_snake_segment(self, screen, x, y, color, is_head, segment_index, direction=None):
        rect = pygame.Rect(x*CELL+1, y*CELL+1, CELL-2, CELL-2)
        draw_rounded_rect(screen, color, rect, 4 if is_head else 2)
        if self.pattern == "striped" and not is_head and segment_index % 2 == 0:
            stripe_rect = pygame.Rect(x*CELL+1, y*CELL+1 + CELL//3, CELL-2, CELL//3)
            lighter = (min(color[0]+40,255), min(color[1]+40,255), min(color[2]+40,255))
            draw_rounded_rect(screen, lighter, stripe_rect, 2)
        elif self.pattern == "dotted" and not is_head:
            cx = x*CELL + CELL//2
            cy = y*CELL + CELL//2
            pygame.draw.circle(screen, WHITE, (cx, cy), 3)
        if is_head and self.eyes and direction:
            cx = x*CELL + CELL//2
            cy = y*CELL + CELL//2
            if direction == "UP":
                left_eye = (cx - 5, cy - 5)
                right_eye = (cx + 5, cy - 5)
            elif direction == "DOWN":
                left_eye = (cx - 5, cy + 5)
                right_eye = (cx + 5, cy + 5)
            elif direction == "LEFT":
                left_eye = (cx - 5, cy - 5)
                right_eye = (cx - 5, cy + 5)
            elif direction == "RIGHT":
                left_eye = (cx + 5, cy - 5)
                right_eye = (cx + 5, cy + 5)
            else:
                left_eye = (cx - 4, cy - 4)
                right_eye = (cx + 4, cy - 4)
            pygame.draw.circle(screen, WHITE, left_eye, 3)
            pygame.draw.circle(screen, WHITE, right_eye, 3)
            pygame.draw.circle(screen, BLACK, left_eye, 1)
            pygame.draw.circle(screen, BLACK, right_eye, 1)

    def _draw_game(self, screen, fsm, fmd, flg, chat_input):
        # screen shake
        shake_x = random.randint(-self.screen_shake, self.screen_shake) if self.screen_shake else 0
        shake_y = random.randint(-self.screen_shake, self.screen_shake) if self.screen_shake else 0
        self.screen_shake = max(0, self.screen_shake - 1)

        gs = self.game_state
        # game area
        game_rect = pygame.Rect(0,0,GRID_W*CELL, GRID_H*CELL)
        draw_gradient_rect(screen, game_rect, (10,10,20), (0,0,0))
        for gx in range(0, GRID_W*CELL, CELL):
            pygame.draw.line(screen, (30,30,40), (gx+shake_x, shake_y), (gx+shake_x, GRID_H*CELL+shake_y), 1)
        for gy in range(0, GRID_H*CELL, CELL):
            pygame.draw.line(screen, (30,30,40), (shake_x, gy+shake_y), (GRID_W*CELL+shake_x, gy+shake_y), 1)

        # obstacles
        for obs in gs.get("obstacles", []):
            r = pygame.Rect(obs[0]*CELL+1+shake_x, obs[1]*CELL+1+shake_y, CELL-2, CELL-2)
            draw_rounded_rect(screen, (80,50,30), r, 3)

        # pies
        for pie in gs.get("pies", []):
            px,py = pie["pos"]
            col = PIE_COLOR.get(pie.get("type","standard"), YELLOW)
            cx = px*CELL + CELL//2 + shake_x
            cy = py*CELL + CELL//2 + shake_y
            draw_glow(screen, (cx, cy), col, 12)
            pygame.draw.circle(screen, col, (cx, cy), CELL//2-2)
            pygame.draw.circle(screen, WHITE, (cx, cy), 3)

        # powerups
        for pu in gs.get("powerups", []):
            px,py = pu["pos"]
            col = POWERUP_COLOR.get(pu["type"], CYAN)
            cx = px*CELL + CELL//2 + shake_x
            cy = py*CELL + CELL//2 + shake_y
            draw_glow(screen, (cx, cy), col, 15)
            draw_rounded_rect(screen, col, pygame.Rect(cx-8, cy-8, 16, 16), 4)

        # snakes
        snakes = gs.get("snakes", {})
        for uname, snake in snakes.items():
            body = snake.get("body", [])
            alive = snake.get("alive", True)
            color_name = snake.get("color", "neon_green")
            base_color, head_color = SNAKE_COLOR_OPTIONS.get(color_name, SNAKE_COLOR_OPTIONS["neon_green"])
            if not alive:
                base_color = (60,60,60)
                head_color = (40,40,40)
            head_dir = snake.get("dir", "UP")
            for idx, cell in enumerate(body):
                is_head = (idx == 0)
                col_to_use = head_color if is_head else base_color
                self._draw_snake_segment(screen, cell[0]+shake_x//CELL, cell[1]+shake_y//CELL, col_to_use, is_head, idx, head_dir if is_head else None)
            if snake.get("shield", 0) > 0:
                head = body[0]
                cx = head[0]*CELL + CELL//2 + shake_x
                cy = head[1]*CELL + CELL//2 + shake_y
                pygame.draw.circle(screen, BLUE, (cx, cy), CELL//2, 2)
            if snake.get("speed_boost", 0) > 0:
                head = body[0]
                cx = head[0]*CELL + CELL//2 + shake_x
                cy = head[1]*CELL + CELL//2 + shake_y
                pygame.draw.circle(screen, CYAN, (cx, cy), CELL//2-2, 2)

        # sidebar
        sx = GRID_W * CELL
        draw_gradient_rect(screen, pygame.Rect(sx,0,SIDEBAR_W,WIN_H), (20,20,40), (10,10,30))
        pygame.draw.line(screen, NEON_PURPLE, (sx, 0), (sx, WIN_H), 2)

        # ---------- MUTE BUTTON (FIXED: uses emoji font) ----------
        mute_rect = pygame.Rect(sx + SIDEBAR_W - 50, 10, 40, 40)
        draw_shadow(screen, mute_rect)
        draw_rounded_rect(screen, DGREY, mute_rect, 8)
        # Load emoji font (fallback to default if not available)
        if self.emoji_font is None:
            try:
                # Windows: Segoe UI Emoji, Linux: Noto Color Emoji
                self.emoji_font = pygame.font.SysFont("segoeuiemoji", 28)
                if self.emoji_font.render("🔊", True, WHITE).get_width() == 0:
                    raise
            except:
                self.emoji_font = pygame.font.Font(None, 28)  # fallback (may not show emoji)
        icon = "🔊" if self.sound_enabled else "🔇"
        icon_surf = self.emoji_font.render(icon, True, WHITE)
        screen.blit(icon_surf, icon_surf.get_rect(center=mute_rect.center))
        self.mute_button_rect = mute_rect

        # ---------- FAN EMOJI BUTTONS (only if spectator and game running) ----------
        if self.role == "fan" and self.game_state.get("status") == "running":
            emojis = ["🎉", "👍", "⭐", "❤️", "👏", "🔥"]
            self.fan_emoji_buttons = []
            start_x = sx + 10
            start_y = WIN_H - 70
            for i, emoji in enumerate(emojis):
                btn_rect = pygame.Rect(start_x + i*40, start_y, 35, 35)
                draw_shadow(screen, btn_rect)
                draw_rounded_rect(screen, (50,50,70), btn_rect, 6)
                emo_surf = fmd.render(emoji, True, WHITE)
                screen.blit(emo_surf, emo_surf.get_rect(center=btn_rect.center))
                self.fan_emoji_buttons.append((btn_rect, emoji))
        else:
            self.fan_emoji_buttons = []

        # Player info
        y = 10
        title = fmd.render("Πthon Arena", True, NEON_PURPLE)
        screen.blit(title, (sx+10, y)); y+=30
        tl = gs.get("time_left", 0)
        time_col = RED if tl<15 else YELLOW if tl<30 else WHITE
        tlabel = fsm.render(f"Time: {tl}s", True, time_col)
        screen.blit(tlabel, (sx+10, y)); y+=24

        for uname, snake in snakes.items():
            health = max(0, snake.get("health", 0))
            is_me = uname == self.username
            col = SNAKE_COLOR_OPTIONS.get(snake.get("color","neon_green"), SNAKE_COLOR_OPTIONS["neon_green"])[0]
            name_t = fsm.render(("▶ " if is_me else "  ") + uname, True, col)
            screen.blit(name_t, (sx+10, y)); y+=18
            bar_w = int((SIDEBAR_W-20) * health / 100)
            pygame.draw.rect(screen, DGREY, pygame.Rect(sx+10, y, SIDEBAR_W-20, 14), border_radius=4)
            pygame.draw.rect(screen, col, pygame.Rect(sx+10, y, bar_w, 14), border_radius=4)
            hp_t = fsm.render(f"HP: {health}", True, WHITE)
            screen.blit(hp_t, (sx+10, y)); y+=20

        y+=10
        role_display = "PLAYER" if self.username in snakes else "FAN"
        rb = fsm.render(f"[{role_display}]", True, TEAL)
        screen.blit(rb, (sx+10, y)); y+=22

        if self.countdown:
            ct = flg.render(str(self.countdown), True, GOLD)
            ct_rect = ct.get_rect(center=(WIN_W//2, WIN_H//2))
            pygame.draw.circle(screen, (0,0,0,150), ct_rect.center, 40)
            screen.blit(ct, ct_rect)

        if gs.get("status") == "finished" or self.game_over:
            go = self.game_over or {}
            winner = go.get("winner") or gs.get("winner")
            loser = go.get("loser")
            scores = go.get("scores", {u:s.get("health",0) for u,s in snakes.items()})
            if not loser and winner:
                others = [u for u in scores.keys() if u != winner]
                loser = others[0] if len(others) == 1 else None
            overlay = pygame.Surface((WIN_W,WIN_H), pygame.SRCALPHA)
            overlay.fill((0,0,0,180))
            screen.blit(overlay, (0,0))
            if winner:
                wt = flg.render(f"Winner: {winner}", True, GOLD)
            else:
                wt = flg.render("Draw", True, GOLD)
            screen.blit(wt, (WIN_W//2 - wt.get_width()//2, WIN_H//2 - 90))
            if loser:
                lt = fmd.render(f"Loser: {loser}", True, RED)
                screen.blit(lt, (WIN_W//2 - lt.get_width()//2, WIN_H//2 - 45))
            reason = go.get("reason")
            if reason == "health_zero":
                rt = fsm.render("Match ended immediately: health reached 0", True, WHITE)
                screen.blit(rt, (WIN_W//2 - rt.get_width()//2, WIN_H//2 - 12))
            for i, (uname, hp) in enumerate(scores.items()):
                st = fmd.render(f"{uname}: {hp} HP", True, WHITE)
                screen.blit(st, (WIN_W//2 - st.get_width()//2, WIN_H//2 + 22 + i*28))

        # Chat area - WITH LINE WRAPPING (FIXED)
        chat_y_start = WIN_H - 190
        chat_area_height = 150
        line_height = 18
        max_visible = chat_area_height // line_height

        # Calculate available width for chat messages (sidebar width minus padding)
        chat_width = SIDEBAR_W - 20  # 280 - 20 = 260 pixels

        with self.msg_lock:
            wrapped_chat_lines = []
            for msg_text, _ in self.messages:
                wrapped_chat_lines.extend(self._wrap_text(msg_text, fsm, chat_width))

            total_lines = len(wrapped_chat_lines)
            max_scroll = max(0, total_lines - max_visible)
            if self.chat_scroll < 0:
                self.chat_scroll = 0
            if self.chat_scroll > max_scroll:
                self.chat_scroll = max_scroll

            start_line = max(0, total_lines - max_visible - self.chat_scroll)
            end_line = min(total_lines, start_line + max_visible)
            visible_lines = wrapped_chat_lines[start_line:end_line]

        pygame.draw.rect(screen, (20,20,30), (sx+5, chat_y_start-5, SIDEBAR_W-10, chat_area_height+5), border_radius=6)
        pygame.draw.rect(screen, GREY, (sx+5, chat_y_start-5, SIDEBAR_W-10, chat_area_height+5), 2, 6)

        # Display wrapped chat lines
        for line_index, line in enumerate(visible_lines):
            mt = fsm.render(line, True, (220,220,200))
            screen.blit(mt, (sx+10, chat_y_start + line_index * line_height))

        if max_scroll > 0:
            scroll_text = fsm.render(f"scroll {self.chat_scroll}/{max_scroll}", True, GREY)
            screen.blit(scroll_text, (sx+10, chat_y_start + chat_area_height - line_height))

        chat_box = pygame.Rect(sx+5, WIN_H-32, SIDEBAR_W-10, 28)
        draw_rounded_rect(screen, DGREY, chat_box, 6)
        pygame.draw.rect(screen, NEON_PURPLE, chat_box, 2, 6)
        # Show the last part of long input text (scrolls horizontally)
        display_input = chat_input if len(chat_input) <= 50 else "..." + chat_input[-47:]
        ct2 = fsm.render(display_input + "_", True, WHITE)
        screen.blit(ct2, (sx+8, WIN_H-30))

        # particles and floating texts
        self.particles = [p for p in self.particles if p.update()]
        for p in self.particles:
            p.draw(screen)
        self.floating_texts = [t for t in self.floating_texts if t.update()]
        for t in self.floating_texts:
            t.draw(screen, fsm)

    def _draw_popup(self, screen, text, font):
        s = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        s.fill((0,0,0,180))
        screen.blit(s, (0,0))
        box = pygame.Rect(WIN_W//2 - 200, WIN_H//2 - 80, 400, 160)
        draw_shadow(screen, box)
        draw_rounded_rect(screen, (30,30,50), box, 15)
        pygame.draw.rect(screen, NEON_PURPLE, box, 2, 15)
        label = font.render(text, True, WHITE)
        screen.blit(label, (box.centerx - label.get_width()//2, box.y + 30))
        yes_rect = pygame.Rect(box.x + 50, box.y + 90, 120, 40)
        no_rect = pygame.Rect(box.x + 230, box.y + 90, 120, 40)
        draw_shadow(screen, yes_rect)
        draw_shadow(screen, no_rect)
        draw_rounded_rect(screen, NEON_GREEN, yes_rect, 8)
        draw_rounded_rect(screen, RED, no_rect, 8)
        yes_t = font.render("Yes", True, WHITE)
        no_t = font.render("No", True, WHITE)
        screen.blit(yes_t, (yes_rect.centerx - yes_t.get_width()//2, yes_rect.centery - yes_t.get_height()//2))
        screen.blit(no_t, (no_rect.centerx - no_t.get_width()//2, no_rect.centery - no_t.get_height()//2))
        return yes_rect, no_rect

    def _draw_fan_popup(self, screen, font):
        s = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        s.fill((0,0,0,180))
        screen.blit(s, (0,0))
        box = pygame.Rect(WIN_W//2 - 200, WIN_H//2 - 80, 400, 160)
        draw_shadow(screen, box)
        draw_rounded_rect(screen, (30,30,50), box, 15)
        pygame.draw.rect(screen, GOLD, box, 2, 15)
        label = font.render("Match finished", True, WHITE)
        screen.blit(label, (box.centerx - label.get_width()//2, box.y + 25))
        sub = pygame.font.SysFont("monospace", 14).render("What would you like to do?", True, GREY)
        screen.blit(sub, (box.centerx - sub.get_width()//2, box.y + 55))
        watch_rect = pygame.Rect(box.x + 40, box.y + 95, 140, 40)
        lobby_rect = pygame.Rect(box.x + 220, box.y + 95, 140, 40)
        draw_shadow(screen, watch_rect)
        draw_shadow(screen, lobby_rect)
        draw_rounded_rect(screen, TEAL, watch_rect, 8)
        draw_rounded_rect(screen, NEON_GREEN, lobby_rect, 8)
        watch_text = font.render("Watch again", True, WHITE)
        lobby_text = font.render("Back to lobby", True, WHITE)
        screen.blit(watch_text, (watch_rect.centerx - watch_text.get_width()//2, watch_rect.centery - watch_text.get_height()//2))
        screen.blit(lobby_text, (lobby_rect.centerx - lobby_text.get_width()//2, lobby_rect.centery - lobby_text.get_height()//2))
        return watch_rect, lobby_rect

    # ---------- MAIN RUN ----------
    def run(self):
        pygame.init()
        screen = pygame.display.set_mode((WIN_W, WIN_H))
        pygame.display.set_caption("Πthon Arena")
        clock = pygame.time.Clock()
        font_sm = pygame.font.SysFont("monospace", 14)
        font_md = pygame.font.SysFont("monospace", 18, bold=True)
        font_lg = pygame.font.SysFont("monospace", 36, bold=True)

        ip_text = "127.0.0.1"
        port_text = "5000"
        user_text = ""
        color_index = 0
        color_names = list(SNAKE_COLOR_OPTIONS.keys())
        active = "user"
        error_msg = ""

        ip_rect = pygame.Rect(200,180,300,36)
        port_rect = pygame.Rect(200,240,300,36)
        user_rect = pygame.Rect(200,300,300,36)
        btn_rect = pygame.Rect(200,360,300,44)
        color_btn_rect = pygame.Rect(200, 420, 300, 40)

        chat_text = ""
        running = True

        while running:
            clock.tick(FPS)
            mx, my = pygame.mouse.get_pos()

            self._check_for_sound_triggers()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

                if self.remap_waiting and event.type == pygame.KEYDOWN and self.remap_action:
                    if event.key not in self.key_map[self.remap_action]:
                        self.key_map[self.remap_action].append(event.key)
                    self.remap_waiting = False
                    self.remap_action = None
                    continue

                # Handle button clicks during game
                if self.phase == "game" and event.type == pygame.MOUSEBUTTONDOWN:
                    # Mute button
                    if self.mute_button_rect and self.mute_button_rect.collidepoint(mx, my):
                        print("Mute button clicked")
                        self.toggle_sound()
                    # Fan emoji buttons
                    for btn_rect, emoji in self.fan_emoji_buttons:
                        if btn_rect.collidepoint(mx, my):
                            print(f"Emoji {emoji} clicked")
                            players = list(self.game_state.get("snakes", {}).keys())
                            if players:
                                target = players[0] if len(players) == 1 else "both players"
                                cheer_msg = f"[FAN] {self.username} cheers for {target} with {emoji}!"
                            else:
                                cheer_msg = f"[FAN] {self.username} cheers with {emoji}!"
                            self.send_chat(cheer_msg)
                            break

                # All the original event handling for each phase (unchanged)
                if self.phase == "connect":
                    if event.type == pygame.KEYDOWN or (event.type == pygame.MOUSEBUTTONDOWN and btn_rect.collidepoint(mx,my)):
                        error_msg = ""
                    if event.type == pygame.MOUSEBUTTONDOWN:
                        if ip_rect.collidepoint(mx,my): active="ip"
                        elif port_rect.collidepoint(mx,my): active="port"
                        elif user_rect.collidepoint(mx,my): active="user"
                        elif btn_rect.collidepoint(mx,my):
                            if user_text.strip():
                                self.phase = "color"
                            else:
                                error_msg = "Enter username"
                        elif color_btn_rect.collidepoint(mx,my):
                            color_index = (color_index + 1) % len(color_names)
                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_TAB:
                            active = {"ip":"port","port":"user","user":"ip"}[active]
                        elif event.key == pygame.K_RETURN:
                            if user_text.strip():
                                self.phase = "color"
                            else:
                                error_msg = "Enter username"
                        elif event.key == pygame.K_BACKSPACE:
                            if active=="ip": ip_text=ip_text[:-1]
                            elif active=="port": port_text=port_text[:-1]
                            else: user_text=user_text[:-1]
                        else:
                            ch = event.unicode
                            if active=="ip": ip_text+=ch
                            elif active=="port": port_text+=ch
                            elif len(user_text)<20: user_text+=ch

                elif self.phase == "color":
                    if event.type == pygame.MOUSEBUTTONDOWN:
                        change_btn, next_btn = self._draw_color(screen, font_md, font_lg, color_names, color_index, error_msg)
                        if change_btn.collidepoint(mx, my):
                            color_index = (color_index + 1) % len(color_names)
                        elif next_btn.collidepoint(mx, my):
                            self.snake_color = color_names[color_index]
                            self.phase = "controls"
                            error_msg = ""
                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_RETURN:
                            self.snake_color = color_names[color_index]
                            self.phase = "controls"
                            error_msg = ""
                        elif event.key == pygame.K_LEFT or event.key == pygame.K_RIGHT:
                            color_index = (color_index + 1) % len(color_names)

                elif self.phase == "controls":
                    if event.type == pygame.MOUSEBUTTONDOWN:
                        for d, rect in self.control_buttons.items():
                            if rect.collidepoint(mx, my):
                                self.remap_action = d
                                self.remap_waiting = True
                        if hasattr(self, 'pattern_rects'):
                            for pat, rect in self.pattern_rects.items():
                                if rect.collidepoint(mx, my):
                                    self.pattern = pat
                        if hasattr(self, 'eyes_rect') and self.eyes_rect.collidepoint(mx, my):
                            self.eyes = not self.eyes
                        if hasattr(self, 'controls_next_rect') and self.controls_next_rect.collidepoint(mx, my):
                            self.phase = "rules"
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
                        self.phase = "rules"

                elif self.phase == "rules":
                    if event.type == pygame.MOUSEBUTTONDOWN:
                        btn_rect_rules = pygame.Rect(WIN_W//2 - 100, WIN_H - 60, 200, 45)
                        if btn_rect_rules.collidepoint(mx, my):
                            self.rules_shown = True
                            ok, reason = self.connect(ip_text, int(port_text), user_text, self.snake_color)
                            if ok:
                                self.phase = "lobby"
                                error_msg = ""
                            else:
                                error_msg = reason
                                self.phase = "connect"
                                active = "user"
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
                        ok, reason = self.connect(ip_text, int(port_text), user_text, self.snake_color)
                        if ok:
                            self.phase = "lobby"
                            error_msg = ""
                        else:
                            error_msg = reason
                            self.phase = "connect"
                            active = "user"

                elif self.phase == "lobby":
                    if event.type == pygame.MOUSEBUTTONDOWN:
                        if hasattr(self, 'exit_rect') and self.exit_rect.collidepoint(mx, my):
                            if self.sock:
                                try:
                                    self.sock.close()
                                except:
                                    pass
                            running = False
                            break
                        if hasattr(self, 'lb_rect') and self.lb_rect.collidepoint(mx, my):
                            self._send({"type": "get_leaderboard"})
                            self.show_leaderboard = True
                        y_start = 220
                        for i, p in enumerate(self.online):
                            if p == self.username:
                                continue
                            rect = pygame.Rect(WIN_W//2 - 100, y_start + i*30, 200, 25)
                            if rect.collidepoint(mx, my):
                                self._send({"type": "challenge", "target": p})
                                with self.msg_lock:
                                    self.messages.append((f"[System] Challenged {p}", pygame.time.get_ticks()))
                    if self.game_state.get("status") == "countdown":
                        self.phase = "game"
                        self._play_sound('game_start')
                        if self.sound_enabled:
                            self._start_bg_music()

                elif self.phase == "challenge_popup":
                    if event.type == pygame.MOUSEBUTTONDOWN:
                        box = pygame.Rect(WIN_W//2 - 200, WIN_H//2 - 80, 400, 160)
                        yes_rect = pygame.Rect(box.x + 50, box.y + 90, 120, 40)
                        no_rect = pygame.Rect(box.x + 230, box.y + 90, 120, 40)
                        if yes_rect.collidepoint(mx, my):
                            self._send({"type": "challenge_response", "target": self.pending_challenge, "accept": True})
                            self.pending_challenge = None
                            self.phase = "lobby"
                        elif no_rect.collidepoint(mx, my):
                            self._send({"type": "challenge_response", "target": self.pending_challenge, "accept": False})
                            self.pending_challenge = None
                            self.phase = "lobby"
                    if self.game_state.get("status") == "countdown":
                        self.phase = "game"
                        self._play_sound('game_start')
                        if self.sound_enabled:
                            self._start_bg_music()

                elif self.phase == "rematch_popup":
                    if event.type == pygame.MOUSEBUTTONDOWN:
                        box = pygame.Rect(WIN_W//2 - 200, WIN_H//2 - 80, 400, 160)
                        yes_rect = pygame.Rect(box.x + 50, box.y + 90, 120, 40)
                        no_rect = pygame.Rect(box.x + 230, box.y + 90, 120, 40)
                        if yes_rect.collidepoint(mx, my):
                            self._send({"type": "rematch"})
                            self.rematch_request = False
                            if self.rematch_timer:
                                self.rematch_timer.cancel()
                                self.rematch_timer = None
                        elif no_rect.collidepoint(mx, my):
                            self._send({"type": "decline_rematch"})
                            self.rematch_request = False
                            if self.rematch_timer:
                                self.rematch_timer.cancel()
                                self.rematch_timer = None
                            self.phase = "lobby"
                            self._stop_bg_music()

                elif self.phase == "fan_rematch_popup":
                    if event.type == pygame.MOUSEBUTTONDOWN:
                        box = pygame.Rect(WIN_W//2 - 200, WIN_H//2 - 80, 400, 160)
                        watch_rect = pygame.Rect(box.x + 40, box.y + 95, 140, 40)
                        lobby_rect = pygame.Rect(box.x + 220, box.y + 95, 140, 40)
                        if watch_rect.collidepoint(mx, my):
                            self.phase = "lobby"
                            self.fan_skip_popup = False
                        elif lobby_rect.collidepoint(mx, my):
                            self.phase = "lobby"
                            self.fan_skip_popup = True
                    if self.game_state.get("status") == "countdown":
                        self.phase = "game"
                        self._play_sound('game_start')
                        if self.sound_enabled:
                            self._start_bg_music()
                        self.fan_skip_popup = False
                    elif self.game_state.get("status") == "waiting":
                        self.phase = "lobby"
                        self.fan_skip_popup = False

                elif self.phase == "game":
                    if event.type == pygame.KEYDOWN:
                        for direction, keys in self.key_map.items():
                            if event.key in keys:
                                self.send_move(direction)
                                break
                        if event.key == pygame.K_RETURN:
                            if chat_text.startswith("/p2p "):
                                self.p2p_send(chat_text[5:])
                            else:
                                self.send_chat(chat_text)
                            chat_text = ""
                        elif event.key == pygame.K_BACKSPACE:
                            chat_text = chat_text[:-1]
                        else:
                            if event.unicode and event.unicode.isprintable():
                                chat_text += event.unicode
                    if event.type == pygame.MOUSEWHEEL:
                        self.chat_auto_scroll = False
                        self.chat_scroll += event.y
                        if self.chat_scroll < 0:
                            self.chat_scroll = 0
                        with self.msg_lock:
                            total = len(self.messages)
                            max_scroll = max(0, total - 9)
                            if self.chat_scroll > max_scroll:
                                self.chat_scroll = max_scroll
                        if self.chat_scroll == 0:
                            self.chat_auto_scroll = True

                # Close leaderboard popup
                if self.show_leaderboard and event.type == pygame.MOUSEBUTTONDOWN:
                    box = pygame.Rect(WIN_W//2 - 300, WIN_H//2 - 200, 600, 400)
                    close_rect = pygame.Rect(box.right - 80, box.y + 10, 70, 30)
                    if close_rect.collidepoint(mx, my):
                        self.show_leaderboard = False

            # Drawing
            screen.fill(BLACK)
            if self.phase == "connect":
                self._draw_connect(screen, font_sm, font_md, font_lg, ip_text, port_text, user_text, active, error_msg, ip_rect, port_rect, user_rect, btn_rect, color_btn_rect, color_names[color_index])
            elif self.phase == "color":
                self._draw_color(screen, font_md, font_lg, color_names, color_index, error_msg)
            elif self.phase == "controls":
                self._draw_controls(screen, font_md, font_lg, btn_rect)
            elif self.phase == "rules":
                self._draw_rules(screen, font_md, font_lg)
            elif self.phase == "lobby":
                self._draw_lobby(screen, font_md, font_lg)
                if self.show_leaderboard:
                    self._draw_leaderboard_popup(screen, font_md)
            elif self.phase == "game":
                self._draw_game(screen, font_sm, font_md, font_lg, chat_text)
            elif self.phase == "challenge_popup":
                self._draw_lobby(screen, font_md, font_lg)
                self._draw_popup(screen, f"Challenge from {self.pending_challenge}?", font_md)
            elif self.phase == "rematch_popup":
                self._draw_game(screen, font_sm, font_md, font_lg, chat_text)
                self._draw_popup(screen, "Play again?", font_md)
            elif self.phase == "fan_rematch_popup":
                self._draw_game(screen, font_sm, font_md, font_lg, chat_text)
                self._draw_fan_popup(screen, font_md)

            pygame.display.flip()

        pygame.quit()

if __name__ == "__main__":
    client = IthonArenaClient()
    client.run()