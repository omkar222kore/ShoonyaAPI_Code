import os
import sys
import threading
import time
import unittest
from unittest.mock import patch

import pandas as pd

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
BOT_DIR = os.path.dirname(TESTS_DIR)
sys.path.insert(0, BOT_DIR)

import config
import shoonya_scanner_bot as bot


class QuotePollingBroker:
    def get_quote(self, *args, **kwargs):
        raise AssertionError("REST quote polling is not allowed in the monitor loop")


class CancelFlowBroker:
    def __init__(self, sl_status="CANCELLED"):
        self.calls = []
        self.sl_status = sl_status
        self.flat = False

    def cancel_order(self, order_id):
        self.calls.append(("cancel", order_id))
        return True

    def get_order_status(self, order_id):
        self.calls.append(("status", order_id))
        return self.sl_status

    def position_qty(self, tsym):
        return 0 if self.flat else -10

    def place_order(self, tsym, qty, side, remarks="", **kwargs):
        self.calls.append(("place", tsym, qty, side, remarks))
        return "EXIT_ORDER"

    def wait_for_fill(self, order_id, timeout=8.0):
        self.calls.append(("wait", order_id))
        self.flat = True
        return {"status": "COMPLETE", "avgprc": 99.0, "fillshares": 10}


def make_position(**overrides):
    position = {
        "symbol": "TEST",
        "token": "1234",
        "tsym": "TEST-EQ",
        "qty": 10,
        "entry_price": 100.0,
        "entry_time": "10:00:00",
        "sl_price": 101.4,
        "tp_price": 97.2,
        "order_id": "ENTRY_ORDER",
        "sl_order_id": "",
        "sl_trigger_price": 0.0,
        "sl_limit_price": 0.0,
        "closing": False,
    }
    position.update(overrides)
    return position


def make_state(position):
    return {
        "paper": False,
        "open_positions": {"TEST": position},
        "traded_today": ["TEST"],
        "completed_scans": [],
    }


class ExecutionSafeguardTests(unittest.TestCase):
    def setUp(self):
        self.old_paper = bot.PAPER_MODE
        self.old_interval = config.MONITOR_INTERVAL
        self.old_poll_sec = config.ORDER_STATUS_POLL_SEC
        self.old_sync_interval = config.SL_ORDER_SYNC_INTERVAL
        config.ORDER_STATUS_POLL_SEC = 0.0
        config.SL_ORDER_SYNC_INTERVAL = 2.0

    def tearDown(self):
        bot.PAPER_MODE = self.old_paper
        config.MONITOR_INTERVAL = self.old_interval
        config.ORDER_STATUS_POLL_SEC = self.old_poll_sec
        config.SL_ORDER_SYNC_INTERVAL = self.old_sync_interval

    def test_ram_sl_tp_trigger_without_rest_quote(self):
        config.MONITOR_INTERVAL = 0.5
        self.assertEqual(config.MONITOR_INTERVAL, 0.5)
        broker = QuotePollingBroker()
        for price, reason in ((101.4, "SL_HIT"), (97.2, "TP_HIT")):
            state = make_state(make_position())
            with patch.object(bot.fyers_stream, "get_ltp", return_value=price):
                with patch.object(bot, "close_position") as close:
                    bot.monitor_positions(broker, state)
            close.assert_called_once()
            self.assertEqual(close.call_args.args[3], reason)

    def test_monitor_thread_is_not_starved(self):
        config.MONITOR_INTERVAL = 0.05
        config.SL_ORDER_SYNC_INTERVAL = 10.0
        stop = threading.Event()
        calls = []

        def fake_monitor(broker, state):
            calls.append(time.monotonic())
            if len(calls) >= 3:
                stop.set()

        with patch.object(bot, "monitor_positions", side_effect=fake_monitor):
            with patch.object(bot, "sync_sl_orders"):
                thread = bot.start_monitor_thread(object(), {}, stop)
                thread.join(timeout=2.0)

        self.assertTrue(thread.daemon)
        self.assertFalse(thread.is_alive())
        self.assertGreaterEqual(len(calls), 3)
        self.assertLess(calls[-1] - calls[0], 1.0)

    def test_cancel_sl_before_tp_exit(self):
        bot.PAPER_MODE = False
        broker = CancelFlowBroker("CANCELLED")
        state = make_state(make_position(sl_order_id="SL_ORDER", sl_limit_price=102.5))
        with patch.object(bot.app_state, "append_trade"):
            with patch.object(bot.app_state, "save_state"):
                ok = bot.close_position(broker, state, "TEST", "TP_HIT", 99.0)
        self.assertTrue(ok)
        kinds = [item[0] for item in broker.calls]
        self.assertEqual(kinds[0], "cancel")
        self.assertLess(kinds.index("status"), kinds.index("place"))
        self.assertEqual(broker.calls[kinds.index("place")][3], "B")
        self.assertEqual(broker.calls[kinds.index("place")][4], "BB_BLAST_EXIT")
        self.assertNotIn("TEST", state["open_positions"])

    def test_cancel_sl_before_eod_exit(self):
        bot.PAPER_MODE = False
        broker = CancelFlowBroker("CANCELLED")
        state = make_state(make_position(sl_order_id="SL_ORDER", sl_limit_price=102.5))
        with patch.object(bot.app_state, "append_trade"):
            with patch.object(bot.app_state, "save_state"):
                with patch.object(bot.fyers_stream, "get_ltp", return_value=99.0):
                    bot.square_off_all(broker, state)
        kinds = [item[0] for item in broker.calls]
        self.assertEqual(kinds[0], "cancel")
        self.assertLess(kinds.index("status"), kinds.index("place"))
        self.assertNotIn("TEST", state["open_positions"])

    def test_exchange_sl_fill_skips_exit_buy(self):
        bot.PAPER_MODE = False
        broker = CancelFlowBroker("COMPLETE")
        state = make_state(make_position(sl_order_id="SL_ORDER", sl_limit_price=102.5))
        with patch.object(bot.app_state, "append_trade") as append_trade:
            with patch.object(bot.app_state, "save_state"):
                ok = bot.close_position(broker, state, "TEST", "TP_HIT", 99.0)
        self.assertTrue(ok)
        self.assertNotIn("place", [item[0] for item in broker.calls])
        trade = append_trade.call_args.args[0]
        self.assertEqual(trade["Exit_Reason"], "EXCHANGE_SL")
        self.assertNotIn("TEST", state["open_positions"])

    def test_rsi_descending_tie_breaker(self):
        bar_timestamp = pd.Timestamp("2026-11-27 09:45")
        universe = [
            {"symbol": "AAA", "token": "1", "tsym": "AAA-EQ"},
            {"symbol": "BBB", "token": "2", "tsym": "BBB-EQ"},
            {"symbol": "CCC", "token": "3", "tsym": "CCC-EQ"},
        ]
        cache = {
            item["symbol"]: pd.DataFrame([{"Timestamp": bar_timestamp}])
            for item in universe
        }
        features = pd.DataFrame([
            {"Symbol": "AAA", "Timestamp": bar_timestamp, "RSI": 61.0},
            {"Symbol": "BBB", "Timestamp": bar_timestamp, "RSI": 88.0},
            {"Symbol": "CCC", "Timestamp": bar_timestamp, "RSI": 75.0},
        ])
        statuses = {"AAA": "PASS", "BBB": "PASS", "CCC": "PASS"}
        with patch.object(bot.indicators, "compute_features_batch", return_value=features):
            with patch.object(bot.indicators, "entry_status_batch", return_value=statuses):
                matched, _, _, _, _ = bot.evaluate_candidates(cache, universe, bar_timestamp)
        self.assertEqual(matched, ["BBB", "CCC", "AAA"])

    def test_paper_statutory_charge_uses_entry_notional(self):
        bot.PAPER_MODE = True
        state = make_state(make_position(entry_price=100.0, qty=10))
        with patch.object(bot.app_state, "append_trade") as append_trade:
            with patch.object(bot.app_state, "save_state"):
                ok = bot.close_position(QuotePollingBroker(), state, "TEST", "TP_HIT", 50.0)
        self.assertTrue(ok)
        trade = append_trade.call_args.args[0]
        self.assertEqual(trade["Charges"], 12.16)
        self.assertEqual(trade["Est_Net_PnL"], 487.84)


if __name__ == "__main__":
    unittest.main()
