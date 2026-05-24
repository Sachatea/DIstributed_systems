import threading
import time
from concurrent.futures import ThreadPoolExecutor

class Vertex:
    """Клас вершини графа для алгоритму кольорування."""
    def __init__(self, vertex_id, initial_color):
        self.id = vertex_id
        self.color = initial_color
        self.lock = threading.Lock()  # Індивідуальний замок для кожної вершини
        self.neighbors = []           # Список суміжних вершин (об'єктів Vertex)

    def add_neighbor(self, neighbor_vertex):
        if neighbor_vertex not in self.neighbors:
            self.neighbors.append(neighbor_vertex)


class GraphColoring:
    """Реалізація паралельного алгоритму мінімізації кольорів графа."""
    
    @staticmethod
    def compute(vertices, num_threads, max_rounds=20):
        n = len(vertices)
        partitions = GraphColoring._build_partitions(vertices, num_threads)
        
        print(f"=== ЗАПУСК PARALLEL GRAPH COLORING ===")
        print(f"Кількість вершин: {n}, Кількість потоків: {num_threads}")
        print(f"Початкові кольори: {GraphColoring._get_colors_str(vertices)}")
        print("-" * 60)
        
        for t in range(num_threads):
            v_ids = [v.id for v in partitions[t]]
            print(f"Потік {t:2} обробляє вершини: {v_ids}")
        print("-" * 60)

        # Прапорець, який вказує, чи відбулися зміни бодай десь у графі
        global_changed = True
        round_counter = 0

        # Головний ітераційний цикл мінімізації
        while global_changed and round_counter < max_rounds:
            round_counter += 1
            # Локальні змінні для фіксації змін на цьому раунді
            changes_in_round = [False] * num_threads

            def worker(thread_id, my_vertices):
                thread_changed = False
                
                for v in my_vertices:
                    # 1. Протокол Lock Ordering для уникнення Deadlock:
                    # Сортуємо вершину та її сусідів за зростанням їхніх ID
                    locked_nodes = sorted([v] + v.neighbors, key=lambda x: x.id)
                    
                    # Послідовно захоплюємо замки у строго визначеному порядку
                    for node in locked_nodes:
                        node.lock.acquire()
                    
                    try:
                        # 2. Збираємо кольори, які зараз зайняті сусідами
                        used_colors = set(neighbor.color for neighbor in v.neighbors)
                        
                        # 3. Шукаємо мінімальний доступний колір, починаючи з 0
                        min_avail_color = 0
                        while min_avail_color in used_colors:
                            min_avail_color += 1
                        
                        # 4. Якщо знайшли колір менший за поточний — оновлюємо
                        if min_avail_color < v.color:
                            v.color = min_avail_color
                            thread_changed = True
                            
                    finally:
                        # Звільняємо замки у зворотному порядку
                        for node in reversed(locked_nodes):
                            node.lock.release()
                
                changes_in_round[thread_id] = thread_changed

            # Запускаємо потоки для виконання одного раунду мінімізації
            with ThreadPoolExecutor(max_workers=num_threads) as executor:
                for t in range(num_threads):
                    executor.submit(worker, t, partitions[t])

            # Перевіряємо, чи оновився хоч один колір під час цього раунду
            global_changed = any(changes_in_round)
            print(f"Раунд {round_counter:2}: кольори = {GraphColoring._get_colors_str(vertices)} | Зміни: {global_changed}")

        print("-" * 60)
        print(f"Розрахунок завершено за {round_counter} раундів.")
        return round_counter

    @staticmethod
    def _build_partitions(vertices, num_threads):
        """Рівномірний статичний розподіл об'єктів вершин між потоками."""
        n = len(vertices)
        parts = [[] for _ in range(num_threads)]
        base = n // num_threads
        extra = n % num_threads
        
        start = 0
        for t in range(num_threads):
            size = base + (1 if t < extra else 0)
            parts[t] = vertices[start:start + size]
            start += size
        return parts

    @staticmethod
    def _get_colors_str(vertices):
        colors = [v.color for v in sorted(vertices, key=lambda x: x.id)]
        unique_colors_count = len(set(colors))
        return f"{colors} ({unique_colors_count} кольорів)"


# ─── ДЕМОНСТРАЦІЙНИЙ ЗАПУСК ──────────────────────────────────────────
if __name__ == "__main__":
    # Створюємо граф з 8 вершин (0-7).
    # Задаємо їм найгірше початкове кольорування (кожна вершина має унікальний великий колір)
    num_vertices = 8
    vertices = [Vertex(i, initial_color=i) for i in range(num_vertices)]
    
    # Побудуємо зв'язки (двонаправлені ребра) для демонстраційного графа
    edges = [
        (0, 1), (0, 2), (1, 2), (1, 3), 
        (2, 4), (3, 4), (3, 5), (4, 6), 
        (5, 6), (5, 7), (6, 7)
    ]
    
    for u, v in edges:
        vertices[u].add_neighbor(vertices[v])
        vertices[v].add_neighbor(vertices[u])

    threads_count = 3
    
    start_time = time.time()
    total_rounds = GraphColoring.compute(vertices, threads_count)
    end_time = time.time()
    
    print(f"Час виконання алгоритму: {(end_time - start_time) * 1000:.2f} мс")

    # Перевірка на локальну оптимальність та відсутність конфліктів
    valid = True
    for v in vertices:
        for neighbor in v.neighbors:
            if v.color == neighbor.color:
                valid = False
                
    print("\n=== ФІНАЛЬНИЙ ВЕРИФІКАТОР ===")
    print(f"Граф зафарбовано коректно (немає суміжних вершин одного кольору): {valid}")
    unique_colors = set(v.color for v in vertices)
    print(f"Використано всього кольорів: {len(unique_colors)} (а саме: {list(unique_colors)})")