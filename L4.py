import threading
import time
import random
from datetime import datetime

# ==============================================================================
# Потокобезпечний логер (Logger)
# ==============================================================================
class Logger:
    _lock = threading.Lock()

    @classmethod
    def log(cls, philosopher_id: int, msg: str):
        with cls._lock:
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            print(f"[{timestamp}] P{philosopher_id} | {msg}")

    @classmethod
    def info(cls, msg: str):
        with cls._lock:
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            print(f"[{timestamp}] {msg}")

# ==============================================================================
# Кастомний лічильний семафор (CustomSemaphore) на базі Condition (wait/notify)
# ==============================================================================
class CustomSemaphore:
    def __init__(self, initial_permits: int):
        if initial_permits < 0:
            raise ValueError("permits must be >= 0")
        self._permits = initial_permits
        self._condition = threading.Condition()

    def acquire(self, on_acquired_callback=None):
        with self._condition:
            while self._permits == 0:
                self._condition.wait()
            self._permits -= 1
            if on_acquired_callback:
                on_acquired_callback(self._permits)
            return self._permits

    def try_acquire(self) -> bool:
        with self._condition:
            if self._permits > 0:
                self._permits -= 1
                return True
            return False

    def release(self, on_released_callback=None):
        with self._condition:
            self._permits += 1
            if on_released_callback:
                on_released_callback(self._permits)
            self._condition.notify_all()
            return self._permits

# ==============================================================================
# ВАРІАНТ 1: Виделка-Монітор (ForkMonitor)
# ==============================================================================
class ForkMonitor:
    def __init__(self, fork_id: int):
        self._id = fork_id
        self._taken = False
        self._condition = threading.Condition()

    def id(self) -> int:
        return self._id

    def pick_up(self):
        with self._condition:
            while self._taken:
                self._condition.wait()
            self._taken = True

    def put_down(self):
        with self._condition:
            self._taken = False
            self._condition.notify_all()

# ==============================================================================
# ВАРІАНТ 1: Потік філософа з обмеженням кімнати (PhilosopherRoom)
# ==============================================================================
class PhilosopherRoom(threading.Thread):
    def __init__(self, philosopher_id: int, left: ForkMonitor, right: ForkMonitor, room: CustomSemaphore, iterations: int):
        super().__init__(name=f"P{philosopher_id}")
        self._id = philosopher_id
        self._left = left
        self._right = right
        self._room = room
        self._iterations = iterations

    def run(self):
        try:
            for i in range(1, self._iterations + 1):
                self._think()

                Logger.log(self._id, f"wants to eat (iteration {i})")
                
                # Обмеження кімнати атомарно логує залишок дозволів
                self._room.acquire(
                    lambda p: Logger.log(self._id, f"entered room (room permits left={p})")
                )

                # Наївне взяття: спочатку ліва, потім права. Дедлок неможливий через room = N-1
                self._left.pick_up()
                Logger.log(self._id, f"picked LEFT fork {self._left.id()}")

                self._right.pick_up()
                Logger.log(self._id, f"picked RIGHT fork {self._right.id()}")

                self._eat()

                self._right.put_down()
                Logger.log(self._id, f"put down RIGHT fork {self._right.id()}")

                self._left.put_down()
                Logger.log(self._id, f"put down LEFT fork {self._left.id()}")

                self._room.release(
                    lambda p: Logger.log(self._id, f"left room (room permits left={p})")
                )
        except Exception as e:
            Logger.log(self._id, f"interrupted/error: {str(e)}")

    def _think(self):
        Logger.log(self._id, "thinking...")
        time.sleep(random.randint(30, 120) / 1000.0)

    def _eat(self):
        Logger.log(self._id, "EATING")
        time.sleep(random.randint(30, 120) / 1000.0)

# ==============================================================================
# ВАРІАНТ 2: Виделка-Семафор (ForkSemaphore)
# ==============================================================================
class ForkSemaphore:
    def __init__(self, fork_id: int):
        self._id = fork_id
        self._sem = CustomSemaphore(1)

    def id(self) -> int:
        return self._id

    def try_acquire(self) -> bool:
        return self._sem.try_acquire()

    def release(self):
        self._sem.release()

# ==============================================================================
# ВАРІАНТ 2: Потік філософа з Мутексом та Відкатом (PhilosopherMutexForks)
# ==============================================================================
class PhilosopherMutexForks(threading.Thread):
    def __init__(self, philosopher_id: int, left: ForkSemaphore, right: ForkSemaphore, mutex: CustomSemaphore, iterations: int):
        super().__init__(name=f"P{philosopher_id}")
        self._id = philosopher_id
        self._left = left
        self._right = right
        self._mutex = mutex
        self._iterations = iterations

    def run(self):
        try:
            for i in range(1, self._iterations + 1):
                self._think()

                Logger.log(self._id, f"wants to eat (iteration {i})")

                self._start_main_cycle()

                # Сюди потрапляємо утримуючи обидві виделки. Мутекс відпускаємо тільки зараз.
                self._mutex.release()

                self._eat()

                self._right.release()
                self._left.release()
                Logger.log(self._id, f"put down forks {self._left.id()} and {self._right.id()}")
        except Exception as e:
            Logger.log(self._id, f"interrupted/error: {str(e)}")

    def _start_main_cycle(self):
        while True:
            self._mutex.acquire()
            got_left = False
            got_right = False

            try:
                got_left = self._left.try_acquire()
                if got_left:
                    got_right = self._right.try_acquire()

                if got_left and got_right:
                    Logger.log(self._id, f"picked LEFT fork {self._left.id()} and RIGHT fork {self._right.id()}")
                    break  # Успіх, виделки у нас, виходимо тримаючи мутекс
            finally:
                # Якщо хоча б одну виделку не вдалося взяти — робимо відкат (backoff)
                if not (got_left and got_right):
                    if got_left:
                        self._left.release()
                    self._mutex.release()

            # Пауза (Backoff) для уникнення зациклення (Livelock)
            time.sleep(random.randint(5, 25) / 1000.0)

    def _think(self):
        Logger.log(self._id, "thinking...")
        time.sleep(random.randint(30, 120) / 1000.0)

    def _eat(self):
        Logger.log(self._id, "EATING")
        time.sleep(random.randint(30, 120) / 1000.0)

# ==============================================================================
# Головна керуюча функція (App)
# ==============================================================================
N = 5
ITERATIONS = 10

def run_variant_1():
    room = CustomSemaphore(N - 1)
    forks = [ForkMonitor(i) for i in range(N)]
    threads = []

    for i in range(N):
        left_fork = forks[i]
        right_fork = forks[(i + 1) % N]
        t = PhilosopherRoom(i, left_fork, right_fork, room, ITERATIONS)
        threads.append(t)
        t.start()

    for t in threads:
        t.join()
    Logger.info("Variant 1 finished")

def run_variant_2():
    mutex = CustomSemaphore(1)
    forks = [ForkSemaphore(i) for i in range(N)]
    threads = []

    for i in range(N):
        left_fork = forks[i]
        right_fork = forks[(i + 1) % N]
        t = PhilosopherMutexForks(i, left_fork, right_fork, mutex, ITERATIONS)
        threads.append(t)
        t.start()

    for t in threads:
        t.join()
    Logger.info("Variant 2 finished")

if __name__ == "__main__":
    Logger.info("=== Variant 1: N=5, ONE counting semaphore (room=N-1) ===")
    run_variant_1()

    time.sleep(0.4)

    Logger.info("\n=== Variant 2: N=5, mutex + five fork semaphores (custom) ===")
    run_variant_2()