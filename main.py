"""Entry point for WeChat AI Auto-Reply."""

import logging
import sys

from core.ai import AIEngine
from core.config import ConfigManager
from core.human_simulator import HumanSimulator
from core.wechat import WeChatAgent
from ui.app import AppGUI


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    config = ConfigManager()
    ai = AIEngine(config)
    human_sim = HumanSimulator(config)
    wx_agent = WeChatAgent()

    app = AppGUI(config, ai, human_sim, wx_agent)
    app.run()


if __name__ == "__main__":
    main()
