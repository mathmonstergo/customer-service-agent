from pathlib import Path


def test_systemd_template_uses_placeholders_for_machine_specific_paths():
    text = Path("systemd/customer-service-agent.service.template").read_text(encoding="utf-8")
    assert "WorkingDirectory=__WORKDIR__" in text
    assert "EnvironmentFile=__ENVFILE__" in text
    assert "ExecStart=__PYTHON__ -m customer_service_agent.cli wechat-service" in text
    assert "customer_service_agent.cli wechat-service" in text
    assert "Restart=always" in text


def test_install_script_renders_template_and_installs_user_service():
    text = Path("scripts/install_user_service.sh").read_text(encoding="utf-8")
    assert "__WORKDIR__" in text
    assert "__ENVFILE__" in text
    assert "__PYTHON__" in text
    assert "sed" in text
    assert "${HOME}/.config/systemd/user/customer-service-agent.service" in text
    assert "systemctl --user daemon-reload" in text
    assert "systemctl --user enable customer-service-agent.service" in text
