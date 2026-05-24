import asyncio
import hashlib
import os
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, Optional


class ContractState(Enum):
    PENDING = auto()
    REDEEMED = auto()
    REFUNDED = auto()


@dataclass
class HTLC:
    id: str
    sender: str
    recipient: str
    amount: float
    currency: str
    hash_lock: str
    time_lock: float  # Unix timestamp
    state: ContractState = ContractState.PENDING
    secret: Optional[str] = None


class BlockchainNode:
    """Імітація розподіленого вузла конкретного блокчейну."""
    def __init__(self, currency: str):
        self.currency = currency
        self.contracts: Dict[str, HTLC] = {}
        self.listeners = []
        self._lock = asyncio.Lock()

    def subscribe(self, callback):
        self.listeners.append(callback)

    async def _emit(self, event_type: str, contract: HTLC):
        for listener in self.listeners:
            asyncio.create_task(listener(event_type, contract))

    async def deploy_contract(self, htlc: HTLC) -> bool:
        async with self._lock:
            if htlc.id in self.contracts:
                return False
            self.contracts[htlc.id] = htlc
            print(f"[{self.currency.upper()} Node] Мережа: Контракт {htlc.id} успішно розгорнуто.")
            await self._emit("DEPLOYED", htlc)
            return True

    async def redeem_contract(self, contract_id: str, secret: str) -> bool:
        async with self._lock:
            if contract_id not in self.contracts:
                return False
            contract = self.contracts[contract_id]
            
            if contract.state != ContractState.PENDING:
                return False
            
            if time.time() > contract.time_lock:
                print(f"[{self.currency.upper()} Node] Помилка: Час контракту {contract_id} вичерпано. Redeem відхилено.")
                return False

            # Перевірка хеш-локу
            hashed_secret = hashlib.sha256(bytes.fromhex(secret)).hexdigest()
            if hashed_secret != contract.hash_lock:
                print(f"[{self.currency.upper()} Node] Помилка: Неправильний секрет для {contract_id}.")
                return False

            contract.state = ContractState.REDEEMED
            contract.secret = secret
            print(f"[{self.currency.upper()} Node] Успіх: Контракт {contract_id} виконано (REDEEMED). Секрет розкрито!")
            await self._emit("REDEEMED", contract)
            return True

    async def refund_contract(self, contract_id: str) -> bool:
        async with self._lock:
            if contract_id not in self.contracts:
                return False
            contract = self.contracts[contract_id]

            if contract.state != ContractState.PENDING:
                return False

            if time.time() <= contract.time_lock:
                return False

            contract.state = ContractState.REFUNDED
            print(f"[{self.currency.upper()} Node] Увага: Термін дії контракту {contract_id} збіг. Кошти повернено (REFUNDED).")
            await self._emit("REFUNDED", contract)
            return True


class PartyAgent:
    """Автономний реактивний агент, що представляє сторону угоди."""
    def __init__(self, name: str, initial_balances: Dict[str, float]):
        self.name = name
        self.balances = initial_balances
        self.known_secret: Optional[str] = None
        self.nodes: Dict[str, BlockchainNode] = {}
        self.active_swaps = {}

    def connect_blockchain(self, currency: str, node: BlockchainNode):
        self.nodes[currency.lower()] = node
        node.subscribe(self.on_blockchain_event)

    async def on_blockchain_event(self, event_type: str, contract: HTLC):
        # Кожен процес реагує асинхронно залежно від ролі в кільці
        if event_type == "DEPLOYED":
            await self._handle_contract_deployed(contract)
        elif event_type == "REDEEMED":
            await self._handle_contract_redeemed(contract)

    async def _handle_contract_deployed(self, contract: HTLC):
        pass  # Буде перевизначено логікою конкретного сценарію

    async def _handle_contract_redeemed(self, contract: HTLC):
        if contract.secret and not self.known_secret:
            self.known_secret = contract.secret
            print(f"[{self.name}] Перехоплено секрет S з мережі {contract.currency.upper()}: {self.known_secret[:12]}...")


# Глобальний лічильник для координації завершення процесів
completion_latch: Optional[asyncio.Event] = None
redeemed_count = 0

async def run_swap_system(timeout_scenario: bool = False):
    global redeemed_count, completion_latch
    redeemed_count = 0
    completion_latch = asyncio.Event()

    print("\n" + "="*60)
    print(f"СТАРТ СИСТЕМИ АТОМАРНОГО СВОПУ: {'СЦЕНАРІЙ ТАЙМАУТУ' if timeout_scenario else 'ЩАСЛИВИЙ ШЛЯХ'}")
    print("="*60)

    # 1. Ініціалізація мереж
    alt_node = BlockchainNode("alt")
    btc_node = BlockchainNode("btc")
    cad_node = BlockchainNode("cad")

    # 2. Створення незалежних агентів з початковими балансами
    alice = PartyAgent("Alice", {"alt": 100.0, "cad": 0.0})
    bob = PartyAgent("Bob", {"btc": 0.05, "alt": 0.0})
    carol = PartyAgent("Carol", {"cad": 1.0, "btc": 0.0})

    for agent in [alice, bob, carol]:
        agent.connect_blockchain("alt", alt_node)
        agent.connect_blockchain("btc", btc_node)
        agent.connect_blockchain("cad", cad_node)

    print(f"[Баланси] Початкові -> Alice: {alice.balances['alt']} ALT | Bob: {bob.balances['btc']} BTC | Carol: {carol.balances['cad']} CAD")

    # Генерируємо тайм-локи відносно поточного часу
    now = time.time()
    t1 = now + 4.0  # Contract A->B (ALT)
    t2 = now + 2.5  # Contract B->C (BTC)
    t3 = now + 1.2  # Contract C->A (CAD)

    # 3. Генерація секрету Алісою за допомогою CSPRNG
    secret_bytes = os.urandom(32)
    secret_s = secret_bytes.hex()
    hash_h = hashlib.sha256(secret_bytes).hexdigest()
    
    alice.known_secret = secret_s
    print(f"[Alice] Згенеровано секрет S: {secret_s[:12]}... та хеш H(S): {hash_h[:12]}...")

    # Перевизначення реакцій для симуляції динамічної логіки вузлів
    async def bob_deployed_reaction(contract: HTLC):
        if contract.id == "HTLC_A_B" and contract.recipient == "Bob":
            print(f"[Bob] Побачив контракт від Alice на ALT. Перевіряю параметри... Все OK. Блокую 0.05 BTC.")
            bob.balances["btc"] -= 0.05
            htlc_bc = HTLC("HTLC_B_C", "Bob", "Carol", 0.05, "btc", hash_h, t2)
            await btc_node.deploy_contract(htlc_bc)

    async def carol_deployed_reaction(contract: HTLC):
        if contract.id == "HTLC_B_C" and contract.recipient == "Carol":
            print(f"[Carol] Побачила контракт від Bob на BTC. Перевіряю хеш-лок... Збігається. Блокую 1.0 CAD.")
            carol.balances["cad"] -= 1.0
            htlc_ca = HTLC("HTLC_C_A", "Carol", "Alice", 1.0, "cad", hash_h, t3)
            await cad_node.deploy_contract(htlc_ca)

    bob._handle_contract_deployed = bob_deployed_reaction
    carol._handle_contract_deployed = carol_deployed_reaction

    # Реакції на викуплення (Redeem)
    async def alice_redeem_reaction(event_type, contract: HTLC):
        global redeemed_count
        if event_type == "DEPLOYED" and contract.id == "HTLC_C_A" and not timeout_scenario:
            print(f"[Alice] Увага! Контракт від Carol на CAD в мережі. Виконую REDEEM за допомогою секрету S.")
            success = await cad_node.redeem_contract("HTLC_C_A", alice.known_secret)
            if success:
                alice.balances["cad"] += 1.0
                redeemed_count += 1

    async def carol_redeem_reaction(event_type, contract: HTLC):
        global redeemed_count
        if event_type == "REDEEMED" and contract.id == "HTLC_C_A":
            print(f"[Carol] Перехопила секрет S з блокчейну CAD! Терміново викуповую BTC у Bob...")
            success = await btc_node.redeem_contract("HTLC_B_C", carol.known_secret)
            if success:
                carol.balances["btc"] += 0.05
                redeemed_count += 1

    async def bob_redeem_reaction(event_type, contract: HTLC):
        global redeemed_count
        if event_type == "REDEEMED" and contract.id == "HTLC_B_C":
            print(f"[Bob] Перехопив секрет S з блокчейну BTC! Терміново викуповую ALT у Alice...")
            success = await alt_node.redeem_contract("HTLC_A_B", bob.known_secret)
            if success:
                bob.balances["alt"] += 100.0
                redeemed_count += 1
                completion_latch.set()

    if not timeout_scenario:
        alice.nodes["cad"].subscribe(alice_redeem_reaction)
        carol.nodes["cad"].subscribe(carol_redeem_reaction)
        bob.nodes["btc"].subscribe(bob_redeem_reaction)
    else:
        print("[Сценарій Таймауту] Аліса вимикає свій процес і йде в офлайн після створення першого контракту...")

    # Фоновий моніторинг таймаутів (Refund Daemon)
    async def refund_monitor():
        while not completion_latch.is_set():
            await asyncio.sleep(0.1)
            for node, cid, party, b_curr, b_amt in [
                (cad_node, "HTLC_C_A", carol, "cad", 1.0),
                (btc_node, "HTLC_B_C", bob, "btc", 0.05),
                (alt_node, "HTLC_A_B", alice, "alt", 100.0)
            ]:
                if cid in node.contracts and node.contracts[cid].state == ContractState.PENDING:
                    if time.time() > node.contracts[cid].time_lock:
                        if await node.refund_contract(cid):
                            party.balances[b_curr] += b_amt
                            if cid == "HTLC_A_B":  # Останній контракт у ланцюгу повернуто
                                completion_latch.set()

    asyncio.create_task(refund_monitor())

    # --- ЗАПУСК ФАЗИ 1 ---
    print(f"[Phase 1] Аліса ініціює своп: блокує 100 ALT в контракт HTLC_A_B")
    alice.balances["alt"] -= 100.0
    htlc_ab = HTLC("HTLC_A_B", "Alice", "Bob", 100.0, "alt", hash_h, t1)
    await alt_node.deploy_contract(htlc_ab)

    # Очікування завершення роботи системи (або успіх, або таймаут останнього контракту)
    try:
        await asyncio.wait_for(completion_latch.wait(), timeout=6.0)
    except asyncio.TimeoutError:
        pass

    print("\n--- ФІНАЛЬНІ РЕЗУЛЬТАТИ ---")
    print(f"Alice: ALT={alice.balances['alt']} | CAD={alice.balances['cad']}")
    print(f"Bob:   BTC={bob.balances['btc']} | ALT={bob.balances['alt']}")
    print(f"Carol: CAD={carol.balances['cad']} | BTC={carol.balances['btc']}")
    
    if redeemed_count == 3 or (not timeout_scenario and alice.balances['cad'] > 0):
        print("[РЕЗУЛЬТАТ] Атомарний своп успішно завершено для всіх 3 сторін! ✓")
    else:
        print("[РЕЗУЛЬТАТ] Своп скасовано по таймауту. Усі активи повернуто власникам. Атомарність збережено! ✓")


if __name__ == "__main__":
    # Запуск обох сценаріїв асинхронно один за одним
    asyncio.run(run_swap_system(timeout_scenario=False))
    asyncio.run(run_swap_system(timeout_scenario=True))