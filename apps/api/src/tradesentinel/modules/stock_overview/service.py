from datetime import datetime

from tradesentinel.domain.stock_overview import StockOverviewWindow


class StockOverviewService:
    def window(self, as_of: datetime) -> StockOverviewWindow:
        try:
            start = as_of.replace(year=as_of.year - 5)
        except ValueError:
            start = as_of.replace(year=as_of.year - 5, day=28)
        return StockOverviewWindow(start=start, end=as_of)
