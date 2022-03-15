
class FEActionError(Exception):
    pass


class Action:
    def __init__(self, action_name, action_item, move_x, move_y):
        # if action_name != 'Attack' or action_name != 'Item' or action_name != 'Wait':
        #     raise FEActionError(f"Action was not of type Attack, Item, or Wait. Was: '{action_name}'")
        # WHY DOES THIS BREAK EVERYTHING

        self.name = action_name

        if action_name == 'Attack' and action_item is None:
            raise FEActionError('Attack actions must also have a unit action item associated with them.')

        if action_name == 'Item' and action_item is None:
            raise FEActionError('Item actions must also have an Item action item associated with them.')

        self.action_item = action_item
        self.x = move_x
        self.y = move_y

    def is_attack(self):
        return self.name == 'Attack'

    def is_item(self):
        return self.name == 'Item'

    def is_wait(self):
        return self.name == 'Wait'

    def action_index(self):
        """
        Gets what the index would be of the qtable entry of the action.
        :return: 0 if 'Wait', 1 if 'Item', 2 if 'Attack'
        """
        if self.name == 'Wait':
            return 0
        elif self.name == 'Item':
            return 1
        else:
            return 2

    def __str__(self):
        if self.action_item is None:
            return f"{self.name}"
        return f"{self.x},{self.y} - {self.name} - {self.action_item}"

