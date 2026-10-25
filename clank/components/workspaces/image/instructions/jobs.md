# Long computations

Your shell tool stops a command after a few minutes, and while a command runs you can do nothing else. Run any command
you expect to take more than two minutes (a simulation, a sweep, a training run, a long build, a batch of seeds) with
Clank's `run_job` instead: it runs in the folder, detached, at the lowest CPU priority so the model keeps its speed, its
output in a log under `.clank/jobs/agent/`.

After starting a job, tell the user in a line what it computes and what you expect it to give, then go on with other
work or end your turn. You are told when it ends: how it ended, after how long, its log's last lines and the files it
wrote. `job_status` shows a job now (or every job), and `job_stop` stops one. Do not poll a job in a loop.
