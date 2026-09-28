"""Tk `after` bookkeeping so a destroyed widget never gets called back."""

import logging

log = logging.getLogger(__name__)


class AfterJobsMixin:
    """Mix into a Tk widget: `schedule()` instead of `after()`; destroy() cancels the rest."""

    def _after_job_set(self):
        jobs = self.__dict__.get("_after_jobs")
        if jobs is None:
            jobs = self.__dict__["_after_jobs"] = set()
        return jobs

    def schedule(self, ms, func, *args):
        jobs = self._after_job_set()
        job = None

        def run():
            jobs.discard(job)
            func(*args)

        job = self.after(ms, run)
        jobs.add(job)
        return job

    def cancel_job(self, job):
        """Cancel a job from schedule(); None and already-run jobs are ignored. Returns None."""
        if job is None:
            return None
        self._after_job_set().discard(job)
        try:
            self.after_cancel(job)
        except Exception:
            log.debug("after_cancel(%s) failed", job, exc_info=True)
        return None

    def cancel_all_jobs(self):
        for job in list(self._after_job_set()):
            self.cancel_job(job)

    def destroy(self):
        self.cancel_all_jobs()
        super().destroy()
