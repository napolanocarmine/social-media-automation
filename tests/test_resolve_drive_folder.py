from pathlib import Path

from social_automation.config_loaders import resolve_drive_folder_id


def test_resolve_prefers_arg_then_env_then_yaml(tmp_path: Path) -> None:
    yaml_path = tmp_path / "cat.yaml"
    yaml_path.write_text(
        "drive_root_folder_id: from-yaml\n",
        encoding="utf-8",
    )
    assert resolve_drive_folder_id(
        folder_id_arg="from-arg",
        folder_id_env="from-env",
        categories_yaml=yaml_path,
    ) == "from-arg"
    assert resolve_drive_folder_id(
        folder_id_arg="",
        folder_id_env="from-env",
        categories_yaml=yaml_path,
    ) == "from-env"
    assert resolve_drive_folder_id(
        folder_id_arg="",
        folder_id_env="",
        categories_yaml=yaml_path,
    ) == "from-yaml"
