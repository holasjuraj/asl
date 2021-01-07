import numpy as np

from garage.core import Serializable
from garage.policies import Policy
from garage.misc import special

from sandbox.asa.envs import GridworldGathererEnv


class GridworldTargetPolicy(Policy, Serializable):
    """
    Policy with fixed behaviour of navigating agent to the target tile. Agent
    takes the shortest route, but only does very primitive obstacle avoidance.
    """

    def __init__(self, env_spec, target):
        """
        :param target: [row, column] of target tile
        """
        self.target = np.array(target)
        Serializable.quick_init(self, locals())
        super().__init__(env_spec=env_spec)

    def get_action(self, observation):
        moves = {(-1,  0): 0,
                 ( 0,  1): 1,
                 ( 1,  0): 2,
                 ( 0, -1): 3,
                 ( 0,  0): 0  # when agent is already on target tile, go up
                }
        pos = np.asarray(observation[:2], dtype='int32')

        # Get primary & secondary moves
        delta = self.target - pos
        abs_d = np.abs(delta)
        move_r, move_c = np.diag( delta // np.maximum(abs_d, [1, 1]) )
        move_1, move_2 = (move_r, move_c) if abs_d[0] >= abs_d[1] else (move_c, move_r)

        # If primary move goes out of map / into wall, use secondary move
        next_pos = pos + move_1
        m = GridworldGathererEnv.MAP
        if np.min(next_pos) < 0  \
           or  next_pos[0] >= len(m)  \
           or  next_pos[1] >= len(m[0])  \
           or  m[next_pos[0]][next_pos[1]] in '#WXx':
            move_1 = move_2

        return moves[tuple(move_1)], dict()

    def get_params_internal(self, **tags):
        return []

    def skill_stopping_func(self, path):
        moves = np.array([[-1, 0], [0, 1], [1, 0], [0, -1]])
        last_pos = path['observations'][-1][:2]
        a = special.from_onehot(path["actions"][-1])
        last_move = moves[a]
        return np.array_equal(last_pos + last_move, self.target)



class GridworldStepPolicy(Policy, Serializable):
    """
    Policy with fixed behaviour of moving one tile in desired direction.
    """
    def __init__(self, env_spec, direction):
        """
        :param direction: 0-4 or 'up' / 'right' / 'down' / 'left'
        """
        if isinstance(direction, int):
            self.direction = direction
        else:
            self.direction = {'up': 0, 'right': 1, 'down': 2, 'left': 3}[direction]
        Serializable.quick_init(self, locals())
        super().__init__(env_spec=env_spec)

    def get_action(self, observation):
        return self.direction, dict()

    def get_params_internal(self, **tags):
        return []

    def skill_stopping_func(self, path):
        return True