import numpy as np
import matplotlib
matplotlib.use('qt5Agg')
import matplotlib.pyplot as plt

from gym import Env
from gym.spaces import Discrete, Box
from garage.envs.base import Step

from garage.core.serializable import Serializable
from garage.misc.overrides import overrides
from garage.misc import logger


class MinibotEnv(Env, Serializable):
    '''
    Simulated two-wheeled robot in an environment with obstacles.
    
    Robot`s max. travel distance in one timestep is 0.2 (if both motors are set to 100% power).
    Robot`s wheels are on its sides, and robot is 0.764 wide (2.4/pi), i.e. robot can rotate 90
    degrees in 3 timesteps (if motors are at +100% and -100%).
    Robot always starts facing north (however, agent itself does not have a notion of its orientation).
    
    Robot is equipped with a 'radar' which scans presence of obstacles within its approximity.
    Radar output is a sqare bit matrix: presence/absence of obstacle in grid points
    [agent`s X position +- N*radar_resolution ; agent`s Y position +- M*radar_resolution]
    where 0 <= N,M <= radar_range.

    Agent`s actions are optionally discretized from {<-1,-0.33> , <-0.33,0.33> , <0.33,1>} to [-1, 0, 1],
    to ensure full motor output (bang-bang policy).


    Maps legend:
        'S' : starting point
        'F' / '.' / ' ': free space
        'W' / 'x' / '#': wall
        'H' / 'O': hole (terminates episode)
        'G' : goal
    '''
    
    all_maps = [
        ["........", # min = 11 actions
         "........",
         "........",
         "........",
         "........",
         "...##...",
         "...##...",
         "..S##G.."
        ],
        ["........", # min = 13 actions
         "........",
         "...##...",
         "...##...",
         "...##...",
         "...##...",
         "..S##G..",
         "...##..."
        ],
        ["........", # min = 21 actions
         "........",
         "...###..",
         "..S###..",
         "...###..",
         "######..",
         "..G###..",
         "........"
        ]
    ]
    map_colors = ['maroon', 'midnightblue', 'darkgreen', 'darkgoldenrod']
    EPSILON = 0.0001

    def __init__(self, radar_range=2, radar_resolution=1, discretized=True, use_maps='all'):
        '''
        :param radar_range: how many measurings does 'radar' make, Manhattan distance from agent
        :param radar_resolution: distance between two measurings of agent`s 'radar'
        :param use_maps: which maps to use, list of indexes or 'all'
        '''
        Serializable.quick_init(self, locals())
        
        self.radar_range = radar_range
        self.radar_resolution = radar_resolution
        self.discretized = discretized
        self.agent_width = 2.4/np.pi
        self.max_action_distance = 0.2

        self.current_map_idx = None
        self.agent_pos = None
        self.agent_ori = None
        
        # Maps initialization
        if use_maps == 'all':
            raw_maps = self.all_maps
        else:
            raw_maps = [self.all_maps[i] for i in use_maps]
        self.maps = []
        self.bit_maps = []
        for i in range(len(raw_maps)):
            # Normalize char map
            m = np.array([list(row.upper()) for row in raw_maps[i]])
            m[np.logical_or(m == '.', m == ' ')] = 'F'
            m[np.logical_or(m == 'X', m == '#')] = 'W'
            m[m == 'O'] = 'H'
            self.maps.append(m)
            # Make bit map
            bm = np.zeros(m.shape)
            bm[np.logical_or(m == 'W', m == 'H')] = 1
            self.bit_maps.append(bm)


    @overrides
    @property
    def action_space(self):
        '''
        Power on left/right motor
        '''
        return Box(low=-1, high=1, shape=(2,), dtype=np.float32)

    @overrides
    @property
    def observation_space(self):
        '''
        0 = free space, 1 = wall/hole
        '''
        obs_wide = self.radar_range * 2 + 1
        return Box(low=0, high=1, shape=(obs_wide, obs_wide), dtype=np.float32)


    @overrides
    def get_current_obs(self):
        '''
        Get what agent can see (up to radar_range distance), rotated according
        to agent`s orientation.
        '''
        return self._get_obs(self.agent_pos, self.agent_ori, self._get_current_map(bitmap=True))


    def _get_obs(self, pos, ori, map_):
        '''
        Get what agent would see on map_ from position pos (up to radar_range distance), rotated
        according to orientation ori.
        '''
        bound = self.radar_range * self.radar_resolution
        ls = np.linspace(-bound, bound, 2 * self.radar_range + 1)
        xx, yy = np.meshgrid(ls, -ls)   # negative ls because we want the observation vector to be ordered front-to-back (row-column style)
        points = np.array([xx.flatten(), yy.flatten()])
        # Transform points from agent`s coordinates to world coordinates
        r = self._rotation_matrix(ori)
        points = pos.reshape((2, 1)) + r @ points
        # Fill in observation vector
        obs = np.zeros(points.shape[1])
        for i, point in enumerate(points.T):
            obs[i] = self._tile_type_at_pos(point, bitmap=True, map_=map_)
        return obs


    @overrides
    def reset(self):
        '''
        Choose random map for this rollout, init agent facing north.
        '''
        self.current_map_idx = np.random.choice(len(self.maps))
        m = self.maps[self.current_map_idx]
        (start_r,), (start_c,) = np.nonzero(m == 'S')
        self.agent_pos = self._rc_to_xy([start_r, start_c])
        self.agent_ori = 0
        return self.get_current_obs()


    # @overrides
    def reset_to_state(self, start_obs, **kwargs):
        '''
        Choose state that matches given observation.
        '''
        # This is pretty inefficient implementation. It could serve if method is only rarely,
        # called, otherwise some serious refactoring should take place.
        oris = np.arange(4) * np.pi / 2
        alpha = np.pi / 6
        oris = np.concatenate([oris, oris + alpha, oris + 2 * alpha])
        # First round
        for map_idx in np.random.permutation(len(self.bit_maps)):   # try each map (in random order)
            m = self.bit_maps[map_idx]
            rows, cols = m.shape
            xx, yy = np.meshgrid(np.arange(cols), np.arange(rows))
            points = np.array([xx.flatten(), yy.flatten()])
            for o in oris:          # try each orientation
                for p in points.T:  # try each mid-tile point
                    if np.all(start_obs == self._get_obs(p, o, m)):
                        self.agent_pos, self.agent_ori = p, o
                        self.current_map_idx = map_idx
                        return start_obs
        # Second round
        for map_idx in np.random.permutation(len(self.bit_maps)):   # try each map (in random order)
            m = self.bit_maps[map_idx]
            rows, cols = m.shape
            xx, yy = np.meshgrid(np.arange(cols), np.arange(rows))
            points = np.array([xx.flatten(), yy.flatten()])
            deltas = np.array([-0.4, -0.2, 0, 0.2, 0.4])
            for o in oris:          # try each orientation
                for p in points.T:  # for each mid-tile point
                    for dx in deltas:
                     for dy in deltas:
                        pp = p + np.array([dx, dy])
                        if np.all(start_obs == self._get_obs(pp, o, m)):
                            self.agent_pos, self.agent_ori = pp, o
                            self.current_map_idx = map_idx
                            return start_obs
        raise ValueError('MinibotEnv.reset_to_state: unable to find suitable state for observation:\n{}'.format(start_obs))


    @overrides
    def reset(self):
        '''
        Choose random map for this rollout, init agent facing north.
        '''
        self.current_map_idx = np.random.choice(len(self.maps))
        m = self.maps[self.current_map_idx]
        (start_r,), (start_c,) = np.nonzero(m == 'S')
        self.agent_pos = self._rc_to_xy([start_r, start_c])
        self.agent_ori = 0
        return self.get_current_obs()
    

    @overrides
    def step(self, action):
        '''
        :param action: power on left & right motor
        '''
        if self.discretized:
            # discretization from {<-1,-0.33> , <-0.33,0.33> , <0.33,1>} to [-1, 0, 1]
            action = np.clip(np.round(action * 1.5), a_min=-1, a_max=1)
        # Set new state
        next_pos, next_ori = self._get_new_position(action)
        self.agent_pos = next_pos
        self.agent_ori = next_ori
        # Determine reward and termination
        m = self._get_current_map()
        next_state_type = self._tile_type_at_pos(next_pos)
        if next_state_type == 'H':
            done = True
            reward = -1
        elif next_state_type in ['F', 'S']:
            done = False
            reward = 0
        elif next_state_type == 'G':
            done = True
            reward = 1
        else:
            raise NotImplementedError
        # Return observation (and others)
        obs = self.get_current_obs()
        return Step(observation=obs, reward=reward, done=done,
                    agent_pos=self.agent_pos, agent_ori=self.agent_ori,
                    map=self.current_map_idx)


    def _get_new_position(self, action):
        '''
        Using current state and given action, return new state (position, orientation) considering walls.
        Does not change the agent`s position
        :return: tuple(position, orientation)
        '''
        m = self._get_current_map()
        rows, cols = m.shape
        pos0 = self.agent_pos
        ori0 = self.agent_ori
        move_vector, ori_change = self._get_raw_move(action)
        pos1 = pos0 + move_vector
        ori1 = ori0 + ori_change

        # Collision detection
        t0 = np.round(pos0)  # starting tile
        t1 = np.round(pos1)  # ending tile
        if self._tile_type_at_pos(pos1) != 'W':  # no collision (t1=='W' also implies t1 != t0)
            return pos1, ori1

        dtx = t0[0] != t1[0]  # was tile changed in x-direction
        dty = t0[1] != t1[1]  # was tile changed in y-direction
        mid_x, mid_y = (t0 + t1) / 2
        near_wall_x = mid_x - np.sign(move_vector[0]) * 0.01
        near_wall_y = mid_y - np.sign(move_vector[1]) * 0.01
        if dtx and not dty:  # bumped into wall E/W
            pos1[0] = near_wall_x
            return pos1, ori1
        if dty and not dtx:  # bumped into wall N/S
            pos1[1] = near_wall_y
            return pos1, ori1

        # now we know: t1=='W' , dtx , dty ... i.e. we moved diagonally, traversing another tile either on E/W xor on N/S
        t_ew_wall = self._tile_type_at_pos((t1[0], t0[1])) == 'W'
        t_ns_wall = self._tile_type_at_pos((t0[0], t1[1])) == 'W'
        if not t_ew_wall  and  not t_ns_wall:
            tx = (mid_x - pos0[0]) / (pos1[0] - pos0[0])
            ty = (mid_y - pos0[1]) / (pos1[1] - pos0[1])
            if tx < ty:  # travelled through empty tile on E/W, bumped into wall on N/S
                pos1[1] = near_wall_y
            else:            # travelled through empty tile on N/S, bumped into wall on E/W
                pos1[0] = near_wall_x
            return pos1, ori1
        if t_ew_wall:  # bumped into wall on E/W
            pos1[0] = near_wall_x
        if t_ns_wall:  # bumped into wall on N/S
            pos1[1] = near_wall_y
        # combination of last two: bumped into corner
        return pos1, ori1


    def _get_raw_move(self, action):
        '''
        Computes:
        1) a vector: in which direction the agent should move (in world coordinates)
        2) orientation change
        Does not handle collisions, nor does it actually changes agent`s position.
        '''
        al, ar = action * self.max_action_distance  # scale motor power <-1,1> to actual distance <-0.2,0.2>
        w = self.agent_width

        if np.abs(al - ar) < self.EPSILON:
            # al == ar -> Agent moves in straight line
            relative_move_vector = np.array([0, al])
            ori_change = 0
        elif np.abs(al + ar) < self.EPSILON:
            # al == -ar -> Agent rotates in place
            relative_move_vector = np.array([0, 0])
            ori_change = ar * 2 / w
        else:
            # Agent moves and rotates at the same time
            r = (w * (ar + al)) / (2 * (ar - al))
            alpha = (ar + al) / (2 * r)
            me_pos = np.array([0, 0])  # agent`s position in his frame of reference
            rot_center = np.array([-r, 0])
            me_pos = me_pos - rot_center                      # 1) move to rotation center
            me_pos = self._rotation_matrix(alpha) @ me_pos    # 2) rotate
            me_pos = me_pos + rot_center                      # 3) move back
            # Vector me_pos now represents in which direction the agent should move !!! in his frame of reference !!!
            relative_move_vector = me_pos
            ori_change = alpha
        absolute_move_vector = self._rotation_matrix(self.agent_ori) @ relative_move_vector
        return absolute_move_vector, ori_change


    def _rotation_matrix(self, alpha):
        '''
        2-D rotation matrix for column-vectors (i.e. usage: x' = R @ x).
        '''
        sin = np.sin(alpha)
        cos = np.cos(alpha)
        return np.array([[cos, -sin], [sin, cos]])


    def _tile_type_at_pos(self, position, bitmap=False, map_=None):
        '''
        Return type of a tile at given X,Y position on a map_, or on current map if map_ is None.
        '''
        m = map_ if map_ is not None else self._get_current_map(bitmap)
        rows, cols = m.shape
        x, y = np.round(position)
        r, c = self._xy_to_rc([x, y], rows=rows)
        if r < 0 or c < 0 or r >= rows or c >= cols:
            return 1 if bitmap else 'W'
        return m[r, c]


    def _rc_to_xy(self, pos, rows=None):
        '''
        Get position as [X,Y], instead of [row, column].
        :param pos: (r,c) position
        :param rows: number of rows in a map, or None (current map is used)
        '''
        r, c = pos
        if rows is None:
            rows, _ = self._get_current_map().shape
        return np.array([c, rows - r - 1])

    def _xy_to_rc(self, pos, rows=None):
        '''
        Get position as [row, column], instead of [X,Y]. Original [X,Y] position will be rounded to nearest tile.
        :param pos: (x,y) position
        :param rows: number of rows in a map, or None (current map is used)
        '''
        x, y = np.round(pos)
        if rows is None:
            rows, _ = self._get_current_map().shape
        return np.array([rows - y - 1, x], dtype='int32')


    def _get_current_map(self, bitmap=False):
        '''
        Return current map, or bitmap (for observations).
        '''
        if bitmap:
            return self.bit_maps[self.current_map_idx]
        return self.maps[self.current_map_idx]
