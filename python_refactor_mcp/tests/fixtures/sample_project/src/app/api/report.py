from app.services.report import ReportDAO, build_report


def handle() -> int:
    dao = ReportDAO()
    return build_report() + dao.load()
