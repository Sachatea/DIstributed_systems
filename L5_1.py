import threading
import time
from concurrent.futures import ThreadPoolExecutor

# Значення «нескінченність»
INF = 9223372036854775807 // 2


class AtomicLong:
    def __init__(self, initial_value=0):
        self._value = initial_value
        self._lock = threading.Lock()

    def get(self):
        with self._lock:
            return self._value

    def compare_and_set(self, expect, update):
        with self._lock:
            if self._value == expect:
                self._value = update
                return True
            return False


class Graph:
    """Структура орієнтованого зваженого графа."""
    def __init__(self, size):
        self._size = size
        self._out_edges = [[] for _ in range(size)]  # Вихідні ребра [to, weight]
        self._in_edges = [[] for _ in range(size)]   # Вхідні ребра [from, weight]
        self._edge_count = 0

    def size(self):
        return self._size

    def add_directed_edge(self, from_v, to_v, weight):
        self._out_edges[from_v].append([to_v, weight])
        self._in_edges[to_v].append([from_v, weight])
        self._edge_count += 1

    def get_in_edges(self, v):
        return self._in_edges[v]


class ShortestPath:
    """Реалізація паралельного алгоритму Single-Source Shortest Path (Bellman-Ford)."""
    
    @staticmethod
    def compute(graph, source, num_threads):
        n = graph.size()

        # 1. Ініціалізація вектора відстаней D потокобезпечними обгортками
        D = [AtomicLong(0 if i == source else INF) for i in range(n)]

        print(f"=== ЗАПУСК PARALLEL BELLMAN-FORD ===")
        print(f"Кількість вершин: {n}, Кількість потоків: {num_threads}")
        print(f"Початкові відстані D: {ShortestPath._format_d(D, n)}")
        print("-" * 50)

        # 2. Статичний розподіл вершин між потоками (Static Partitioning)
        partitions = ShortestPath._build_partitions(n, num_threads)
        for t in range(num_threads):
            print(f"Потік {t:2} обробляє вершини: {ShortestPath._format_partition(partitions[t])}")
        print("-" * 50)

        iter_counter = [0]
        iter_lock = threading.Lock()

        # Бар'єрна дія (виконується останнім потоком, що прийшов на бар'єр в кінці ітерації)
        def barrier_action():
            with iter_lock:
                iter_counter[0] += 1
                curr_iter = iter_counter[0]
            print(f"Ітерація {curr_iter:3}/{n}: D = {ShortestPath._format_d(D, n)}")

        # Синхронізаційний бар'єр для потоків
        barrier = threading.Barrier(num_threads, action=barrier_action)

        # 3. Робоча функція для кожного потоку
        def worker(thread_id, my_vertices):
            try:
                # Алгоритм Беллмана-Форда вимагає рівно |V| ітерацій для гарантованої збіжності
                for _ in range(n):
                    
                    # Релаксація для кожної вершини v, закріпленої за потоком
                    for v in my_vertices:
                        for edge in graph.get_in_edges(v):
                            w = edge[0]
                            weight = edge[1]
                            
                            dw = D[w].get()  # Атомарне зчитування відстані до сусіда
                            if dw < INF:
                                # Виконуємо потокобезпечну мінімізацію (CAS-loop)
                                ShortestPath._atomic_min(D[v], dw + weight)

                    # Очікуємо завершення поточної ітерації релаксації всіма потоками
                    barrier.wait()
            except threading.BrokenBarrierError:
                print(f"[Потік {thread_id}] Помилка: Бар'єр зламано.")

        # 4. Запуск пулу потоків
        start_time = time.time()
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            for t in range(num_threads):
                executor.submit(worker, t, partitions[t])
        end_time = time.time()

        print("-" * 50)
        print(f"Розрахунок завершено за {iter_counter[0]} ітерацій.")
        print(f"Час виконання: {(end_time - start_time) * 1000:.2f} мс")

        # Повертаємо фінальні відстані у вигляді звичайного списку чисел
        return [D[i].get() for i in range(n)]

    @staticmethod
    def _atomic_min(atomic_long, value):
        """Реалізація CAS-loop (Compare-And-Swap) для знаходження мінімуму."""
        while True:
            current = atomic_long.get()
            if current <= value:
                return  # Поточне значення вже краще або рівне, виходимо
            if atomic_long.compare_and_set(current, value):
                return  # Успішно оновили значення, виходимо

    @staticmethod
    def _build_partitions(n, num_threads):
        """Рівномірно розподіляє вершини графа між обчислювальними потоками."""
        parts = [[] for _ in range(num_threads)]
        base = n // num_threads
        extra = n % num_threads
        
        start = 0
        for t in range(num_threads):
            size = base + (1 if t < extra else 0)
            parts[t] = list(range(start, start + size))
            start += size
        return parts

    @staticmethod
    def _format_d(D, n):
        res = []
        for i in range(n):
            v = D[i].get()
            res.append("∞" if v >= INF else str(v))
        return "[" + ", ".join(res) + "]"

    @staticmethod
    def _format_partition(arr):
        if not arr:
            return "{}"
        return "{" + ", ".join(map(str, arr)) + "}"


# ─── ДЕМОНСТРАЦІЙНИЙ ЗАПУСК ──────────────────────────────────────────
if __name__ == "__main__":
    # Створимо тестовий граф з 6 вершин (0-5)
    # Структура взята для наочної демонстрації покрокової релаксації
    g = Graph(6)
    g.add_directed_edge(0, 1, 4)   # 0 -> 1 (вага 4)
    g.add_directed_edge(0, 2, 2)   # 0 -> 2 (вага 2)
    g.add_directed_edge(1, 3, 2)   # 1 -> 3 (вага 2)
    g.add_directed_edge(2, 1, 1)   # 2 -> 1 (вага 1)
    g.add_directed_edge(2, 3, 4)   # 2 -> 3 (ваga 4)
    g.add_directed_edge(2, 4, 5)   # 2 -> 4 (вага 5)
    g.add_directed_edge(3, 5, 2)   # 3 -> 5 (вага 2)
    g.add_directed_edge(4, 5, -2)  # 4 -> 5 (вага -2, граф підтримує від'ємні ваги!)

    # Запускаємо алгоритм з вершини 0, використовуючи 3 паралельні потоки
    source_vertex = 0
    threads_count = 3
    
    final_distances = ShortestPath.compute(g, source_vertex, threads_count)
    
    print("\n=== ФІНАЛЬНИЙ РЕЗУЛЬТАТ ===")
    for vertex, dist in enumerate(final_distances):
        print(f"Найкоротша відстань від вершини {source_vertex} до {vertex} = {dist}")