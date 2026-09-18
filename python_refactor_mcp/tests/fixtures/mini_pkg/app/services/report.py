class ReportDAO:
    def load(self) -> int:
        return 1


def build_report() -> int:
    return ReportDAO().load()
