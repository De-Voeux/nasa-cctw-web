"""Credential handling: parsed locally, never printed, never overriding the real environment."""
import pytest

from seagis_extractor import auth


def test_load_dotenv_parses_quotes_comments_and_export(tmp_path):
    p = tmp_path / ".env"
    p.write_text('# comment\nEARTHDATA_USERNAME=alice\nexport EARTHDATA_TOKEN="abc.def.ghi"\nEMPTY=\nbad line\n'
                 "COPERNICUSMARINE_SERVICE_PASSWORD='p=w#d'\n")
    env = auth.load_dotenv(p)
    assert env == {"EARTHDATA_USERNAME": "alice", "EARTHDATA_TOKEN": "abc.def.ghi", "EMPTY": "",
                   "COPERNICUSMARINE_SERVICE_PASSWORD": "p=w#d"}


def test_apply_env_sets_only_missing_non_empty(tmp_path):
    p = tmp_path / ".env"
    p.write_text("A=1\nB=2\nC=\n")
    environ = {"B": "already"}
    assert auth.apply_env(p, environ) == ["A"]
    assert environ == {"A": "1", "B": "already"}


def test_missing_token_error_does_not_echo_anything(capsys):
    with pytest.raises(auth.AuthError) as e:
        auth.earthdata_token({})
    assert "EARTHDATA_TOKEN" in str(e.value)
    assert capsys.readouterr() == ("", "")


def test_copernicus_configured_from_env_or_credentials_file(tmp_path):
    assert auth.copernicus_configured({"COPERNICUSMARINE_SERVICE_USERNAME": "u",
                                       "COPERNICUSMARINE_SERVICE_PASSWORD": "p"}, home=tmp_path)
    assert not auth.copernicus_configured({}, home=tmp_path)
    (tmp_path / ".copernicusmarine").mkdir()
    (tmp_path / ".copernicusmarine" / ".copernicusmarine-credentials").write_text("x")
    assert auth.copernicus_configured({}, home=tmp_path)
