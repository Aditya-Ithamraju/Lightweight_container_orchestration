# mcu/payloads/task_print.py
# Contract: runner will exec() this file content, then call main(config)
def main(config):
    # Simulate some MCU work
    msg = config.get("msg", "Hello from task_print")
    for i in range(3):
        print(f"[TASK] {msg} #{i+1}")
