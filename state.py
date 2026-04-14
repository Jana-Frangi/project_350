import json
import random

from .logging_utils import log_message
from .player import Player


class State:
    DIRECTION_MAP = {
        "w": [-1, 0],
        "a": [0, -1],
        "s": [1, 0],
        "d": [0, 1],
        "": [0, 0]
    }

    def __init__(self):
        self.dimensions = [30, 80]
        self.food_pos = self.get_random_position()
        self.players = {}

    # Logs a message
    def log_message(self, type, message):
        log_message(type, "State", message)

    # Converts the object to a JSON string so it can be sent to the client
    def to_json(self):
        return json.dumps({
            "dimensions": self.dimensions,
            "food_pos": self.food_pos,
            "players": {username: player.to_dict() for username, player in self.players.items()}
        })

    # Gets a random position
    def get_random_position(self, buffer=0):
        return [
            random.randint(1 + buffer, self.dimensions[0] - 2 - buffer),
            random.randint(1 + buffer, self.dimensions[1] - 2 - buffer)
        ]

    # Appends a number until the username is unique
    def get_unique_username(self, username):
        suffix, counter = "", 1
        while username + suffix in self.players:
            suffix = str(counter)
            counter += 1

        self.log_message("INFO", f"Unique username: {username + suffix}")
        return username + suffix

    # Adds a new player to the map
    def add_player(self, username):
        self.log_message("INFO", f"Player {username}: Adding to list of players in game")

        start_segment = [self.get_random_position(buffer=5)]
        start_direction = [0, 0]
        colour_pair_id = random.randint(1, 7)

        player = Player(start_segment, start_direction, colour_pair_id)
        self.players[username] = player

        self.log_message("DEBUG", f"List of players: {[username for username in self.players]}")

    # Removes a player from the map
    def remove_player(self, username):
        if username in self.players:
            self.log_message("INFO", f"Player {username}: Removing from list of players in game")
            self.players.pop(username)
            self.log_message("DEBUG", f"List of players: {[username for username in self.players]}")

    # Gets the segments from all the snakes
    def get_occupied_positions(self):
        occupied_positions = []

        for player in self.players.values():
            occupied_positions.extend(player.segments)

        return occupied_positions

    # Regenerates the food if a snake ate it
    def regenerate_food(self, eater, occupied_positions):
        self.log_message("INFO", f"Player {eater}: Ate food")

        self.food_pos = self.get_random_position()
        while self.food_pos in occupied_positions:
            self.food_pos = self.get_random_position()

        self.players[eater].score += 1

    # Moves all snakes one step
    def update_state(self):
        eliminated_players = []
        occupied_positions = self.get_occupied_positions()
        eater = None

        for username, player in self.players.items():
            # Do not move until the player presses a key
            if player.direction == [0, 0]:
                continue

            # Add the new head
            player.add_new_head()

            # Update whether he survived the move
            if not player.check_is_alive(occupied_positions, self.dimensions):
                self.log_message("INFO", f"Player {username}: Has died")
                eliminated_players.append(username)
                continue

            # Check if he ate food
            if player.get_head() != self.food_pos:
                player.pop_tail()
            else:
                eater = username

        # Player got the food
        if eater is not None:
            self.regenerate_food(eater, occupied_positions)
            self.sort_leaderboard()

        for username in eliminated_players:
            self.remove_player(username)

    # Sorts the players based on score
    def sort_leaderboard(self):
        self.players = dict(sorted(self.players.items(), key=lambda player: player[1].score, reverse=True))

    # Updates the player's direction to match their keypress
    def update_player_direction(self, username, key):
        if username in self.players and key in State.DIRECTION_MAP:
            player = self.players[username]

            new_dir = State.DIRECTION_MAP[key]
            if player.direction == [0, 0] or not self.is_opposite_direction(new_dir, player.direction):
                player.direction = new_dir
                self.log_message("INFO", f"Player {username}: Direction updated to {key}")

    # Checks if two directions are opposites
    def is_opposite_direction(self, dir1, dir2):
        return [dir1[0] + dir2[0], dir1[1] + dir2[1]] == [0, 0]