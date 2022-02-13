import combat
from unit import *
from combat import *
from map import Map
from item import Item
from player import Player, RandomPlayer
from map_factory import OutdoorMapFactory

# Games will go up to not including TURN_LIMIT turns
# (A turn is defined as one side moving all their units)
TURN_LIMIT = 101


class FireEmblem:
    def __init__(self, tile_map: Map, blue_team: list, red_team: list, blue_player: Player, red_player: Player):
        self.map = tile_map
        self.blue_team = blue_team
        self.red_team = red_team
        self.blue_player = blue_player
        self.red_player = red_player

        self.turn_count = 0
        self.blue_victory = False
        self.red_victory = False

        # Current unit is an index to the unit lists, not a unit object.
        self.current_unit = 0
        self.current_phase = 'Blue'

    def step(self):
        if self.current_phase == 'Blue':
            self.__blue_phase()
            self.current_unit += 1

            if self.current_unit >= len(self.blue_team):
                self.current_phase = 'Red'
                self.current_unit = 0

        elif self.current_phase == 'Red':
            self.__red_phase()
            self.current_unit += 1

            if self.current_unit >= len(self.red_team):
                self.current_phase = 'Blue'
                self.current_unit = 0
                self.turn_count += 1

        if self.turn_count == TURN_LIMIT:
            self.red_victory = True

        if self.blue_victory:
            return 1
        if self.red_victory:
            return -1

        return 0

    def __blue_phase(self):
        unit = self.blue_team[self.current_unit]
        new_coords = self.blue_player.determine_move_coordinates(self.blue_team, self.red_team, self.map, unit)
        unit.goto(new_coords[0], new_coords[1])

        action_choice = self.blue_player.determine_action(self.red_team, self.map, unit, unit.x, unit.y)
        print(f"{unit.name} moved to coordinates {unit.x}, {unit.y} and chose {action_choice.name}")

        if action_choice.is_attack():
            # Defender in this case is from self.enemies
            defender = action_choice.action_item
            combat_stats = combat.get_combat_stats(unit, defender, self.map)
            result = combat.simulate_combat(combat_stats)
            print(f"\t {result.name}")

            if result is CombatResults.DEFENDER_DEATH:
                self.red_team.remove(defender)
                if not self.red_team:
                    self.blue_victory = True

            elif result is CombatResults.ATTACKER_DEATH:
                if unit.terminal_condition:
                    self.red_victory = True
                self.blue_team.remove(unit)

        elif action_choice.is_item():
            item_to_use = action_choice.action_item
            heal_amount = item_to_use.info['heal_amount']
            unit.heal(heal_amount)
            item_to_use.info['uses'] -= 1
            if item_to_use.info['uses'] == 0:
                unit.inventory.remove(item_to_use)

    def __red_phase(self):
        unit = self.red_team[self.current_unit]
        new_coords = self.red_player.determine_move_coordinates(self.red_team, self.blue_team, self.map, unit)
        unit.goto(new_coords[0], new_coords[1])

        action_choice = self.red_player.determine_action(self.blue_team, self.map, unit, unit.x, unit.y)
        print(f"{unit.name} moved to coordinates {unit.x}, {unit.y} and chose {action_choice.name}")

        if action_choice.is_attack():
            # Defender in this case is from self.enemies
            defender = action_choice.action_item
            combat_stats = combat.get_combat_stats(unit, defender, self.map)
            result = combat.simulate_combat(combat_stats)
            print(f"\t {result.name}")

            if result is CombatResults.DEFENDER_DEATH:
                if unit.terminal_condition:
                    self.red_victory = True
                self.blue_team.remove(defender)

            elif result is CombatResults.ATTACKER_DEATH:
                self.red_team.remove(unit)
                if not self.red_team:
                    self.blue_victory = True

        elif action_choice.is_item():
            item_to_use = action_choice.action_item
            heal_amount = item_to_use.info['heal_amount']
            unit.heal(heal_amount)
            item_to_use.info['uses'] -= 1
            if item_to_use.info['uses'] == 0:
                unit.inventory.remove(item_to_use)


if __name__ == "__main__":
    map_factory = OutdoorMapFactory(10, 15, 10, 15)
    tile_map,number_tile_map = map_factory.generate_map()

    lyn = Unit(0xceb4, 0, 0, 2, 0x0204, 17, 6, 8, 10, 6, 2, 0, 0, True, [0x1, 0x6b], True)
    bandit = Unit(0xe9b8, 0, 1, 2, 0x1410, 21, 4, 1, 4, 0, 3, 0, 0, False, [0x1f], False)

    allies = [lyn]
    enemies = [bandit]

    result = 0

    game = FireEmblem(tile_map, allies, enemies, RandomPlayer(), RandomPlayer())
    while result == 0:
        print(f'TURN {game.turn_count}')
        result = game.step()

    print(f"Here's the result of the game: {result}")
