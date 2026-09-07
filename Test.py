import json

from simple_task_management_system import SimpleTaskManagementSystem


class SimpleTaskManagementSystemImpl(SimpleTaskManagementSystem):

    def __init__(self):
        self.tasks = {}
        self.next_id = 1

    def add_task(self, timestamp: int, name: str, priority: int) -> str:
        task_id = f"task_id_{self.next_id}"
        self.next_id += 1

        self.tasks[task_id] = {
            "name": name,
            "priority": priority
        }

        return task_id

    def update_task(
        self,
        timestamp: int,
        task_id: str,
        name: str,
        priority: int
    ) -> bool:

        if task_id not in self.tasks:
            return False

        self.tasks[task_id]["name"] = name
        self.tasks[task_id]["priority"] = priority

        return True

    def get_task(self, timestamp: int, task_id: str) -> str | None:

        if task_id not in self.tasks:
            return None

        task = self.tasks[task_id]

        return json.dumps(
            {
                "name": task["name"],
                "priority": task["priority"]
            },
            separators=(",", ":")
        )
