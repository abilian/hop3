from dataclasses import dataclass

Message = list[str]


@dataclass(frozen=True)
class Printer:
    verbose = False

    def print(self, msg):
        for item in msg:
            t = item["t"]
            v = item["v"]
            meth = getattr(self, f"print_{t}")
            meth(v)

    def print_table(self, table):
        for row in table:
            for item in row:
                print(item, end=" ")
            print()
