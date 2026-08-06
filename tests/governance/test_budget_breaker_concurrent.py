"""并发测试：验证 BudgetBreaker 加锁后线程安全"""
import threading
from maref.governance.budget_breaker import BudgetBreaker

def test_concurrent_record_spend():
    """10 线程并发写入 1000 次，总和应精确 = 10000"""
    bb = BudgetBreaker(max_per_agent=1_000_000)
    n_threads = 10
    n_ops = 1000
    barrier = threading.Barrier(n_threads)
    errors = []

    def worker(agent_id: str, task_id_prefix: str):
        barrier.wait()
        try:
            for i in range(n_ops):
                bb.record_spend(agent_id, f"{task_id_prefix}-{i}", 1.0)
        except Exception as e:
            errors.append(e)

    threads = []
    for i in range(n_threads):
        t = threading.Thread(target=worker, args=(f"agent-{i}", f"task-{i}"))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    total = 0
    for i in range(n_threads):
        aid = f"agent-{i}"
        spent = bb.get_agent_spend(aid)
        total += spent
        assert spent == float(n_ops), f"{aid} spend={spent} expected={n_ops}"
        stats = bb.get_stats(aid)
        assert stats["total_spend"] == float(n_ops)

    assert total == float(n_threads * n_ops), f"total={total} expected={n_threads * n_ops}"
    assert len(errors) == 0, f"errors={errors}"
    print(f"✅ concurrent_record_spend: total={total} OK")

def test_concurrent_state_transition():
    """10 线程并发检查预算 + Trip，验证状态机线程安全"""
    bb = BudgetBreaker(max_per_agent=100.0)
    n_threads = 10
    barrier = threading.Barrier(n_threads)
    results = []
    errors = []

    def worker(agent_id: str):
        barrier.wait()
        try:
            ok = bb.check_agent_budget(agent_id, 150.0)
            results.append(ok)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=("shared-agent",)) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert all(r is False for r in results), f"expected all False, got {results}"
    stats = bb.get_stats("shared-agent")
    assert stats["state"] == "open"
    assert stats["trip_count"] >= 1
    assert len(errors) == 0
    print(f"✅ concurrent_state_transition: state={stats['state']} trip_count={stats['trip_count']}")

def test_concurrent_mixed():
    """混合读写：5 读 + 5 写同时运行"""
    bb = BudgetBreaker(max_per_agent=1_000_000)
    n_workers = 10
    barrier = threading.Barrier(n_workers)
    errors = []

    def reader(agent_id: str):
        barrier.wait()
        try:
            for _ in range(500):
                bb.get_agent_spend(agent_id)
                bb.get_stats(agent_id)
                bb.is_open(agent_id)
                bb.check_burn_rate(agent_id)
        except Exception as e:
            errors.append(e)

    def writer(agent_id: str):
        barrier.wait()
        try:
            for i in range(500):
                bb.record_spend(agent_id, f"{agent_id}-task-{i}", 1.0)
        except Exception as e:
            errors.append(e)

    threads = []
    for i in range(5):
        threads.append(threading.Thread(target=reader, args=(f"r-agent-{i}",)))
        threads.append(threading.Thread(target=writer, args=(f"w-agent-{i}",)))

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"errors={errors}"
    for i in range(5):
        assert bb.get_agent_spend(f"w-agent-{i}") == 500.0, f"w-agent-{i} data lost"
    print(f"✅ concurrent_mixed: all reads/writes completed without error")

if __name__ == "__main__":
    test_concurrent_record_spend()
    test_concurrent_state_transition()
    test_concurrent_mixed()
    print("\n🎉 All concurrent tests passed!")
