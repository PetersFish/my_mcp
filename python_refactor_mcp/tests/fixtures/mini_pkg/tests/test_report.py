from app.services.report import ReportDAO, build_report


def test_build() -> None:
    assert build_report() == 1
    assert ReportDAO().load() == 1
