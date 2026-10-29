"""Deterministic moving-block bootstrap for descriptive expectancy intervals."""

import random
from decimal import Decimal
from math import floor
from typing import Sequence

from tradepilot.reporting.canonical import sha256_hex
from tradepilot.validation.models import BootstrapInterval, UncertaintyStatus


def moving_block_bootstrap(
    outcomes: Sequence[Decimal], *, block_length: int = 5,
    resamples: int = 1000, minimum_trades: int = 30,
    seed_material: str = "tradepilot-bootstrap",
) -> BootstrapInterval:
    values = tuple(outcomes)
    if block_length <= 0 or resamples <= 0 or minimum_trades <= 0:
        raise ValueError("bootstrap policy values must be positive")
    if len(values) < minimum_trades or len(values) < block_length:
        return BootstrapInterval(UncertaintyStatus.INSUFFICIENT_SAMPLE, None, None, len(values), block_length, resamples)
    seed = int(sha256_hex(seed_material.encode("utf-8")), 16)
    generator = random.Random(seed)
    means = []
    for _ in range(resamples):
        sample = []
        while len(sample) < len(values):
            start = generator.randrange(len(values))
            sample.extend(values[(start + offset) % len(values)] for offset in range(block_length))
        sample = sample[:len(values)]
        means.append(sum(sample, Decimal(0)) / Decimal(len(sample)))
    means.sort()
    lower_index = floor(Decimal("0.025") * Decimal(resamples - 1))
    upper_index = floor(Decimal("0.975") * Decimal(resamples - 1))
    return BootstrapInterval(
        UncertaintyStatus.DEFINED, means[lower_index], means[upper_index],
        len(values), block_length, resamples,
    )
