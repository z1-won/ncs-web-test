"""세분류 건의 단계 정의표와 상태 전이(ncs_service.flow) — DB 없이 표와 규칙만 본다."""

import re
import unittest

from ncs_service import flow
from ncs_service.accounts import ROLES
from ncs_service.migrations import MIGRATIONS
from ncs_service.progress import STAGE_NUMBERS


def event(stage, action, volume="v1", note="", actor="김에디터(kim)", at="2026-11-21T10:00:00"):
    return {"volume_id": volume, "stage": stage, "action": action, "at": at, "actor": actor, "note": note}


class StageTableTests(unittest.TestCase):
    def test_keys_are_unique_and_roles_exist(self):
        keys = [stage.key for stage in flow.STAGES]
        self.assertEqual(len(keys), len(set(keys)))
        for stage in flow.STAGES:
            self.assertIn(stage.unit, (flow.CASE, flow.VOLUME))
            self.assertIn(stage.kind, flow.TRANSITIONS)
            self.assertTrue(stage.submit and stage.confirm, stage.key)
            self.assertLessEqual(set(stage.submit) | set(stage.confirm), set(ROLES), stage.key)
        self.assertIn(flow.PROXY_ROLE, ROLES)
        self.assertLessEqual(set(flow.MANAGER_ROLES), set(ROLES))

    def test_every_legacy_stage_maps_to_this_table(self):
        """원고 진행 현황의 7단계는 모두 이 표의 단계로 옮겨진다(7은 분량과 권리 증빙 둘)."""
        for number in STAGE_NUMBERS:
            self.assertTrue(flow.legacy_stages(number), number)
        self.assertEqual([stage.key for stage in flow.legacy_stages(7)], ["volume", "rights"])

    def test_improvements_match_the_schema(self):
        sql = dict(MIGRATIONS)["013_cases"]
        listed = re.search(r"improvement IN \(([^)]*)\)", sql).group(1)
        self.assertEqual(tuple(re.findall(r"'([^']+)'", listed)), flow.IMPROVEMENTS)

    def test_stage_keys_and_actions_are_not_in_the_schema(self):
        sql = dict(MIGRATIONS)["013_cases"]
        for word in [stage.key for stage in flow.STAGES if stage.key != "volume"] + [flow.SUBMIT, flow.REOPEN]:
            self.assertNotIn(f"'{word}'", sql)


class TransitionTests(unittest.TestCase):
    def test_roundtrip(self):
        stage = flow.BY_KEY["revision"]
        state = flow.WAITING
        for action, expected in [(flow.SUBMIT, flow.SUBMITTED), (flow.REQUEST, flow.REQUESTED), (flow.SUBMIT, flow.SUBMITTED),
                                 (flow.COMPLETE, flow.DONE), (flow.REOPEN, flow.SUBMITTED)]:
            state = flow.next_state(stage, state, action)
            self.assertEqual(state, expected)

    def test_handoff_and_external(self):
        self.assertEqual(flow.next_state(flow.BY_KEY["draft_edit"], flow.WAITING, flow.COMPLETE), flow.DONE)
        stage = flow.BY_KEY["review1"]
        self.assertEqual(flow.next_state(stage, flow.SUBMITTED, flow.JUDGE), flow.VERDICT)
        self.assertEqual(flow.next_state(stage, flow.VERDICT, flow.COMPLETE), flow.DONE)

    def test_wrong_moves_say_why(self):
        with self.assertRaisesRegex(flow.FlowError, "넘기기 단계"):
            flow.next_state(flow.BY_KEY["draft_edit"], flow.WAITING, flow.REQUEST)
        with self.assertRaisesRegex(flow.FlowError, "지금 ‘대기’"):
            flow.next_state(flow.BY_KEY["revision"], flow.WAITING, flow.REQUEST)
        with self.assertRaisesRegex(flow.FlowError, "지금 ‘완료’"):
            flow.next_state(flow.BY_KEY["revision"], flow.DONE, flow.COMPLETE)
        with self.assertRaises(flow.FlowError):
            flow.next_state(flow.BY_KEY["revision"], flow.WAITING, "delete")

    def test_skipped_completion_needs_a_reason(self):
        stage = flow.BY_KEY["revision"]
        with self.assertRaisesRegex(flow.FlowError, "사유"):
            flow.next_state(stage, flow.WAITING, flow.COMPLETE)
        self.assertEqual(flow.next_state(stage, flow.WAITING, flow.COMPLETE, note="종이로 확인함"), flow.DONE)

    def test_who_may_act(self):
        stage = flow.BY_KEY["revision"]
        self.assertEqual(flow.allowed(stage, flow.SUBMIT, "author"), (True, False))
        self.assertEqual(flow.allowed(stage, flow.COMPLETE, "author"), (False, False))
        self.assertEqual(flow.allowed(stage, flow.COMPLETE, "editor"), (True, False))
        self.assertEqual(flow.allowed(flow.BY_KEY["volume"], flow.COMPLETE, "editor"), (True, True))      # 직능연의 확인을 에디터가 대신 적음
        self.assertEqual(flow.allowed(flow.BY_KEY["volume"], flow.COMPLETE, "reviewer"), (False, False))


class FoldTests(unittest.TestCase):
    def test_events_fold_into_states_per_volume_and_stage(self):
        current = flow.states([
            event("revision", flow.SUBMIT, actor="이집필(lee)"), event("revision", flow.REQUEST, note="표 3 다시"),
            event("revision", flow.SUBMIT, volume="v2"), event("plan", flow.COMPLETE, volume=None, note="건너뜀"),
            event("", flow.CREATED, volume=None), event("draft_edit", flow.COMPLETE), event("draft_edit", flow.REOPEN),
        ])
        self.assertEqual(current[("v1", "revision")]["state"], flow.REQUESTED)
        self.assertEqual(current[("v1", "revision")]["note"], "표 3 다시")
        self.assertEqual(current[("v2", "revision")]["state"], flow.SUBMITTED)
        self.assertEqual(current[(None, "plan")]["state"], flow.DONE)
        self.assertEqual(current[("v1", "draft_edit")]["state"], flow.WAITING)
        skipped = flow.states([event("revision", flow.COMPLETE, note="종이로 확인"), event("revision", flow.REOPEN)])
        self.assertEqual(skipped[("v1", "revision")]["state"], flow.WAITING)                      # 건너뛴 완료를 되돌리면 제출됨이 아니라 대기
        self.assertEqual(len(current), 4)


if __name__ == "__main__":
    unittest.main()
