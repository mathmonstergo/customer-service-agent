from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_gitignore_does_not_ignore_project_tests() -> None:
    """测试目录是项目质量资产，不能被 .gitignore 整体忽略。"""
    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "\ntests/\n" not in f"\n{gitignore}\n"
