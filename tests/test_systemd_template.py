from pathlib import Path


def test_systemd_template_uses_placeholders_for_machine_specific_paths():
    text = Path("systemd/cyclops.service.template").read_text(encoding="utf-8")
    assert "Description=Cyclops" in text
    assert "WorkingDirectory=__WORKDIR__" in text
    assert "EnvironmentFile=__ENVFILE__" in text
    assert "ExecStart=__PYTHON__ -m cyclops wechat-service" in text
    assert "Restart=always" in text


def test_install_script_renders_template_and_installs_user_service():
    text = Path("scripts/install_user_service.sh").read_text(encoding="utf-8")
    assert "__WORKDIR__" in text
    assert "__ENVFILE__" in text
    assert "__PYTHON__" in text
    assert "sed" in text
    assert "${HOME}/.config/systemd/user/cyclops.service" in text
    assert "systemctl --user daemon-reload" in text
    assert "systemctl --user enable cyclops.service" in text
