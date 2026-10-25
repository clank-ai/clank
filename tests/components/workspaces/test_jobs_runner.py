"""Design 0021 §6: jobs run in a workspace's container for flows' boxes and for the agent the owner talks to alike, from
one runner in the workspaces component, and every job runs at the lowest CPU priority (`nice -n 19`), so the model,
on the same machine, keeps its speed while a job computes. The flows' job module gives the runner's names as before."""

from clank.components.flows import jobs as flow_jobs
from clank.components.workspaces.service import jobs


def test_every_job_runs_at_the_lowest_cpu_priority_under_its_time_limit() -> None:
    assert 'nice -n 19 timeout --kill-after=10 "$1" sh -c "$2"' in jobs.START
    assert (jobs.TIMED_OUT, jobs.KILLED, jobs.TERMINATED) == (124, 137, 143)


def test_the_flows_jobs_are_the_same_runners() -> None:
    assert flow_jobs.START is jobs.START
    assert flow_jobs.start is jobs.start
    assert flow_jobs.read_state is jobs.read_state
    assert flow_jobs.ended_words(124, minutes=30) == "ran past its 30 minutes and was ended"
