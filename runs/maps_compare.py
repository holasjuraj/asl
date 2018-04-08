#!/usr/bin/env python

# Policy optimization algorithm
from rllab.algos.trpo import TRPO

# Baseline for Advantage function { A(s) = V(s) - B(s) }
from rllab.baselines.linear_feature_baseline import LinearFeatureBaseline

# Environment
# from rllab.envs.grid_world_env import GridWorldEnv
# from sandbox.asl.envs.simple_grid_env import GridWorldObsEnv
from sandbox.asl.envs.grid_maze_env import GridMazeEnv
from rllab.envs.normalized_env import normalize

# Policy network
from rllab.policies.categorical_mlp_policy import CategoricalMLPPolicy

# Experiment-running util
from rllab.misc.instrument import run_experiment_lite

subdir, use_maps = None, None
def run_task(*_):
    env = normalize(GridMazeEnv(plot={'save':'~/rllab/data/local/'+subdir},
                                use_maps=use_maps
                                ))

    policy = CategoricalMLPPolicy(
        env_spec=env.spec,
        # The neural network policy should have two hidden layers, each with 32 hidden units.
        hidden_sizes=(32, 32)
    )

    baseline = LinearFeatureBaseline(env_spec=env.spec)

    algo = TRPO(
        env=env,
        policy=policy,
        baseline=baseline,
        batch_size=3333,
        max_path_length=100,
        n_itr=30,
        discount=0.99,
        step_size=0.01,
    )
    algo.train()

for maps, suffix in [([0,1], 'easy'), ([2], 'hard'), ([0,1,2], 'both')]:
    for seed in [10, 20, 30, 40, 50]:
        use_maps = maps
        l_subdir = 'asl-compare-maps/{}_{}'.format(suffix, seed)
        subdir = l_subdir
        # Run pickled
        run_experiment_lite(
            run_task,
            exp_name=l_subdir,
            # Number of parallel workers for sampling
            n_parallel=2,
            # Only keep the snapshot parameters for the last iteration
            snapshot_mode="last",
            # Specifies the seed for the experiment. If this is not provided, a random seed will be used
            seed=seed,
        )