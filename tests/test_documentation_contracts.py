from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_spec_mandated_adr_set_is_present_and_named_consistently():
    adr_root = ROOT / "docs" / "adr"
    expected = {f"ADR-{number:03d}" for number in range(1, 15)}
    found = {path.name[:7] for path in adr_root.glob("ADR-*.md")}
    assert found == expected
    for identifier in sorted(expected):
        matches = list(adr_root.glob(f"{identifier}-*.md"))
        assert len(matches) == 1
        assert identifier in matches[0].read_text(encoding="utf-8")


def test_spec_mandated_documentation_sections_exist():
    docs_root = ROOT / "docs"
    for section in ("architecture", "concepts", "guides", "reference", "adr"):
        section_root = docs_root / section
        assert section_root.is_dir()
        assert any(section_root.glob("*.md"))


def test_ci_examples_are_runnable_and_match_project_commands():
    github = (ROOT / "docs/guides/github-actions.yml").read_text(encoding="utf-8")
    gitlab = (ROOT / "docs/guides/gitlab-ci.yml").read_text(encoding="utf-8")
    for workflow in (github, gitlab):
        assert "pip install -e '.[dev]'" in workflow
        assert "pytest" in workflow
        assert "pnpm --filter @sdpstudio/web test" in workflow
        assert "pnpm --filter @sdpstudio/web build" in workflow
