"""시스템 설계의 뒤로 넘긴 낮은 이슈(190, 194~200) 테스트. 표준 라이브러리 unittest만 사용한다."""
import io
import re
import unicodedata
import unittest
from contextlib import redirect_stdout

from _studio import ROOT, STUDIO, systems as sy

BRIEF = {"pillars": [{"name": "욕심이 곧 성장", "test": "t"}, {"name": "숙성이 읽힌다", "test": "t"}], "mvp": ["보석 숙성 3단계", "조준 무기"], "out_of_scope": ["멀티플레이"]}
CONCEPTS = [{"id": "gems", "status": "approved", "brief": BRIEF}, {"id": "other", "status": "proposed"}]
FORMAT = ROOT / "skills/system-design/references/systems-format.md"


def system(sid="ripening", scope="mvp", **over):
    return {"id": sid, "scope": scope, "pillars": ["욕심이 곧 성장", "숙성이 읽힌다"], "mvp": ["보석 숙성 3단계", "조준 무기"], "rules": [{"id": "r1", "text": "보석은 3단계로 익는다"}], **over}


def run(*entries, concepts=CONCEPTS, **top):
    return sy.validate({"systems": list(entries) or [system()], **top}, concepts=concepts)


def codes(rows):
    return [x["code"] for x in rows]


def printed(result, fn=sy.print_extra):
    out = io.StringIO()
    with redirect_stdout(out):
        fn(result)
    return out.getvalue()


class OutOfScopeInTheWrongColumn(unittest.TestCase):
    """194: 범위 밖 항목을 mvp나 pillars 칸에 적으면 범위 밖이라고 말한다."""

    def test_an_out_of_scope_item_in_mvp_is_named_as_out_of_scope(self):
        r = run(system(mvp=["보석 숙성 3단계", "조준 무기", "멀티플레이"]))
        self.assertNotIn("unknown_mvp", codes(r["errors"]))
        e = next(x for x in r["errors"] if x["code"] == "out_of_scope_claimed")
        self.assertEqual(e["where"], "ripening")
        self.assertIn("멀티플레이", e["message"])
        self.assertIn("범위 밖", e["message"])

    def test_an_out_of_scope_item_in_pillars_is_named_as_out_of_scope(self):
        r = run(system(pillars=["욕심이 곧 성장", "숙성이 읽힌다", "멀티플레이"]))
        self.assertNotIn("unknown_pillar", codes(r["errors"]))
        self.assertIn("out_of_scope_claimed", codes(r["errors"]))

    def test_a_plain_typo_is_still_unknown(self):
        self.assertIn("unknown_mvp", codes(run(system(mvp=["보석 숙성 3단게", "조준 무기"]))["errors"]))


class NoApprovedConcept(unittest.TestCase):
    """195: 승인된 컨셉이 없으면 concept을 적으라는 안내가 막다른 길이다."""

    def message(self, concepts):
        return next(e["message"] for e in run(concepts=concepts)["errors"] if e["where"] == "concept")

    def test_zero_approved_points_to_concept_exploration(self):
        text = self.message([{"id": "gems", "status": "proposed", "brief": BRIEF}])
        self.assertIn("concept-exploration", text)
        self.assertNotIn("최상위에 concept(컨셉 id)을 적습니다", text)

    def test_two_approved_still_ask_for_a_choice(self):
        text = self.message([*CONCEPTS, {"id": "more", "status": "approved", "brief": BRIEF}])
        self.assertIn("concept", text)
        self.assertNotIn("concept-exploration", text)


class DuplicateRule(unittest.TestCase):
    """196: 규칙 id 중복은 어느 시스템인지 말하고, 그 시스템이 표에서 빠진다고 알린다."""

    def result(self):
        return run(system(rules=[{"id": "r1", "text": "a"}, {"id": "r1", "text": "b"}]))

    def test_the_place_names_the_system(self):
        e = next(x for x in self.result()["errors"] if x["code"] == "duplicate_id")
        self.assertEqual(e["where"], "ripening.rules.r1")

    def test_duplicate_systems_keep_their_place(self):
        e = next(x for x in run(system(), system())["errors"] if x["code"] == "duplicate_id")
        self.assertEqual(e["where"], "ripening")

    def test_the_dropped_system_is_named_in_the_report(self):
        r = self.result()
        self.assertEqual(r["rows"], [])
        self.assertEqual(r["dropped"], ["ripening"])
        self.assertIn("ripening", printed(r))


class ArrayWording(unittest.TestCase):
    """197: '글의 배열입니다'는 어색하다."""

    def test_the_message_is_natural(self):
        text = next(e["message"] for e in run(system(pillars="글"))["errors"] if e["code"] == "schema")
        self.assertIn("문자열 배열이어야 합니다", text)
        self.assertNotIn("글의 배열", text)
        self.assertNotIn("은(는)", text)


class Normalization(unittest.TestCase):
    """198: 같아 보이는 NFD 문구는 같은 문구다."""

    def test_an_nfd_pillar_matches_the_brief(self):
        nfd = [unicodedata.normalize("NFD", p) for p in ("욕심이 곧 성장", "숙성이 읽힌다")]
        r = run(system(pillars=nfd, mvp=[unicodedata.normalize("NFD", m) for m in ("보석 숙성 3단계", "조준 무기")]))
        self.assertEqual((r["errors"], r["warnings"]), ([], []))

    def test_an_nfd_brief_matches_nfc_systems(self):
        brief = {**BRIEF, "pillars": [{"name": unicodedata.normalize("NFD", "욕심이 곧 성장"), "test": "t"}, {"name": "숙성이 읽힌다", "test": "t"}]}
        r = run(concepts=[{"id": "gems", "status": "approved", "brief": brief}])
        self.assertEqual((r["errors"], r["warnings"]), ([], []))

    def test_an_nfd_out_of_scope_item_is_caught(self):
        r = run(system(mvp=["보석 숙성 3단계", "조준 무기", unicodedata.normalize("NFD", "멀티플레이")]))
        self.assertIn("out_of_scope_claimed", codes(r["errors"]))


class Count(unittest.TestCase):
    """199: 시스템 개수는 오류 종류와 상관없이 같다."""

    def test_the_count_does_not_depend_on_the_kind_of_error(self):
        bad_status = run(system(), system("b", status="weird"))
        bad_scope = run(system(), system("b", scope="soon"))
        self.assertEqual(bad_status["count"], bad_scope["count"])
        self.assertEqual(bad_status["count"], 2)
        self.assertEqual(bad_status["dropped"], bad_scope["dropped"])

    def test_the_count_line_says_how_many_dropped(self):
        text = printed(run(system(), system("b", scope="soon")), sy.print_counts)
        self.assertIn("시스템 2개", text)
        self.assertIn("형식 오류로 빠짐 1", text)

    def test_a_clean_count_line_has_no_dropped_note(self):
        self.assertNotIn("빠짐", printed(run(), sy.print_counts))


class DuplicateItems(unittest.TestCase):
    """200: pillars, mvp, depends_on의 중복은 표에 두 번 나온다."""

    def test_each_list_warns_on_a_repeat(self):
        for key, value in (("pillars", ["욕심이 곧 성장", "욕심이 곧 성장", "숙성이 읽힌다"]), ("mvp", ["조준 무기", "보석 숙성 3단계", "조준 무기"])):
            r = run(system(**{key: value}))
            w = next(x for x in r["warnings"] if x["code"] == "duplicate_item")
            self.assertEqual(w["where"], "ripening", key)
            self.assertIn(key, w["message"])

    def test_depends_on_repeat_warns(self):
        r = run(system("a"), system("b", depends_on=["a", "a"]))
        self.assertIn("duplicate_item", codes(r["warnings"]))

    def test_an_nfd_repeat_is_a_repeat(self):
        r = run(system(pillars=["욕심이 곧 성장", unicodedata.normalize("NFD", "욕심이 곧 성장"), "숙성이 읽힌다"]))
        self.assertIn("duplicate_item", codes(r["warnings"]))

    def test_no_repeat_no_warning(self):
        self.assertEqual(run()["warnings"], [])


class LaterAfterMvp(unittest.TestCase):
    """190: 나중 시스템은 MVP 시스템과 같은 단계에 섞이지 않는다."""

    def test_a_later_system_without_dependencies_comes_after_the_mvp(self):
        r = run(system("a"), system("b", depends_on=["a"]), system("hud", "later", mvp=[]))
        order = {x["id"]: x["order"] for x in r["rows"]}
        self.assertEqual(order, {"a": 1, "b": 2, "hud": 3})

    def test_later_systems_keep_their_own_dependencies(self):
        r = run(system("a"), system("hud", "later", mvp=[], depends_on=["a"]), system("map", "later", mvp=[], depends_on=["hud"]))
        order = {x["id"]: x["order"] for x in r["rows"]}
        self.assertEqual(order, {"a": 1, "hud": 2, "map": 3})

    def test_without_mvp_systems_later_starts_at_one(self):
        r = run(system("hud", "later", mvp=[]))
        self.assertEqual(r["rows"][0]["order"], 1)


class CodesAreDocumented(unittest.TestCase):
    def test_every_system_code_is_in_the_format_table(self):
        code = (STUDIO / "scripts/studio_data/systems.py").read_text(encoding="utf-8")
        doc = FORMAT.read_text(encoding="utf-8")
        table = doc[doc.index("\n## 검사\n"):]
        found = set(re.findall(r'_err\(\w+, "([a-z_]+)"', code)) | set(re.findall(r'issue\("([a-z_]+)"', code))
        self.assertGreater(len(found), 10)
        self.assertEqual(sorted(c for c in found if f"| `{c}`" not in table and f", `{c}`" not in table), [])


if __name__ == "__main__":
    unittest.main()
