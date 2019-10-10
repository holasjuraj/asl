from garage.core.serializable import Serializable
from garage.spaces import Discrete
# TODO probably change to garage.[tf|theano].spaces.Discrete
import numpy as np


class HierarchicalPolicy(Serializable):
    """
    Wrapper for hierarchical policy containing top-level and skill policies.
    """

    # noinspection PyMissingConstructor
    def __init__(
            self,
            top_policy,
            skill_policy_prototype,
            skill_policies,
            skill_stop_functions=None,
            skill_max_timesteps=100
    ):
        """
        :param top_policy: policy for top-level agent, to be trained
        :param skill_policies: list of trained skill policies
        :param skill_policy_prototype: an empty policy serving as a prototype for newly created skill policies. New
               policies are generated by calling Serializable.clone() upon this prototype, producing a new instance of
               the policy initialized with same parameters as the prototype.
        :param skill_stop_functions: list of stopping functions (path_dict -> bool) for trained skills
        :param skill_max_timesteps: maximum length of skill execution
        """
        Serializable.quick_init(self, locals())
        self._top_policy = top_policy
        self._skill_policy_prototype = skill_policy_prototype
        self._skill_policies = skill_policies
        self._num_orig_skills = len(skill_policies)
        self.skill_max_timesteps = skill_max_timesteps

        # pad _skills_end_obss to align indexes with skill_policies
        self._skills_end_obss = [None for _ in range(self._num_orig_skills)]

        # if _skill_stop_functions is not provided, default stopping function (return False) is assigned to all
        self._skill_stop_functions = skill_stop_functions if skill_stop_functions is not None \
                                     else [lambda path: False for _ in range(self._num_orig_skills)]
        assert(len(self._skill_stop_functions) == self._num_orig_skills)

        # Check top-level policy
        if not isinstance(top_policy.action_space, Discrete) \
                or top_policy.action_space.n != self.num_skills:
            raise TypeError('Top level policy must have Discrete(num_skills) action space.')

    @property
    def num_skills(self):
        return len(self._skill_policies)

    def get_top_policy(self):
        """
        :return: Policy of top-level agent
        :rtype: garage.policies.base.Policy
        """
        return self._top_policy

    def get_skill_policy(self, i):
        """
        :param i: Number of skill
        :return: Policy of selected skill
        :rtype: garage.policies.base.Policy
        """
        return self._skill_policies[i]

    def get_skill_stopping_func(self, i):
        """
        :param i: Number of skill
        :return: function ({actions, observations} -> bool) that indicates that skill execution is done
        """
        return self._skill_stop_functions[i]

    def create_new_skill(self, end_obss):
        """
        Create new untrained skill and add it to skills list, along with its stopping function.
        :return: new skill policy and skill ID (index of the skill)
        :rtype: tuple(garage.policies.base.Policy, int)
        """
        new_skill_id = len(self._skill_policies)
        new_skill_pol = Serializable.clone(self._skill_policy_prototype)
        self._skill_policies.append(new_skill_pol)
        self._skills_end_obss.append(np.copy(end_obss))
        self._skill_stop_functions.append(
            lambda path: path['observations'][-1] in self._skills_end_obss[new_skill_id]
        )
        return new_skill_pol, new_skill_id
