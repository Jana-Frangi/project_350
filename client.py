"""
Πthon Arena - Client (Fancy Design + Working Sound Mute)
Run: python client.py
"""

import pygame
import socket
import threading
import json
import sys
import math
import array

CELL = 20
GRID_W = 30
GRID_H = 30
SIDEBAR_W = 280
WIN_W = GRID_W * CELL + SIDEBAR_W
WIN_H = GRID_H * CELL
FPS = 30

# ========== FANCY COLOR PALETTE (NO GREEN) ==========
BLACK = (0,0,0)
WHITE = (255,255,255)
GREY = (180,180,180)
DGREY = (40,40,60)
DARK_PURPLE = (20,10,40)
PURPLE = (120,60,200)
NEON_PINK = (255,50,150)
NEON_CYAN = (0,255,255)
GOLD = (255,215,0)
MAGENTA = (255,0,255)
DARK_BG = (10,5,20)

SNAKE_COLOR_OPTIONS = {
    "cyan": ((0,255,255), (0,200,200)),
    "magenta": ((255,50,150), (200,20,100)),
    "gold": ((255,215,0), (200,160,0)),
    "purple": ((160,80,255), (100,40,200)),
    "red": ((255,70,70), (200,40,40)),
    "orange": ((255,140,50), (200,90,20))
}

PIE_COLOR = {"standard": GOLD, "golden": (255,230,80), "poison": PURPLE}
POWERUP_COLOR = {"speed": NEON_CYAN, "shield": (80,150,255), "growth": (255,120,50)}

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
        self.sock = None
        self.reader = None
        self.username = ""
        self.snake_color = "cyan"
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
        self.last_countdown = None
        self.last_time_left = None

        # Key mapping
        self.key_map = {
            "UP": [pygame.K_UP, pygame.K_w],
            "DOWN": [pygame.K_DOWN, pygame.K_s],
            "LEFT": [pygame.K_LEFT, pygame.K_a],
            "RIGHT": [pygame.K_RIGHT, pygame.K_d]
        }
        self.remap_action = None
        self.remap_waiting = False

        self.pattern = "solid"
        self.eyes = True
        self.rules_shown = False

        # Sound system
        self.sound_enabled = True
        self.music_playing = False
        self.sounds = {}
        self._init_sounds()

        # Sound toggle button (in-game)
        self.sound_toggle_rect = pygame.Rect(GRID_W*CELL + 10, WIN_H - 70, 50, 50)

        # Animation helpers
        self.food_pulse = 0

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
        except Exception as e:
            print(f"Sound creation failed: {e}")
            self.sound_enabled = False

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
            self.music_playing = False

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
            # Mute: stop music immediately
            self._stop_bg_music()
        else:
            # Unmute: restart music only if game is active
            status = self.game_state.get("status")
            if status in ("running", "countdown") and self.phase == "game":
                self._start_bg_music()
        # Update button icon (handled in draw)

    def _get_free_port(self):
        sock = socket.socket()
        sock.bind(('', 0))
        port = sock.getsockname()[1]
        sock.close()
        return port

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
            elif status == "finished" and not self.game_over:
                snakes = self.game_state.get("snakes", {})
                winner = self.game_state.get("winner")
                loser = next((u for u in snakes if u != winner), None) if winner else None
                self.game_over = {"winner": winner, "loser": loser, "scores": {u: s.get("health", 0) for u, s in snakes.items()}, "reason": "Health reached 0 or time ended"}
                if self.username not in snakes:
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
                    # Only start music if sound is enabled
                    if self.sound_enabled:
                        self._start_bg_music()
        elif mtype == "lobby":
            self.online = msg.get("online", [])
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

        # Powerup collected
        prev_powerups = {tuple(p["pos"]): p["type"] for p in self.prev_game_state.get("powerups", [])}
        curr_powerups = {tuple(p["pos"]): p["type"] for p in self.game_state.get("powerups", [])}
        for pos, ptype in prev_powerups.items():
            if pos not in curr_powerups:
                self._play_sound('powerup')
        # Pie eaten
        prev_pies = {tuple(p["pos"]): p["type"] for p in self.prev_game_state.get("pies", [])}
        curr_pies = {tuple(p["pos"]): p["type"] for p in self.game_state.get("pies", [])}
        for pos, ptype in prev_pies.items():
            if pos not in curr_pies:
                if ptype == "poison":
                    self._play_sound('poison')
                else:
                    self._play_sound('pie_eat')
        # Last 10 seconds beep
        tl = self.game_state.get("time_left", 0)
        if tl != self.last_time_left and status == "running":
            if 0 < tl <= 10:
                self._play_sound('countdown_beep')
            self.last_time_left = tl

    # ------------------------------------------------------------------
    # Drawing methods (fancy, same as before but with sound toggle draw)
    # ------------------------------------------------------------------
    def draw_gradient_background(self, screen):
        for y in range(WIN_H):
            ratio = y / WIN_H
            r = int(15 + 5 * ratio)
            g = int(8 + 4 * ratio)
            b = int(30 + 15 * ratio)
            pygame.draw.line(screen, (r,g,b), (0, y), (WIN_W, y))

    def draw_rounded_rect(self, screen, color, rect, radius=8, border=0, border_color=None):
        pygame.draw.rect(screen, color, rect, border_radius=radius)
        if border and border_color:
            pygame.draw.rect(screen, border_color, rect, border, border_radius=radius)

    def _draw_connect(self, screen, fsm, fmd, flg, ip_t, port_t, user_t, active, err, ip_r, port_r, user_r, btn_r, color_btn_r, current_color):
        self.draw_gradient_background(screen)
        title = flg.render("Πthon Arena", True, GOLD)
        screen.blit(title, (WIN_W//2 - title.get_width()//2, 80))
        fields = [("Server IP", ip_t, ip_r, "ip"), ("Port", port_t, port_r, "port"), ("Username", user_t, user_r, "user")]
        for label, val, rect, key in fields:
            color = NEON_CYAN if active==key else GREY
            self.draw_rounded_rect(screen, DGREY, rect, radius=6)
            pygame.draw.rect(screen, color, rect, 2, border_radius=6)
            lbl = fsm.render(label, True, GREY)
            screen.blit(lbl, (rect.x, rect.y-18))
            txt = fmd.render(val + ("_" if active==key else ""), True, WHITE)
            screen.blit(txt, (rect.x+8, rect.y+8))
        hover = btn_r.collidepoint(*pygame.mouse.get_pos())
        btn_color = (100,50,150) if hover else (60,30,100)
        self.draw_rounded_rect(screen, btn_color, btn_r, radius=6)
        bt = fmd.render("Next: Choose Color", True, WHITE)
        screen.blit(bt, (btn_r.centerx - bt.get_width()//2, btn_r.centery - bt.get_height()//2))
        if err:
            et = fsm.render(f"Error: {err}", True, NEON_PINK)
            screen.blit(et, (200,420))

    def _draw_color(self, screen, fmd, flg, btn_r, color_btn_r, color_names, color_index, err):
        self.draw_gradient_background(screen)
        title = flg.render("Choose Your Snake Color", True, GOLD)
        screen.blit(title, (WIN_W//2 - title.get_width()//2, 100))
        color_name = color_names[color_index]
        preview_color = SNAKE_COLOR_OPTIONS[color_name][0]
        pygame.draw.rect(screen, preview_color, (WIN_W//2 - 50, 200, 100, 100), border_radius=12)
        name_text = fmd.render(color_name.upper(), True, WHITE)
        screen.blit(name_text, (WIN_W//2 - name_text.get_width()//2, 320))
        hover_color = color_btn_r.collidepoint(*pygame.mouse.get_pos())
        btn_color = (100,50,150) if hover_color else (60,30,100)
        self.draw_rounded_rect(screen, btn_color, color_btn_r, radius=6)
        ct = fmd.render("Change Color (← →)", True, WHITE)
        screen.blit(ct, (color_btn_r.centerx - ct.get_width()//2, color_btn_r.centery - ct.get_height()//2))
        hover_connect = btn_r.collidepoint(*pygame.mouse.get_pos())
        btn_color2 = (100,50,150) if hover_connect else (60,30,100)
        self.draw_rounded_rect(screen, btn_color2, btn_r, radius=6)
        bt = fmd.render("Next: Customize", True, WHITE)
        screen.blit(bt, (btn_r.centerx - bt.get_width()//2, btn_r.centery - bt.get_height()//2))
        if err:
            et = fmd.render(f"Error: {err}", True, NEON_PINK)
            screen.blit(et, (200, 500))

    def _draw_controls(self, screen, fmd, flg, btn_rect):
        self.draw_gradient_background(screen)
        title = flg.render("Customize Controls & Snake Design", True, GOLD)
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
            color = (200,100,0) if self.remap_waiting and self.remap_action == d else (60,30,100)
            self.draw_rounded_rect(screen, color, rect, radius=6)
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
            color = NEON_CYAN if self.pattern == pat else (60,30,100)
            self.draw_rounded_rect(screen, color, rect, radius=6)
            pat_text = fmd.render(pat.upper(), True, WHITE)
            screen.blit(pat_text, (rect.x + 10, rect.y + 8))
        y += 40 * 3 + 10
        eyes_rect = pygame.Rect(right_x, y, 180, 40)
        color = (100,50,150) if self.eyes else (60,30,100)
        self.draw_rounded_rect(screen, color, eyes_rect, radius=6)
        eyes_text = fmd.render("Eyes: " + ("ON" if self.eyes else "OFF"), True, WHITE)
        screen.blit(eyes_text, (eyes_rect.x + 20, eyes_rect.y + 10))
        self.eyes_rect = eyes_rect
        self.pattern_rects = pattern_rects

        next_rect = pygame.Rect(WIN_W//2 - 100, WIN_H - 70, 200, 45)
        self.controls_next_rect = next_rect
        hover = next_rect.collidepoint(*pygame.mouse.get_pos())
        btn_color = (100,50,150) if hover else (60,30,100)
        self.draw_rounded_rect(screen, btn_color, next_rect, radius=6)
        next_text = fmd.render("Next: View Rules", True, WHITE)
        screen.blit(next_text, (next_rect.centerx - next_text.get_width()//2, next_rect.centery - next_text.get_height()//2))

    def _draw_rules(self, screen, fmd, flg):
        self.draw_gradient_background(screen)
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
            ("Standard pie: +10 HP", GOLD, "circle"),
            ("Golden pie: +25 HP", (255,230,80), "circle"),
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
            ("Speed (cyan): Moves twice as fast for 5 seconds", NEON_CYAN, "rect"),
            ("Shield (blue): Protects from one collision (no HP loss)", (80,150,255), "rect"),
            ("Growth (orange): Instantly adds 3 segments to your snake", (255,120,50), "rect")
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
        btn_color = (100,50,150) if hover else (60,30,100)
        self.draw_rounded_rect(screen, btn_color, btn_rect, radius=6)
        btn_text = fmd.render("I Understand", True, WHITE)
        screen.blit(btn_text, (btn_rect.centerx - btn_text.get_width()//2, btn_rect.centery - btn_text.get_height()//2))
        return btn_rect

    def _draw_lobby(self, screen, fmd, flg):
        self.draw_gradient_background(screen)
        title = flg.render("Πthon Arena - Lobby", True, GOLD)
        screen.blit(title, (WIN_W//2 - title.get_width()//2, 100))
        y = 180
        head = fmd.render("Online Players (click to challenge):", True, WHITE)
        screen.blit(head, (WIN_W//2 - head.get_width()//2, y))
        y += 40
        for p in self.online:
            color = NEON_CYAN if p == self.username else WHITE
            txt = fmd.render(f"{'★ ' if p == self.username else '  '}{p}", True, color)
            screen.blit(txt, (WIN_W//2 - txt.get_width()//2, y))
            y += 30
        if len(self.online) <= 1:
            wait = fmd.render("Waiting for other players...", True, GREY)
            screen.blit(wait, (WIN_W//2 - wait.get_width()//2, y+20))

        exit_rect = pygame.Rect(WIN_W - 120, 20, 100, 40)
        hover = exit_rect.collidepoint(*pygame.mouse.get_pos())
        btn_color = (150,40,40) if hover else (100,20,20)
        self.draw_rounded_rect(screen, btn_color, exit_rect, radius=6)
        exit_text = fmd.render("Exit Game", True, WHITE)
        screen.blit(exit_text, (exit_rect.centerx - exit_text.get_width()//2, exit_rect.centery - exit_text.get_height()//2))
        self.exit_rect = exit_rect

    def _draw_snake_segment(self, screen, x, y, color, is_head, segment_index, direction=None):
        rect = pygame.Rect(x*CELL+1, y*CELL+1, CELL-2, CELL-2)
        if is_head:
            for i in range(rect.height):
                blend = i / rect.height
                r = int(color[0] * (1-blend) + min(color[0]+80,255) * blend)
                g = int(color[1] * (1-blend) + min(color[1]+80,255) * blend)
                b = int(color[2] * (1-blend) + min(color[2]+80,255) * blend)
                pygame.draw.line(screen, (r,g,b), (rect.x, rect.y+i), (rect.x+rect.width, rect.y+i))
        else:
            pygame.draw.rect(screen, color, rect, border_radius=4)

        if self.pattern == "striped" and segment_index % 2 == 0:
            stripe_rect = pygame.Rect(x*CELL+1, y*CELL+1 + CELL//3, CELL-2, CELL//3)
            lighter = (min(color[0]+60,255), min(color[1]+60,255), min(color[2]+60,255))
            pygame.draw.rect(screen, lighter, stripe_rect)
        elif self.pattern == "dotted" and (segment_index % 2 == 0):
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
            pygame.draw.circle(screen, WHITE, left_eye, 4)
            pygame.draw.circle(screen, WHITE, right_eye, 4)
            pygame.draw.circle(screen, BLACK, left_eye, 2)
            pygame.draw.circle(screen, BLACK, right_eye, 2)

    def draw_sound_toggle_button(self, screen):
        hover = self.sound_toggle_rect.collidepoint(pygame.mouse.get_pos())
        bg_color = (60,40,100) if hover else (30,20,60)
        self.draw_rounded_rect(screen, bg_color, self.sound_toggle_rect, radius=12)
        self.draw_rounded_rect(screen, NEON_CYAN, self.sound_toggle_rect, radius=12, border=2, border_color=NEON_CYAN)
        icon = "🔊" if self.sound_enabled else "🔇"
        font = pygame.font.SysFont("segoeuiemoji", 28)
        icon_surf = font.render(icon, True, WHITE)
        icon_rect = icon_surf.get_rect(center=self.sound_toggle_rect.center)
        screen.blit(icon_surf, icon_rect)

    def _draw_game(self, screen, fsm, fmd, flg, chat_input):
        gs = self.game_state
        # Grid
        for gx in range(0, GRID_W*CELL, CELL):
            pygame.draw.line(screen, (40,30,60), (gx,0), (gx,GRID_H*CELL))
        for gy in range(0, GRID_H*CELL, CELL):
            pygame.draw.line(screen, (40,30,60), (0,gy), (GRID_W*CELL,gy))

        # Obstacles
        for obs in gs.get("obstacles", []):
            r = pygame.Rect(obs[0]*CELL+1, obs[1]*CELL+1, CELL-2, CELL-2)
            pygame.draw.rect(screen, (80,50,40), r)
            pygame.draw.rect(screen, (140,90,60), r, 2)

        # Pies (pulsing)
        pulse = abs(math.sin(self.food_pulse * 0.01)) * 0.3 + 0.7
        for pie in gs.get("pies", []):
            px,py = pie["pos"]
            col = PIE_COLOR.get(pie.get("type","standard"), GOLD)
            cx = px*CELL + CELL//2
            cy = py*CELL + CELL//2
            radius = int((CELL//2-2) * pulse)
            pygame.draw.circle(screen, col, (cx,cy), radius)
            pygame.draw.circle(screen, WHITE, (cx,cy), max(2, radius//3))

        # Powerups
        for pu in gs.get("powerups", []):
            px,py = pu["pos"]
            col = POWERUP_COLOR.get(pu["type"], NEON_CYAN)
            cx = px*CELL + CELL//2
            cy = py*CELL + CELL//2
            glow = pygame.Surface((CELL, CELL), pygame.SRCALPHA)
            pygame.draw.rect(glow, (*col, 100), (0,0,CELL,CELL), border_radius=8)
            screen.blit(glow, (px*CELL, py*CELL))
            pygame.draw.rect(screen, col, (px*CELL+4, py*CELL+4, CELL-8, CELL-8), border_radius=4)

        # Snakes
        snakes = gs.get("snakes", {})
        for uname, snake in snakes.items():
            body = snake.get("body", [])
            alive = snake.get("alive", True)
            color_name = snake.get("color", "cyan")
            base_color, head_color = SNAKE_COLOR_OPTIONS.get(color_name, SNAKE_COLOR_OPTIONS["cyan"])
            if not alive:
                base_color = (80,80,100)
                head_color = (60,60,80)
            head_dir = snake.get("dir", "UP")
            for idx, cell in enumerate(body):
                is_head = (idx == 0)
                col_to_use = head_color if is_head else base_color
                self._draw_snake_segment(screen, cell[0], cell[1], col_to_use, is_head, idx, head_dir if is_head else None)
            if snake.get("shield", 0) > 0:
                head = body[0]
                cx = head[0]*CELL + CELL//2
                cy = head[1]*CELL + CELL//2
                pygame.draw.circle(screen, (80,150,255), (cx,cy), CELL//2, 2)
            if snake.get("speed_boost", 0) > 0:
                head = body[0]
                cx = head[0]*CELL + CELL//2
                cy = head[1]*CELL + CELL//2
                pygame.draw.circle(screen, NEON_CYAN, (cx,cy), CELL//2-2, 2)

        # Sidebar
        sx = GRID_W * CELL
        pygame.draw.rect(screen, DARK_BG, pygame.Rect(sx,0,SIDEBAR_W,WIN_H))
        pygame.draw.line(screen, GOLD, (sx,0), (sx,WIN_H), 2)

        y = 10
        title = fmd.render("Πthon Arena", True, GOLD)
        screen.blit(title, (sx+10, y)); y+=30
        tl = gs.get("time_left", 0)
        time_col = NEON_PINK if tl<15 else GOLD if tl<30 else WHITE
        tlabel = fsm.render(f"Time: {tl}s", True, time_col)
        screen.blit(tlabel, (sx+10, y)); y+=24

        for uname, snake in snakes.items():
            health = max(0, snake.get("health", 0))
            is_me = uname == self.username
            col = SNAKE_COLOR_OPTIONS.get(snake.get("color","cyan"), SNAKE_COLOR_OPTIONS["cyan"])[0]
            name_t = fsm.render(("▶ " if is_me else "  ") + uname, True, col)
            screen.blit(name_t, (sx+10, y)); y+=18
            bar_w = int((SIDEBAR_W-20) * health / 100)
            pygame.draw.rect(screen, DGREY, pygame.Rect(sx+10, y, SIDEBAR_W-20, 14))
            for i in range(bar_w):
                ratio = i / (SIDEBAR_W-20)
                grad_col = (int(0 + 255*ratio), int(100 + 100*ratio), int(255 - 100*ratio))
                pygame.draw.line(screen, grad_col, (sx+10+i, y), (sx+10+i, y+14))
            hp_t = fsm.render(f"HP: {health}", True, WHITE)
            screen.blit(hp_t, (sx+10, y)); y+=20
        y+=10
        role_display = "PLAYER" if self.username in snakes else "FAN"
        rb = fsm.render(f"[{role_display}]", True, NEON_CYAN)
        screen.blit(rb, (sx+10, y)); y+=22

        if self.countdown:
            ct = flg.render(str(self.countdown), True, GOLD)
            screen.blit(ct, (WIN_W//2 - ct.get_width()//2, WIN_H//2 - ct.get_height()//2))

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
                lt = fmd.render(f"Loser: {loser}", True, NEON_PINK)
                screen.blit(lt, (WIN_W//2 - lt.get_width()//2, WIN_H//2 - 45))
            reason = go.get("reason")
            if reason == "health_zero":
                rt = fsm.render("Match ended immediately: health reached 0", True, WHITE)
                screen.blit(rt, (WIN_W//2 - rt.get_width()//2, WIN_H//2 - 12))
            for i, (uname, hp) in enumerate(scores.items()):
                st = fmd.render(f"{uname}: {hp} HP", True, WHITE)
                screen.blit(st, (WIN_W//2 - st.get_width()//2, WIN_H//2 + 22 + i*28))

        # Chat area
        chat_y_start = WIN_H - 230
        chat_area_height = 180
        line_height = 18
        max_visible = chat_area_height // line_height

        with self.msg_lock:
            total = len(self.messages)
            max_scroll = max(0, total - max_visible)
            if self.chat_scroll < 0:
                self.chat_scroll = 0
            if self.chat_scroll > max_scroll:
                self.chat_scroll = max_scroll
            start_idx = total - max_visible - self.chat_scroll
            if start_idx < 0:
                start_idx = 0
            end_idx = start_idx + max_visible
            if end_idx > total:
                end_idx = total
            visible_msgs = self.messages[start_idx:end_idx]

        pygame.draw.rect(screen, (20,20,40), (sx+5, chat_y_start-5, SIDEBAR_W-10, chat_area_height+5))
        pygame.draw.rect(screen, GREY, (sx+5, chat_y_start-5, SIDEBAR_W-10, chat_area_height+5), 1)

        for i, (msg_text, _) in enumerate(visible_msgs):
            if len(msg_text) > 35:
                msg_text = msg_text[:32] + "..."
            mt = fsm.render(msg_text, True, (220,220,200))
            screen.blit(mt, (sx+10, chat_y_start + i*line_height))

        if max_scroll > 0:
            scroll_text = fsm.render(f"scroll {self.chat_scroll}/{max_scroll}", True, GREY)
            screen.blit(scroll_text, (sx+10, chat_y_start + chat_area_height - line_height))

        chat_box = pygame.Rect(sx+5, WIN_H-32, SIDEBAR_W-10, 28)
        self.draw_rounded_rect(screen, DGREY, chat_box, radius=6)
        pygame.draw.rect(screen, NEON_CYAN, chat_box, 1, border_radius=6)
        ct2 = fsm.render(chat_input[-35:] + "_", True, WHITE)
        screen.blit(ct2, (sx+8, WIN_H-30))

        self.draw_sound_toggle_button(screen)
        self.food_pulse += 1

    def _draw_popup(self, screen, text, font):
        s = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        s.fill((0,0,0,180))
        screen.blit(s, (0,0))
        box = pygame.Rect(WIN_W//2 - 200, WIN_H//2 - 80, 400, 160)
        self.draw_rounded_rect(screen, (40,30,70), box, radius=12)
        pygame.draw.rect(screen, GOLD, box, 3, border_radius=12)
        label = font.render(text, True, WHITE)
        screen.blit(label, (box.centerx - label.get_width()//2, box.y + 30))
        yes_rect = pygame.Rect(box.x + 50, box.y + 90, 120, 40)
        no_rect = pygame.Rect(box.x + 230, box.y + 90, 120, 40)
        self.draw_rounded_rect(screen, (100,50,150), yes_rect, radius=6)
        self.draw_rounded_rect(screen, (150,40,40), no_rect, radius=6)
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
        self.draw_rounded_rect(screen, (40,30,70), box, radius=12)
        pygame.draw.rect(screen, GOLD, box, 3, border_radius=12)
        label = font.render("Match finished", True, WHITE)
        screen.blit(label, (box.centerx - label.get_width()//2, box.y + 25))
        sub = pygame.font.SysFont("monospace", 14).render("What would you like to do?", True, GREY)
        screen.blit(sub, (box.centerx - sub.get_width()//2, box.y + 55))
        watch_rect = pygame.Rect(box.x + 40, box.y + 95, 140, 40)
        lobby_rect = pygame.Rect(box.x + 220, box.y + 95, 140, 40)
        self.draw_rounded_rect(screen, (80,150,255), watch_rect, radius=6)
        self.draw_rounded_rect(screen, (100,50,150), lobby_rect, radius=6)
        watch_text = font.render("Watch again", True, WHITE)
        lobby_text = font.render("Back to lobby", True, WHITE)
        screen.blit(watch_text, (watch_rect.centerx - watch_text.get_width()//2, watch_rect.centery - watch_text.get_height()//2))
        screen.blit(lobby_text, (lobby_rect.centerx - lobby_text.get_width()//2, lobby_rect.centery - lobby_text.get_height()//2))
        return watch_rect, lobby_rect

    # ------------------------------------------------------------------
    # Main loop (with sound toggle click)
    # ------------------------------------------------------------------
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

                # Sound toggle click (only in game)
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if self.phase == "game" and self.sound_toggle_rect.collidepoint(mx, my):
                        self.toggle_sound()
                        continue

                if self.remap_waiting and event.type == pygame.KEYDOWN and self.remap_action:
                    if event.key not in self.key_map[self.remap_action]:
                        self.key_map[self.remap_action].append(event.key)
                    self.remap_waiting = False
                    self.remap_action = None
                    continue

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
                        if btn_rect.collidepoint(mx,my):
                            self.snake_color = color_names[color_index]
                            self.phase = "controls"
                            error_msg = ""
                        elif color_btn_rect.collidepoint(mx,my):
                            color_index = (color_index + 1) % len(color_names)
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
                    if event.type == pygame.MOUSEBUTTONDOWN and hasattr(self, 'exit_rect') and self.exit_rect.collidepoint(mx, my):
                        if self.sock:
                            try:
                                self.sock.close()
                            except:
                                pass
                        running = False
                        break
                    if event.type == pygame.MOUSEBUTTONDOWN:
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
                        elif lobby_rect.collidepoint(mx, my):
                            self.phase = "lobby"
                    if self.game_state.get("status") == "countdown":
                        self.phase = "game"
                        self._play_sound('game_start')
                        if self.sound_enabled:
                            self._start_bg_music()
                    elif self.game_state.get("status") == "waiting":
                        self.phase = "lobby"

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

            # Drawing
            if self.phase in ("connect", "color", "controls", "rules", "lobby", "challenge_popup", "rematch_popup", "fan_rematch_popup"):
                self.draw_gradient_background(screen)
            else:
                screen.fill(BLACK)

            if self.phase == "connect":
                self._draw_connect(screen, font_sm, font_md, font_lg, ip_text, port_text, user_text, active, error_msg, ip_rect, port_rect, user_rect, btn_rect, color_btn_rect, color_names[color_index])
            elif self.phase == "color":
                self._draw_color(screen, font_md, font_lg, btn_rect, color_btn_rect, color_names, color_index, error_msg)
            elif self.phase == "controls":
                self._draw_controls(screen, font_md, font_lg, btn_rect)
            elif self.phase == "rules":
                self._draw_rules(screen, font_md, font_lg)
            elif self.phase == "lobby":
                self._draw_lobby(screen, font_md, font_lg)
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