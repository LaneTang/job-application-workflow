"""Behavioral checks using fictional applications in temporary workspaces."""
import importlib.util
from datetime import date
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo

spec = importlib.util.spec_from_file_location('dashboard', Path(__file__).resolve().parents[1] / 'scripts/dashboard.py')
dashboard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dashboard)


class ApplicationRecordsTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.store = dashboard.Store(self.workspace.name)
        self.job_id = 'example/company/123'

    def test_saved_answer_needs_verified_fill_and_stale_write_is_rejected(self):
        self.store.upsert({'id': self.job_id, 'questions': [{'id': 'start', 'text': 'Start date?', 'required': True}]})
        saved = self.store.answer({'job_id': self.job_id, 'answers': [{'id': 'start', 'answer': 'June 1', 'expected_answer': ''}]})
        self.assertEqual(saved['jobs'][0]['questions'][0]['status'], 'answered')
        self.assertFalse(saved['jobs'][0]['ready_to_go'])
        with self.assertRaises(dashboard.Conflict):
            self.store.upsert({'id': self.job_id, 'questions': [{'id': 'start', 'status': 'applied', 'expected_answer': 'old answer'}]})
        self.store.upsert({'id': self.job_id, 'questions': [{'id': 'start', 'status': 'applied', 'expected_answer': 'June 1'}]})
        ready = self.store.upsert({'id': self.job_id, 'state': 'ready_for_review', 'verification': dict.fromkeys(dashboard.VERIFICATION_KEYS, True)})
        self.assertTrue(ready['jobs'][0]['ready_to_go'])
        edited = self.store.answer({'job_id': self.job_id, 'answers': [{'id': 'start', 'answer': 'June 2', 'expected_answer': 'June 1'}]})
        self.assertFalse(edited['jobs'][0]['ready_to_go'])
        self.assertEqual(len(edited['jobs']), 1)

    def test_submission_evidence_survives_progress_and_prevents_reopening(self):
        evidence = {'kind': 'user_confirmation', 'text': 'Fictional submission confirmed', 'observed_at': '2020-01-01T12:00:00Z'}
        self.store.upsert({'id': self.job_id, 'state': 'submitted', 'submitted_at': '2020-01-01', 'submission_evidence': evidence})
        event = {'job_id': self.job_id, 'kind': 'interview_completed', 'round': 2, 'date': '2020-01-02', 'source': 'Fictional test'}
        self.store.record_event(event)
        state = self.store.record_event(event)
        self.assertEqual(state['jobs'][0]['state'], 'interviewing')
        self.assertEqual(state['jobs'][0]['submission_evidence'], evidence)
        self.assertEqual(len(state['jobs'][0]['recruiting_events']), 1)
        with self.assertRaises(dashboard.Conflict):
            self.store.upsert({'id': self.job_id, 'state': 'filling'})
        self.assertTrue((Path(self.workspace.name) / 'applications/README.md').is_file())

    def test_ghost_threshold_and_waiting_for_candidate(self):
        job = {'state': 'submitted', 'submitted_at': '2020-01-01'}
        zone = ZoneInfo('UTC')
        self.assertFalse(dashboard.recruiting_view(job, date(2020, 1, 22), zone)['ghost'])
        self.assertTrue(dashboard.recruiting_view(job, date(2020, 1, 23), zone)['ghost'])
        job['recruiting_events'] = [{'kind': 'action_requested', 'date': '2020-01-02'}]
        view = dashboard.recruiting_view(job, date(2020, 2, 1), zone)
        self.assertFalse(view['ghost'])
        self.assertEqual(view['waiting_on'], 'candidate')


if __name__ == '__main__':
    unittest.main()
