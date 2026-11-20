"""art-handoff: 설계 층이 그림 쪽에 넘길 것(읽혀야 하는 것, 그릴 것)을 design/art-handoff.md에 모으는 절차 문서.
검사기는 없다. 표준 라이브러리 unittest만 사용한다."""
import re
import unittest

from _studio import ROOT, provenance as cp

SKILL = ROOT / "skills/art-handoff"
DOC = SKILL / "SKILL.md"
RECORD = SKILL / "references/handoff-record.md"
CHANGE = SKILL / "references/after-art-change.md"
HANDOFF = ROOT / "skills/production-handoff/SKILL.md"


def read(path):
    return path.read_text(encoding="utf-8")


def anchors(path):
    """GitHub식 제목 앵커. 코드 블록 안의 줄은 제목이 아니다."""
    found, fenced = set(), False
    for line in read(path).splitlines():
        if line.startswith("```"):
            fenced = not fenced
        elif not fenced and re.match(r"#{1,6} ", line):
            title = line.lstrip("#").strip().lower()
            found.add(re.sub(r"[^\w\- ]", "", title).replace(" ", "-"))
    return found


def section(text, heading):
    """heading 줄부터 같은 단계 이상의 다음 제목 전까지."""
    level = heading.split(" ")[0]
    start = text.index(f"\n{heading}\n")
    nxt = re.search(rf"\n#{{1,{len(level)}}} ", text[start + 1:])
    return text[start:start + 1 + nxt.start()] if nxt else text[start:]


class SkillShape(unittest.TestCase):
    def test_entry_references_and_codex_card_exist(self):
        for path in (DOC, RECORD, CHANGE, SKILL / "agents/openai.yaml"):
            self.assertTrue(path.is_file(), path)

    def test_description_is_english_and_says_when(self):
        head = read(DOC).split("---")[1]
        self.assertIn("name: art-handoff", head)
        self.assertRegex(head, r'description: "[A-Z]')
        self.assertIn("Use after", head)

    def test_no_scripts(self):
        self.assertFalse((SKILL / "scripts").exists())   # 파이썬 코드는 studio-data에만 둔다

    def test_relative_links_and_anchors_resolve(self):
        for path in (DOC, RECORD, CHANGE, HANDOFF):
            for target, anchor in re.findall(r"\]\(([^)#:]*)(?:#([^)]*))?\)", read(path)):
                dest = (path.parent / target) if target else path
                self.assertTrue(dest.exists(), f"{path.name}: {target}")
                if anchor and dest.suffix == ".md":
                    self.assertIn(anchor, anchors(dest), f"{path.name}: {target}#{anchor}")


class Flow(unittest.TestCase):
    def test_does_not_choose_style_or_colors(self):
        text = read(DOC)
        self.assertIn("그림체와 색은 정하지 않는다", text)

    def test_readability_comes_from_the_hypothesis_word_table(self):
        text = read(DOC)
        self.assertIn("../playtest-verdict/SKILL.md#1-플레이-전-가설에-id와-최소-표본을-단다", text)
        self.assertIn("말 인용 표", text)
        self.assertIn("design/systems.json", text)

    def test_each_item_names_the_hypotheses_that_lean_on_it(self):
        text = read(DOC) + read(RECORD)
        self.assertIn("기대는 가설", text)
        step2 = section(read(DOC), "### 2. 기대는 가설을 잇는다")
        self.assertIn("`_main`", step2)
        self.assertIn("7단계에서 `_main` 가설을 더하면", step2)   # 이 스킬을 쓸 때는 아직 없다
        self.assertIn('기대는 가설이 없으면 "없음"', step2)   # 그 항목은 그림이 바꿔도 다시 확인하지 않는다

    def test_assets_are_copied_from_data_ids_not_counted_by_hand(self):
        text = read(DOC)
        self.assertIn("data/*.json", text)
        self.assertIn("id", section(text, "### 3. 그릴 것을 데이터에서 옮긴다"))

    def test_user_decides_when_art_direction_comes(self):
        text = section(read(DOC), "### 4. 그림 방향을 언제 정할지 사용자가 정한다")
        for word in ("**다시 확인 전:**", "**다시 확인 뒤:**", "[결정: 사용자"):
            self.assertIn(word, text, word)

    def test_hands_fields_to_art_direction(self):
        text = read(DOC)
        self.assertIn("art-direction", text)
        for field in ("`id`", "`what`", "`group`", "`on`", "`cue`", "`source`"):
            self.assertIn(field, text, field)

    def test_draw_list_maps_to_asset_sourcing_wanted(self):
        step5 = section(read(DOC), "### 5. 넘긴다")
        self.assertIn("`asset-sourcing`", step5)
        for field in ("`wanted`", "`file`", "`list`", "`key`", "`skip`", "`asset_class`", "`meanings`"):
            self.assertIn(field, step5, field)
        self.assertIn("그릴 것: <asset-sourcing", read(RECORD))

    def test_asset_sourcing_handoff_is_conditional_ordered_and_covers_edge_rows(self):
        step5 = section(read(DOC), "### 5. 넘긴다")
        bullet = next(line for line in step5.splitlines() if "`asset-sourcing`" in line)
        self.assertTrue(bullet.startswith("- game-art-skills를 쓰면"), bullet)   # 사람에게 맡기는 길도 있다
        self.assertIn("그림 방향(`art/direction.json`)을 정한 뒤", bullet)   # 장부 검사가 예산을 그 파일에서 읽는다
        self.assertIn("다시 확인 뒤 길이면", bullet)
        self.assertIn("예산 이름 중 맞는 것을 사용자와 골라", bullet)   # 종류는 자유 글자, asset_class는 예산 이름
        self.assertIn("`art-direction`에서 예산을 더한다", bullet)
        self.assertIn("함께 쓰는 그림", bullet)
        self.assertIn("`covers`를 여럿", bullet)
        self.assertIn("배열 안의 배열", bullet)   # list는 객체의 점 경로만 따라간다
        self.assertIn("빠진 id를 검사기가 보지 않는다", bullet)

    def test_graphics_docs_name_asset_sourcing(self):
        self.assertIn("`asset-sourcing`", read(ROOT / "README.md"))
        roadmap = re.search(r"\| 6 \|[^\n]*", read(ROOT / "docs/architecture.md")).group(0)
        self.assertIn("`asset-sourcing`", roadmap)

    def test_decided_colors_have_a_place_without_art_skills(self):
        self.assertIn("## 정한 색과 단서", read(RECORD))
        step4 = section(read(DOC), "### 4. 그림 방향을 언제 정할지 사용자가 정한다")
        self.assertIn("쓰지 않으면 항목마다 기록의 '정한 색과 단서'에 적는다", step4)

    def test_art_change_without_main_adds_the_recheck(self):
        text = read(CHANGE)
        self.assertIn("다시 확인할 변화 없음", text)
        self.assertIn("1~5번", text)

    def test_art_change_after_a_verdict_is_recorded_as_after_results(self):
        text = read(CHANGE)
        self.assertIn("../../playtest-verdict/references/changes.md#판정한-가설의-문장을-고칠-때", text)
        self.assertIn("after_results", text)

    def test_art_change_updates_the_production_record(self):
        text = read(CHANGE)
        judged = text[text.index("**판정이 있다:**"):]
        self.assertIn("design/production.md", judged)
        self.assertIn('판정 칸을 "아직"으로 되돌린다', judged)

    def test_art_change_on_leaned_items_goes_to_the_user(self):
        text = read(CHANGE)
        for word in ("기대는 가설", "화면 판", "`cut`", "사용자가 정한다"):
            self.assertIn(word, text, word)
        self.assertIn("../../playtest-verdict/references/changes.md#다시-시험할-때", text)


class Record(unittest.TestCase):
    def test_template_is_not_a_test_bed(self):
        text = read(RECORD)
        for word in ("intent_matters", "deck_clicks", "cards.json", "my-cards"):
            self.assertNotIn(word, text, word)

    def test_record_lives_in_design_and_names_its_sections(self):
        text = read(RECORD)
        self.assertIn("design/art-handoff.md", text)
        for head in ("## 읽혀야 하는 것", "## 그릴 것", "## 그림 방향을 언제 정하나", "## 바뀐 이력"):
            self.assertIn(head, text, head)

    def test_docs_have_no_provenance_errors(self):
        report = cp.check_paths_cli([str(DOC), str(RECORD), str(CHANGE)])
        errors = [f"{r.path}:{f.line}: {f.message}" for r in report for f in r.findings if f.level == "error"]
        self.assertEqual(errors, [])

    def test_source_column_is_not_named_like_a_provenance_column(self):
        # 머리글이 정확히 '출처'인 표는 수치 표로 보여 행마다 태그를 요구받는다(388번). 틀 전체의 검사는 test_check_provenance
        self.assertIn("| 나온 곳 |", read(RECORD))
        step1 = section(read(DOC), "### 1. 읽혀야 하는 것을 모은다")
        self.assertIn("나온 곳", step1)
        self.assertIn("나온 곳과 기대는 가설 → `source`", section(read(DOC), "### 5. 넘긴다"))


class Links(unittest.TestCase):
    def test_production_handoff_sends_step7_here_and_stays_under_the_cap(self):
        text = read(HANDOFF)
        step7 = section(text, "### 7. 본 게임 빌드에서 가설을 다시 확인한다")
        self.assertLess(step7.find("../art-handoff/SKILL.md"), step7.find("\n1. "))   # 화면 판을 정하기 전에
        self.assertGreater(step7.find("../art-handoff/SKILL.md"), 0)
        self.assertIn("[art-handoff](../art-handoff/SKILL.md)", section(text, "## 한계"))
        self.assertNotIn("그 연결은 아직 없다", text)
        self.assertLess(len(text.encode("utf-8")), 20000)

    def test_readme_and_guide_list_the_skill(self):
        self.assertIn("(skills/art-handoff/SKILL.md)", read(ROOT / "README.md"))
        self.assertIn("`art-handoff`", read(ROOT / "docs/guide.md"))

    def test_counts_say_fifteen(self):
        for rel in ("README.md", "docs/guide.md", "docs/walkthrough.html"):
            text = read(ROOT / rel)
            self.assertNotRegex(text, r"스킬 14개|열네 (개|폴더)", rel)
            self.assertRegex(text, r"스킬 15개|열다섯", rel)

    def test_graphics_link_is_no_longer_called_on_hold(self):
        for rel in ("README.md", "docs/guide.md", "docs/walkthrough.html"):
            self.assertNotIn("보류 중", read(ROOT / rel), rel)

    def test_architecture_roadmap_has_the_stage(self):
        text = read(ROOT / "docs/architecture.md")
        self.assertTrue(re.search(r"\| 6 \|[^\n]*`art-handoff`[^\n]*\| 1차 완료", text))


if __name__ == "__main__":
    unittest.main()
