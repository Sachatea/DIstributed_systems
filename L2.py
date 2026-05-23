import sys
import logging

# Налаштування логування
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s -- %(message)s',
    datefmt='%H:%M:%S.%MS' 
)
logger = logging.getLogger("MISFinder")


class Tree:
    """Дерево (неорієнтований граф без циклів) у вигляді списків суміжності."""
    def __init__(self, n: int):
        self.n = n
        self.adj = [[] for _ in range(n + 1)]

    def size(self) -> int:
        return self.n

    def add_edge(self, u: int, v: int):
        self.adj[u].append(v)
        self.adj[v].append(u)

    def neighbors(self, u: int) -> list[int]:
        return self.adj[u]


class MISResult:
    """Результат обчислення MIS."""
    def __init__(self, max_size: int, node_set: list[int]):
        self.max_size = max_size
        self.set = node_set


class MISFinder:
    """Пошук Maximum Independent Set (MIS) у дереві за O(|V|+|E|)."""
    def __init__(self, tree: Tree, root: int):
        self.tree = tree
        self.root = root
        self.include = []
        self.exclude = []

    def solve(self) -> MISResult:
        n = self.tree.size()
        self.include = [0] * (n + 1)
        self.exclude = [0] * (n + 1)

        logger.info(f"Початок пошуку MIS у дереві. Корінь (root) = {self.root}")

        # 1) DP-обчислення (DFS знизу-вгору)
        self._dfs_dp(self.root, 0)

        best = max(self.include[self.root], self.exclude[self.root])
        logger.info(f"DP завершено: include[root]={self.include[self.root]}, exclude[root]={self.exclude[self.root]}, I[root]={best}")

        # 2) Відновлення набору S
        take_root = self.include[self.root] >= self.exclude[self.root]
        node_set = []
        self._restore(self.root, 0, take_root, node_set)

        node_set.sort()

        logger.info(f"Набір S відновлено. |S| = {len(node_set)}")
        logger.info(f"S = {node_set}")

        return MISResult(best, node_set)

    def _dfs_dp(self, u: int, parent: int):
        # Базові значення
        self.include[u] = 1
        self.exclude[u] = 0

        logger.info(f"DFS u={u} (parent={parent})")

        for v in self.tree.neighbors(u):
            if v == parent:
                continue

            self._dfs_dp(v, u)

            # Формула DP
            self.include[u] += self.exclude[v]
            self.exclude[u] += max(self.include[v], self.exclude[v])

        logger.info(f"DP[u={u}]: include={self.include[u]} (беремо u), exclude={self.exclude[u]} (не беремо u), I[u]={max(self.include[u], self.exclude[u])}")

    def _restore(self, u: int, parent: int, take_u: bool, node_set: list[int]):
        if take_u:
            node_set.append(u)
            # Вмикаємо DEBUG рівень за потреби, але для ідентичності виведемо через звичайний логер
            # Якщо хочеш бачити ці повідомлення, можна замінити на logger.info
            # logger.debug(f"Включаємо u={u} у S => дітей брати НЕ можна.")
        else:
            pass
            # logger.debug(f"НЕ включаємо u={u} у S => по дітях беремо оптимум.")

        for v in self.tree.neighbors(u):
            if v == parent:
                continue

            if take_u:
                self._restore(v, u, False, node_set)
            else:
                take_v = self.include[v] >= self.exclude[v]
                self._restore(v, u, take_v, node_set)


def main():
    # Швидке зчитування всіх токенів з вводу (sys.stdin.read)
    input_data = sys.stdin.read().split()
    if not input_data:
        return

    n = int(input_data[0])
    tree = Tree(n)

    idx = 1
    # Читаємо N-1 ребер
    for _ in range(n - 1):
        u = int(input_data[idx])
        v = int(input_data[idx + 1])
        tree.add_edge(u, v)
        idx += 2

    # Перевіряємо, чи є ще один токен для кореня
    root = 1
    if idx < len(input_data):
        root = int(input_data[idx])

    # Створюємо логер і для головного модуля
    app_logger = logging.getLogger("App")
    app_logger.info(f"Вхід: N={n}, root={root}")

    finder = MISFinder(tree, root)
    res = finder.solve()

    print(f"MIS_size={res.max_size}")
    print(f"MIS_nodes={res.set}")


if __name__ == "__main__":
    main()

#python3 L2.py < input2.txt
