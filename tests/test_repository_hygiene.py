from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_gitignore_does_not_ignore_project_tests() -> None:
    """测试目录是项目质量资产，不能被 .gitignore 整体忽略。"""
    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "\ntests/\n" not in f"\n{gitignore}\n"


def test_runtime_surface_uses_cyclops_package_name() -> None:
    """运行面应完成包名迁移；关键约束是不保留旧包目录或入口。"""
    legacy_snake = "_".join(["customer", "service", "agent"])
    legacy_kebab = "-".join(["customer", "service", "agent"])
    legacy_title = " ".join(["Customer", "Service", "Agent"])

    assert not (PROJECT_ROOT / legacy_snake).exists()

    checked_roots = [
        PROJECT_ROOT / ".env.example",
        PROJECT_ROOT / "README.md",
        PROJECT_ROOT / "environment.yml",
        PROJECT_ROOT / "pyproject.toml",
        PROJECT_ROOT / "cyclops",
        PROJECT_ROOT / "scripts",
        PROJECT_ROOT / "systemd",
        PROJECT_ROOT / "tests",
        PROJECT_ROOT / "web",
    ]
    text_suffixes = {
        ".css",
        ".html",
        ".js",
        ".json",
        ".md",
        ".py",
        ".sh",
        ".toml",
        ".ts",
        ".tsx",
        ".yml",
    }
    disallowed = (legacy_snake, legacy_kebab, legacy_title)
    offenders: list[str] = []
    for root in checked_roots:
        paths = [root] if root.is_file() else [path for path in root.rglob("*") if path.is_file()]
        for path in paths:
            if path.suffix not in text_suffixes:
                continue
            text = path.read_text(encoding="utf-8")
            for token in disallowed:
                if token in text:
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)} contains {token}")

    assert offenders == []
