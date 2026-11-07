from unittest.mock import MagicMock
from sqlalchemy.exc import OperationalError
from app import check_database


def test_database_failure_is_actionable_and_does_not_leak_details(monkeypatch,capsys):
    engine=MagicMock()
    engine.connect.side_effect=OperationalError('SELECT 1',{},Exception('do-not-print-this-password'))
    monkeypatch.setattr(check_database,'engine',engine)
    monkeypatch.setattr(check_database.settings,'database_url','postgresql+psycopg://test:secret@postgres:5432/test')
    assert check_database.main()==1
    output=capsys.readouterr().err
    assert 'docker compose up -d postgres' in output and '127.0.0.1:5434' in output
    assert 'do-not-print-this-password' not in output and 'secret' not in output


def test_database_success_uses_read_only_probe(monkeypatch,capsys):
    engine=MagicMock()
    monkeypatch.setattr(check_database,'engine',engine)
    assert check_database.main()==0
    statement=engine.connect.return_value.__enter__.return_value.execute.call_args.args[0]
    assert str(statement)=='SELECT 1'
    assert 'Database connection OK.' in capsys.readouterr().out
