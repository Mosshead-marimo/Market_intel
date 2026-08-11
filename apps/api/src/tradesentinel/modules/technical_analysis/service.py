from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from itertools import pairwise
from typing import Literal

from tradesentinel.domain.market_data import MarketInterval
from tradesentinel.domain.technical import (
    AdjustedTechnicalBar,
    AdxOutput,
    AdxPoint,
    AtrOutput,
    EmaOutput,
    IndicatorPoint,
    IndicatorSeries,
    LevelOutput,
    MacdOutput,
    MacdPoint,
    MomentumOutput,
    PriceLevel,
    RsiOutput,
    SmaOutput,
    TechnicalCalculationInput,
    TechnicalSnapshot,
    TechnicalStatus,
    TechnicalWindow,
    TechnicalWindowInput,
    TrendOutput,
    VolatilityOutput,
)
from tradesentinel.modules.technical_analysis.errors import (
    TechnicalDataError,
    TechnicalInsufficientHistoryError,
)

ZERO = Decimal(0)
ONE = Decimal(1)
HUNDRED = Decimal(100)
ANNUALIZATION = {
    MarketInterval.DAILY: Decimal(252),
    MarketInterval.WEEKLY: Decimal(52),
    MarketInterval.MONTHLY: Decimal(12),
}


def _require(indicator: str, observed: int, required: int) -> None:
    if observed < required:
        raise TechnicalInsufficientHistoryError(indicator, required, observed)


def _series(period: int, points: tuple[IndicatorPoint, ...]) -> IndicatorSeries:
    return IndicatorSeries(period=period, latest=points[-1].value, points=points)


class TechnicalAnalysisService:
    def window(self, request: TechnicalWindowInput) -> TechnicalWindow:
        if request.start is not None and request.end is not None:
            return TechnicalWindow(start=request.start, end=request.end)
        end = request.as_of or datetime.now(UTC)
        if end.tzinfo is None:
            end = end.replace(tzinfo=UTC)
        try:
            start = end.replace(year=end.year - 1)
        except ValueError:
            start = end.replace(year=end.year - 1, day=28)
        return TechnicalWindow(start=start, end=end)

    def adjusted_bars(self, request: TechnicalCalculationInput) -> tuple[AdjustedTechnicalBar, ...]:
        bars = request.history.bars
        timestamps = [bar.timestamp for bar in bars]
        if timestamps != sorted(timestamps) or len(timestamps) != len(set(timestamps)):
            raise TechnicalDataError("history timestamps must be unique and ascending")
        adjusted: list[AdjustedTechnicalBar] = []
        for bar in bars:
            if bar.close <= 0 or bar.adjusted_close <= 0:
                raise TechnicalDataError("close and adjusted close must be positive")
            ratio = bar.adjusted_close / bar.close
            try:
                adjusted.append(
                    AdjustedTechnicalBar(
                        timestamp=bar.timestamp,
                        open=bar.open * ratio,
                        high=bar.high * ratio,
                        low=bar.low * ratio,
                        close=bar.adjusted_close,
                        volume=bar.volume,
                    )
                )
            except ValueError as exc:
                raise TechnicalDataError("adjusted OHLC values are inconsistent") from exc
        return tuple(adjusted)

    @staticmethod
    def _sma_points(
        values: tuple[tuple[datetime, Decimal], ...], period: int, indicator: str = "sma"
    ) -> tuple[IndicatorPoint, ...]:
        _require(indicator, len(values), period)
        return tuple(
            IndicatorPoint(
                timestamp=values[index][0],
                value=sum((item[1] for item in values[index - period + 1 : index + 1]), ZERO)
                / Decimal(period),
            )
            for index in range(period - 1, len(values))
        )

    @staticmethod
    def _ema_points(
        values: tuple[tuple[datetime, Decimal], ...], period: int, indicator: str = "ema"
    ) -> tuple[IndicatorPoint, ...]:
        _require(indicator, len(values), period)
        alpha = Decimal(2) / Decimal(period + 1)
        seed = sum((item[1] for item in values[:period]), ZERO) / Decimal(period)
        points = [IndicatorPoint(timestamp=values[period - 1][0], value=seed)]
        current = seed
        for timestamp, value in values[period:]:
            current = (value - current) * alpha + current
            points.append(IndicatorPoint(timestamp=timestamp, value=current))
        return tuple(points)

    def sma(self, request: TechnicalCalculationInput) -> SmaOutput:
        bars = self.adjusted_bars(request)
        period = request.parameters.sma_period
        points = self._sma_points(tuple((bar.timestamp, bar.close) for bar in bars), period)
        return SmaOutput(
            instrument=request.history.instrument,
            interval=request.history.interval,
            series=_series(period, points),
        )

    def ema(self, request: TechnicalCalculationInput) -> EmaOutput:
        bars = self.adjusted_bars(request)
        period = request.parameters.ema_period
        points = self._ema_points(tuple((bar.timestamp, bar.close) for bar in bars), period)
        return EmaOutput(
            instrument=request.history.instrument,
            interval=request.history.interval,
            series=_series(period, points),
        )

    def rsi(self, request: TechnicalCalculationInput) -> RsiOutput:
        bars = self.adjusted_bars(request)
        period = request.parameters.rsi_period
        _require("rsi", len(bars), period + 1)
        changes = tuple(bars[index].close - bars[index - 1].close for index in range(1, len(bars)))
        gains = tuple(max(change, ZERO) for change in changes)
        losses = tuple(max(-change, ZERO) for change in changes)
        average_gain = sum(gains[:period], ZERO) / Decimal(period)
        average_loss = sum(losses[:period], ZERO) / Decimal(period)

        def value() -> Decimal:
            if average_gain == 0 and average_loss == 0:
                return Decimal(50)
            if average_loss == 0:
                return HUNDRED
            if average_gain == 0:
                return ZERO
            return HUNDRED - HUNDRED / (ONE + average_gain / average_loss)

        points = [IndicatorPoint(timestamp=bars[period].timestamp, value=value())]
        for index in range(period, len(changes)):
            average_gain = (average_gain * Decimal(period - 1) + gains[index]) / Decimal(period)
            average_loss = (average_loss * Decimal(period - 1) + losses[index]) / Decimal(period)
            points.append(IndicatorPoint(timestamp=bars[index + 1].timestamp, value=value()))
        return RsiOutput(
            instrument=request.history.instrument,
            interval=request.history.interval,
            series=_series(period, tuple(points)),
        )

    def macd(self, request: TechnicalCalculationInput) -> MacdOutput:
        bars = self.adjusted_bars(request)
        parameters = request.parameters
        values = tuple((bar.timestamp, bar.close) for bar in bars)
        fast = {
            item.timestamp: item.value
            for item in self._ema_points(values, parameters.macd_fast_period, "macd")
        }
        slow = self._ema_points(values, parameters.macd_slow_period, "macd")
        macd_values = tuple(
            (item.timestamp, fast[item.timestamp] - item.value)
            for item in slow
            if item.timestamp in fast
        )
        signal = self._ema_points(macd_values, parameters.macd_signal_period, "macd")
        macd_by_time = dict(macd_values)
        points = tuple(
            MacdPoint(
                timestamp=item.timestamp,
                macd=macd_by_time[item.timestamp],
                signal=item.value,
                histogram=macd_by_time[item.timestamp] - item.value,
            )
            for item in signal
        )
        return MacdOutput(
            instrument=request.history.instrument,
            interval=request.history.interval,
            fast_period=parameters.macd_fast_period,
            slow_period=parameters.macd_slow_period,
            signal_period=parameters.macd_signal_period,
            latest=points[-1],
            points=points,
        )

    def _true_ranges(
        self, bars: tuple[AdjustedTechnicalBar, ...]
    ) -> tuple[tuple[datetime, Decimal], ...]:
        if not bars:
            return ()
        values = [(bars[0].timestamp, bars[0].high - bars[0].low)]
        values.extend(
            (
                bar.timestamp,
                max(
                    bar.high - bar.low,
                    abs(bar.high - bars[index - 1].close),
                    abs(bar.low - bars[index - 1].close),
                ),
            )
            for index, bar in enumerate(bars[1:], start=1)
        )
        return tuple(values)

    @staticmethod
    def _wilder_points(
        values: tuple[tuple[datetime, Decimal], ...], period: int, indicator: str
    ) -> tuple[IndicatorPoint, ...]:
        _require(indicator, len(values), period)
        current = sum((item[1] for item in values[:period]), ZERO) / Decimal(period)
        points = [IndicatorPoint(timestamp=values[period - 1][0], value=current)]
        for timestamp, value in values[period:]:
            current = (current * Decimal(period - 1) + value) / Decimal(period)
            points.append(IndicatorPoint(timestamp=timestamp, value=current))
        return tuple(points)

    def atr(self, request: TechnicalCalculationInput) -> AtrOutput:
        bars = self.adjusted_bars(request)
        period = request.parameters.atr_period
        _require("atr", len(bars), period + 1)
        points = self._wilder_points(self._true_ranges(bars), period, "atr")
        return AtrOutput(
            instrument=request.history.instrument,
            interval=request.history.interval,
            series=_series(period, points),
        )

    def adx(self, request: TechnicalCalculationInput) -> AdxOutput:
        bars = self.adjusted_bars(request)
        period = request.parameters.adx_period
        _require("adx", len(bars), period * 2)
        tr: list[Decimal] = []
        positive_dm: list[Decimal] = []
        negative_dm: list[Decimal] = []
        timestamps: list[datetime] = []
        for previous, current in pairwise(bars):
            upward = current.high - previous.high
            downward = previous.low - current.low
            positive_dm.append(upward if upward > downward and upward > 0 else ZERO)
            negative_dm.append(downward if downward > upward and downward > 0 else ZERO)
            tr.append(
                max(
                    current.high - current.low,
                    abs(current.high - previous.close),
                    abs(current.low - previous.close),
                )
            )
            timestamps.append(current.timestamp)
        smoothed_tr = sum(tr[:period], ZERO)
        smoothed_positive = sum(positive_dm[:period], ZERO)
        smoothed_negative = sum(negative_dm[:period], ZERO)
        directional: list[tuple[datetime, Decimal, Decimal, Decimal]] = []

        def append_directional(timestamp: datetime) -> None:
            positive = ZERO if smoothed_tr == 0 else HUNDRED * smoothed_positive / smoothed_tr
            negative = ZERO if smoothed_tr == 0 else HUNDRED * smoothed_negative / smoothed_tr
            denominator = positive + negative
            dx = ZERO if denominator == 0 else HUNDRED * abs(positive - negative) / denominator
            directional.append((timestamp, positive, negative, dx))

        append_directional(timestamps[period - 1])
        for index in range(period, len(tr)):
            smoothed_tr = smoothed_tr - smoothed_tr / Decimal(period) + tr[index]
            smoothed_positive = (
                smoothed_positive - smoothed_positive / Decimal(period) + positive_dm[index]
            )
            smoothed_negative = (
                smoothed_negative - smoothed_negative / Decimal(period) + negative_dm[index]
            )
            append_directional(timestamps[index])
        _require("adx", len(directional), period)
        current_adx = sum((item[3] for item in directional[:period]), ZERO) / Decimal(period)
        first = directional[period - 1]
        points = [
            AdxPoint(
                timestamp=first[0],
                adx=current_adx,
                positive_di=first[1],
                negative_di=first[2],
            )
        ]
        for timestamp, positive, negative, dx in directional[period:]:
            current_adx = (current_adx * Decimal(period - 1) + dx) / Decimal(period)
            points.append(
                AdxPoint(
                    timestamp=timestamp,
                    adx=current_adx,
                    positive_di=positive,
                    negative_di=negative,
                )
            )
        return AdxOutput(
            instrument=request.history.instrument,
            interval=request.history.interval,
            period=period,
            latest=points[-1],
            points=tuple(points),
        )

    def _levels(
        self, request: TechnicalCalculationInput, side: Literal["support", "resistance"]
    ) -> LevelOutput:
        bars = self.adjusted_bars(request)
        parameters = request.parameters
        _require(side, len(bars), parameters.level_lookback)
        selected = bars[-parameters.level_lookback :]
        current_price = selected[-1].close
        extreme = (
            min(selected, key=lambda item: (item.low, item.timestamp))
            if side == "support"
            else max(selected, key=lambda item: (item.high, -item.timestamp.timestamp()))
        )
        extreme_value = extreme.low if side == "support" else extreme.high
        levels = [
            PriceLevel(
                method="rolling_extreme",
                level=extreme_value,
                touches=1,
                first_tested_at=extreme.timestamp,
                last_tested_at=extreme.timestamp,
                distance_percent=(extreme_value / current_price - ONE) * HUNDRED,
            )
        ]
        span = parameters.pivot_span
        pivots: list[tuple[datetime, Decimal]] = []
        for index in range(span, len(selected) - span):
            candidate = selected[index]
            neighbors = selected[index - span : index] + selected[index + 1 : index + span + 1]
            if side == "support":
                values = tuple(item.low for item in neighbors)
                if candidate.low <= min(values) and candidate.low < max(values):
                    pivots.append((candidate.timestamp, candidate.low))
            else:
                values = tuple(item.high for item in neighbors)
                if candidate.high >= max(values) and candidate.high > min(values):
                    pivots.append((candidate.timestamp, candidate.high))
        atr_value = self.atr(request).series.latest
        tolerance = atr_value * parameters.pivot_atr_multiplier
        clusters: list[list[tuple[datetime, Decimal]]] = []
        for pivot in pivots:
            candidates = [
                (
                    abs(
                        pivot[1] - sum((item[1] for item in cluster), ZERO) / Decimal(len(cluster))
                    ),
                    index,
                )
                for index, cluster in enumerate(clusters)
                if abs(pivot[1] - sum((item[1] for item in cluster), ZERO) / Decimal(len(cluster)))
                <= tolerance
            ]
            if candidates:
                clusters[min(candidates)[1]].append(pivot)
            else:
                clusters.append([pivot])
        clustered: list[PriceLevel] = []
        for cluster in clusters:
            level = sum((item[1] for item in cluster), ZERO) / Decimal(len(cluster))
            if (side == "support" and level <= current_price) or (
                side == "resistance" and level >= current_price
            ):
                tested = sorted(item[0] for item in cluster)
                clustered.append(
                    PriceLevel(
                        method="pivot_cluster",
                        level=level,
                        touches=len(cluster),
                        first_tested_at=tested[0],
                        last_tested_at=tested[-1],
                        distance_percent=(level / current_price - ONE) * HUNDRED,
                    )
                )
        clustered.sort(
            key=lambda item: (
                abs(item.level - current_price),
                -item.touches,
                item.level,
                item.first_tested_at,
            )
        )
        levels.extend(clustered[: parameters.pivot_max_levels])
        return LevelOutput(
            instrument=request.history.instrument,
            interval=request.history.interval,
            side=side,
            current_price=current_price,
            lookback=parameters.level_lookback,
            levels=tuple(levels),
        )

    def support(self, request: TechnicalCalculationInput) -> LevelOutput:
        return self._levels(request, "support")

    def resistance(self, request: TechnicalCalculationInput) -> LevelOutput:
        return self._levels(request, "resistance")

    def trend(self, request: TechnicalCalculationInput) -> TrendOutput:
        bars = self.adjusted_bars(request)
        parameters = request.parameters
        values = tuple((bar.timestamp, bar.close) for bar in bars)
        fast = self._ema_points(values, parameters.trend_fast_period, "trend")[-1].value
        slow = self._ema_points(values, parameters.trend_slow_period, "trend")[-1].value
        spread = fast / slow - ONE
        direction = (
            "rising"
            if spread > parameters.trend_spread_threshold
            else "falling"
            if spread < -parameters.trend_spread_threshold
            else "sideways"
        )
        adx_value = self.adx(request).latest.adx
        strength = "weak" if adx_value < 20 else "developing" if adx_value < 25 else "strong"
        return TrendOutput(
            instrument=request.history.instrument,
            interval=request.history.interval,
            direction=direction,
            strength=strength,
            fast_ema=fast,
            slow_ema=slow,
            spread_percent=spread * HUNDRED,
            adx=adx_value,
        )

    def momentum(self, request: TechnicalCalculationInput) -> MomentumOutput:
        bars = self.adjusted_bars(request)
        parameters = request.parameters
        _require("momentum", len(bars), parameters.momentum_roc_period + 1)
        rsi_value = self.rsi(request).series.latest
        histogram = self.macd(request).latest.histogram
        roc = (bars[-1].close / bars[-parameters.momentum_roc_period - 1].close - ONE) * HUNDRED
        positive = sum((rsi_value > parameters.momentum_rsi_upper, histogram > 0, roc > 0))
        negative = sum((rsi_value < parameters.momentum_rsi_lower, histogram < 0, roc < 0))
        direction = "positive" if positive >= 2 else "negative" if negative >= 2 else "neutral"
        return MomentumOutput(
            instrument=request.history.instrument,
            interval=request.history.interval,
            direction=direction,
            positive_votes=positive,
            negative_votes=negative,
            rsi=rsi_value,
            macd_histogram=histogram,
            rate_of_change=roc,
        )

    @staticmethod
    def _realized(values: tuple[Decimal, ...], factor: Decimal) -> Decimal:
        returns = tuple((current / previous).ln() for previous, current in pairwise(values))
        mean = sum(returns, ZERO) / Decimal(len(returns))
        variance = sum(((item - mean) ** 2 for item in returns), ZERO) / Decimal(
            max(1, len(returns) - 1)
        )
        return (variance * factor).sqrt()

    def volatility(self, request: TechnicalCalculationInput) -> VolatilityOutput:
        bars = self.adjusted_bars(request)
        period = request.parameters.volatility_period
        _require("volatility", len(bars), period + 1)
        factor = ANNUALIZATION[request.history.interval]
        rolling = tuple(
            IndicatorPoint(
                timestamp=bars[index].timestamp,
                value=self._realized(
                    tuple(bar.close for bar in bars[index - period : index + 1]), factor
                ),
            )
            for index in range(period, len(bars))
        )
        current = rolling[-1].value
        percentile = None
        regime: Literal["low", "normal", "high", "unknown"] = "unknown"
        if len(rolling) >= 5:
            percentile = Decimal(sum(item.value <= current for item in rolling)) / Decimal(
                len(rolling)
            )
            regime = (
                "low"
                if percentile <= request.parameters.volatility_low_percentile
                else "high"
                if percentile >= request.parameters.volatility_high_percentile
                else "normal"
            )
        atr_percent = self.atr(request).series.latest / bars[-1].close * HUNDRED
        return VolatilityOutput(
            instrument=request.history.instrument,
            interval=request.history.interval,
            regime=regime,
            period=period,
            annualized_volatility=current,
            atr_percent=atr_percent,
            percentile_rank=percentile,
            rolling=rolling,
        )

    def snapshot(self, request: TechnicalCalculationInput) -> TechnicalSnapshot:
        calculations = {
            "rsi": self.rsi,
            "macd": self.macd,
            "ema": self.ema,
            "sma": self.sma,
            "atr": self.atr,
            "adx": self.adx,
            "support": self.support,
            "resistance": self.resistance,
            "trend": self.trend,
            "momentum": self.momentum,
            "volatility": self.volatility,
        }
        outputs: dict[str, object | None] = {}
        warnings: list[str] = []
        for name, calculation in calculations.items():
            try:
                outputs[name] = calculation(request)
            except TechnicalInsufficientHistoryError as exc:
                outputs[name] = None
                warnings.append(
                    f"{name} requires {exc.details['required']} observations; "
                    f"{exc.details['observed']} were available."
                )
        bars = self.adjusted_bars(request)
        available = sum(value is not None for value in outputs.values())
        status = (
            TechnicalStatus.COMPLETED
            if not warnings
            else TechnicalStatus.PARTIAL
            if available
            else TechnicalStatus.EMPTY
        )
        return TechnicalSnapshot(
            instrument=request.history.instrument,
            status=status,
            interval=request.history.interval,
            requested_start=request.requested_start,
            requested_end=request.requested_end,
            observed_start=bars[0].timestamp if bars else None,
            observed_end=bars[-1].timestamp if bars else None,
            data_cutoff=bars[-1].timestamp if bars else None,
            observation_count=len(bars),
            parameters=request.parameters,
            provider=request.history.provider,
            cache=request.history.cache,
            warnings=tuple(warnings),
            **outputs,
        )
