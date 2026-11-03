"""Test the full message reading pipeline.

Importing this module has zero side effects: all heavy imports
(pythoncom, wechat_agent) and all connection logic live inside
main(), which only runs when this file is executed directly.
"""


def main():
    import sys
    import time
    import io
    import pythoncom
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding='utf-8', errors='replace'
    )

    pythoncom.CoInitialize()

    from wechat_agent import WeChatAgent

    agent = WeChatAgent()
    print("Connecting...")
    agent.connect()
    print("Connected!")

    print("\nCurrent chat name:", agent.get_current_chat_name())

    print("\nMessages:")
    msgs = agent.get_messages()
    for m in msgs:
        sender = "SELF" if m["is_self"] else "FRIEND"
        print(f"  {sender}: {m['text'][:80]!r}")

    print(f"\nTotal messages: {len(msgs)}")
    print(f"Resetting counter to {len(msgs)}")
    agent.reset_msg_count()

    print("\nWaiting 5 seconds for new messages...")
    time.sleep(5)

    new = agent.get_new_messages()
    print(f"New messages: {len(new)}")
    for m in new:
        print(f"  FRIEND: {m['text'][:80]!r}")

    agent.disconnect()
    print("Done")


if __name__ == "__main__":
    main()
