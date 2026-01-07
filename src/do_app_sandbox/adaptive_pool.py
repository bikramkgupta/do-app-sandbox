"""Adaptive pool sizing algorithms for SandboxManager.

Implements state-of-the-art algorithms for dynamically adjusting pool size
based on demand patterns, optimizing for both cost and latency.

Algorithms implemented:
1. Exponential Moving Average (EMA) - Simple, reactive
2. PID Controller - Control theory approach (Kubernetes-style)
3. Predictive Scaling - Time-series based forecasting
4. Hybrid Adaptive - Combines prediction with reactive scaling
"""

import math
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ScalingAlgorithm(Enum):
    """Available scaling algorithms."""
    FIXED = "fixed"                    # Current: fixed target_ready
    EMA = "ema"                        # Exponential moving average
    PID = "pid"                        # PID controller
    PREDICTIVE = "predictive"          # Time-series prediction
    HYBRID = "hybrid"                  # Prediction + reactive
    QUEUING = "queuing"                # Queue theory optimal


@dataclass
class ScalingMetrics:
    """Metrics for scaling decisions."""
    timestamp: float
    arrival_rate: float              # Requests per second
    pool_hit_rate: float             # % served from pool
    avg_latency_ms: float            # Average acquire latency
    current_ready: int               # Current pool size
    current_in_use: int              # Currently acquired
    cold_start_rate: float           # Cold starts per second


@dataclass
class ScalingDecision:
    """Result of a scaling calculation."""
    target_ready: int
    confidence: float                # 0-1, how confident in this decision
    reason: str                      # Human-readable explanation
    predicted_demand: Optional[float] = None
    algorithm: str = ""


class ScaleUpStrategy(Enum):
    """Strategy for scaling up the pool."""
    IMMEDIATE = "immediate"          # Jump directly to target (risky)
    LINEAR = "linear"                # Add fixed N per interval
    PERCENTAGE = "percentage"        # Add X% of current per interval
    EXPONENTIAL = "exponential"      # Double each interval (fast)
    AIMD = "aimd"                    # Additive Increase (like TCP)


@dataclass
class AdaptiveConfig:
    """Configuration for adaptive scaling."""
    # General
    min_ready: int = 0               # Never go below this
    max_ready: int = 100             # Never exceed this
    target_hit_rate: float = 0.9     # Target 90% pool hits
    target_latency_ms: float = 500   # Target <500ms latency

    # Scale-up parameters
    scale_up_strategy: ScaleUpStrategy = ScaleUpStrategy.PERCENTAGE
    scale_up_step: int = 10          # For LINEAR: add this many per step
    scale_up_percent: float = 0.5    # For PERCENTAGE: add 50% of current
    scale_up_interval: float = 30    # Seconds between scale-up steps
    scale_up_max_step: int = 50      # Maximum sandboxes to add in one step

    # Scale-down parameters (always slow)
    scale_down_percent: float = 0.2  # Remove at most 20% per step
    scale_down_cooldown: float = 300 # 5 min after last scale-up

    # EMA parameters
    ema_alpha: float = 0.3           # Smoothing factor (0.1=slow, 0.5=fast)
    ema_buffer_seconds: float = 60   # Buffer for anticipated demand

    # PID parameters
    pid_kp: float = 0.5              # Proportional gain
    pid_ki: float = 0.1              # Integral gain
    pid_kd: float = 0.05             # Derivative gain
    pid_interval: float = 10         # Control interval seconds

    # Predictive parameters
    history_window: int = 3600       # 1 hour of history
    prediction_horizon: int = 300    # Predict 5 min ahead
    seasonality_hours: list = field(default_factory=lambda: [1, 24])

    # Hybrid parameters
    base_capacity_ratio: float = 0.3  # 30% from prediction
    burst_capacity_ratio: float = 0.7 # 70% reactive buffer

    # Queuing theory
    creation_time_avg: float = 60    # Average sandbox creation time
    target_wait_percentile: float = 0.95


class PoolSizer(ABC):
    """Abstract base class for pool sizing algorithms."""

    @abstractmethod
    def calculate_target(self, metrics: ScalingMetrics) -> ScalingDecision:
        """Calculate the target pool size based on current metrics."""
        pass

    @abstractmethod
    def record_event(self, event_type: str, timestamp: float = None):
        """Record an event (acquire, release, etc.) for tracking."""
        pass


class FixedPoolSizer(PoolSizer):
    """Fixed pool size (current behavior)."""

    def __init__(self, target: int):
        self.target = target

    def calculate_target(self, metrics: ScalingMetrics) -> ScalingDecision:
        return ScalingDecision(
            target_ready=self.target,
            confidence=1.0,
            reason=f"Fixed target: {self.target}",
            algorithm="fixed"
        )

    def record_event(self, event_type: str, timestamp: float = None):
        pass  # No tracking needed


class EMAPoolSizer(PoolSizer):
    """Exponential Moving Average based pool sizing.

    Simple but effective. Tracks arrival rate with exponential decay
    and adjusts target based on smoothed demand.

    target = min_ready + (arrival_rate_ema * buffer_seconds)
    """

    def __init__(self, config: AdaptiveConfig):
        self.config = config
        self.arrival_rate_ema = 0.0
        self.last_update = time.time()
        self.events: deque = deque(maxlen=1000)

    def record_event(self, event_type: str, timestamp: float = None):
        ts = timestamp or time.time()
        self.events.append((ts, event_type))

    def _calculate_arrival_rate(self, window_seconds: float = 60) -> float:
        """Calculate arrival rate over recent window."""
        now = time.time()
        cutoff = now - window_seconds
        recent = sum(1 for ts, et in self.events if ts > cutoff and et == "acquire")
        return recent / window_seconds

    def calculate_target(self, metrics: ScalingMetrics) -> ScalingDecision:
        now = time.time()
        dt = now - self.last_update
        self.last_update = now

        # Calculate current arrival rate
        current_rate = self._calculate_arrival_rate()

        # Update EMA
        alpha = self.config.ema_alpha
        self.arrival_rate_ema = alpha * current_rate + (1 - alpha) * self.arrival_rate_ema

        # Calculate target: enough to handle anticipated arrivals
        anticipated_demand = self.arrival_rate_ema * self.config.ema_buffer_seconds
        target = self.config.min_ready + int(anticipated_demand)
        target = max(self.config.min_ready, min(self.config.max_ready, target))

        return ScalingDecision(
            target_ready=target,
            confidence=0.7,  # EMA is moderately confident
            reason=f"EMA rate={self.arrival_rate_ema:.3f}/s, anticipated={anticipated_demand:.1f}",
            predicted_demand=anticipated_demand,
            algorithm="ema"
        )


class PIDPoolSizer(PoolSizer):
    """PID Controller based pool sizing.

    Uses control theory to maintain target latency/hit rate.
    Similar to Kubernetes Horizontal Pod Autoscaler.

    error = target_metric - actual_metric
    adjustment = Kp*error + Ki*∫error + Kd*d(error)/dt
    """

    def __init__(self, config: AdaptiveConfig):
        self.config = config
        self.integral = 0.0
        self.last_error = 0.0
        self.last_update = time.time()
        self.current_target = config.min_ready

    def record_event(self, event_type: str, timestamp: float = None):
        pass  # PID uses metrics, not individual events

    def calculate_target(self, metrics: ScalingMetrics) -> ScalingDecision:
        now = time.time()
        dt = now - self.last_update
        self.last_update = now

        # Error based on hit rate (primary) and latency (secondary)
        hit_rate_error = self.config.target_hit_rate - metrics.pool_hit_rate
        latency_error = (metrics.avg_latency_ms - self.config.target_latency_ms) / 1000

        # Combined error (weighted)
        error = 0.7 * hit_rate_error + 0.3 * latency_error

        # PID calculation
        self.integral += error * dt
        self.integral = max(-10, min(10, self.integral))  # Anti-windup

        derivative = (error - self.last_error) / dt if dt > 0 else 0
        self.last_error = error

        adjustment = (
            self.config.pid_kp * error +
            self.config.pid_ki * self.integral +
            self.config.pid_kd * derivative
        )

        # Scale adjustment to pool size units
        # Positive error = need more capacity
        pool_adjustment = int(adjustment * 10)  # Scale factor
        new_target = self.current_target + pool_adjustment
        new_target = max(self.config.min_ready, min(self.config.max_ready, new_target))
        self.current_target = new_target

        return ScalingDecision(
            target_ready=new_target,
            confidence=0.8,
            reason=f"PID error={error:.3f}, P={self.config.pid_kp*error:.2f}, "
                   f"I={self.config.pid_ki*self.integral:.2f}, D={self.config.pid_kd*derivative:.2f}",
            algorithm="pid"
        )


class PredictivePoolSizer(PoolSizer):
    """Time-series prediction based pool sizing.

    Uses historical patterns to predict future demand.
    Inspired by Netflix's Scryer and AWS Predictive Scaling.
    """

    def __init__(self, config: AdaptiveConfig):
        self.config = config
        self.history: deque = deque(maxlen=config.history_window)
        self.hourly_patterns: dict[int, list] = {h: [] for h in range(24)}

    def record_event(self, event_type: str, timestamp: float = None):
        ts = timestamp or time.time()
        self.history.append((ts, event_type))

        # Track hourly patterns
        if event_type == "acquire":
            hour = time.localtime(ts).tm_hour
            self.hourly_patterns[hour].append(ts)

    def _get_hourly_rate(self, hour: int) -> float:
        """Get average arrival rate for a specific hour."""
        events = self.hourly_patterns.get(hour, [])
        if len(events) < 2:
            return 0.0

        # Count events in last 7 days for this hour
        now = time.time()
        week_ago = now - 7 * 24 * 3600
        recent = [e for e in events if e > week_ago]

        if not recent:
            return 0.0

        # Events per hour averaged over days
        days_with_data = len(set(time.localtime(e).tm_mday for e in recent))
        return len(recent) / max(1, days_with_data) / 3600  # per second

    def _predict_demand(self, horizon_seconds: int) -> float:
        """Predict demand for next horizon_seconds."""
        now = time.time()
        future = now + horizon_seconds

        # Get predicted hourly rate
        future_hour = time.localtime(future).tm_hour
        base_rate = self._get_hourly_rate(future_hour)

        # Adjust for recent trend
        recent_rate = self._calculate_recent_rate(60)
        trend_factor = recent_rate / max(0.001, base_rate) if base_rate > 0 else 1.0
        trend_factor = max(0.5, min(2.0, trend_factor))  # Clamp

        predicted_rate = base_rate * trend_factor
        return predicted_rate * horizon_seconds

    def _calculate_recent_rate(self, window: float) -> float:
        """Calculate arrival rate over recent window."""
        now = time.time()
        cutoff = now - window
        count = sum(1 for ts, et in self.history if ts > cutoff and et == "acquire")
        return count / window

    def calculate_target(self, metrics: ScalingMetrics) -> ScalingDecision:
        predicted = self._predict_demand(self.config.prediction_horizon)

        # Add safety buffer based on prediction confidence
        events_count = len(self.history)
        confidence = min(1.0, events_count / 100)  # More history = more confident
        safety_factor = 1.5 - 0.3 * confidence  # 1.2-1.5x buffer

        target = int(predicted * safety_factor)
        target = max(self.config.min_ready, min(self.config.max_ready, target))

        return ScalingDecision(
            target_ready=target,
            confidence=confidence,
            reason=f"Predicted {predicted:.1f} requests in next {self.config.prediction_horizon}s, "
                   f"safety={safety_factor:.2f}x",
            predicted_demand=predicted,
            algorithm="predictive"
        )


class QueuingTheoryPoolSizer(PoolSizer):
    """Queue theory (M/M/c) based optimal pool sizing.

    Uses queuing theory to calculate optimal pool size for target latency.
    Based on Erlang C formula for multi-server queues.
    """

    def __init__(self, config: AdaptiveConfig):
        self.config = config
        self.events: deque = deque(maxlen=1000)

    def record_event(self, event_type: str, timestamp: float = None):
        ts = timestamp or time.time()
        self.events.append((ts, event_type))

    def _calculate_arrival_rate(self, window: float = 300) -> float:
        """Calculate λ (arrival rate)."""
        now = time.time()
        cutoff = now - window
        count = sum(1 for ts, et in self.events if ts > cutoff and et == "acquire")
        return count / window

    def _erlang_c(self, c: int, rho: float) -> float:
        """Calculate Erlang C probability (probability of waiting).

        P(wait) = (c*rho)^c / (c! * (1-rho)) / sum((c*rho)^k/k! for k=0..c-1) + (c*rho)^c/(c!*(1-rho))
        """
        if rho >= 1 or c < 1:
            return 1.0

        # Calculate (c*rho)^c / c!
        a = c * rho
        numerator = (a ** c) / math.factorial(c)

        # Calculate sum
        sum_terms = sum((a ** k) / math.factorial(k) for k in range(c))

        denominator = sum_terms + numerator / (1 - rho)

        if denominator == 0:
            return 1.0

        return (numerator / (1 - rho)) / denominator

    def calculate_target(self, metrics: ScalingMetrics) -> ScalingDecision:
        # λ = arrival rate, μ = service rate (1/creation_time for cold starts)
        lambda_rate = self._calculate_arrival_rate()
        mu = 1.0 / self.config.creation_time_avg  # Service rate

        if lambda_rate == 0:
            return ScalingDecision(
                target_ready=self.config.min_ready,
                confidence=0.5,
                reason="No recent arrivals",
                algorithm="queuing"
            )

        # Find minimum c where wait probability < threshold
        target_prob = 1 - self.config.target_wait_percentile

        for c in range(1, self.config.max_ready + 1):
            rho = lambda_rate / (c * mu)
            if rho >= 1:
                continue

            prob_wait = self._erlang_c(c, rho)
            if prob_wait <= target_prob:
                return ScalingDecision(
                    target_ready=c,
                    confidence=0.85,
                    reason=f"M/M/c optimal: λ={lambda_rate:.4f}, μ={mu:.4f}, "
                           f"P(wait)={prob_wait:.3f} <= {target_prob:.3f}",
                    algorithm="queuing"
                )

        return ScalingDecision(
            target_ready=self.config.max_ready,
            confidence=0.6,
            reason=f"Demand exceeds capacity: λ={lambda_rate:.4f}",
            algorithm="queuing"
        )


class HybridAdaptivePoolSizer(PoolSizer):
    """Hybrid approach combining prediction with reactive scaling.

    This is the recommended approach for production:
    1. Base capacity from predictions (handles known patterns)
    2. Reactive buffer for unexpected bursts
    3. Step-wise scale-up (avoids API rate limits)
    4. Slow scale-down (avoids thrashing)

    Similar to AWS/GCP production autoscalers.
    """

    def __init__(self, config: AdaptiveConfig):
        self.config = config
        self.predictive = PredictivePoolSizer(config)
        self.ema = EMAPoolSizer(config)
        self.current_target = config.min_ready
        self.desired_target = config.min_ready  # What we want to reach
        self.last_scale_up = 0.0
        self.last_scale_down = 0.0
        self.last_scale_step = 0.0

    def record_event(self, event_type: str, timestamp: float = None):
        self.predictive.record_event(event_type, timestamp)
        self.ema.record_event(event_type, timestamp)

    def _calculate_scale_up_step(self, current: int, desired: int) -> int:
        """Calculate how much to scale up in this step."""
        gap = desired - current
        if gap <= 0:
            return 0

        strategy = self.config.scale_up_strategy

        if strategy == ScaleUpStrategy.IMMEDIATE:
            # Jump directly (not recommended for large pools)
            step = gap

        elif strategy == ScaleUpStrategy.LINEAR:
            # Fixed step size
            step = min(gap, self.config.scale_up_step)

        elif strategy == ScaleUpStrategy.PERCENTAGE:
            # Percentage of current (at least 1, at most max_step)
            step = max(1, int(current * self.config.scale_up_percent))
            step = min(step, gap, self.config.scale_up_max_step)

        elif strategy == ScaleUpStrategy.EXPONENTIAL:
            # Double current, but cap at gap
            step = min(max(1, current), gap, self.config.scale_up_max_step)

        elif strategy == ScaleUpStrategy.AIMD:
            # Additive increase: fixed step (like TCP slow start)
            step = min(self.config.scale_up_step, gap)

        else:
            step = min(gap, self.config.scale_up_step)

        return min(step, self.config.scale_up_max_step)

    def calculate_target(self, metrics: ScalingMetrics) -> ScalingDecision:
        now = time.time()

        # Get predictions from both algorithms
        pred_decision = self.predictive.calculate_target(metrics)
        ema_decision = self.ema.calculate_target(metrics)

        # Weighted combination
        # More weight to prediction if we have confidence, else use EMA
        pred_weight = pred_decision.confidence * self.config.base_capacity_ratio
        ema_weight = 1 - pred_weight

        base_target = int(
            pred_decision.target_ready * pred_weight +
            ema_decision.target_ready * ema_weight
        )

        # Add burst buffer based on recent variance
        recent_max = max(metrics.current_ready + metrics.current_in_use, base_target)
        burst_buffer = int((recent_max - base_target) * self.config.burst_capacity_ratio)

        self.desired_target = base_target + burst_buffer
        self.desired_target = max(
            self.config.min_ready,
            min(self.config.max_ready, self.desired_target)
        )

        reason_parts = [f"pred={pred_decision.target_ready}", f"ema={ema_decision.target_ready}"]

        # Step-wise scaling
        if self.desired_target > self.current_target:
            # Scale UP - check if enough time has passed since last step
            time_since_step = now - self.last_scale_step

            if time_since_step >= self.config.scale_up_interval or self.last_scale_step == 0:
                step = self._calculate_scale_up_step(self.current_target, self.desired_target)
                self.current_target += step
                self.last_scale_up = now
                self.last_scale_step = now
                reason_parts.append(f"scale_up +{step} ({self.config.scale_up_strategy.value})")
            else:
                wait_time = self.config.scale_up_interval - time_since_step
                reason_parts.append(f"scale_up pending ({wait_time:.0f}s)")

        elif self.desired_target < self.current_target:
            # Scale DOWN - slow and cautious
            time_since_scale_up = now - self.last_scale_up

            if time_since_scale_up > self.config.scale_down_cooldown:
                # Scale down by at most X% at a time
                max_decrease = max(1, int(self.current_target * self.config.scale_down_percent))
                actual_decrease = min(max_decrease, self.current_target - self.desired_target)
                self.current_target -= actual_decrease
                self.last_scale_down = now
                reason_parts.append(f"scale_down -{actual_decrease}")
            else:
                cooldown_remaining = self.config.scale_down_cooldown - time_since_scale_up
                reason_parts.append(f"scale_down cooldown ({cooldown_remaining:.0f}s)")

        self.current_target = max(
            self.config.min_ready,
            min(self.config.max_ready, self.current_target)
        )

        return ScalingDecision(
            target_ready=self.current_target,
            confidence=(pred_decision.confidence + 0.7) / 2,
            reason=f"Hybrid[desired={self.desired_target}]: " + ", ".join(reason_parts),
            predicted_demand=pred_decision.predicted_demand,
            algorithm="hybrid"
        )


def create_pool_sizer(
    algorithm: ScalingAlgorithm,
    config: Optional[AdaptiveConfig] = None,
    fixed_target: int = 10
) -> PoolSizer:
    """Factory function to create a pool sizer."""
    config = config or AdaptiveConfig()

    if algorithm == ScalingAlgorithm.FIXED:
        return FixedPoolSizer(fixed_target)
    elif algorithm == ScalingAlgorithm.EMA:
        return EMAPoolSizer(config)
    elif algorithm == ScalingAlgorithm.PID:
        return PIDPoolSizer(config)
    elif algorithm == ScalingAlgorithm.PREDICTIVE:
        return PredictivePoolSizer(config)
    elif algorithm == ScalingAlgorithm.QUEUING:
        return QueuingTheoryPoolSizer(config)
    elif algorithm == ScalingAlgorithm.HYBRID:
        return HybridAdaptivePoolSizer(config)
    else:
        raise ValueError(f"Unknown algorithm: {algorithm}")


# Convenience function for testing
def simulate_workload(
    sizer: PoolSizer,
    duration_seconds: int = 3600,
    base_rate: float = 0.1,
    burst_times: list[tuple[int, float, int]] = None  # (start, rate, duration)
) -> list[ScalingDecision]:
    """Simulate a workload and collect scaling decisions.

    Args:
        sizer: Pool sizer to test
        duration_seconds: Simulation duration
        base_rate: Base arrival rate (per second)
        burst_times: List of (start_time, rate_multiplier, duration) for bursts

    Returns:
        List of scaling decisions over time
    """
    import random

    burst_times = burst_times or []
    decisions = []
    current_time = 0
    metrics = ScalingMetrics(
        timestamp=0,
        arrival_rate=base_rate,
        pool_hit_rate=0.9,
        avg_latency_ms=100,
        current_ready=10,
        current_in_use=0,
        cold_start_rate=0
    )

    while current_time < duration_seconds:
        # Determine current rate
        rate = base_rate
        for start, multiplier, dur in burst_times:
            if start <= current_time < start + dur:
                rate = base_rate * multiplier
                break

        # Generate arrivals
        arrivals = random.poisson(rate)  # Poisson process
        for _ in range(arrivals):
            sizer.record_event("acquire", current_time)

        # Get scaling decision
        metrics.timestamp = current_time
        metrics.arrival_rate = rate
        decision = sizer.calculate_target(metrics)
        decisions.append(decision)

        current_time += 1  # 1 second steps

    return decisions
