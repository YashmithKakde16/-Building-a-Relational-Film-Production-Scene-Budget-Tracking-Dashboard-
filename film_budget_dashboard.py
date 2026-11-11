"""
Film Production & Scene Budget Tracking Dashboard
Single-file runnable Python desktop application: SQLite database + Tkinter GUI.
Run with:  python film_budget_dashboard.py   (VS Code / terminal)
"""

import math
import sqlite3
from datetime import date
from tkinter import *
from tkinter import messagebox
from tkinter import ttk

DEFAULT_EMAIL = "tbd@studio.com"  # used when a new production is auto-created


# ==========================================
# DATABASE CLASS
# ==========================================

class Database:
    def __init__(self, db):
        self.con = sqlite3.connect(db)
        # Foreign keys are OFF by default in SQLite - must be enabled per connection
        self.con.execute("PRAGMA foreign_keys = ON")
        self.cur = self.con.cursor()
        self.create_tables()
        self.seed_if_empty()

    def create_tables(self):
        self.cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS productions(
                production_id INTEGER PRIMARY KEY AUTOINCREMENT,
                title         TEXT NOT NULL UNIQUE,
                contact_email TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS scene_shoots(
                scene_id      INTEGER PRIMARY KEY AUTOINCREMENT,
                production_id INTEGER NOT NULL,
                scene_ref     TEXT NOT NULL,
                shoot_date    TEXT NOT NULL,
                FOREIGN KEY (production_id) REFERENCES productions(production_id)
                    ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS budget_items(
                item_id     INTEGER PRIMARY KEY AUTOINCREMENT,
                scene_id    INTEGER NOT NULL,
                description TEXT NOT NULL,
                amount      REAL NOT NULL CHECK (amount >= 0),
                FOREIGN KEY (scene_id) REFERENCES scene_shoots(scene_id)
                    ON DELETE CASCADE
            );
            """
        )
        self.con.commit()

    def seed_if_empty(self):
        self.cur.execute("SELECT COUNT(*) FROM productions")
        if self.cur.fetchone()[0] > 0:
            return
        samples = [
            ("Midnight Express", "anna@midnightfilms.com", [
                ("Scene 14 - Rooftop Chase", "2026-03-10", [("Camera Rental", 4500.0), ("Stunt Crew", 8200.0)]),
                ("Scene 22 - Courtroom", "2026-03-15", [("Location Permit", 1200.0)]),
            ]),
            ("Silent Harbor", "raj@silentharbor.com", [
                ("Scene 03 - Dockside Meeting", "2026-04-02", [("Actor Fees", 15000.0), ("Lighting Gear", 2300.0)]),
            ]),
        ]
        for title, email, scenes in samples:
            self.cur.execute("INSERT INTO productions(title, contact_email) VALUES (?, ?)", (title, email))
            pid = self.cur.lastrowid
            for ref, shoot_date, items in scenes:
                self.cur.execute(
                    "INSERT INTO scene_shoots(production_id, scene_ref, shoot_date) VALUES (?, ?, ?)",
                    (pid, ref, shoot_date),
                )
                sid = self.cur.lastrowid
                for desc, amt in items:
                    self.cur.execute(
                        "INSERT INTO budget_items(scene_id, description, amount) VALUES (?, ?, ?)",
                        (sid, desc, amt),
                    )
        self.con.commit()

    # ---------- Insert ----------
    def add_record(self, title, scene_ref, description, amount):
        """Reuse the production if it exists (case-insensitive), else create it.
        Then add one scene shoot and one budget item under it."""
        self.cur.execute(
            "SELECT production_id FROM productions WHERE LOWER(title) = LOWER(?)", (title,)
        )
        row = self.cur.fetchone()
        if row:
            pid = row[0]
        else:
            self.cur.execute(
                "INSERT INTO productions(title, contact_email) VALUES (?, ?)",
                (title, DEFAULT_EMAIL),
            )
            pid = self.cur.lastrowid
        self.cur.execute(
            "INSERT INTO scene_shoots(production_id, scene_ref, shoot_date) VALUES (?, ?, ?)",
            (pid, scene_ref, date.today().isoformat()),
        )
        sid = self.cur.lastrowid
        self.cur.execute(
            "INSERT INTO budget_items(scene_id, description, amount) VALUES (?, ?, ?)",
            (sid, description, amount),
        )
        self.con.commit()

    # ---------- Fetch ----------
    def fetch_join(self):
        self.cur.execute(
            """
            SELECT s.scene_id, p.title, s.scene_ref, s.shoot_date,
                   COALESCE(b.description, '(no items)'), COALESCE(b.amount, 0)
            FROM scene_shoots s
            JOIN productions p ON p.production_id = s.production_id
            LEFT JOIN budget_items b ON b.scene_id = s.scene_id
            ORDER BY s.scene_id, b.item_id
            """
        )
        return self.cur.fetchall()

    def fetch_table(self, table):
        if table not in ("productions", "scene_shoots", "budget_items"):
            raise ValueError("Unknown table")
        self.cur.execute(f"SELECT * FROM {table}")
        return self.cur.fetchall()

    def delete_choices(self, kind):
        """Return list of (label, id) for the delete dropdown."""
        if kind == "Film Production":
            self.cur.execute("SELECT production_id, title FROM productions ORDER BY production_id")
            return [(f"{i} - {t}", i) for i, t in self.cur.fetchall()]
        if kind == "Scene Shoot":
            self.cur.execute(
                """SELECT s.scene_id, p.title, s.scene_ref FROM scene_shoots s
                   JOIN productions p ON p.production_id = s.production_id
                   ORDER BY s.scene_id"""
            )
            return [(f"{i} - {t} / {r}", i) for i, t, r in self.cur.fetchall()]
        if kind == "Budget Item":
            self.cur.execute(
                "SELECT item_id, description, amount FROM budget_items ORDER BY item_id"
            )
            return [(f"{i} - {d} ({a:,.2f})", i) for i, d, a in self.cur.fetchall()]
        return []

    # ---------- Delete ----------
    def delete(self, kind, record_id):
        table, col = {
            "Film Production": ("productions", "production_id"),
            "Scene Shoot": ("scene_shoots", "scene_id"),
            "Budget Item": ("budget_items", "item_id"),
        }[kind]
        self.cur.execute(f"DELETE FROM {table} WHERE {col} = ?", (record_id,))
        self.con.commit()


# ==========================================
# GUI
# ==========================================

def build_app(db):
    root = Tk()
    root.title("FILM PRODUCTION BUDGET TRACKER")
    root.geometry("1100x720+50+50")
    root.config(bg="#2c3e50")

    # Form variables
    prod_var = StringVar()
    scene_var = StringVar()
    desc_var = StringVar()
    amount_var = StringVar()
    del_kind_var = StringVar(value="Film Production")
    del_choice_var = StringVar()
    delete_map = {}  # label -> id for the current dropdown contents

    # ---------------- Insert Panel ----------------
    insert_frame = LabelFrame(
        root, text=" Insert Panel ", font=("Calibri", 14, "bold"),
        bg="#065535", fg="white", padx=10, pady=8,
    )
    insert_frame.pack(side=TOP, fill=X, padx=10, pady=(10, 5))

    def lbl(parent, text, r, c):
        Label(parent, text=text, font=("Calibri", 13), bg="#065535", fg="white").grid(
            row=r, column=c, padx=8, pady=6, sticky="w")

    def ent(parent, var, r, c, w=28):
        e = Entry(parent, textvariable=var, font=("Calibri", 13), width=w)
        e.grid(row=r, column=c, padx=8, pady=6, sticky="w")
        return e

    lbl(insert_frame, "Production Title", 0, 0)
    ent(insert_frame, prod_var, 0, 1)
    lbl(insert_frame, "Scene Reference", 0, 2)
    ent(insert_frame, scene_var, 0, 3)
    lbl(insert_frame, "Expense Description", 1, 0)
    ent(insert_frame, desc_var, 1, 1)
    lbl(insert_frame, "Expense Amount", 1, 2)
    ent(insert_frame, amount_var, 1, 3)

    # ---------------- Delete Panel ----------------
    delete_frame = LabelFrame(
        root, text=" Delete Panel ", font=("Calibri", 14, "bold"),
        bg="#7b241c", fg="white", padx=10, pady=8,
    )
    delete_frame.pack(side=TOP, fill=X, padx=10, pady=5)

    Label(delete_frame, text="Delete a", font=("Calibri", 13), bg="#7b241c", fg="white").grid(
        row=0, column=0, padx=8, pady=6, sticky="w")
    kind_combo = ttk.Combobox(
        delete_frame, textvariable=del_kind_var, state="readonly", font=("Calibri", 13), width=18,
        values=("Film Production", "Scene Shoot", "Budget Item"),
    )
    kind_combo.grid(row=0, column=1, padx=8, pady=6, sticky="w")

    Label(delete_frame, text="Record", font=("Calibri", 13), bg="#7b241c", fg="white").grid(
        row=0, column=2, padx=8, pady=6, sticky="w")
    choice_combo = ttk.Combobox(
        delete_frame, textvariable=del_choice_var, state="readonly", font=("Calibri", 13), width=45,
    )
    choice_combo.grid(row=0, column=3, padx=8, pady=6, sticky="w")

    # ---------------- Tabbed Display ----------------
    style = ttk.Style()
    style.configure("mystyle.Treeview", font=("Calibri", 12), rowheight=26)
    style.configure("mystyle.Treeview.Heading", font=("Calibri", 13, "bold"))

    notebook = ttk.Notebook(root)
    notebook.pack(side=TOP, fill=BOTH, expand=True, padx=10, pady=(5, 10))

    def make_tab(title, columns):
        frame = Frame(notebook)
        notebook.add(frame, text=title)
        tv = ttk.Treeview(frame, columns=columns, show="headings", style="mystyle.Treeview")
        for c in columns:
            tv.heading(c, text=c)
            tv.column(c, width=130, anchor="w")
        vsb = ttk.Scrollbar(frame, orient="vertical", command=tv.yview)
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=tv.xview)
        tv.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side=RIGHT, fill=Y)
        hsb.pack(side=BOTTOM, fill=X)
        tv.pack(side=LEFT, fill=BOTH, expand=True)
        return tv

    tv_join = make_tab(" Master View (JOIN) ",
                       ("Scene ID", "Production Title", "Scene Reference", "Shoot Date",
                        "Expense Description", "Expense Amount"))
    tv_prod = make_tab(" productions ", ("production_id", "title", "contact_email"))
    tv_scene = make_tab(" scene_shoots ", ("scene_id", "production_id", "scene_ref", "shoot_date"))
    tv_items = make_tab(" budget_items ", ("item_id", "scene_id", "description", "amount"))

    # ---------------- Refresh helpers ----------------
    def fill(tv, rows):
        tv.delete(*tv.get_children())
        for r in rows:
            tv.insert("", END, values=r)

    def refresh_tables():
        fill(tv_join, db.fetch_join())
        fill(tv_prod, db.fetch_table("productions"))
        fill(tv_scene, db.fetch_table("scene_shoots"))
        fill(tv_items, db.fetch_table("budget_items"))

    def refresh_dropdown(*_):
        """Rebuild the record dropdown from the DB so it never holds a stale ID."""
        delete_map.clear()
        choices = db.delete_choices(del_kind_var.get())
        for label, rid in choices:
            delete_map[label] = rid
        choice_combo["values"] = [label for label, _ in choices]
        del_choice_var.set("")  # clear selection - nothing stale left selected

    def clear_inputs():
        prod_var.set("")
        scene_var.set("")
        desc_var.set("")
        amount_var.set("")

    def refresh_all():
        refresh_tables()
        refresh_dropdown()

    kind_combo.bind("<<ComboboxSelected>>", refresh_dropdown)

    # ---------------- Actions ----------------
    def add_record():
        title = prod_var.get().strip()
        scene = scene_var.get().strip()
        desc = desc_var.get().strip()
        amt_text = amount_var.get().strip()

        if not title or not scene or not desc or not amt_text:
            messagebox.showerror("Error in Input", "Please fill in all the fields.")
            return
        try:
            amount = float(amt_text)
        except ValueError:
            messagebox.showerror("Invalid Amount", "Expense Amount must be a number.")
            return
        if math.isnan(amount) or math.isinf(amount):
            messagebox.showerror("Invalid Amount", "Expense Amount must be a real number.")
            return
        if amount < 0:
            messagebox.showerror("Invalid Amount", "Expense Amount cannot be negative.")
            return

        db.add_record(title, scene, desc, amount)
        messagebox.showinfo("Success", "Record added.")
        clear_inputs()
        refresh_all()

    def delete_selected():
        kind = del_kind_var.get()
        label = del_choice_var.get()
        if not label or label not in delete_map:
            messagebox.showwarning("Selection Required", "Please select a record to delete.")
            return
        if not messagebox.askyesno("Confirm Delete", f"Delete {kind}: {label}?"):
            return
        db.delete(kind, delete_map[label])
        messagebox.showinfo("Success", f"{kind} deleted.")
        clear_inputs()
        refresh_all()

    Button(
        insert_frame, text="Add Record", command=add_record, width=16,
        font=("Calibri", 13, "bold"), fg="#ecf0f1", bg="#0b3d2a", bd=0, cursor="hand2",
    ).grid(row=0, column=4, rowspan=2, padx=15, pady=6)

    Button(
        delete_frame, text="Delete Selected", command=delete_selected, width=16,
        font=("Calibri", 13, "bold"), fg="#ecf0f1", bg="#4a140f", bd=0, cursor="hand2",
    ).grid(row=0, column=4, padx=15, pady=6)

    refresh_all()
    return root


if __name__ == "__main__":
    database = Database("FilmBudget.db")
    app = build_app(database)
    app.mainloop()
