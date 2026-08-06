"""并发测试：验证 CircuitBreaker 加锁后线程安全"""
import threading
from maref.governance.circuit_breaker import CircuitBreaker, BreakerState

def test_concurrent_check_depth():
    """10 线程同时检查深度触发 trip"""
    cb = CircuitBreaker(max_depth=3)
    n_threads = 10
    barrier = threading.Barrier(n_threads)
    results = []
    errors = []

    def worker():
        barrier.wait()
        try:
            results.append(cb.check_depth(10))
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert all(r is False for r in results), f"expected all False, got {results}"
    stats = cb.get_stats()
    assert stats["state"] == "open"
    assert stats["trip_count"] >= 1
    assert len(errors) == 0
    print(f"✅ concurrent_check_depth: state={stats['state']} trip_count={stats['trip_count']}")

def test_concurrent_record_failure():
    """10 线程并发记录失败，验证 trip 正确触发"""
    cb = CircuitBreaker(max_consecutive_failures=3)
    n_threads = 10
    barrier = threading.Barrier(n_threads)
    errors = []

    def worker():
        barrier.wait()
        try:
            for _ in range(5):
                cb.record_failure()
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    stats = cb.get_stats()
    # Many trips should have happened (failure_count stays 0 after each trip)
    assert stats["trip_count"] >= (n_threads * 5) // 3, f"expected >= {n_threads * 5 // 3}, got {stats['trip_count']}"
    assert stats["failure_count"] < 3, f"failure_count should be < 3, got {stats['failure_count']}"
    assert len(errors) == 0
    print(f"✅ concurrent_record_failure: trip_count={stats['trip_count']} failure_count={stats['failure_count']}")

def test_concurrent_recovery():
    """验证 HALF_OPEN → CLOSED 恢复路径线程安全"""
    cb = CircuitBreaker(max_depth=5, cooldown_seconds=.01)
    # First, trip the breaker
    cb.check_depth(10)
    assert cb.is_open

    # Wait for cooldown + jitter
    import time
    time.sleep(0.1)

    # Concurrent recovery attempts
    n_threads = 5
    barrier = threading.Barrier(n_threads)
    errors = []

    def worker():
        barrier.wait()
        try:
            cb.check_depth(1)  # should succeed and set HALF_OPEN then CLOSED
            cb.record_success()
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert cb.state == BreakerState.CLOSED, f"should be CLOSED, got {cb.state}"
    assert len(errors) == 0
    print(f"✅ concurrent_recovery: state={cb.state.value}")

def test_concurrent_mixed():
    """混合读写：状态检查 + 失败记录同时运行"""
    cb = CircuitBreaker(max_consecutive_failures=5000)
    n_threads = 10
    barrier = threading.Barrier(n_threads)
    errors = []

    def reader():
        barrier.wait()
        try:
            for _ in range(200):
                cb.state
                cb.is_open
                cb.get_stats()
                cb.get_config()
                cb.check_depth(1)
                cb.check_oscillation(1.0, 0, "CLOSED")
        except Exception as e:
            errors.append(e)

    def writer():
        barrier.wait()
        try:
            for _ in range(200):
                cb.record_failure()
        except Exception as e:
            errors.append(e)

    threads = []
    for i in range(5):
        threads.append(threading.Thread(target=reader))
        threads.append(threading.Thread(target=writer))

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"errors={errors}"
    stats = cb.get_stats()
    print(f"✅ concurrent_mixed: all done (failures={stats['failure_count']}, trips={stats['trip_count']})")

if __name__ == "__main__":
    test_concurrent_check_depth()
    test_concurrent_record_failure()
    test_concurrent_recovery()
    test_concurrent_mixed()
    print("\n🎉 All CircuitBreaker concurrent tests passed!")
