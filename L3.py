import asyncio
import sys
import math
from dataclasses import dataclass
from typing import List

# --- 1. КЛАС РЕЗУЛЬТАТУ ОБЧИСЛЕНЬ ---
@dataclass
class MISResult:
    mis: List[int]
    stages: int
    rounds: int
    messages: int

# --- 2. СТРУКТУРА ДАНИХ ГРАФА ---
class Graph:
    def __init__(self, n: int):
        if n <= 0:
            raise ValueError("Кількість вершин N має бути додатною")
        self._n = n
        self._m = 0
        self.adj = [[] for _ in range(n + 1)]

    def n(self) -> int:
        return self._n

    def m(self) -> int:
        return self._m

    def add_edge(self, u: int, v: int):
        if u < 1 or u > self._n or v < 1 or v > self._n:
            raise ValueError("Вершини повинні бути в діапазоні від 1 до N")
        if u == v:
            return
        self.adj[u].append(v)
        self.adj[v].append(u)
        self._m += 1

    def neighbors(self, u: int) -> List[int]:
        return self.adj[u]

# --- 3. ДЕТЕРМІНОВАНИЙ ГЕНЕРАТОР ХЕШІВ ---
def mix64(z: int) -> int:
    MASK = 0xFFFFFFFFFFFFFFFF
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK
    z = z ^ (z >> 31)
    return z

def deterministic_val(seed: int, stage: int, u: int) -> float:
    MASK = 0xFFFFFFFFFFFFFFFF
    C1 = 0x9E3779B97F4A7C15
    C2 = 0xBF58476D1CE4E5B9

    x = seed
    x = (x ^ (stage * C1)) & MASK
    x = (x ^ (u * C2)) & MASK

    m = mix64(x)
    top53 = (m >> 11) & ((1 << 53) - 1)
    return top53 / float(1 << 53)

# --- 4. НАДІЙНИЙ БАР'ЄР З ЗАТВОРКАМИ ПОКОЛІНЬ (GENERATION-BASED BARRIER) ---
class GenerationBarrier:
    """
    Повноцінний бар'єр, стійкий до швидких циклічних перезапусків.
    Звільняє потоки тільки у межах своєї поточної фази (покоління).
    """
    def __init__(self, parties: int):
        self.parties = parties
        self.count = 0
        self.generation = 0
        self.cond = asyncio.Condition()

    async def wait(self):
        async with self.cond:
            local_gen = self.generation
            self.count += 1
            if self.count == self.parties:
                # Останній потік відкриває затвор та перемикає покоління
                self.count = 0
                self.generation += 1
                self.cond.notify_all()
            else:
                # Всі інші чекають, поки поточне покоління не зміниться
                while local_gen == self.generation:
                    await self.cond.wait()

# --- 5. ГОЛОВНИЙ КЛАС АЛГОРИТМУ ЛЮБІ ---
class LubyMIS:
    def __init__(self, g: Graph, threads: int, seed: int):
        self.g = g
        self.n = g.n()
        self.threads = max(1, threads)
        self.seed = seed

        self.active = [1] * (self.n + 1)
        self.winner = [0] * (self.n + 1)
        self.remove = [0] * (self.n + 1)
        self.val = [0.0] * (self.n + 1)
        self.messages = 0

    async def _worker_task(self, start: int, end: int, barriers: list, stage_info: dict):
        try:
            while stage_info["running"]:
                stage_no = stage_info["stage_no"]

                # ---------- Раунд 1: Розрахунок пріоритетів ----------
                for u in range(start, end + 1):
                    if self.active[u] == 1:
                        self.val[u] = deterministic_val(self.seed, stage_no, u)
                    else:
                        self.val[u] = -1.0
                
                await barriers[0].wait()  # Бар'єр після Раунду 1

                # ---------- Раунд 2: Локальні максимуми ----------
                for u in range(start, end + 1):
                    if self.active[u] == 0:
                        continue
                    
                    is_winner = True
                    vu = self.val[u]
                    
                    for v in self.g.neighbors(u):
                        if self.active[v] == 0:
                            continue
                        
                        self.messages += 1
                        vv = self.val[v]
                        
                        if vv > vu or (math.isclose(vv, vu) and v > u):
                            is_winner = False
                            break
                    
                    self.winner[u] = 1 if is_winner else 0

                await barriers[1].wait()  # Бар'єр після Раунду 2

                # ---------- Раунд 3: Маркування на видалення ----------
                for u in range(start, end + 1):
                    if self.active[u] == 0:
                        continue
                    
                    if self.winner[u] == 1:
                        self.remove[u] = 1
                        for v in self.g.neighbors(u):
                            if self.active[v] == 1:
                                self.remove[v] = 1
                                self.messages += 1

                await barriers[2].wait()  # Бар'єр після Раунду 3 (очікування головного циклу)
        except asyncio.CancelledError:
            pass

    def any_active(self) -> bool:
        for u in range(1, self.n + 1):
            if self.active[u] == 1:
                return True
        return False

    async def solve(self) -> MISResult:
        mis = []
        stages = 0
        rounds = 0

        block = (self.n + self.threads - 1) // self.threads
        stage_info = {"running": True, "stage_no": 1}
        
        blocks_ranges = []
        for t in range(self.threads):
            start = 1 + t * block
            end = min(self.n, (t + 1) * block)
            if start <= end:
                blocks_ranges.append((start, end))

        worker_count = len(blocks_ranges)
        # 3 надійні бар'єри (кількість воркерів + 1 керуючий потік)
        barriers = [GenerationBarrier(worker_count + 1) for _ in range(3)]

        workers = []
        for start, end in blocks_ranges:
            task = asyncio.create_task(self._worker_task(start, end, barriers, stage_info))
            workers.append(task)

        while self.any_active():
            stages += 1
            stage_info["stage_no"] = stages

            for i in range(1, self.n + 1):
                self.winner[i] = 0
                self.remove[i] = 0

            # Синхронно штовхаємо раунди
            await barriers[0].wait()
            rounds += 1

            await barriers[1].wait()
            rounds += 1

            await barriers[2].wait()
            rounds += 1

            # Опрацювання результатів поточного етапу
            winners_list = []
            removed_list = []

            for u in range(1, self.n + 1):
                if self.active[u] == 1 and self.winner[u] == 1:
                    mis.append(u)
                    winners_list.append(u)

            for u in range(1, self.n + 1):
                if self.remove[u] == 1 and self.active[u] == 1:
                    self.active[u] = 0
                    removed_list.append(u)

            winners_list.sort()
            removed_list.sort()
            active_now = [u for u in range(1, self.n + 1) if self.active[u] == 1]
            mis_so_far = sorted(mis.copy())

            print(f"[Stage {stages}]")
            print(f"  winners(I')={winners_list}")
            print(f"  removed={removed_list}")
            print(f"  active_left={len(active_now)} {active_now}")
            print(f"  MIS_so_far={len(mis_so_far)} {mis_so_far}\n")

        stage_info["running"] = False
        for w in workers:
            w.cancel()
        await asyncio.gather(*workers, return_exceptions=True)

        mis.sort()
        return MISResult(mis, stages, rounds, self.messages)

# --- 6. ВАЛІДАТОР МНОЖИНИ ---
def verify_independent(g: Graph, mis: List[int]):
    in_mis = [False] * (g.n() + 1)
    for u in mis:
        in_mis[u] = True

    for u in range(1, g.n() + 1):
        for v in g.neighbors(u):
            if u < v and in_mis[u] and in_mis[v]:
                raise RuntimeError(f"Помилка! Множина НЕ є незалежною: ребро ({u},{v}) всередині MIS")

# --- 7. ТОЧКА ВХОДУ ---
async def main():
    threads = 4
    seed = 42

    print("Запуск алгоритму Любі на демо-графі (6 вершин, 7 ребер)...")
    g = Graph(6)
    g.add_edge(1, 2)
    g.add_edge(2, 3)
    g.add_edge(3, 4)
    g.add_edge(4, 5)
    g.add_edge(5, 6)
    g.add_edge(1, 6)
    g.add_edge(2, 5)

    solver = LubyMIS(g, threads, seed)
    res = await solver.solve()

    print("========================================")
    print("Luby MIS (Maximal Independent Set)")
    print(f"Graph: N={g.n()}, M={g.m()}")
    print(f"Threads={threads}, Seed={seed}")
    print("----------------------------------------")
    print(f"MIS_size={len(res.mis)}")
    print(f"MIS_nodes={res.mis}")
    print("----------------------------------------")
    print(f"stages={res.stages}")
    print(f"rounds={res.rounds} (3 per stage)")
    print(f"messages={res.messages} (approx. neighbor inspections/notifications)")
    print("========================================")

    verify_independent(g, res.mis)
    print("Перевірка інваріанта незалежності пройдена успішно! ✓")

if __name__ == "__main__":
    asyncio.run(main())