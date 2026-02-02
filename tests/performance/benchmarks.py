"""
Performance benchmarks for GS1 Parser.
"""

import time
import statistics
from typing import List, Tuple

from gs1_parser import parse_gs1, ParseOptions


def benchmark(func, iterations: int = 1000) -> Tuple[float, float, float]:
    """
    Run a benchmark and return timing statistics.
    
    Returns:
        (mean_ms, min_ms, max_ms)
    """
    times = []
    
    for _ in range(iterations):
        start = time.perf_counter()
        func()
        elapsed = time.perf_counter() - start
        times.append(elapsed * 1000)  # Convert to ms
    
    return (
        statistics.mean(times),
        min(times),
        max(times)
    )


def run_benchmarks():
    """Run all benchmarks and print results."""
    print("=" * 60)
    print("GS1 Parser Benchmarks")
    print("=" * 60)
    print()
    
    # Test inputs
    test_cases = [
        ("Simple GTIN", "0106285096000842"),
        ("GTIN + Expiry", "0106285096000842172901"),
        ("GTIN + Batch (variable)", "010628509600084210BATCH123"),
        ("Multiple fixed AIs", "01062850960008421729013111290115"),
        ("With GS separators", "010628509600084210ABC\x1d17290131\x1d21XYZ"),
        ("Complex real-world", "]d2010611800002210721NWHFG1H8HN5P95\x1d17270301\x1d10250987"),
    ]
    
    print("Fast-path parsing (well-formed inputs):")
    print("-" * 60)
    
    for name, input_str in test_cases:
        mean, min_t, max_t = benchmark(
            lambda s=input_str: parse_gs1(s),
            iterations=1000
        )
        print(f"  {name:30} {mean:8.3f}ms avg ({min_t:.3f}-{max_t:.3f})")
    
    print()
    print("Solver parsing (ambiguous inputs):")
    print("-" * 60)
    
    ambiguous_cases = [
        ("Missing separator (short)", "010628509600084210ABC17290131"),
        ("Missing separator (long)", "0106285096000842101234567890123456789017290131"),
    ]
    
    options = ParseOptions(allow_ambiguous=True, max_alternatives=5)
    
    for name, input_str in ambiguous_cases:
        mean, min_t, max_t = benchmark(
            lambda s=input_str: parse_gs1(s, options=options),
            iterations=100
        )
        print(f"  {name:30} {mean:8.3f}ms avg ({min_t:.3f}-{max_t:.3f})")
    
    print()
    print("Throughput test (1000 iterations):")
    print("-" * 60)
    
    # Use a realistic complex input
    complex_input = "]d2010611800002210721SERIAL123\x1d17270301\x1d10BATCH456"
    
    start = time.perf_counter()
    for _ in range(1000):
        parse_gs1(complex_input)
    total = time.perf_counter() - start
    
    throughput = 1000 / total
    print(f"  Throughput: {throughput:.0f} parses/second")
    print(f"  Total time: {total:.3f}s for 1000 parses")
    
    print()
    print("=" * 60)


if __name__ == "__main__":
    run_benchmarks()
