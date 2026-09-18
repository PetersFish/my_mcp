from app.services.report import ReportDAO


def test_dao() -> None:
    assert ReportDAO().load() == 1
