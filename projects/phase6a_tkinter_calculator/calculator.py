import tkinter as tk


class Calculator(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MAYDAY Phase 6A Calculator")
        self.geometry("320x430")
        self.resizable(False, False)
        self.expression = tk.StringVar()
        entry = tk.Entry(self, textvariable=self.expression, font=("Segoe UI", 22), justify="right")
        entry.pack(fill="x", padx=12, pady=12, ipady=10)
        buttons = [
            ("7", "8", "9", "/"),
            ("4", "5", "6", "*"),
            ("1", "2", "3", "-"),
            ("0", ".", "=", "+"),
        ]
        for row in buttons:
            frame = tk.Frame(self)
            frame.pack(fill="both", expand=True, padx=12, pady=4)
            for label in row:
                tk.Button(
                    frame,
                    text=label,
                    font=("Segoe UI", 18),
                    command=lambda value=label: self.press(value),
                ).pack(side="left", fill="both", expand=True, padx=4)
        tk.Button(self, text="Clear", font=("Segoe UI", 16), command=self.clear).pack(
            fill="x", padx=16, pady=12
        )

    def press(self, value):
        if value == "=":
            try:
                allowed = set("0123456789.+-*/() ")
                expr = self.expression.get()
                if not set(expr) <= allowed:
                    raise ValueError("unsupported input")
                self.expression.set(str(eval(expr, {"__builtins__": {}}, {})))
            except Exception:
                self.expression.set("Error")
        else:
            current = "" if self.expression.get() == "Error" else self.expression.get()
            self.expression.set(current + value)

    def clear(self):
        self.expression.set("")


if __name__ == "__main__":
    Calculator().mainloop()
