"""
Πthon Arena - Server (Final with Proper Rematch Handling)
Run: python server.py <port>
"""

import socket
import threading
import json
import random
import time
import sys

GRID_W, GRID_H = 30, 30
TICK_RATE = 0.15
GAME_DURATION = 120
INITIAL_HEALTH = 100
MAX_HEALTH = 100

PIE_TYPES = [
    {"type": "standard", "value": 10, "color": "yellow"},
    {"type": "golden",   "value": 25, "color": "gold"},
    {"type": "poison",   "value": -15, "color": "purple"},
]
MAX_PIES = 5
POWERUP_TYPES = [
    {"type": "speed",   "effect": "speed_boost", "duration": 5, "color": "cyan"},
    {"type": "shield",  "effect": "shield",      "duration": 8, "color": "blue"},
    {"type": "growth",  "effect": "instant_grow","duration": 0, "color": "orange"},
]
MAX_POWERUPS = 2

# Walls
WALLS = []
for x in range(GRID_W):
    WALLS.append([x, 0])
    WALLS.append([x, GRID_H-1])
for y in range(1, GRID_H-1):
    WALLS.append([0, y])
    WALLS.append([GRID_W-1, y])

OBSTACLES = WALLS + [
    [5,5], [5,6], [6,5],
    [15,10], [15,11],
    [20,20], [21,20], [20,21],
    [10,25], [11,25],
]

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

class IthonArenaServer:
    def __init__(self, port):
        self.port = port
        self.lock = threading.RLock()
        self.players = {}
        self.fans = set()
        self.game_state = {
            "snakes": {}, "pies": [], "powerups": [],
            "obstacles": OBSTACLES,
            "status": "waiting", "winner": None, "time_left": GAME_DURATION,
        }
        self.game_started = False
        self.game_thread = None
        self.current_players = []
        self.rematch_votes = set()
        self.rematch_timer = None

    def start(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(('0.0.0.0', self.port))
        srv.listen(10)
        print(f"[SERVER] Listening on port {self.port}")
        while True:
            conn, addr = srv.accept()
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            threading.Thread(target=self.handle_client, args=(conn, addr), daemon=True).start()

    def handle_client(self, conn, addr):
        username = None
        try:
            reader = LineReader(conn)
            raw_line = reader.readline()
            raw = raw_line.decode().strip() if raw_line else ''
            if not raw:
                conn.close()
                return
            parts = raw.split('|')
            if len(parts) >= 3:
                username, p2p_port, color = parts[0], int(parts[1]), parts[2]
            else:
                username, p2p_port, color = raw, None, "green"

            with self.lock:
                if username in self.players:
                    self._send(conn, {"type": "auth", "status": "fail", "reason": "Username taken"})
                    conn.close()
                    return
                self.players[username] = {"conn": conn, "p2p_port": p2p_port, "ip": addr[0], "color": color}
                self.fans.add(username)
                self._send(conn, {"type": "auth", "status": "ok", "role": "fan", "online": list(self.players.keys())})
            self._broadcast_lobby()
            while True:
                msg = reader.read_json()
                if not msg:
                    break
                self._handle_message(username, msg)
        except Exception as e:
            print(f"Error: {e}")
        finally:
            if username:
                with self.lock:
                    self.players.pop(username, None)
                    self.fans.discard(username)
                    if username in self.current_players:
                        self.current_players.remove(username)
                        if len(self.current_players) < 2 and self.game_state["status"] == "running":
                            self._finish_game(None, reason="player left")
                self._broadcast_lobby()
            conn.close()

    def _handle_message(self, username, msg):
        mtype = msg.get("type")
        if mtype == "move" and username in self.current_players:
            direction = msg.get("dir")
            if direction in ("UP","DOWN","LEFT","RIGHT"):
                with self.lock:
                    snake = self.game_state["snakes"].get(username)
                    if snake and snake["alive"]:
                        opposites = {"UP":"DOWN","DOWN":"UP","LEFT":"RIGHT","RIGHT":"LEFT"}
                        if direction != opposites.get(snake["dir"]):
                            snake["dir"] = direction
        elif mtype == "chat":
            text = msg.get("text", "")[:200]
            self._broadcast_all({"type": "chat", "from": username, "text": text})
        elif mtype == "get_lobby":
            self._send(self.players[username]["conn"], {"type": "lobby", "online": list(self.players.keys())})
        elif mtype == "challenge":
            target = msg.get("target")
            if target in self.players and target != username:
                self._send(self.players[target]["conn"], {"type": "challenge", "from": username})
        elif mtype == "challenge_response":
            target = msg.get("target")
            accept = msg.get("accept", False)
            if accept:
                with self.lock:
                    if self.game_state["status"] != "waiting":
                        self._send(self.players[username]["conn"], {"type": "error", "text": "Game already in progress"})
                        return
                    self.current_players = [username, target]
                    self.fans.discard(username)
                    self.fans.discard(target)
                    self._init_snake(username, self.players[username]["color"])
                    self._init_snake(target, self.players[target]["color"])
                    self.game_state["snakes"] = {u: self.game_state["snakes"][u] for u in self.current_players}
                self._broadcast_lobby()
                self._start_match()
        elif mtype == "rematch":
            with self.lock:
                if username not in self.current_players:
                    return
                self.rematch_votes.add(username)
                # Notify the other player that this player wants rematch
                other = self.current_players[0] if self.current_players[1] == username else self.current_players[1]
                self._send(self.players[other]["conn"], {"type": "rematch_request"})
                if len(self.rematch_votes) == 2:
                    # Both want rematch
                    if self.rematch_timer:
                        self.rematch_timer.cancel()
                    self._reset_game(keep_players=True)
                    self._broadcast_state()
                    self._broadcast_lobby()
                    self._start_match()
        elif mtype == "decline_rematch":
            with self.lock:
                # One player declines -> reset game and put both players back into fans
                self._reset_game(keep_players=False)
                self._broadcast_state()
                self._broadcast_lobby()
                # Notify both players (already via state and lobby)

    def _start_match(self):
        with self.lock:
            self.game_state["status"] = "countdown"
            self.game_state["winner"] = None
            self.game_state["time_left"] = GAME_DURATION
            p1, p2 = self.current_players[0], self.current_players[1]
            p1_ip = self.players[p1]["ip"]
            p1_port = self.players[p1]["p2p_port"]
            p2_ip = self.players[p2]["ip"]
            p2_port = self.players[p2]["p2p_port"]
            self._send(self.players[p1]["conn"], {"type": "peer_info", "peer_ip": p2_ip, "peer_port": p2_port})
            self._send(self.players[p2]["conn"], {"type": "peer_info", "peer_ip": p1_ip, "peer_port": p1_port})
        self._broadcast_state()
        self.game_thread = threading.Thread(target=self._game_loop, daemon=True)
        self.game_thread.start()

    def _game_loop(self):
        for i in range(3,0,-1):
            self._broadcast_all({"type": "countdown", "value": i})
            time.sleep(1)
        with self.lock:
            if self.game_state["status"] != "countdown":
                return
            self.game_state["status"] = "running"
            self.game_state["pies"].clear()
            self.game_state["powerups"].clear()
            for _ in range(MAX_PIES):
                self._spawn_pie()
            for _ in range(MAX_POWERUPS):
                self._spawn_powerup()
        deadline = time.time() + GAME_DURATION
        last_tick = time.time()
        while True:
            time.sleep(0.05)
            now = time.time()
            if now - last_tick >= TICK_RATE:
                last_tick = now
                with self.lock:
                    if self.game_state["status"] != "running":
                        break
                    self.game_state["time_left"] = max(0, int(deadline - now))
                    self._tick()
                    if self.game_state["status"] == "finished":
                        self._broadcast_state()
                        break
                    if self.game_state["time_left"] <= 0:
                        self._end_game_by_time()
                        self._broadcast_state()
                        break
                self._broadcast_state()
        self._broadcast_state()
        # After game ends, we do NOT auto-reset. Clients will decide rematch.
        # Reset rematch votes for next time
        with self.lock:
            self.rematch_votes.clear()

    def _tick(self):
        dirs = {"UP":(0,-1),"DOWN":(0,1),"LEFT":(-1,0),"RIGHT":(1,0)}
        for snake in self.game_state["snakes"].values():
            if snake["shield"] > 0:
                snake["shield"] -= TICK_RATE
            if snake["speed_boost"] > 0:
                snake["speed_boost"] -= TICK_RATE
        # Collect powerups
        for pu in self.game_state["powerups"][:]:
            for snake in self.game_state["snakes"].values():
                if not snake["alive"]:
                    continue
                if snake["body"][0] == pu["pos"]:
                    if pu["type"] == "speed":
                        snake["speed_boost"] = pu["duration"]
                    elif pu["type"] == "shield":
                        snake["shield"] = pu["duration"]
                    elif pu["type"] == "growth":
                        tail = snake["body"][-1]
                        for _ in range(3):
                            snake["body"].append(tail)
                    self.game_state["powerups"].remove(pu)
                    self._spawn_powerup()
                    break
        # Move snakes
        for username, snake in list(self.game_state["snakes"].items()):
            if not snake["alive"]:
                continue
            speed = 2 if snake["speed_boost"] > 0 else 1
            for _ in range(speed):
                dx, dy = dirs[snake["dir"]]
                head = snake["body"][0]
                new_head = [head[0]+dx, head[1]+dy]
                # Collision with walls/obstacles
                if new_head in OBSTACLES:
                    if snake["shield"] <= 0:
                        snake["health"] = max(0, snake["health"] - 20)
                        if snake["health"] == 0:
                            snake["alive"] = False
                            self._check_game_over()
                        else:
                            self._reset_snake(username)
                    continue
                # Self collision
                if new_head in snake["body"][:-1]:
                    if snake["shield"] <= 0:
                        snake["health"] = max(0, snake["health"] - 10)
                        if snake["health"] == 0:
                            snake["alive"] = False
                            self._check_game_over()
                        else:
                            self._reset_snake(username)
                    continue
                # Other snake collision
                collided = False
                for oname, osnake in self.game_state["snakes"].items():
                    if oname == username or not osnake["alive"]:
                        continue
                    if new_head in osnake["body"]:
                        if snake["shield"] <= 0:
                            snake["health"] = max(0, snake["health"] - 30)
                            if snake["health"] == 0:
                                snake["alive"] = False
                                self._check_game_over()
                            else:
                                self._reset_snake(username)
                        collided = True
                        break
                if collided:
                    continue
                # Move
                snake["body"].insert(0, new_head)
                # Eat pie?
                ate = False
                for pie in self.game_state["pies"][:]:
                    if new_head == pie["pos"]:
                        new_health = snake["health"] + pie["value"]
                        snake["health"] = max(0, min(MAX_HEALTH, new_health))
                        self.game_state["pies"].remove(pie)
                        self._spawn_pie()
                        ate = True
                        break
                if not ate:
                    snake["body"].pop()
                if snake["health"] <= 0:
                    snake["alive"] = False
                    self._check_game_over()
                if speed == 2:
                    break

    def _reset_snake(self, username):
        while True:
            x = random.randint(3, GRID_W-4)
            y = random.randint(3, GRID_H-4)
            if [x,y] not in OBSTACLES:
                break
        self.game_state["snakes"][username]["body"] = [[x,y], [x,y+1], [x,y+2]]
        self.game_state["snakes"][username]["dir"] = "UP"

    def _check_game_over(self):
        alive = [u for u,s in self.game_state["snakes"].items() if s["alive"]]
        if len(alive) <= 1:
            winner = alive[0] if alive else None
            self._finish_game(winner, reason="A player reached 0 HP")

    def _end_game_by_time(self):
        snakes = self.game_state["snakes"]
        if not snakes:
            self._finish_game(None, reason="Time is over")
        else:
            winner = max(snakes, key=lambda u: snakes[u]["health"])
            self._finish_game(winner, reason="Time is over")

    def _finish_game(self, winner, reason="game_over"):
        if self.game_state["status"] == "finished":
            return
        self.game_state["status"] = "finished"
        self.game_state["winner"] = winner
        snakes = self.game_state["snakes"]
        scores = {u: s["health"] for u,s in snakes.items()}
        loser = next((u for u in snakes if u != winner), None) if winner else None
        self._broadcast_all({
            "type": "game_over",
            "winner": winner,
            "loser": loser,
            "scores": scores,
            "reason": "health_zero" if (winner and loser and scores.get(loser,1)<=0) else "time_up"
        })
        # No automatic rematch timer; clients will request rematch after a delay

    def _reset_game(self, keep_players=False):
        with self.lock:
            print("[GAME] Resetting...")
            self.game_started = False
            self.game_state["status"] = "waiting"
            self.game_state["winner"] = None
            self.game_state["pies"].clear()
            self.game_state["powerups"].clear()
            self.game_state["time_left"] = GAME_DURATION
            self.game_state["snakes"].clear()
            self.rematch_votes.clear()
            if not keep_players:
                for u in self.current_players:
                    self.fans.add(u)
                self.current_players.clear()
            else:
                for u in self.current_players:
                    self._init_snake(u, self.players[u]["color"])

    def _init_snake(self, username, color):
        taken = [cell for s in self.game_state["snakes"].values() for cell in s["body"]]
        while True:
            x = random.randint(3, GRID_W-4)
            y = random.randint(3, GRID_H-4)
            if [x,y] not in taken and [x,y] not in OBSTACLES:
                break
        self.game_state["snakes"][username] = {
            "body": [[x,y], [x,y+1], [x,y+2]],
            "health": INITIAL_HEALTH,
            "dir": "UP",
            "alive": True,
            "shield": 0,
            "speed_boost": 0,
            "color": color,
        }

    def _spawn_pie(self):
        for _ in range(50):
            x = random.randint(1, GRID_W-2)
            y = random.randint(1, GRID_H-2)
            pos = [x,y]
            if pos in OBSTACLES:
                continue
            if any(p["pos"] == pos for p in self.game_state["pies"]):
                continue
            if any(pos in s["body"] for s in self.game_state["snakes"].values()):
                continue
            if any(p["pos"] == pos for p in self.game_state["powerups"]):
                continue
            self.game_state["pies"].append({"pos": pos, **random.choice(PIE_TYPES)})
            return

    def _spawn_powerup(self):
        for _ in range(20):
            x = random.randint(1, GRID_W-2)
            y = random.randint(1, GRID_H-2)
            pos = [x,y]
            if pos in OBSTACLES:
                continue
            if any(p["pos"] == pos for p in self.game_state["pies"]):
                continue
            if any(pos in s["body"] for s in self.game_state["snakes"].values()):
                continue
            if any(p["pos"] == pos for p in self.game_state["powerups"]):
                continue
            pu = random.choice(POWERUP_TYPES)
            self.game_state["powerups"].append({"pos": pos, **pu, "remaining": pu["duration"]})
            return

    def _broadcast_state(self):
        self._broadcast_all({"type": "state", "data": self.game_state})

    def _broadcast_lobby(self):
        with self.lock:
            online = list(self.players.keys())
        self._broadcast_all({"type": "lobby", "online": online})

    def _broadcast_all(self, obj):
        payload = json.dumps(obj).encode() + b'\n'
        with self.lock:
            targets = [p["conn"] for p in self.players.values()]
        for conn in targets:
            try:
                conn.sendall(payload)
            except:
                pass

    @staticmethod
    def _send(conn, obj):
        try:
            conn.sendall(json.dumps(obj).encode() + b'\n')
        except:
            pass

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python server.py <port>")
        sys.exit(1)
    port = int(sys.argv[1])
    IthonArenaServer(port).start()