import sys
from enum import Enum


class Direction(Enum):
    LEFT = 1
    RIGHT = 2

    def opposite(self):
        return Direction.RIGHT if self == Direction.LEFT else Direction.LEFT


class Message:
    """Повідомлення HS алгоритму."""
    def __init__(self, origin_id: int, phase: int, ttl: int, direction: Direction, is_reply: bool):
        self.origin_id = origin_id    # id кандидата (того, хто запустив хвилю)
        self.phase = phase            # фаза k
        self.ttl = ttl                # залишок "хопів" (тільки для OUT)
        self.direction = direction    # напрям руху цього повідомлення
        self.is_reply = is_reply      # False = OUT, True = REPLY

    def dec_ttl(self):
        """Для OUT: зменшуємо ttl при пересиланні далі"""
        return Message(self.origin_id, self.phase, self.ttl - 1, self.direction, self.is_reply)

    def __repr__(self):
        return f"Message(origin_id={self.origin_id}, phase={self.phase}, ttl={self.ttl}, dir={self.direction.name}, is_reply={self.is_reply})"


class Node:
    """Вузол у кільці."""
    def __init__(self, node_id: int):
        self.id = node_id
        self.active = True          # чи бере участь у виборах як кандидат
        self.phase = 0              # поточна фаза k
        
        # прапори "отримав відповідь" для поточної фази
        self.got_left_reply = False
        self.got_right_reply = False
        
        # для симуляції: щоб не слати OUT для однієї і тієї ж фази багато разів
        self.started_phase = -1

    def needs_to_start_current_phase(self) -> bool:
        """Чи готовий кандидат стартувати OUT для своєї поточної фази?"""
        return self.active and self.started_phase != self.phase

    def reset_replies_for_new_phase(self):
        """Скидання reply-прапорів при переході у наступну фазу"""
        self.got_left_reply = False
        self.got_right_reply = False


class RingNetwork:
    """Симуляція кільця + HS алгоритму за синхронними раундами."""
    def __init__(self, ids: list[int]):
        self._validate_unique(ids)
        
        self.nodes = [Node(node_id) for node_id in ids]
        self.n = len(self.nodes)
        
        self.inbox = self._new_empty_boxes()
        self.outbox = self._new_empty_boxes()
        
        self.total_messages_sent = 0
        self.rounds = 0
        self.leader_id = None

    def _validate_unique(self, ids: list[int]):
        if len(set(ids)) != len(ids):
            raise ValueError("All node IDs must be unique for HS algorithm.")
        if len(ids) < 2:
            raise ValueError("Ring must contain at least 2 nodes.")

    def _new_empty_boxes(self) -> list[list]:
        return [[] for _ in range(self.n)]

    def _left_of(self, i: int) -> int:
        return (i - 1 + self.n) % self.n

    def _right_of(self, i: int) -> int:
        return (i + 1) % self.n

    def _send(self, from_idx: int, direction: Direction, msg: Message):
        """Надіслати повідомлення від вузла from_idx до сусіда."""
        to_idx = self._left_of(from_idx) if direction == Direction.LEFT else self._right_of(from_idx)
        self.outbox[to_idx].append(msg)
        self.total_messages_sent += 1

    def _start_phase(self, idx: int):
        """Старт поточної фази кандидата: OUT в обидва боки з hopLimit = 2^phase"""
        node = self.nodes[idx]
        if not node.active:
            return

        hop_limit = 1 << node.phase  # 2^phase

        # OUT вліво та вправо
        self._send(idx, Direction.LEFT, Message(node.id, node.phase, hop_limit, Direction.LEFT, False))
        self._send(idx, Direction.RIGHT, Message(node.id, node.phase, hop_limit, Direction.RIGHT, False))

        node.started_phase = node.phase

    def _handle_message(self, idx: int, msg: Message):
        """Обробка одного повідомлення у вузлі idx."""
        me = self.nodes[idx]

        if not msg.is_reply:
            self._handling_out_message(idx, msg, me)
        else:
            self._handling_reply_message(idx, msg, me)

    def _handling_reply_message(self, idx: int, msg: Message, me: Node):
        if msg.origin_id == me.id:
            # REPLY повернувся до кандидата
            if msg.phase != me.phase:
                return

            if msg.direction == Direction.LEFT:
                me.got_left_reply = True
            else:
                me.got_right_reply = True

            # Якщо кандидат отримав відповіді з обох боків — переходимо до наступної фази
            if me.got_left_reply and me.got_right_reply:
                me.phase += 1
                me.reset_replies_for_new_phase()
        else:
            # Це REPLY не для мене — просто пересилаємо далі
            self._send(idx, msg.direction, msg)

    def _handling_out_message(self, idx: int, msg: Message, me: Node):
        if msg.origin_id == me.id:
            # Власне OUT повернулося до мене => я лідер
            self.leader_id = me.id
            return

        if msg.origin_id < me.id:
            # Кандидат слабший за мене => відсіюємо повідомлення
            return

        # Я зустрів сильнішого кандидата => вибуваю
        me.active = False

        if msg.ttl == 0:
            # Дійшли до межі => перетворюємо OUT на REPLY і шлемо назад
            back = msg.direction.opposite()
            reply = Message(msg.origin_id, msg.phase, 0, back, True)
            self._send(idx, back, reply)
        else:
            # TTL ще є => пересилаємо далі, зменшивши ttl
            self._send(idx, msg.direction, msg.dec_ttl())

    def _start_phases_for_necessary_nodes(self):
        for i in range(self.n):
            if self.nodes[i].needs_to_start_current_phase():
                self._start_phase(i)

    def _safety_check(self):
        any_in_transit = any(len(box) > 0 for box in self.inbox)
        if not any_in_transit:
            raise RuntimeError("No messages in transit but leader not elected. Check correctness/IDs.")

    def run(self):
        """Запуск симуляції HS до знаходження лідера."""
        # На початку всі активні вузли стартують фазу 0
        self._start_phases_for_necessary_nodes()

        # Переходимо до 1-го раунду доставки
        self.inbox = self.outbox
        self.outbox = self._new_empty_boxes()
        self.rounds = 0

        # Основний цикл раундів
        while self.leader_id is None:
            self.rounds += 1

            # Обробляємо всі повідомлення в цьому раунді
            for i in range(self.n):
                if self.leader_id is not None:
                    break
                for msg in self.inbox[i]:
                    if self.leader_id is not None:
                        break
                    self._handle_message(i, msg)

            if self.leader_id is not None:
                break

            # Стартуємо нові фази для тих, хто успішно пройшов попередню
            self._start_phases_for_necessary_nodes()

            # Переносимо пошту на наступний раунд
            self.inbox = self.outbox
            self.outbox = self._new_empty_boxes()

            self._safety_check()


if __name__ == "__main__":
    # Перевіряємо аргументи командного рядка, якщо порожньо — беремо дефолтні
    if len(sys.argv) > 1:
        try:
            ids = [int(x) for x in sys.argv[1:]]
        except ValueError:
            print("Будь ласка, введіть коректні цілі числа для ID.")
            sys.exit(1)
    else:
        ids = [4, 2, 15, 8, 11, 3]

    ring = RingNetwork(ids)
    ring.run()

    print(f"leaderId={ring.leader_id}")
    print(f"rounds={ring.rounds}")
    print(f"messages={ring.total_messages_sent}")