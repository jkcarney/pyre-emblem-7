import abc
import random
from abc import ABC
import os
import combat
import item
from item_type import *
import numpy as np
import numpy.ma as npma
import feutils
from feutils import FEAttackRangeError
from termcolor import colored


class Unit(ABC):
    """
    The base class for the Unit, used primarily as a data holder for the BlueUnit and RedUnit classes

    Unit primarily functions as a data holding class. There is not much/any functionality regarding actual
    learning; that is relegated to the BlueUnit class.
    """
    def __init__(self, character_code, x, y, level, job_code, hp_max,
                 strength, skill, spd, luck, defense, res, magic, ally,
                 inventory_codes: list, terminal_condition, run_name):
        self.terminal_condition = terminal_condition

        self.character_code = character_code
        self.x = x
        self.y = y
        self.level = level
        self.hp_max = hp_max
        self.current_hp = hp_max
        self.strength = strength
        self.magic = magic
        self.skill = skill
        self.speed = spd
        self.luck = luck
        self.defense = defense
        self.res = res

        self.inventory = item.construct_unit_inventory(inventory_codes)

        self.name = feutils.character_name_table(self.character_code)
        self.job = feutils.class_table(job_code)
        self.move = feutils.movement_table(self.job)
        self.terrain_group = feutils.job_terrain_group(self.job)

        if ally:
            self.con = feutils.character_constitution_table(self.name)
        else:
            self.con = feutils.job_constitution_table(self.job)

        self.run_name = run_name

    def __str__(self):
        return self.name

    def equip_item(self, index):
        self.inventory[0], self.inventory[index] = self.inventory[index], self.inventory[0]

    def get_attack_range(self):
        atk_range = set()

        for i in self.inventory:
            if i.item_type is ItemType.WEAPON or i.item_type is ItemType.TOME:
                item_ranges = list(map(int, i.info['range'].split(',')))
                for r in item_ranges:
                    atk_range.add(r)

        return sorted(list(atk_range))

    def has_consumable(self):
        for i in self.inventory:
            if i.item_type == ItemType.HEAL_CONSUMABLE:
                return True

        return False

    def get_all_consumables(self):
        consums = []
        for i in self.inventory:
            if i.item_type == ItemType.HEAL_CONSUMABLE:
                consums.append(i)

        return consums

    def goto(self, new_x, new_y):
        self.x, self.y = new_x, new_y

    def use_item(self, index):
        inventory_item = self.inventory[index]
        if inventory_item.item_type == ItemType.HEAL_CONSUMABLE:
            heal_total = self.heal(inventory_item.info['heal_amount'])
            inventory_item.info['uses'] -= 1

            if inventory_item.info['uses'] == 0:
                self.inventory.remove(inventory_item)

            return heal_total

        return None

    def heal(self, amount):
        heal_total = min(self.hp_max - self.current_hp, amount)

        self.current_hp += amount
        if self.current_hp > self.hp_max:
            self.current_hp = self.hp_max

        return heal_total

    def take_dmg(self, amount):
        if amount < 0:
            return
        self.current_hp -= amount

    @abc.abstractmethod
    def determine_action(self, state, env, ally_team, enemy_team):
        pass

    @abc.abstractmethod
    def determine_move(self, action, ally_team, enemy_team, env):
        pass

    @abc.abstractmethod
    def determine_target(self, env, enemy_team):
        pass

    @abc.abstractmethod
    def determine_item_to_use(self, env, enemy_team):
        pass

    @abc.abstractmethod
    def close(self, reward=None):
        pass


class RedUnit(Unit):
    """
    A class that represents the units that oppose the agent units (or blue units)

    These units are considered "dumb" in that they never learn anything.
    """
    def determine_action(self, state, env, ally_team, enemy_team):
        health_percent = self.current_hp / self.hp_max
        consumable_count = len(self.get_all_consumables())
        if health_percent <= 0.35 and consumable_count > 0:
            return 1

        action_mask = env.generate_action_mask(self, ally_team, enemy_team)
        if not action_mask[2]:  # If action_mask[2] is false, that means the unit can attack! So do it
            return 2

        return 0  #

    def determine_move(self, action, ally_team, enemy_team, env):
        valid_moves = env.generate_valid_moves(action, self, ally_team, enemy_team)
        choice = random.choice(valid_moves)
        return choice

    def determine_target(self, env, enemy_team):
        attackable_targets = feutils.attackable_units(self, enemy_team)
        if len(attackable_targets) == 0:
            raise FEAttackRangeError(f"No units were in attack range of {self.name} at coordinate {self.x},{self.y}")

        return random.choice(attackable_targets)

    def determine_item_to_use(self, env, enemy_team):
        usable_items = self.get_all_consumables()
        return random.randrange(len(usable_items))

    def close(self, reward=None):
        return False


class BlueUnit(Unit):
    """
    Class that represents the reinforcement learning agents.

    This class implements the abstract methods in the Unit class that allow for learning to take place.
    To find justifications for some algorithms here, see 'research/algorithms.md'
    """
    def __init__(self, character_code, x, y, level, job_code, hp_max, strength, skill, spd, luck, defense, res, magic,
                 ally, inventory_codes: list, terminal_condition, run_name):
        super().__init__(character_code, x, y, level, job_code, hp_max, strength, skill, spd, luck, defense, res, magic,
                         ally, inventory_codes, terminal_condition, run_name)

        self._version = "5"

        self.state_space = np.array([10, 10])
        self.action_space = np.array([3])

        # RL hyper-parameters
        self.alpha = 0.1    # Learning rate
        self.gamma = 0.6    # Discount rate (how important the next move is when calculating expected value) (0 underplanning, 1 overplanning)
        self.epsilon = 0.1  # Exploration rate; how often do we explore vs exploit
        self.td_lambda = 1  # Temporal difference count

        # Heuristic hyper-parameters
        self.tau = 0.9      # Used in combat heuristic: how much do we care about enemy combat stats vs our own?
        self.zeta = 0.3     # HP threshold for low HP; used in movement heuristic
        self.phi = 3        # Valuation constant for movement heuristic

        # Maintain a history of state-action pairs. We use this if the unit dies on the enemy turn
        self.state_action_history = []

        self.table_name = f'{self.name}_qtable_v{self._version}_{self.run_name}_{self.alpha}-{self.gamma}.npy'

        self.q_table = self.init_q_table()

    def init_q_table(self):
        """
        Either loads q-table on disk if it exists or creates a new one

        :return: a q-table (nd array that is 10x10x3)
        """
        if not os.path.exists(f'qtables/{self.table_name}'):
            return np.zeros(np.concatenate((self.state_space, self.action_space)))
        else:
            return np.load(f'qtables/{self.table_name}')

    def close(self, reward=None):
        """
        Saves the current state of the q-table to disk.
        Call this AFTER LEARNING!

        :return: True in all cases
        """
        if reward is not None:
            # Grab last state action if unit incurred negative reward for episode ending
            last_state_action = self.state_action_history[-1]
            dummy = 0
            current = self.q_table[last_state_action]

            new_value = current + self.alpha * (reward + (self.gamma * dummy) - current)
            self.q_table[last_state_action] = new_value

        np.save(f'qtables/{self.table_name}', self.q_table)
        return True

    def update_qtable(self, state, next_state, reward, action):
        """
        Updates q-table greedily using q-learning algorithm.
        Q(s,a) <- Q(s,a) + α[R + γ max(Q(s, a)) - Q(s,a)]

        :param next_state:
        :param state:
        :param reward:
        :param action:
        :return:
        """
        state_action = state + (action,)

        qmax = np.max(self.q_table[next_state])
        current = self.q_table[state_action]

        new_value = current + self.alpha * (reward + (self.gamma * qmax) - current)
        self.q_table[state_action] = new_value

    def determine_action(self, state, env, ally_team, enemy_team):
        """
        Given a state and the environment, determine what action should be taken.
        This will either be exploiting the learned Q-table value or exploration

        :param state: The state as a tuple of ints (ie, 5,6)
        :param env:  The environment object
        :param ally_team: A list of units allied to self
        :param enemy_team: A list of unit that are adversarial to self
        :return: 0, 1, or 2
            0 -> Wait
            1 -> Item
            2 -> Attack
        """

        # Mask invalid Q-Table entries (actions that cannot be taken given the state of the environment)
        # They will be masked as -inf and will not be selectable by get_random_unmasked_action or argmax
        action_mask = env.generate_action_mask(self, ally_team, enemy_team)
        state_action_space = npma.masked_array(self.q_table[state],
                                               fill_value=float('-inf'),
                                               mask=action_mask,
                                               copy=True)

        if np.random.uniform(0, 1) < self.epsilon:
            action = feutils.get_random_unmasked_action(state_action_space)  # Explore action space
            text = colored('(EXPLORE)', 'yellow')
            print(f'{self.name} chose {action} {text}')
        else:
            action = np.argmax(state_action_space)  # Exploit learned value
            text = colored('(EXPLOIT)', 'magenta')
            print(f'{self.name} chose {action} {text}')

        return action  # 0, 1, or 2

    def determine_move(self, action, ally_team, enemy_team, env):
        """
        Given an action that this unit wishes to take, determine the coordinate that this unit should move to that
        would maximize a heuristic.

        The coordinate generated by this function is guaranteed to be valid; the unit (self) is able to move to that
        coordinate and can do that action at that coordinate.

        :param action: The action the unit would take (0, 1, or 2)
        :param ally_team: The team allied to self
        :param enemy_team: The adversarial team to self
        :param env: The environment of the game
        :return: A tuple representing a x,y pair to move to on the grid.
        """
        valid_moves = env.generate_valid_moves(action, self, ally_team, enemy_team)
        if action == 2:
            return self.move_attack_heuristic(valid_moves, enemy_team, env)
        else:  # We can treat both 1 (Item) and 0 (Wait) pretty similarly heuristic-wise
            return self.move_wait_heuristic(valid_moves, enemy_team, ally_team, env)

    def move_wait_heuristic(self, valid_moves, enemy_units, ally_team, env):
        """
        Justification for this algorithm will be found in 'research/algorithms.md'
        :param valid_moves:
        :param enemy_units:
        :param ally_team:
        :param env:
        :return:
        """
        best_coords = self.x, self.y
        best_h = float('-inf')

        edc = feutils.get_closest_unit_manhattan(self.x, self.y, enemy_units)
        health = self.current_hp / self.hp_max

        for x, y in valid_moves:
            edxy = feutils.get_closest_unit_manhattan(x, y, enemy_units)
            tile = env.map.get_tile(x, y)
            dxy = tile.defense
            axy = tile.avoid
            h = ((edc - edxy) * (health - self.zeta)) + self.phi * dxy * axy
            if h > best_h:
                best_h = h
                best_coords = x, y

        return best_coords

    def move_attack_heuristic(self, valid_moves, enemy_units, env):
        """
        Determine which tile to move to, given that we want to attack.
        This is accomplished by simply finding the tile where the combat heuristic is maximized

        :param valid_moves:
        :param enemy_units:
        :param env:
        :return:
        """
        best_coords = self.x, self.y
        best_h = float('-inf')

        for x, y in valid_moves:
            attackables = feutils.get_attackable_units(self, enemy_units, x, y)
            for unit in attackables:
                h = self.combat_heuristic(unit, env)
                if h > best_h:
                    best_h = h
                    best_coords = x, y

        return best_coords

    def determine_target(self, env, enemy_team):
        """
        Determine which unit to attack in this unit's attack range.
        NOTE: when this method is called it is assumed the unit is already moved to the tile that they will attack from
        If they are at a tile where they can attack no enemy units, an FEAttackRangeError will be raised.

        :param env:
        :param enemy_team:
        :except FEAttackRangeError if no enemy units could be attacked from the current position
        :return: A Unit object that self will attack
        """

        attackable_targets = feutils.attackable_units(self, enemy_team)
        if len(attackable_targets) == 0:
            raise FEAttackRangeError(f"No units were in attack range of {self.name} at coordinate {self.x},{self.y}")

        enemy_choice = None
        h_best = float('-inf')
        for target in attackable_targets:
            h = self.combat_heuristic(target, env)
            if h > h_best:
                enemy_choice = target
                h_best = h

        return enemy_choice

    def combat_heuristic(self, enemy_unit, env):
        """
        A justification for this algorithm will be found in 'research/algorithms.md'
        :param env:
        :param enemy_unit:
        :return: A heuristic of self fighting enemy_unit
        """
        summary = combat.get_combat_stats(self, enemy_unit, env.map)
        ha, hd = summary.attacker_summary.hit_chance, summary.defender_summary.hit_chance
        ma, md = summary.attacker_summary.might, summary.defender_summary.might
        ca, cd = summary.attacker_summary.crit_chance, summary.defender_summary.crit_chance
        da, dd = int(summary.attacker_summary.doubling), int(summary.defender_summary.doubling)

        return (da + 1) * (ma * ha + ma * ca) - self.tau * ((da + 1) * (md * hd + md * cd))

    def determine_item_to_use(self, env, enemy_team):
        """
        Allied units have one item for simplification anyways, so lets not complicate this heuristic

        :param env:
        :param enemy_team:
        :return:
        """
        usable_items = self.get_all_consumables()
        i = random.choice(usable_items)
        return self.inventory.index(i)
