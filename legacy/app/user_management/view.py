from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import ttk

from app.auth import db
from app.common import theme
from app.common.context import AppContext
from app.common.widgets import show_toast


class UserManagementView(tk.Frame):
    def __init__(self, parent, ctx: AppContext):
        super().__init__(parent, bg=theme.BG_PRIMARY)
        self.ctx = ctx
        self.selected_user_id: int | None = None
        self._build()

    def on_show(self) -> None:
        self._reload()

    def _build(self) -> None:
        pad = tk.Frame(self, bg=theme.BG_PRIMARY, padx=24, pady=18)
        pad.pack(fill="both", expand=True)

        tk.Label(
            pad,
            text="User Management",
            bg=theme.BG_PRIMARY,
            fg=theme.TEXT_PRIMARY,
            font=(theme.FONT_HEADER[0], 18, "bold"),
        ).pack(anchor="w")
        tk.Label(
            pad,
            text="Administrator access only",
            bg=theme.BG_PRIMARY,
            fg=theme.TEXT_MUTED,
            font=theme.FONT_LABEL,
        ).pack(anchor="w", pady=(0, 14))

        create_card = tk.Frame(
            pad, bg=theme.BG_CARD, highlightbackground=theme.BORDER, highlightthickness=1
        )
        create_card.pack(fill="x", pady=(0, 14))
        create_inner = tk.Frame(create_card, bg=theme.BG_CARD, padx=14, pady=12)
        create_inner.pack(fill="x")

        tk.Label(
            create_inner,
            text="Create new user",
            bg=theme.BG_CARD,
            fg=theme.TEXT_PRIMARY,
            font=(theme.FONT_HEADER[0], 12, "bold"),
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 10))

        tk.Label(
            create_inner, text="Username", bg=theme.BG_CARD, fg=theme.TEXT_MUTED, font=theme.FONT_LABEL
        ).grid(row=1, column=0, sticky="w")
        self.username_var = tk.StringVar()
        tk.Entry(
            create_inner,
            textvariable=self.username_var,
            bg=theme.BG_SECONDARY,
            fg=theme.TEXT_PRIMARY,
            insertbackground=theme.TEXT_PRIMARY,
            relief="flat",
            width=20,
        ).grid(row=2, column=0, padx=(0, 14), sticky="w")

        tk.Label(
            create_inner, text="Temp password", bg=theme.BG_CARD, fg=theme.TEXT_MUTED, font=theme.FONT_LABEL
        ).grid(row=1, column=1, sticky="w")
        self.password_var = tk.StringVar()
        tk.Entry(
            create_inner,
            textvariable=self.password_var,
            show="\u2022",
            bg=theme.BG_SECONDARY,
            fg=theme.TEXT_PRIMARY,
            insertbackground=theme.TEXT_PRIMARY,
            relief="flat",
            width=20,
        ).grid(row=2, column=1, padx=(0, 14), sticky="w")

        tk.Label(
            create_inner, text="Role", bg=theme.BG_CARD, fg=theme.TEXT_MUTED, font=theme.FONT_LABEL
        ).grid(row=1, column=2, sticky="w")
        self.role_var = tk.StringVar(value="analyst")
        ttk.Combobox(
            create_inner,
            textvariable=self.role_var,
            values=["analyst", "administrator"],
            width=16,
            state="readonly",
        ).grid(row=2, column=2, padx=(0, 14), sticky="w")

        tk.Button(
            create_inner,
            text="Add User",
            command=self._add_user,
            bg=theme.BG_SECONDARY,
            fg=theme.ACCENT_GREEN,
            relief="flat",
            font=(theme.FONT_LABEL[0], 9, "bold"),
            cursor="hand2",
            padx=14,
        ).grid(row=2, column=3, sticky="w")

        table_card = tk.Frame(
            pad, bg=theme.BG_CARD, highlightbackground=theme.BORDER, highlightthickness=1
        )
        table_card.pack(fill="both", expand=True, pady=(0, 14))
        style = ttk.Style()
        style.configure(
            "Users.Treeview",
            background=theme.BG_CARD,
            fieldbackground=theme.BG_CARD,
            foreground=theme.TEXT_PRIMARY,
            rowheight=24,
            font=theme.FONT_MONO_SMALL,
        )
        columns = ("username", "role", "created", "reset", "active")
        self.tree = ttk.Treeview(
            table_card, columns=columns, show="headings", style="Users.Treeview", height=12
        )
        for col, label, width in zip(
            columns,
            ["Username", "Role", "Created", "Must Reset PW", "Active"],
            [170, 120, 190, 120, 90],
        ):
            self.tree.heading(col, text=label)
            self.tree.column(col, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True, side="left", pady=1)
        scroll = ttk.Scrollbar(table_card, orient="vertical", command=self.tree.yview)
        scroll.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._load_selected_user())

        editor_card = tk.Frame(
            pad, bg=theme.BG_CARD, highlightbackground=theme.BORDER, highlightthickness=1
        )
        editor_card.pack(fill="x")
        editor = tk.Frame(editor_card, bg=theme.BG_CARD, padx=14, pady=12)
        editor.pack(fill="x")

        tk.Label(
            editor,
            text="Selected user details",
            bg=theme.BG_CARD,
            fg=theme.TEXT_PRIMARY,
            font=(theme.FONT_HEADER[0], 12, "bold"),
        ).grid(row=0, column=0, columnspan=4, sticky="w")
        tk.Label(
            editor,
            text="Pick a user above to inspect and update their account data.",
            bg=theme.BG_CARD,
            fg=theme.TEXT_MUTED,
            font=theme.FONT_LABEL,
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(2, 10))

        tk.Label(
            editor, text="Username", bg=theme.BG_CARD, fg=theme.TEXT_MUTED, font=theme.FONT_LABEL
        ).grid(row=2, column=0, sticky="w")
        self.edit_username_var = tk.StringVar()
        tk.Entry(
            editor,
            textvariable=self.edit_username_var,
            bg=theme.BG_SECONDARY,
            fg=theme.TEXT_PRIMARY,
            insertbackground=theme.TEXT_PRIMARY,
            relief="flat",
            width=20,
        ).grid(row=3, column=0, padx=(0, 14), sticky="w")

        tk.Label(editor, text="Role", bg=theme.BG_CARD, fg=theme.TEXT_MUTED, font=theme.FONT_LABEL).grid(
            row=2, column=1, sticky="w"
        )
        self.edit_role_var = tk.StringVar(value="analyst")
        ttk.Combobox(
            editor,
            textvariable=self.edit_role_var,
            values=["analyst", "administrator"],
            width=16,
            state="readonly",
        ).grid(row=3, column=1, padx=(0, 14), sticky="w")

        self.edit_active_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            editor,
            text="Active",
            variable=self.edit_active_var,
            bg=theme.BG_CARD,
            fg=theme.TEXT_PRIMARY,
            selectcolor=theme.BG_SECONDARY,
            activebackground=theme.BG_CARD,
            font=theme.FONT_LABEL,
            bd=0,
            highlightthickness=0,
        ).grid(row=3, column=2, sticky="w")

        self.edit_reset_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            editor,
            text="Force password reset",
            variable=self.edit_reset_var,
            bg=theme.BG_CARD,
            fg=theme.TEXT_PRIMARY,
            selectcolor=theme.BG_SECONDARY,
            activebackground=theme.BG_CARD,
            font=theme.FONT_LABEL,
            bd=0,
            highlightthickness=0,
        ).grid(row=3, column=3, sticky="w")

        tk.Label(
            editor, text="New password", bg=theme.BG_CARD, fg=theme.TEXT_MUTED, font=theme.FONT_LABEL
        ).grid(row=4, column=0, sticky="w", pady=(10, 0))
        self.edit_password_var = tk.StringVar()
        tk.Entry(
            editor,
            textvariable=self.edit_password_var,
            show="\u2022",
            bg=theme.BG_SECONDARY,
            fg=theme.TEXT_PRIMARY,
            insertbackground=theme.TEXT_PRIMARY,
            relief="flat",
            width=20,
        ).grid(row=5, column=0, padx=(0, 14), sticky="w")

        tk.Label(
            editor, text="Created at", bg=theme.BG_CARD, fg=theme.TEXT_MUTED, font=theme.FONT_LABEL
        ).grid(row=4, column=1, sticky="w", pady=(10, 0))
        self.edit_created_var = tk.StringVar(value="No user selected")
        tk.Label(
            editor,
            textvariable=self.edit_created_var,
            bg=theme.BG_SECONDARY,
            fg=theme.TEXT_PRIMARY,
            font=theme.FONT_MONO_SMALL,
            padx=8,
            pady=6,
            anchor="w",
        ).grid(row=5, column=1, columnspan=2, sticky="ew")

        actions = tk.Frame(editor, bg=theme.BG_CARD)
        actions.grid(row=6, column=0, columnspan=4, sticky="w", pady=(14, 0))
        tk.Button(
            actions,
            text="Save Changes",
            command=self._save_selected_user,
            bg=theme.BG_SECONDARY,
            fg=theme.ACCENT_CYAN,
            relief="flat",
            font=(theme.FONT_LABEL[0], 9, "bold"),
            cursor="hand2",
            padx=14,
        ).pack(side="left")
        tk.Button(
            actions,
            text="Clear Selection",
            command=self._clear_selection,
            bg=theme.BG_SECONDARY,
            fg=theme.TEXT_MUTED,
            relief="flat",
            font=(theme.FONT_LABEL[0], 9, "bold"),
            cursor="hand2",
            padx=14,
        ).pack(side="left", padx=8)

    def _reload(self) -> None:
        current = self.selected_user_id
        users = {u["id"]: u for u in db.list_users()}

        self.tree.delete(*self.tree.get_children())
        for u in users.values():
            self.tree.insert(
                "",
                "end",
                iid=str(u["id"]),
                values=(
                    u["username"],
                    u["role"],
                    u["created_at"][:19],
                    "Yes" if u["must_reset_password"] else "No",
                    "Yes" if u["active"] else "No",
                ),
            )

        if current in users:
            self.tree.selection_set(str(current))
            self.tree.see(str(current))
            self._populate_editor(users[current])
        else:
            self._clear_editor()

    def _selected_id(self):
        sel = self.tree.selection()
        return int(sel[0]) if sel else None

    def _load_selected_user(self) -> None:
        uid = self._selected_id()
        self.selected_user_id = uid
        if uid is None:
            self._clear_editor()
            return

        row = db.get_user_by_id(uid)
        if row is None:
            self._clear_editor()
            return
        self._populate_editor(row)

    def _populate_editor(self, row) -> None:
        self.selected_user_id = int(row["id"])
        self.edit_username_var.set(row["username"])
        self.edit_role_var.set(row["role"])
        self.edit_active_var.set(bool(row["active"]))
        self.edit_reset_var.set(bool(row["must_reset_password"]))
        self.edit_password_var.set("")
        self.edit_created_var.set(row["created_at"][:19])

    def _clear_editor(self) -> None:
        self.selected_user_id = None
        self.edit_username_var.set("")
        self.edit_role_var.set("analyst")
        self.edit_active_var.set(True)
        self.edit_reset_var.set(False)
        self.edit_password_var.set("")
        self.edit_created_var.set("No user selected")

    def _clear_selection(self) -> None:
        self.tree.selection_remove(*self.tree.selection())
        self._clear_editor()

    def _add_user(self) -> None:
        username = self.username_var.get().strip()
        password = self.password_var.get()
        role = self.role_var.get()
        if not username or not password:
            show_toast(
                self.winfo_toplevel(),
                "Missing fields",
                "Username and password are required.",
                "warning",
            )
            return
        try:
            db.create_user(username, password, role)
        except sqlite3.IntegrityError:
            show_toast(
                self.winfo_toplevel(),
                "Could not add user",
                f"Username '{username}' already exists.",
                "critical",
            )
            return
        except Exception as exc:
            show_toast(self.winfo_toplevel(), "Could not add user", str(exc), "critical")
            return
        self.username_var.set("")
        self.password_var.set("")
        self._reload()
        show_toast(
            self.winfo_toplevel(),
            "User added",
            f"{username} created with role '{role}'.",
            "success",
        )

    def _save_selected_user(self) -> None:
        if self.selected_user_id is None:
            show_toast(
                self.winfo_toplevel(),
                "No user selected",
                "Choose a user from the table before saving changes.",
                "warning",
            )
            return

        username = self.edit_username_var.get().strip()
        role = self.edit_role_var.get().strip()
        password = self.edit_password_var.get()
        if not username:
            show_toast(
                self.winfo_toplevel(),
                "Missing fields",
                "Username cannot be empty.",
                "warning",
            )
            return

        try:
            db.update_user(
                self.selected_user_id,
                username=username,
                role=role,
                active=self.edit_active_var.get(),
                must_reset_password=self.edit_reset_var.get(),
                new_password=password or None,
            )
        except sqlite3.IntegrityError:
            show_toast(
                self.winfo_toplevel(),
                "Could not update user",
                f"Username '{username}' already exists.",
                "critical",
            )
            return
        except Exception as exc:
            show_toast(self.winfo_toplevel(), "Could not update user", str(exc), "critical")
            return

        self._reload()
        show_toast(
            self.winfo_toplevel(),
            "User updated",
            f"{username} changes saved.",
            "success",
        )
